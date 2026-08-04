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
            for eid, o, h, l, c, v in self.con.execute(
                "SELECT EID, OPEN_PX, HIGH_PX, LOW_PX, CLOSE_PX, VOL FROM HIST WHERE TRADING_KEY = ?",
                (key,),
            ):
                hist.setdefault((o, h, l, c, v), []).append(int(eid))
            quote_index: dict[tuple, list[str]] = {}
            for sym, o, h, l, c, v in quotes:
                quote_index.setdefault((o, h, l, c, v), []).append(str(sym))
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
                f"Backend `{scheme}` is not implemented. Supported: sqlite, duckdb, parquet, csv, feather."
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
