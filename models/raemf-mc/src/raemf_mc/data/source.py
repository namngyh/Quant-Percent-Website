"""Read-only market data sources, so the model can run on live sessions.

`ingest.parse_vnindex_csv` exists to repair one specific broken export: a vendor
CSV that splits thousands-separated prices across extra fields and strips the
remainder's leading zeros. None of that applies to a database, where the numbers
arrive already typed. So this module bypasses the parser and goes straight to
the validation stage -- the same `drop_exact_duplicates`,
`validate_ohlc_invariants` and `check_implausible_daily_moves` the CSV path
runs, because those checks guard against bad *data*, not bad parsing.

Read-only is enforced by the server: the session is opened with
`default_transaction_read_only=on`, so a write is refused whatever the client
asks for.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from raemf_mc.data.ingest import (
    DroppedRow,
    check_implausible_daily_moves,
    drop_exact_duplicates,
    validate_ohlc_invariants,
)

OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
DEFAULT_COLUMN_MAP = {
    "date": "trading_date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}
DEFAULT_TABLE = "bars_1d"
DEFAULT_SYMBOL = "VNINDEX"
ENV_FILENAME = ".env"


def find_env_file(start: str | Path | None = None) -> Path | None:
    """Locate `.env` in `start` or any parent directory."""
    origin = Path(start) if start is not None else Path.cwd()
    origin = origin if origin.is_dir() else origin.parent
    for directory in [origin.resolve(), *origin.resolve().parents]:
        candidate = directory / ENV_FILENAME
        if candidate.is_file():
            return candidate
    return None


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Parse `KEY=VALUE` lines, ignoring blanks, comments and `export`.

    Everything after the first `=` is kept verbatim apart from one layer of
    surrounding quotes: a Postgres password may contain `#`, spaces or `=`.
    """
    values: dict[str, str] = {}
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_env_file(start: str | Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Load `.env` into `os.environ`; real environment variables win by default."""
    path = find_env_file(start)
    if path is None:
        return {}
    values = parse_env_file(path)
    for key, value in values.items():
        if override or not os.environ.get(key):
            os.environ[key] = value
    return values


def resolve_dsn(dsn: str | None = None, dsn_env: str = "RAEMF_MARKET_DSN") -> str:
    """Connection string from an explicit DSN or from the environment/`.env`.

    Scheduled runs start with a bare environment, so `.env` is the fallback. The
    credential never belongs in a tracked config file.
    """
    if dsn:
        return str(dsn)
    value = os.environ.get(dsn_env, "").strip()
    if not value:
        load_env_file()
        value = os.environ.get(dsn_env, "").strip()
    if not value:
        raise ValueError(
            f"Chua co DSN: dat bien moi truong {dsn_env} trong `.env` (da gitignore) "
            "hoac truyen --dsn."
        )
    return value


class PostgresOHLCVSource:
    """Read-only PostgreSQL/TimescaleDB source for one symbol's daily bars."""

    backend = "postgres"

    def __init__(
        self,
        dsn: str,
        table: str = DEFAULT_TABLE,
        symbol: str = DEFAULT_SYMBOL,
        column_map: dict[str, str] | None = None,
        *,
        symbol_column: str = "symbol",
        schema: str | None = None,
        connect_timeout: int = 15,
    ) -> None:
        import psycopg

        self.table = str(table)
        self.symbol = str(symbol)
        self.symbol_column = str(symbol_column)
        self.schema = str(schema) if schema else None
        self.column_map = {**DEFAULT_COLUMN_MAP, **(column_map or {})}
        self._connection = psycopg.connect(
            str(dsn),
            connect_timeout=int(connect_timeout),
            autocommit=True,
            options="-c default_transaction_read_only=on",
        )

    def _table_identifier(self):
        from psycopg import sql

        return sql.Identifier(self.schema, self.table) if self.schema else sql.Identifier(self.table)

    def read_raw(self) -> pd.DataFrame:
        """Unvalidated OHLCV frame, one row per session, ascending by date.

        Numeric columns are cast server-side: PostgreSQL `numeric` arrives as
        `Decimal`, which pandas would keep as an object column and every
        downstream comparison would then be done in arbitrary precision.
        """
        from psycopg import sql

        projection = [
            sql.SQL("{} AS {}").format(
                sql.Identifier(self.column_map["date"]), sql.Identifier("date")
            )
        ]
        projection += [
            sql.SQL("{}::double precision AS {}").format(
                sql.Identifier(self.column_map[name]), sql.Identifier(name)
            )
            for name in OHLCV_COLUMNS
            if name != "date" and self.column_map.get(name)
        ]
        statement = sql.SQL(
            "SELECT {columns} FROM {table} WHERE {symbol_column} = %s ORDER BY {order}"
        ).format(
            columns=sql.SQL(", ").join(projection),
            table=self._table_identifier(),
            symbol_column=sql.Identifier(self.symbol_column),
            order=sql.Identifier(self.column_map["date"]),
        )
        with self._connection.cursor() as cursor:
            cursor.execute(statement, [self.symbol])
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
        frame = pd.DataFrame(rows, columns=columns)
        if frame.empty:
            raise ValueError(
                f"Bang {self.table!r} khong co phien nao cho symbol {self.symbol!r}"
            )
        frame["date"] = pd.to_datetime(frame["date"])
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0).astype("int64")
        return frame[OHLCV_COLUMNS]

    def execute_for_test(self, statement: str) -> None:
        """Attempt a statement so tests can prove the server rejects writes."""
        import psycopg

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(statement)  # type: ignore[arg-type]
        except psycopg.Error as error:
            raise PermissionError(f"Nguon Postgres la read-only: {error}") from error
        raise PermissionError("Cau lenh ghi khong bi chan -- ket noi khong o che do read-only")

    def close(self) -> None:
        self._connection.close()


