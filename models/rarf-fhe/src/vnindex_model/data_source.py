"""Read-only market data sources for the online update layer.

The batch pipeline reads a static CSV via :mod:`vnindex_model.data`. The online
layer instead polls whatever store the VPS keeps sessions in, so it needs a
driver-agnostic interface plus connectors that *cannot* modify the source:

* SQLite is opened with ``?mode=ro`` and additionally guarded by an authorizer
  callback that vetoes every write opcode;
* DuckDB is opened with ``read_only=True``;
* PostgreSQL/TimescaleDB is opened with ``default_transaction_read_only=on`` so
  the *server* rejects writes, whatever the client asks for;
* the CSV backend only ever calls read APIs.

The read-only discipline follows the connectors already proven in the Dynamic
Graph repository (``dynamicgraph/data/connectors.py``).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from .data import load_price_data
from .dotenv import load_env_file

OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
DEFAULT_COLUMN_MAP = {name: name for name in OHLCV_COLUMNS}


class ReadOnlyViolation(RuntimeError):
    """Raised when a connector attempts to modify the source database."""


@runtime_checkable
class MarketDataSource(Protocol):
    """Minimal contract the online updater depends on."""

    def latest_date(self) -> pd.Timestamp:
        """Most recent session available in the source."""

    def fetch_since(self, since: pd.Timestamp | None, lookback_buffer_days: int | None) -> pd.DataFrame:
        """Sessions after ``since`` plus enough trailing context to build features.

        ``lookback_buffer_days`` counts sessions at or before ``since``; ``None``
        returns the full history, which is what feature parity with the batch
        pipeline requires (``build_features`` has expanding-window columns).
        """

    def close(self) -> None:
        """Release the underlying handle."""


def _normalize(frame: pd.DataFrame, column_map: dict[str, str], date_unit: str | None) -> pd.DataFrame:
    renamed = frame.rename(columns={source: canonical for canonical, source in column_map.items()})
    missing = [name for name in ["date", "close"] if name not in renamed]
    if missing:
        raise ValueError(f"Nguồn dữ liệu thiếu cột bắt buộc sau khi map: {missing}")
    out = pd.DataFrame({name: renamed[name] for name in OHLCV_COLUMNS if name in renamed})
    if date_unit:
        out["date"] = pd.to_datetime(out["date"], unit=date_unit, errors="coerce")
    else:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for column in [name for name in OHLCV_COLUMNS if name != "date" and name in out]:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)


def _slice_since(frame: pd.DataFrame, since: pd.Timestamp | None, lookback_buffer_days: int | None) -> pd.DataFrame:
    if since is None:
        return frame.reset_index(drop=True)
    since = pd.Timestamp(since)
    history = frame[frame["date"] <= since]
    if lookback_buffer_days is not None:
        history = history.tail(int(lookback_buffer_days))
    fresh = frame[frame["date"] > since]
    return pd.concat([history, fresh], ignore_index=True)


def _readonly_authorizer(action: int, *_: Any) -> int:
    """SQLite authorizer that denies every mutating action code."""
    allowed = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_PRAGMA,
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_RECURSIVE,
    }
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def open_sqlite_readonly(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite database read-only, with a write-denying authorizer."""
    connection = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True, timeout=30)
    connection.set_authorizer(_readonly_authorizer)
    return connection


