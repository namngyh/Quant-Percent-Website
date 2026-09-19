"""Read-only connectors.

Every connector is strictly read-only:
  * SQLite is opened with `?mode=ro` and additionally guarded by an
    `authorizer` callback that vetoes every write opcode;
  * DuckDB is opened with `read_only=True`;
  * file backends only ever call read APIs.

Each connector returns a long-format DataFrame conforming to the data contract
declared in `dynamicgraph.constants.DATA_CONTRACT_COLUMNS`.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from dynamicgraph.constants import (
    DATA_CONTRACT_COLUMNS,
    EXTENDED_COLUMNS,
    ICB_INDUSTRY_NAMES,
    ICB_SUPERSECTOR_NAMES,
    UNKNOWN_SECTOR,
)
from dynamicgraph.data.schema_inference import (
    INDEX_SYMBOL_CANDIDATES,
    decode_dates,
    infer_columns_from_names,
    inspect_sqlite_schema,
)
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

EPOCH = dt.date(1970, 1, 1)

#: DataPro stores a cumulative corporate-action rate scaled by 1e6.
#: Verified against 12 HPG adjustment events (see reports/data_audit_report.md):
#:     adjusted_close(t) = close(t) * (1 - ADJUST_RATE(t) / 1e6)
DATAPRO_ADJUST_SCALE = 1_000_000.0


class ReadOnlyViolation(RuntimeError):
    """Raised when a connector attempts to modify the raw database."""


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


def open_sqlite_readonly(path: str | Path, strict: bool = True) -> sqlite3.Connection:
    """Open a SQLite database read-only, with a write-denying authorizer."""
    uri = f"file:{Path(path).as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30, check_same_thread=False)
    if strict:
        con.set_authorizer(_readonly_authorizer)
    return con


@dataclass
class SourceMetadata:
    """Everything the audit report needs to know about the source."""

    path: str
    backend: str
    tables: list[str] = field(default_factory=list)
    n_symbols: int = 0
    date_min: str | None = None
    date_max: str | None = None
    has_adjusted_price: bool = False
    has_volume: bool = False
    has_turnover: bool = False
    has_sector: bool = False
    adjustment_method: str | None = None
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


class BaseConnector(ABC):
    """Read-only source of a long-format price panel."""

    backend: str = "base"

    def __init__(self, path: str | Path, config: Any = None) -> None:
        self.path = str(path)
        self.config = config
        self.metadata = SourceMetadata(path=self.path, backend=self.backend)

    @abstractmethod
    def list_symbols(self) -> pd.DataFrame:
        """Return a frame with at least `ticker`, `sector`, `is_index`."""

    @abstractmethod
    def load(
        self,
        tickers: Iterable[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Return the long-format panel for `tickers` between `start`/`end`."""

    def close(self) -> None:  # pragma: no cover - default no-op
        return None

    def __enter__(self) -> "BaseConnector":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# DataPro vendor SQLite