def clean_ohlcv_frame(
    raw: pd.DataFrame, max_drop_fraction: float = 0.05
) -> tuple[pd.DataFrame, list[DroppedRow], int]:
    """Run the CSV path's validation stage on an already-typed frame.

    Deliberately the same checks in the same order as `clean_vnindex_data`, so a
    row the file path would have dropped is dropped here too. The database is
    cleaner than the vendor CSV -- it repairs 13 of the 14 sessions where the CSV
    violates `low <= close` -- but "cleaner" is an observation, not a licence to
    skip validation.
    """
    total = len(raw)
    if "line_number" not in raw.columns:
        # `DroppedRow` records where a rejected row came from. The CSV path fills
        # this with the physical file line; for a query the closest honest
        # analogue is the row's position in the ordered result set, which is what
        # a human would count to find it again.
        raw = raw.assign(line_number=range(1, total + 1))
    deduped, duplicates = drop_exact_duplicates(raw)
    valid, invalid = validate_ohlc_invariants(deduped)
    dropped = duplicates + invalid
    fraction = len(dropped) / total if total else 0.0
    if fraction > max_drop_fraction:
        raise ValueError(
            f"dropped fraction {fraction:.4f} exceeds max_drop_fraction="
            f"{max_drop_fraction}; {len(dropped)}/{total} rows dropped"
        )
    valid = valid.sort_values("date").reset_index(drop=True)
    clean = valid[OHLCV_COLUMNS]
    check_implausible_daily_moves(clean)
    return clean, dropped, total


def load_vnindex_from_database(
    dsn: str | None = None,
    *,
    dsn_env: str = "RAEMF_MARKET_DSN",
    table: str = DEFAULT_TABLE,
    symbol: str = DEFAULT_SYMBOL,
    column_map: dict[str, str] | None = None,
    max_drop_fraction: float = 0.05,
) -> tuple[pd.DataFrame, list[DroppedRow], int]:
    """Cleaned VN-Index OHLCV indexed by date, straight from the database.

    Same return shape as `loader.load_vnindex_ohlcv_with_report`, so callers can
    swap sources without changing anything downstream.
    """
    source = PostgresOHLCVSource(
        resolve_dsn(dsn, dsn_env), table=table, symbol=symbol, column_map=column_map
    )
    try:
        raw = source.read_raw()
    finally:
        source.close()
    clean, dropped, total = clean_ohlcv_frame(raw, max_drop_fraction=max_drop_fraction)
    indexed = clean.set_index("date")
    indexed.index.name = "date"
    return indexed, dropped, total


def describe_source(dsn: str | None = None, *, dsn_env: str = "RAEMF_MARKET_DSN") -> dict[str, Any]:
    """Inventory of the daily table: symbols, row counts, date coverage.

    Read-only. Written so a new machine can confirm what it is pointed at
    without anyone having to guess the schema.
    """
    import psycopg
    from psycopg import sql

    connection = psycopg.connect(
        resolve_dsn(dsn, dsn_env),
        connect_timeout=15,
        autocommit=True,
        options="-c default_transaction_read_only=on",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = %s ORDER BY ordinal_position",
                (DEFAULT_TABLE,),
            )
            columns = [{"name": name, "type": kind} for name, kind in cursor.fetchall()]
            cursor.execute(
                sql.SQL(
                    "SELECT symbol, count(*), min(trading_date), max(trading_date) "
                    "FROM {table} GROUP BY symbol ORDER BY count(*) DESC LIMIT 40"
                ).format(table=sql.Identifier(DEFAULT_TABLE))
            )
            symbols = [
                {"symbol": s, "rows": int(n), "first": str(lo), "last": str(hi)}
                for s, n, lo, hi in cursor.fetchall()
            ]
    finally:
        connection.close()
    return {"table": DEFAULT_TABLE, "columns": columns, "symbols": symbols}