class SQLiteMarketDataSource:
    """Read-only SQLite/vendor-file source."""

    backend = "sqlite"

    def __init__(
        self,
        path: str | Path,
        table: str,
        column_map: dict[str, str] | None = None,
        date_unit: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.table = str(table)
        self.column_map = {**DEFAULT_COLUMN_MAP, **(column_map or {})}
        self.date_unit = date_unit
        self._connection = open_sqlite_readonly(self.path)

    def _read(self) -> pd.DataFrame:
        raw = pd.read_sql(f'SELECT * FROM "{self.table}"', self._connection)
        return _normalize(raw, self.column_map, self.date_unit)

    def latest_date(self) -> pd.Timestamp:
        return pd.Timestamp(self._read()["date"].max())

    def fetch_since(self, since: pd.Timestamp | None, lookback_buffer_days: int | None) -> pd.DataFrame:
        return _slice_since(self._read(), since, lookback_buffer_days)

    def execute_for_test(self, statement: str) -> None:
        """Attempt a statement so tests can prove writes are rejected."""
        try:
            self._connection.execute(statement)
        except sqlite3.DatabaseError as error:
            raise ReadOnlyViolation(f"Nguồn SQLite là read-only: {error}") from error
        raise ReadOnlyViolation("Câu lệnh ghi không bị chặn — kết nối không ở chế độ read-only")

    def close(self) -> None:
        self._connection.close()


class DuckDBMarketDataSource:
    """Read-only DuckDB source."""

    backend = "duckdb"

    def __init__(
        self,
        path: str | Path,
        table: str,
        column_map: dict[str, str] | None = None,
        date_unit: str | None = None,
    ) -> None:
        import duckdb

        self.path = Path(path)
        self.table = str(table)
        self.column_map = {**DEFAULT_COLUMN_MAP, **(column_map or {})}
        self.date_unit = date_unit
        self._connection = duckdb.connect(str(self.path), read_only=True)

    def _read(self) -> pd.DataFrame:
        raw = self._connection.execute(f'SELECT * FROM "{self.table}"').fetch_df()
        return _normalize(raw, self.column_map, self.date_unit)

    def latest_date(self) -> pd.Timestamp:
        return pd.Timestamp(self._read()["date"].max())

    def fetch_since(self, since: pd.Timestamp | None, lookback_buffer_days: int | None) -> pd.DataFrame:
        return _slice_since(self._read(), since, lookback_buffer_days)

    def execute_for_test(self, statement: str) -> None:
        try:
            self._connection.execute(statement)
        except Exception as error:  # duckdb raises several distinct error types
            raise ReadOnlyViolation(f"Nguồn DuckDB là read-only: {error}") from error
        raise ReadOnlyViolation("Câu lệnh ghi không bị chặn — kết nối không ở chế độ read-only")

    def close(self) -> None:
        self._connection.close()


POSTGRES_BACKENDS = {"postgres", "postgresql", "timescaledb"}


def resolve_dsn(config: dict[str, Any]) -> str:
    """Return the connection string for a Postgres source.

    ``dsn_env`` is preferred over a literal ``dsn`` so credentials live in the
    machine's ``.env`` and never in a tracked YAML file. There is deliberately
    no fallback to ``data.source.path``: that key defaults to the batch CSV, and
    silently connecting to the wrong thing is worse than failing loudly.
    """
    env_name = config.get("dsn_env")
    if env_name:
        dsn = os.environ.get(str(env_name), "").strip()
        if not dsn:
            # Task Scheduler starts with a bare environment; fall back to `.env`.
            load_env_file()
            dsn = os.environ.get(str(env_name), "").strip()
        if not dsn:
            raise ValueError(
                f"Biến môi trường {env_name!r} chưa được đặt. DSN Postgres phải nằm trong "
                "`.env` của máy chạy (đã gitignore), không commit vào repo."
            )
        return dsn
    dsn = str(config.get("dsn") or "").strip()
    if not dsn:
        raise ValueError(
            "Backend postgres cần `data.source.dsn_env` (khuyến nghị) hoặc `data.source.dsn`."
        )
    return dsn


class PostgresMarketDataSource:
    """Read-only PostgreSQL/TimescaleDB source.

    The daily panel for one symbol is small (~6 300 sessions), so the connector
    reads the whole history and reuses :func:`_slice_since`. That keeps the
    windowing logic identical to the file backends instead of re-deriving the
    ``lookback_buffer_days`` semantics in SQL, where an off-by-one would stay
    invisible until it corrupted a forecast.

    Identifiers go through :class:`psycopg.sql.Identifier` and the symbol filter
    is a bound parameter, so a table or symbol name cannot inject SQL.
    """

    backend = "postgres"

    def __init__(
        self,
        dsn: str,
        table: str,
        column_map: dict[str, str] | None = None,
        date_unit: str | None = None,
        *,
        symbol: str | None = None,
        symbol_column: str = "symbol",
        schema: str | None = None,
        connect_timeout: int = 15,
    ) -> None:
        import psycopg

        self.table = str(table)
        self.schema = str(schema) if schema else None
        self.symbol = str(symbol) if symbol else None
        self.symbol_column = str(symbol_column or "symbol")
        self.column_map = {**DEFAULT_COLUMN_MAP, **(column_map or {})}
        self.date_unit = date_unit
        self._connection = psycopg.connect(
            str(dsn),
            connect_timeout=int(connect_timeout),
            autocommit=True,
            options="-c default_transaction_read_only=on",
        )

    # -- SQL construction ---------------------------------------------------
    def _table_identifier(self):
        from psycopg import sql

        return sql.Identifier(self.schema, self.table) if self.schema else sql.Identifier(self.table)

    def _where(self):
        from psycopg import sql

        if not self.symbol:
            return sql.SQL(""), []
        return sql.SQL(" WHERE {} = %s").format(sql.Identifier(self.symbol_column)), [self.symbol]

    def _select_columns(self):
        """Project the source columns onto the canonical OHLCV names.

        Numeric columns are cast server-side: PostgreSQL ``numeric`` arrives as
        ``Decimal``, which pandas would otherwise keep as an object column.
        """
        from psycopg import sql

        parts = []
        for canonical in OHLCV_COLUMNS:
            source = self.column_map.get(canonical)
            if not source:
                continue
            column = sql.Identifier(source)
            if canonical == "date":
                parts.append(sql.SQL("{} AS {}").format(column, sql.Identifier(canonical)))
            else:
                parts.append(
                    sql.SQL("{}::double precision AS {}").format(column, sql.Identifier(canonical))
                )
        if not parts:
            raise ValueError("column_map không map được cột nào sang OHLCV")
        return sql.SQL(", ").join(parts)

    def _frame(self, statement, params: list[Any]) -> pd.DataFrame:
        """Run a query and build a DataFrame without going through ``pd.read_sql``.

        ``pd.read_sql`` warns on any DBAPI connection that is not sqlite3, and
        this repository treats warnings as failures.
        """
        with self._connection.cursor() as cursor:
            cursor.execute(statement, params or None)
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
        return pd.DataFrame(rows, columns=columns)

    # -- MarketDataSource protocol -----------------------------------------
    def _read(self) -> pd.DataFrame:
        from psycopg import sql

        where, params = self._where()
        statement = sql.SQL("SELECT {columns} FROM {table}{where} ORDER BY {order}").format(
            columns=self._select_columns(),
            table=self._table_identifier(),
            where=where,
            order=sql.Identifier(self.column_map["date"]),
        )
        # The projection already emits canonical names, so the rename is identity.
        return _normalize(self._frame(statement, params), DEFAULT_COLUMN_MAP, self.date_unit)

    def latest_date(self) -> pd.Timestamp:
        from psycopg import sql

        where, params = self._where()
        statement = sql.SQL("SELECT max({date}) AS date FROM {table}{where}").format(
            date=sql.Identifier(self.column_map["date"]),
            table=self._table_identifier(),
            where=where,
        )
        frame = self._frame(statement, params)
        value = frame["date"].iloc[0] if len(frame) else None
        if value is None:
            raise ValueError(
                f"Bảng {self.table!r} không có phiên nào"
                + (f" cho symbol {self.symbol!r}" if self.symbol else "")
            )
        if self.date_unit:
            return pd.Timestamp(pd.to_datetime(value, unit=self.date_unit))
        return pd.Timestamp(pd.to_datetime(value))

    def fetch_since(
        self, since: pd.Timestamp | None, lookback_buffer_days: int | None
    ) -> pd.DataFrame:
        return _slice_since(self._read(), since, lookback_buffer_days)

    def execute_for_test(self, statement: str) -> None:
        """Attempt a statement so tests can prove writes are rejected."""
        import psycopg

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(statement)  # type: ignore[arg-type]
        except psycopg.Error as error:
            raise ReadOnlyViolation(f"Nguồn Postgres là read-only: {error}") from error
        raise ReadOnlyViolation("Câu lệnh ghi không bị chặn — kết nối không ở chế độ read-only")

    def close(self) -> None:
        self._connection.close()


class CsvMarketDataSource:
    """Local file source reusing the defensive parser in :mod:`vnindex_model.data`.

    Kept as the default so `update-latest` is exercisable before the VPS
    connection string is known, and so tests never need a database.
    """

    backend = "csv"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _read(self) -> pd.DataFrame:
        frame = load_price_data(self.path)[0]
        return frame[[name for name in OHLCV_COLUMNS if name in frame]].reset_index(drop=True)

    def latest_date(self) -> pd.Timestamp:
        return pd.Timestamp(self._read()["date"].max())

    def fetch_since(self, since: pd.Timestamp | None, lookback_buffer_days: int | None) -> pd.DataFrame:
        return _slice_since(self._read(), since, lookback_buffer_days)

    def close(self) -> None:
        return None


def build_market_data_source(config: dict[str, Any]) -> MarketDataSource:
    """Instantiate the connector named by ``data.source.backend``.

    MySQL is still absent on purpose: no such store exists here, and guessing a
    schema would violate the repository's rule against silent assumptions.
    """
    backend = str(config.get("backend", "csv")).lower()
    if backend in POSTGRES_BACKENDS:
        table = config.get("table")
        if not table:
            raise ValueError(f"data.source.table là bắt buộc cho backend {backend}")
        return PostgresMarketDataSource(
            resolve_dsn(config),
            table,
            config.get("column_map"),
            config.get("date_unit"),
            symbol=config.get("symbol"),
            symbol_column=config.get("symbol_column", "symbol"),
            schema=config.get("schema"),
            connect_timeout=int(config.get("connect_timeout", 15)),
        )
    path = config.get("path")
    if not path:
        raise ValueError("data.source.path là bắt buộc")
    if backend == "csv":
        return CsvMarketDataSource(path)
    if backend in {"sqlite", "duckdb"}:
        table = config.get("table")
        if not table:
            raise ValueError(f"data.source.table là bắt buộc cho backend {backend}")
        factory = SQLiteMarketDataSource if backend == "sqlite" else DuckDBMarketDataSource
        return factory(path, table, config.get("column_map"), config.get("date_unit"))
    raise ValueError(
        f"data.source.backend chưa hỗ trợ: {backend!r}. "
        "Hỗ trợ: csv, sqlite, duckdb, postgres. "
        "Cần MySQL thì bổ sung driver sau khi xác nhận schema thật, đừng đoán."
    )