# ---------------------------------------------------------------------------
class DataProSQLiteConnector(BaseConnector):
    """Connector for the DataPro daily store (`HIST` + `QUOTES_INFO`).

    `HIST` is keyed by an opaque numeric `EID` with no foreign key to
    `QUOTES_INFO`. The link is reconstructed by fingerprinting: `QUOTES_INFO`
    carries the latest session's OHLCV snapshot per symbol, and the same tuple
    appears in `HIST` for the matching `EID`. Tuples that are unique on both
    sides give an unambiguous mapping. The result is cached to disk so that the
    (cheap but I/O heavy) resolution runs once.
    """

    backend = "datapro_sqlite"

    def __init__(self, path: str | Path, config: Any = None, cache_path: Path | None = None) -> None:
        super().__init__(path, config)
        self.con = open_sqlite_readonly(path)
        self.cache_path = cache_path
        self._symbol_to_eid: dict[str, int] | None = None
        self._info: pd.DataFrame | None = None

    def close(self) -> None:
        try:
            self.con.close()
        except Exception:  # pragma: no cover
            pass

    # -- symbol <-> EID -------------------------------------------------
    def _load_cached_map(self) -> dict[str, int] | None:
        if self.cache_path is None or not self.cache_path.exists():
            return None
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if payload.get("database") != self.path:
            return None
        latest = self.con.execute("SELECT MAX(TRADING_KEY) FROM HIST").fetchone()[0]
        if payload.get("max_trading_key") != int(latest or 0):
            logger.info("DataPro symbol map cache is stale (database advanced); re-resolving.")
            return None
        mapping = {str(k): int(v) for k, v in payload.get("map", {}).items()}
        logger.info("Loaded cached DataPro symbol map (%d symbols).", len(mapping))
        return mapping

    def _store_map(self, mapping: dict[str, int]) -> None:
        if self.cache_path is None:
            return
        latest = self.con.execute("SELECT MAX(TRADING_KEY) FROM HIST").fetchone()[0]
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(
                {
                    "database": self.path,
                    "max_trading_key": int(latest or 0),
                    "resolved_at": dt.datetime.now().isoformat(timespec="seconds"),
                    "method": "ohlcv_fingerprint",
                    "map": mapping,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def resolve_symbol_map(self, force: bool = False) -> dict[str, int]:
        """Reconstruct symbol -> EID. Cached unless `force`."""
        if self._symbol_to_eid is not None and not force:
            return self._symbol_to_eid
        if not force:
            cached = self._load_cached_map()
            if cached:
                self._symbol_to_eid = cached
                return cached

        keys = [
            int(r[0])
            for r in self.con.execute(
                "SELECT DISTINCT TRADING_KEY FROM HIST ORDER BY TRADING_KEY DESC LIMIT 8"
            )
        ]
        quotes = self.con.execute(
            "SELECT SYMBOL, OPEN_PX, HIGH_PX, LOW_PX, CLOSE_PX, VOL FROM QUOTES_INFO"
        ).fetchall()

        best: dict[str, int] = {}
        best_key: int | None = None
        for key in keys:
            hist: dict[tuple, list[int]] = {}
            for eid, open_px, high_px, low_px, close_px, volume in self.con.execute(
                "SELECT EID, OPEN_PX, HIGH_PX, LOW_PX, CLOSE_PX, VOL FROM HIST WHERE TRADING_KEY = ?",
                (key,),
            ):
                hist.setdefault(
                    (open_px, high_px, low_px, close_px, volume), []
                ).append(int(eid))
            quote_index: dict[tuple, list[str]] = {}
            for sym, open_px, high_px, low_px, close_px, volume in quotes:
                quote_index.setdefault(
                    (open_px, high_px, low_px, close_px, volume), []
                ).append(str(sym))
            mapping = {
                quote_index[k][0]: hist[k][0]
                for k in quote_index
                if k in hist and len(hist[k]) == 1 and len(quote_index[k]) == 1
            }
            if len(mapping) > len(best):
                best, best_key = mapping, key
            if len(mapping) > 0.6 * len(quotes):
                break

        if not best:
            raise ReadOnlyViolation(
                "Could not reconstruct the DataPro symbol->EID mapping. "
                "The QUOTES_INFO snapshot does not match any recent HIST session."
            )

        logger.info(
            "Resolved DataPro symbol map: %d/%d symbols via session %s.",
            len(best),
            len(quotes),
            EPOCH + dt.timedelta(days=best_key or 0),
        )
        self._symbol_to_eid = best
        self._store_map(best)
        return best

    # -- metadata -------------------------------------------------------
    def _quotes_info(self) -> pd.DataFrame:
        if self._info is not None:
            return self._info
        frame = pd.read_sql_query(
            "SELECT SYMBOL, NAME, NAME_EN, EXCHANGE, TYPE, ICB_ID, SHARES_OUT FROM QUOTES_INFO",
            self.con,
        )
        frame["SYMBOL"] = frame["SYMBOL"].astype(str).str.strip().str.upper()
        self._info = frame
        return frame

    @staticmethod
    def icb_to_sector(icb_id: Any) -> str:
        """Map a 6-digit ICB code to an ICB supersector name.

        Falls back to the industry level, then to UNKNOWN. The code layout
        `<industry:2><supersector:2><sector:2>` is an assumption validated
        against ~40 known VN tickers; see artifacts/reports/assumptions.md.
        """
        try:
            code = int(icb_id)
        except (TypeError, ValueError):
            return UNKNOWN_SECTOR
        if code <= 0:
            return UNKNOWN_SECTOR
        text = f"{code:06d}"
        return (
            ICB_SUPERSECTOR_NAMES.get(text[:4])
            or ICB_INDUSTRY_NAMES.get(text[:2])
            or UNKNOWN_SECTOR
        )

    def list_symbols(self) -> pd.DataFrame:
        info = self._quotes_info().copy()
        mapping = self.resolve_symbol_map()
        info["eid"] = info["SYMBOL"].map(mapping)
        info["sector"] = info["ICB_ID"].map(self.icb_to_sector)
        info["is_index"] = info["TYPE"].astype(str).str.upper().eq("IDX")
        info = info.rename(
            columns={
                "SYMBOL": "ticker",
                "NAME_EN": "name",
                "EXCHANGE": "exchange",
                "TYPE": "instrument_type",
                "SHARES_OUT": "shares_outstanding",
            }
        )
        return info[
            ["ticker", "name", "exchange", "instrument_type", "sector", "is_index", "eid",
             "shares_outstanding"]
        ]

    def detect_index_symbol(self, preferred: str | None = None) -> str | None:
        symbols = set(self._quotes_info()["SYMBOL"])
        if preferred and preferred.upper() in symbols:
            return preferred.upper()
        for candidate in INDEX_SYMBOL_CANDIDATES:
            if candidate in symbols:
                return candidate
        return None

    # -- loading --------------------------------------------------------
    def load(
        self,
        tickers: Iterable[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        mapping = self.resolve_symbol_map()
        info = self.list_symbols().set_index("ticker")

        if tickers is None:
            wanted = [t for t in mapping if t in info.index]
        else:
            wanted = [str(t).upper() for t in tickers]

        missing = [t for t in wanted if t not in mapping]
        if missing:
            self.metadata.warnings.append(
                f"{len(missing)} requested symbol(s) have no resolvable EID: {sorted(missing)[:20]}"
            )
            logger.warning("No EID for %d symbol(s): %s", len(missing), sorted(missing)[:20])
        wanted = [t for t in wanted if t in mapping]
        if not wanted:
            raise ValueError("None of the requested tickers exist in the DataPro database.")

        eids = [mapping[t] for t in wanted]
        eid_to_ticker = {mapping[t]: t for t in wanted}

        clauses = ["EID IN ({})".format(",".join("?" * len(eids)))]
        params: list[Any] = list(eids)
        if start:
            clauses.append("TRADING_KEY >= ?")
            params.append((pd.Timestamp(start).date() - EPOCH).days)
        if end:
            clauses.append("TRADING_KEY <= ?")
            params.append((pd.Timestamp(end).date() - EPOCH).days)

        query = (
            "SELECT EID, TRADING_KEY, ADJUST_RATE, OPEN_PX, HIGH_PX, LOW_PX, CLOSE_PX, "
            "REF_PX, VOL, VAL, OUTSTANDING_VOL, LISTED_VOL, "
            "FRN_BUY_VAL, FRN_SELL_VAL "
            f"FROM HIST WHERE {' AND '.join(clauses)}"
        )
        logger.info("Loading %d symbol(s) from DataPro daily store ...", len(wanted))
        raw = pd.read_sql_query(query, self.con, params=params)
        if raw.empty:
            raise ValueError("DataPro query returned no rows for the requested selection.")

        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(raw["TRADING_KEY"].astype("int64"), unit="D", origin="unix"),
                "ticker": raw["EID"].map(eid_to_ticker),
                "open": pd.to_numeric(raw["OPEN_PX"], errors="coerce"),
                "high": pd.to_numeric(raw["HIGH_PX"], errors="coerce"),
                "low": pd.to_numeric(raw["LOW_PX"], errors="coerce"),
                "close": pd.to_numeric(raw["CLOSE_PX"], errors="coerce"),
                "volume": pd.to_numeric(raw["VOL"], errors="coerce"),
                "turnover": pd.to_numeric(raw["VAL"], errors="coerce"),
                "reference_price": pd.to_numeric(raw["REF_PX"], errors="coerce"),
                "shares_outstanding": pd.to_numeric(raw["OUTSTANDING_VOL"], errors="coerce"),
                "foreign_buy_value": pd.to_numeric(raw["FRN_BUY_VAL"], errors="coerce"),
                "foreign_sell_value": pd.to_numeric(raw["FRN_SELL_VAL"], errors="coerce"),
            }
        )
        rate = pd.to_numeric(raw["ADJUST_RATE"], errors="coerce").fillna(0.0)
        factor = 1.0 - rate / DATAPRO_ADJUST_SCALE
        factor = factor.where(factor > 0, np.nan)
        frame["adjusted_close"] = frame["close"] * factor
        frame["adjustment_factor"] = factor

        frame["sector"] = frame["ticker"].map(info["sector"]).fillna(UNKNOWN_SECTOR)
        frame["is_index"] = frame["ticker"].map(info["is_index"]).fillna(False).astype(bool)
        frame["market_cap"] = frame["close"] * frame["shares_outstanding"]

        frame = frame.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)

        self.metadata.tables = ["HIST", "QUOTES_INFO"]
        self.metadata.n_symbols = frame["ticker"].nunique()
        self.metadata.date_min = str(frame["date"].min().date())
        self.metadata.date_max = str(frame["date"].max().date())
        self.metadata.has_adjusted_price = True
        self.metadata.has_volume = True
        self.metadata.has_turnover = True
        self.metadata.has_sector = frame["sector"].ne(UNKNOWN_SECTOR).any()
        self.metadata.adjustment_method = (
            "adjusted_close = close * (1 - ADJUST_RATE/1e6); cumulative vendor factor, "
            "latest session factor = 1.0"
        )
        self.metadata.assumptions += [
            "HIST.TRADING_KEY is days since 1970-01-01. Validated by decoding the maximum key and "
            "matching it to the session represented by the QUOTES_INFO snapshot.",
            "HIST.EID <-> QUOTES_INFO.SYMBOL is reconstructed by unique OHLCV fingerprint on the "
            "latest session, because the vendor schema carries no foreign key between the two "
            "tables. Symbols whose OHLCV tuple is not unique on that session remain unmapped and "
            "are reported rather than guessed.",
            "adjusted_close = close * (1 - ADJUST_RATE/1e6). The scale and functional form were "
            "verified against 12 HPG corporate-action boundaries: the implied factor ratio matched "
            "the observed reference-price-to-previous-close ratio to 5 decimal places at every one.",
            "Prices are quoted in thousand VND and turnover (VAL) in VND. Only ratios and log "
            "differences are used downstream, so the unit mismatch does not propagate.",
            "ICB_ID decodes as <industry:2><supersector:2><sector:2>. Validated against ~40 known "
            "tickers (banks -> 8030, real estate -> 8060, securities -> 8070, steel -> 1070).",
            "Rows with TRADING_KEY before 1990 belong to global reference series (equity indices, "
            "metals, FX), not Vietnamese listings; they do not enter a VN30 universe.",
        ]
        return _finalize_contract(frame)


# ---------------------------------------------------------------------------
# Generic SQLite / DuckDB / file backends
# ---------------------------------------------------------------------------
class GenericSQLConnector(BaseConnector):
    """Connector for an arbitrary SQLite/DuckDB price table.

    The table and column mapping come from schema inference (or explicit
    `data.table` / `data.column_map` overrides).
    """

    backend = "generic_sqlite"

    def __init__(
        self,
        path: str | Path,
        config: Any = None,
        table: str | None = None,
        column_map: dict[str, str] | None = None,
        duckdb_mode: bool = False,
    ) -> None:
        super().__init__(path, config)
        self.duckdb_mode = duckdb_mode
        self.backend = "duckdb" if duckdb_mode else "generic_sqlite"
        self.metadata.backend = self.backend

        if duckdb_mode:
            import duckdb

            self.con = duckdb.connect(str(path), read_only=True)
            tables = [
                r[0] for r in self.con.execute("SELECT table_name FROM information_schema.tables").fetchall()
            ]
            self.schema = {"tables": {t: {} for t in tables}}
        else:
            self.con = open_sqlite_readonly(path)
            self.schema = inspect_sqlite_schema(Path(path))

        self.table = table or self.schema.get("primary_table")
        if self.table is None:
            candidates = self.schema.get("tables", {})
            self.table = max(
                candidates, key=lambda t: candidates[t].get("panel_score", 0), default=None
            )
        if self.table is None:
            raise ValueError(f"No usable price table found in {path}")

        inferred = self.schema.get("tables", {}).get(self.table, {}).get("column_map", {})
        if not inferred:
            cols = self._columns()
            inferred = infer_columns_from_names(cols)
        self.column_map = {**inferred, **(column_map or {})}
        self.date_encoding = (
            self.schema.get("tables", {}).get(self.table, {}).get("date_encoding") or "iso"
        )
        for required in ("date", "ticker", "close"):
            if required not in self.column_map:
                raise ValueError(
                    f"Could not identify a `{required}` column in table `{self.table}`. "
                    f"Set data.column_map.{required} explicitly in the config."
                )

    def _columns(self) -> list[str]:
        if self.duckdb_mode:
            return [r[0] for r in self.con.execute(f'DESCRIBE "{self.table}"').fetchall()]
        return [r[1] for r in self.con.execute(f'PRAGMA table_info("{self.table}")').fetchall()]

    def close(self) -> None:
        try:
            self.con.close()
        except Exception:  # pragma: no cover
            pass

    def _query(self, sql: str, params: list[Any] | None = None) -> pd.DataFrame:
        if self.duckdb_mode:
            return self.con.execute(sql, params or []).fetch_df()
        return pd.read_sql_query(sql, self.con, params=params)

    def list_symbols(self) -> pd.DataFrame:
        col = self.column_map["ticker"]
        frame = self._query(f'SELECT DISTINCT "{col}" AS ticker FROM "{self.table}"')
        frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
        sector_col = self.column_map.get("sector")
        if sector_col:
            sectors = self._query(
                f'SELECT DISTINCT "{col}" AS ticker, "{sector_col}" AS sector FROM "{self.table}"'
            )
            sectors["ticker"] = sectors["ticker"].astype(str).str.strip().str.upper()
            frame = frame.merge(sectors.drop_duplicates("ticker"), on="ticker", how="left")
        else:
            frame["sector"] = UNKNOWN_SECTOR
        frame["is_index"] = frame["ticker"].isin(INDEX_SYMBOL_CANDIDATES)
        return frame

    def detect_index_symbol(self, preferred: str | None = None) -> str | None:
        symbols = set(self.list_symbols()["ticker"])
        if preferred and preferred.upper() in symbols:
            return preferred.upper()
        return next((c for c in INDEX_SYMBOL_CANDIDATES if c in symbols), None)

    def load(
        self,
        tickers: Iterable[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        cmap = self.column_map
        select_parts = [f'"{cmap["date"]}" AS date', f'"{cmap["ticker"]}" AS ticker']
        for field_name in (
            "open", "high", "low", "close", "adjusted_close", "volume", "turnover",
            "sector", "market_cap", "shares_outstanding",
        ):
            if field_name in cmap:
                select_parts.append(f'"{cmap[field_name]}" AS {field_name}')

        clauses: list[str] = []
        params: list[Any] = []
        if tickers is not None:
            wanted = [str(t).upper() for t in tickers]
            clauses.append(f'UPPER("{cmap["ticker"]}") IN ({",".join(["?"] * len(wanted))})')
            params.extend(wanted)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f'SELECT {", ".join(select_parts)} FROM "{self.table}"{where}'
        frame = self._query(sql, params)

        frame["date"] = decode_dates(frame["date"], self.date_encoding)
        frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
        if start:
            frame = frame[frame["date"] >= pd.Timestamp(start)]
        if end:
            frame = frame[frame["date"] <= pd.Timestamp(end)]

        if "sector" not in frame.columns:
            frame["sector"] = UNKNOWN_SECTOR
        frame["is_index"] = frame["ticker"].isin(INDEX_SYMBOL_CANDIDATES)

        self.metadata.tables = [self.table]
        self.metadata.n_symbols = frame["ticker"].nunique()
        if len(frame):
            self.metadata.date_min = str(frame["date"].min().date())
            self.metadata.date_max = str(frame["date"].max().date())
        self.metadata.has_adjusted_price = "adjusted_close" in frame.columns
        self.metadata.has_volume = "volume" in frame.columns
        self.metadata.has_turnover = "turnover" in frame.columns
        self.metadata.has_sector = "sector" in frame.columns
        return _finalize_contract(frame)


#: URL schemes routed to :class:`PostgresConnector`. SQLAlchemy-style driver
#: suffixes (`postgresql+psycopg`) are accepted because `.env.example` has
#: documented that spelling since before a Postgres backend existed.
POSTGRES_SCHEMES = ("postgresql", "postgres", "timescaledb")


def is_postgres_url(value: str | None) -> bool:
    if not value or "://" not in str(value):
        return False
    scheme = str(value).partition("://")[0].lower()
    return scheme.partition("+")[0] in POSTGRES_SCHEMES


def normalise_postgres_dsn(value: str) -> str:
    """Strip the SQLAlchemy driver suffix and alias `timescaledb://`.

    psycopg understands `postgresql://` and `postgres://` only; anything else in
    the scheme is a SQLAlchemy convention it would reject.
    """
    scheme, separator, rest = str(value).partition("://")
    if not separator:
        return str(value)
    base = scheme.lower().partition("+")[0]
    if base == "timescaledb":
        base = "postgresql"
    return f"{base}://{rest}"


def _redact_dsn(value: str) -> str:
    """Hide credentials before the DSN reaches metadata, reports or logs."""
    from dynamicgraph.config import redact

    return redact(str(value))


class PostgresConnector(BaseConnector):
    """Connector for the QuantPercent TimescaleDB daily panel (`bars_1d`).

    Read-only is enforced by the *server*: the session is opened with
    ``default_transaction_read_only=on``, so a write is refused even if a future
    code path asks for one. That is stronger than the client-side discipline the
    file backends rely on.

    Corporate actions
    -----------------
    ``bars_1d.adj_rate`` is a cumulative *divisor* whose most recent value is 1,
    not the DataPro ``ADJUST_RATE/1e6`` multiplier used by
    :class:`DataProSQLiteConnector`. Getting this backwards is silent: prices
    stay plausible and only the returns around corporate actions are wrong.

    The direction was verified, not assumed. Across the 35 symbols with complete
    ``adj_rate`` coverage, every session where ``adj_rate`` changes is a
    corporate-action boundary at which the identity

        (ref_px(t) / close(t-1)) * (adj_rate(t-1) / adj_rate(t)) == 1

    must hold. On 375 such events since 2015 the median is 1.000000 and 364 fall
    within 1% of 1. The 11 that do not are all cases where the vendor left
    ``ref_px`` unadjusted, which is a defect in ``ref_px`` rather than in
    ``adj_rate``: the multiplicative form is off by ~9% median and is ruled out.
    """

    backend = "postgres"

    #: Physical columns of the QuantPercent `bars_1d` table.
    DEFAULT_COLUMN_MAP = {
        "date": "trading_date",
        "ticker": "symbol",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "turnover": "value",
        "reference_price": "ref_px",
        "foreign_buy_value": "frn_buy_val",
        "foreign_sell_value": "frn_sell_val",
    }
    #: Cumulative back-adjustment divisor; absent from generic price tables.
    ADJUSTMENT_COLUMN = "adj_rate"
    DEFAULT_TABLE = "bars_1d"

    def __init__(
        self,
        dsn: str,
        config: Any = None,
        table: str | None = None,
        column_map: dict[str, str] | None = None,
        connect_timeout: int = 15,
    ) -> None:
        import psycopg

        super().__init__(_redact_dsn(dsn), config)
        self.table = table or self.DEFAULT_TABLE
        self.column_map = {**self.DEFAULT_COLUMN_MAP, **(column_map or {})}
        self.con = psycopg.connect(
            normalise_postgres_dsn(dsn),
            connect_timeout=int(connect_timeout),
            autocommit=True,
            options="-c default_transaction_read_only=on",
        )
        # Validation happens after connecting, so any failure here has to release
        # the socket. Left to the garbage collector it resurfaces much later as an
        # unraisable exception inside an unrelated caller.
        try:
            self._available = self._table_columns()
            for required in ("date", "ticker", "close"):
                physical = self.column_map.get(required)
                if not physical or physical not in self._available:
                    raise ValueError(
                        f"Table `{self.table}` has no `{required}` column "
                        f"(looked for {physical!r}). Set data.column_map.{required} in the config."
                    )
        except Exception:
            self.close()
            raise
        self.metadata.backend = self.backend

    # -- introspection ------------------------------------------------------
    def _table_columns(self) -> set[str]:
        schema, _, name = self.table.rpartition(".")
        with self.con.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s AND (%s = '' OR table_schema = %s)",
                (name, schema, schema),
            )
            columns = {row[0] for row in cursor.fetchall()}
        if not columns:
            raise ValueError(f"Table `{self.table}` does not exist or is not visible to this role.")
        return columns

    def _identifier(self, name: str):
        from psycopg import sql

        schema, _, table = name.rpartition(".")
        return sql.Identifier(schema, table) if schema else sql.Identifier(table)

    def _query(self, statement, params: list[Any] | None = None) -> pd.DataFrame:
        """Build the frame from the cursor: `pd.read_sql` warns on non-sqlite DBAPI."""
        with self.con.cursor() as cursor:
            cursor.execute(statement, params or None)
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
        return pd.DataFrame(rows, columns=columns)

    def execute_for_test(self, statement: str) -> None:
        """Attempt a statement so tests can prove the server rejects writes.

        Asserting this against the live server matters: a mock would only prove
        that the mock says no, and the read-only guarantee here is a property of
        the connection options, not of this class.
        """
        import psycopg

        try:
            with self.con.cursor() as cursor:
                cursor.execute(statement)  # type: ignore[arg-type]
        except psycopg.Error as error:
            raise ReadOnlyViolation(f"Postgres source is read-only: {error}") from error
        raise ReadOnlyViolation(
            "A write statement was not rejected - the connection is not read-only"
        )

    def close(self) -> None:
        try:
            self.con.close()
        except Exception:  # pragma: no cover - already closed
            pass

    # -- BaseConnector ------------------------------------------------------
    def list_symbols(self) -> pd.DataFrame:
        from psycopg import sql

        statement = sql.SQL("SELECT DISTINCT {ticker} AS ticker FROM {table}").format(
            ticker=self._identifier(self.column_map["ticker"]),
            table=self._identifier(self.table),
        )
        frame = self._query(statement)
        frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
        frame["sector"] = UNKNOWN_SECTOR
        frame["is_index"] = frame["ticker"].isin(INDEX_SYMBOL_CANDIDATES)
        return frame.sort_values("ticker").reset_index(drop=True)

    def detect_index_symbol(self, preferred: str | None = None) -> str | None:
        symbols = set(self.list_symbols()["ticker"])
        if preferred and preferred.upper() in symbols:
            return preferred.upper()
        return next((c for c in INDEX_SYMBOL_CANDIDATES if c in symbols), None)

    def load(
        self,
        tickers: Iterable[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        from psycopg import sql

        cmap = self.column_map
        fields = [
            name
            for name in (
                "date", "ticker", "open", "high", "low", "close", "volume", "turnover",
                "reference_price", "foreign_buy_value", "foreign_sell_value",
            )
            if cmap.get(name) in self._available
        ]
        selected = [
            sql.SQL("{} AS {}").format(self._identifier(cmap[name]), sql.Identifier(name))
            for name in fields
        ]
        has_adjustment = self.ADJUSTMENT_COLUMN in self._available
        if has_adjustment:
            selected.append(
                sql.SQL("{} AS adjustment_rate").format(sql.Identifier(self.ADJUSTMENT_COLUMN))
            )

        clauses: list = []
        params: list[Any] = []
        if tickers is not None:
            wanted = sorted({str(t).strip().upper() for t in tickers})
            clauses.append(
                sql.SQL("upper({}) = ANY(%s)").format(self._identifier(cmap["ticker"]))
            )
            params.append(wanted)
        if start:
            clauses.append(sql.SQL("{} >= %s").format(self._identifier(cmap["date"])))
            params.append(pd.Timestamp(start).date())
        if end:
            clauses.append(sql.SQL("{} <= %s").format(self._identifier(cmap["date"])))
            params.append(pd.Timestamp(end).date())
        where = (
            sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses) if clauses else sql.SQL("")
        )

        statement = sql.SQL("SELECT {columns} FROM {table}{where}").format(
            columns=sql.SQL(", ").join(selected),
            table=self._identifier(self.table),
            where=where,
        )
        logger.info("Loading daily panel from Postgres table `%s` ...", self.table)
        frame = self._query(statement, params)
        if frame.empty:
            raise ValueError(
                f"Postgres query on `{self.table}` returned no rows for the requested selection."
            )

        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
        for column in frame.columns:
            if column not in {"date", "ticker"}:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")

        if has_adjustment:
            rate = frame.pop("adjustment_rate")
            # A zero or negative divisor is corrupt, not merely missing: NaN keeps
            # it out of the adjusted series instead of producing an absurd price.
            factor = 1.0 / rate.where(rate > 0, np.nan)
            frame["adjusted_close"] = frame["close"] * factor
            frame["adjustment_factor"] = factor
            self.metadata.adjustment_method = (
                "adjusted_close = close / adj_rate (cumulative back-adjustment divisor, latest "
                "session = 1). Verified on 375 adj_rate change events across 35 symbols since "
                "2015: (ref_px/prev_close) * (adj_rate_prev/adj_rate_now) has median 1.000000 "
                "and lies within 1% of 1 on 364 of them."
            )
            self.metadata.assumptions.append(
                "bars_1d.adj_rate is a DIVISOR whose latest value is 1, unlike the DataPro "
                "SQLite ADJUST_RATE which is a 1e6-scaled multiplier. Only 35 of 389 symbols "
                "(the ingestion watchlist: VN30 plus the indices) carry it; the rest were "
                "backfilled without it and have no adjusted price."
            )
        else:
            self.metadata.warnings.append(
                f"Table `{self.table}` has no `{self.ADJUSTMENT_COLUMN}` column, so no adjusted "
                "price is available from this source."
            )

        frame["sector"] = UNKNOWN_SECTOR
        frame["is_index"] = frame["ticker"].isin(INDEX_SYMBOL_CANDIDATES)

        self.metadata.tables = [self.table]
        self.metadata.n_symbols = int(frame["ticker"].nunique())
        self.metadata.date_min = str(frame["date"].min().date())
        self.metadata.date_max = str(frame["date"].max().date())
        self.metadata.has_adjusted_price = bool(
            "adjusted_close" in frame.columns and frame["adjusted_close"].notna().any()
        )
        self.metadata.has_volume = "volume" in frame.columns
        self.metadata.has_turnover = "turnover" in frame.columns
        self.metadata.has_sector = False

        if self.metadata.has_adjusted_price:
            missing = frame.loc[frame["adjusted_close"].isna(), "ticker"].unique()
            if len(missing):
                self.metadata.warnings.append(
                    f"{len(missing)} symbol(s) have no adjustment factor and therefore no adjusted "
                    f"price: {', '.join(sorted(missing)[:10])}"
                    + (" ..." if len(missing) > 10 else "")
                )
        return _finalize_contract(frame)


class FileConnector(BaseConnector):
    """Connector for Parquet / CSV / Feather, either a single file or a
    directory of per-ticker files (ticker taken from the filename stem)."""

    backend = "file"

    def __init__(self, path: str | Path, config: Any = None, column_map: dict[str, str] | None = None) -> None:
        super().__init__(path, config)
        self._frame: pd.DataFrame | None = None
        self._column_map_override = column_map or {}

    def _read_one(self, path: Path) -> pd.DataFrame:
        suffix = path.suffix.lower()
        if suffix in {".parquet", ".pq"}:
            return pd.read_parquet(path)
        if suffix in {".feather", ".arrow"}:
            return pd.read_feather(path)
        if suffix in {".h5", ".hdf5"}:
            return pd.read_hdf(path)
        return pd.read_csv(path)

    def _materialise(self) -> pd.DataFrame:
        if self._frame is not None:
            return self._frame
        root = Path(self.path)
        frames: list[pd.DataFrame] = []
        if root.is_dir():
            files = sorted(
                p for p in root.iterdir()
                if p.suffix.lower() in {".csv", ".parquet", ".pq", ".feather", ".arrow"}
            )
            for file in files:
                part = self._read_one(file)
                mapping = {**infer_columns_from_names(list(part.columns)), **self._column_map_override}
                if "ticker" not in mapping:
                    part["__ticker__"] = file.stem.upper()
                    mapping["ticker"] = "__ticker__"
                frames.append(part.rename(columns={v: k for k, v in mapping.items()}))
        else:
            part = self._read_one(root)
            mapping = {**infer_columns_from_names(list(part.columns)), **self._column_map_override}
            frames.append(part.rename(columns={v: k for k, v in mapping.items()}))

        frame = pd.concat(frames, ignore_index=True)
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
        if "sector" not in frame.columns:
            frame["sector"] = UNKNOWN_SECTOR
        frame["is_index"] = frame["ticker"].isin(INDEX_SYMBOL_CANDIDATES)
        self._frame = frame
        return frame

    def list_symbols(self) -> pd.DataFrame:
        frame = self._materialise()
        return (
            frame[["ticker", "sector", "is_index"]]
            .drop_duplicates("ticker")
            .reset_index(drop=True)
        )

    def detect_index_symbol(self, preferred: str | None = None) -> str | None:
        symbols = set(self._materialise()["ticker"])
        if preferred and preferred.upper() in symbols:
            return preferred.upper()
        return next((c for c in INDEX_SYMBOL_CANDIDATES if c in symbols), None)

    def load(
        self,
        tickers: Iterable[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        frame = self._materialise().copy()
        if tickers is not None:
            frame = frame[frame["ticker"].isin({str(t).upper() for t in tickers})]
        if start:
            frame = frame[frame["date"] >= pd.Timestamp(start)]
        if end:
            frame = frame[frame["date"] <= pd.Timestamp(end)]
        self.metadata.n_symbols = frame["ticker"].nunique()
        if len(frame):
            self.metadata.date_min = str(frame["date"].min().date())
            self.metadata.date_max = str(frame["date"].max().date())
        self.metadata.has_adjusted_price = "adjusted_close" in frame.columns
        self.metadata.has_volume = "volume" in frame.columns
        self.metadata.has_turnover = "turnover" in frame.columns
        return _finalize_contract(frame)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def _finalize_contract(frame: pd.DataFrame) -> pd.DataFrame:
    """Guarantee the contract columns exist, ordered, with sane dtypes."""
    for column in DATA_CONTRACT_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    frame["sector"] = frame["sector"].fillna(UNKNOWN_SECTOR).astype(str)
    frame["is_index"] = frame["is_index"].fillna(False).astype(bool)
    extras = [c for c in EXTENDED_COLUMNS + ["adjustment_factor"] if c in frame.columns]
    ordered = DATA_CONTRACT_COLUMNS + extras
    return frame[ordered].sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)


def build_connector(config: Any, cache_dir: Path | None = None) -> BaseConnector:
    """Instantiate the right connector for `config.data`."""
    raw_path = config.data.database_path
    if not raw_path:
        raise FileNotFoundError(
            "No database configured. Run `python -m dynamicgraph.cli discover-data`, then set "
            "`data.database_path` in config/local.yaml (copy it from config/local.example.yaml)."
        )

    path = str(raw_path)
    backend_hint = str(config.data.backend or "auto").lower()
    if is_postgres_url(path) or backend_hint in {"postgres", "postgresql", "timescaledb"}:
        if not is_postgres_url(path):
            raise ValueError(
                f"data.backend is `{backend_hint}` but data.database_path is not a Postgres URL. "
                "Set DYNAMICGRAPH_DATABASE_URL (or data.database_path) to "
                "postgresql://user:password@host:5432/dbname."
            )
        return PostgresConnector(
            path,
            config,
            table=config.data.table,
            column_map=dict(config.data.column_map or {}),
        )

    if "://" in path:
        scheme, _, rest = path.partition("://")
        if scheme.startswith("sqlite"):
            path = rest.lstrip("/")
            if len(path) > 1 and path[1] != ":":
                path = "/" + path
        elif scheme.startswith("duckdb"):
            path = rest.lstrip("/")
        else:
            raise NotImplementedError(
                f"Backend `{scheme}` is not implemented. Supported: postgresql, sqlite, duckdb, "
                "parquet, csv, feather."
            )

    resolved = Path(path)
    if not resolved.is_absolute():
        from dynamicgraph.config import REPO_ROOT

        resolved = REPO_ROOT / resolved
    if not resolved.exists():
        raise FileNotFoundError(f"Configured database path does not exist: {resolved}")

    backend = str(config.data.backend or "auto").lower()
    cache_path = (cache_dir / "datapro_symbol_map.json") if cache_dir else None

    if backend == "auto":
        if resolved.is_dir():
            backend = "file"
        elif resolved.suffix.lower() in {".parquet", ".pq", ".csv", ".feather", ".arrow", ".h5", ".hdf5"}:
            backend = "file"
        else:
            with resolved.open("rb") as handle:
                magic = handle.read(16)
            if magic == b"SQLite format 3\x00":
                info = inspect_sqlite_schema(resolved)
                backend = info.get("backend", "generic_sqlite")
            elif b"DUCK" in magic:
                backend = "duckdb"
            else:
                raise ValueError(
                    f"Cannot determine the backend for {resolved}. Set `data.backend` explicitly."
                )
        logger.info("Auto-detected backend: %s", backend)

    if backend == "datapro_sqlite":
        return DataProSQLiteConnector(resolved, config, cache_path=cache_path)
    if backend in {"generic_sqlite", "sqlite"}:
        return GenericSQLConnector(
            resolved, config, table=config.data.table, column_map=dict(config.data.column_map or {})
        )
    if backend == "duckdb":
        return GenericSQLConnector(
            resolved, config, table=config.data.table,
            column_map=dict(config.data.column_map or {}), duckdb_mode=True,
        )
    if backend in {"file", "parquet", "csv", "feather"}:
        return FileConnector(resolved, config, column_map=dict(config.data.column_map or {}))
    raise NotImplementedError(f"Unknown backend `{backend}`.")
