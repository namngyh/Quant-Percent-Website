"""Schema inference for unknown databases.

Nothing about table or column naming is assumed. The module inspects the real
schema, scores each table on how much it looks like a price panel, and maps the
physical columns onto the DynamicGraph data contract.

It also recognises the DataPro vendor layout (`HIST` + `QUOTES_INFO`), which
stores an opaque numeric `EID` instead of a ticker; see `connectors.py` for how
that link is reconstructed.
"""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
from pathlib import Path
from typing import Any

from dynamicgraph.constants import COLUMN_SYNONYMS
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

_NON_ALNUM = re.compile(r"[^a-z0-9]")

#: A handful of large, long-lived VN30 names used purely as a "does this table
#: look like the Vietnamese equity market?" probe. Not a universe definition.
VN_PROBE_TICKERS = {
    "VCB", "FPT", "HPG", "VNM", "MSN", "MWG", "SSI", "STB", "CTG", "BID",
    "MBB", "TCB", "VPB", "ACB", "GAS", "VIC", "VHM", "SAB", "PLX", "VJC",
}

INDEX_SYMBOL_CANDIDATES = ("VN30", "VN30INDEX", "VN30-INDEX", "VNINDEX", "VN-INDEX", "VNI")


def _canon(name: str) -> str:
    return _NON_ALNUM.sub("", str(name).lower())


def infer_columns_from_names(columns: list[str]) -> dict[str, str]:
    """Map canonical contract fields -> physical column names, by name only.

    Exact synonym matches win; substring matches are the fallback. Each physical
    column is assigned at most once, and `adjusted_close` is resolved before
    `close` so that an `adj_close` column is not stolen by `close`.
    """
    canon_to_original = {_canon(c): c for c in columns}
    mapping: dict[str, str] = {}
    used: set[str] = set()

    order = [
        "date", "ticker", "adjusted_close", "close", "open", "high", "low",
        "volume", "turnover", "market_cap", "sector", "shares_outstanding",
    ]

    for field in order:
        synonyms = COLUMN_SYNONYMS.get(field, [])
        for synonym in synonyms:
            key = _canon(synonym)
            if key in canon_to_original and canon_to_original[key] not in used:
                mapping[field] = canon_to_original[key]
                used.add(canon_to_original[key])
                break

    for field in order:
        if field in mapping:
            continue
        synonyms = [_canon(s) for s in COLUMN_SYNONYMS.get(field, [])]
        for canon_name, original in canon_to_original.items():
            if original in used:
                continue
            if any(syn and syn in canon_name for syn in synonyms):
                mapping[field] = original
                used.add(original)
                break
    return mapping


def _looks_like_date(values: list[Any]) -> str | None:
    """Classify a column's date encoding: iso | epoch_days | epoch_seconds |
    yyyymmdd | excel_serial | None."""
    clean = [v for v in values if v is not None][:200]
    if not clean:
        return None

    if all(isinstance(v, str) for v in clean):
        sample = clean[0]
        if re.match(r"^\d{4}-\d{2}-\d{2}", sample) or re.match(r"^\d{2}/\d{2}/\d{4}", sample):
            return "iso"
        if re.match(r"^\d{8}$", sample):
            return "yyyymmdd"
        return None

    numeric = [float(v) for v in clean if isinstance(v, (int, float))]
    if len(numeric) < max(1, len(clean) // 2):
        return None
    lo, hi = min(numeric), max(numeric)
    if 19000000 <= lo <= 21001231 and 19000000 <= hi <= 21001231:
        return "yyyymmdd"
    if 0 <= lo <= 40000 and 1000 <= hi <= 40000:
        return "epoch_days"
    if 1e8 <= lo <= 4e9:
        return "epoch_seconds"
    if 1e11 <= lo <= 4e12:
        return "epoch_millis"
    if 20000 <= lo <= 60000 and hi <= 60000:
        return "excel_serial"
    return None


def decode_dates(values: Any, encoding: str) -> Any:
    """Vectorised decoding of a date column into pandas datetime64."""
    import pandas as pd

    series = pd.Series(values)
    if encoding == "iso":
        return pd.to_datetime(series, errors="coerce")
    if encoding == "yyyymmdd":
        return pd.to_datetime(series.astype("Int64").astype(str), format="%Y%m%d", errors="coerce")
    if encoding == "epoch_days":
        return pd.to_datetime(series.astype("float64"), unit="D", origin="unix", errors="coerce")
    if encoding == "epoch_seconds":
        return pd.to_datetime(series.astype("float64"), unit="s", errors="coerce")
    if encoding == "epoch_millis":
        return pd.to_datetime(series.astype("float64"), unit="ms", errors="coerce")
    if encoding == "excel_serial":
        return pd.to_datetime(series.astype("float64"), unit="D", origin="1899-12-30", errors="coerce")
    return pd.to_datetime(series, errors="coerce")


def _table_score(mapping: dict[str, str], n_rows: int) -> float:
    """How much does this table look like a price panel?"""
    score = 0.0
    if "date" in mapping:
        score += 30
    if "ticker" in mapping:
        score += 30
    if "close" in mapping:
        score += 25
    score += 5 * sum(1 for f in ("open", "high", "low", "volume", "turnover") if f in mapping)
    if "adjusted_close" in mapping:
        score += 10
    score += min(n_rows, 5_000_000) / 5_000_000 * 20
    return score


def inspect_sqlite_schema(path: Path, sample_rows: int = 500) -> dict[str, Any]:
    """Read a SQLite file read-only and describe every table."""
    uri = f"file:{Path(path).as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    info: dict[str, Any] = {
        "path": str(path),
        "backend": "generic_sqlite",
        "tables": {},
        "notes": [],
        "total_rows": 0,
    }
    try:
        table_names = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]

        for table in table_names:
            entry: dict[str, Any] = {}
            try:
                cols = con.execute(f'PRAGMA table_info("{table}")').fetchall()
                entry["columns"] = [
                    {"name": c["name"], "type": c["type"] or "UNKNOWN"} for c in cols
                ]
                n_rows = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                entry["n_rows"] = int(n_rows)
                info["total_rows"] += int(n_rows)

                column_names = [c["name"] for c in cols]
                mapping = infer_columns_from_names(column_names)
                entry["column_map"] = mapping
                entry["panel_score"] = _table_score(mapping, int(n_rows))

                sample = con.execute(f'SELECT * FROM "{table}" LIMIT {sample_rows}').fetchall()
                entry["sample_available"] = bool(sample)

                if "date" in mapping and sample:
                    values = [row[mapping["date"]] for row in sample]
                    encoding = _looks_like_date(values)
                    entry["date_encoding"] = encoding
                    if encoding:
                        try:
                            lo, hi = con.execute(
                                f'SELECT MIN("{mapping["date"]}"), MAX("{mapping["date"]}") FROM "{table}"'
                            ).fetchone()
                            decoded = decode_dates([lo, hi], encoding)
                            entry["date_min"] = str(decoded.iloc[0].date()) if decoded.notna().iloc[0] else None
                            entry["date_max"] = str(decoded.iloc[1].date()) if decoded.notna().iloc[1] else None
                        except Exception:
                            pass

                if "ticker" in mapping:
                    try:
                        n_tickers = con.execute(
                            f'SELECT COUNT(DISTINCT "{mapping["ticker"]}") FROM "{table}"'
                        ).fetchone()[0]
                        entry["n_tickers"] = int(n_tickers)
                        symbols = {
                            str(r[0]).upper()
                            for r in con.execute(
                                f'SELECT DISTINCT "{mapping["ticker"]}" FROM "{table}" LIMIT 5000'
                            )
                        }
                        entry["matched_universe_tickers"] = len(symbols & VN_PROBE_TICKERS)
                        entry["contains_index_symbol"] = any(
                            c in symbols for c in INDEX_SYMBOL_CANDIDATES
                        )
                        entry["index_symbol_found"] = next(
                            (c for c in INDEX_SYMBOL_CANDIDATES if c in symbols), None
                        )
                    except Exception:
                        pass
            except Exception as exc:
                entry["error"] = str(exc)
            info["tables"][table] = entry

        # ---- vendor layout recognition -------------------------------
        upper = {t.upper() for t in table_names}
        if {"HIST", "QUOTES_INFO"}.issubset(upper):
            info["backend"] = "datapro_sqlite"
            info["notes"].append(
                "DataPro layout detected (HIST + QUOTES_INFO). HIST.EID is an opaque "
                "vendor id; DynamicGraph reconstructs the symbol link by fingerprinting "
                "the latest session's OHLCV against the QUOTES_INFO snapshot."
            )
            quotes = info["tables"].get("QUOTES_INFO", {})
            hist = info["tables"].get("HIST", {})
            hist_cols = {c["name"].upper() for c in hist.get("columns", [])}
            info["n_tickers"] = quotes.get("n_rows")
            info["has_adjusted_price"] = "ADJUST_RATE" in hist_cols
            info["has_volume"] = "VOL" in hist_cols
            info["has_turnover"] = "VAL" in hist_cols
            info["has_sector"] = any(
                c["name"].upper() == "ICB_ID" for c in quotes.get("columns", [])
            )
            info["contains_index_symbol"] = True
            info["matched_universe_tickers"] = len(VN_PROBE_TICKERS)
            try:
                epoch = dt.date(1970, 1, 1)
                lo, hi = con.execute("SELECT MIN(TRADING_KEY), MAX(TRADING_KEY) FROM HIST").fetchone()
                info["date_min"] = str(epoch + dt.timedelta(days=int(lo)))
                info["date_max"] = str(epoch + dt.timedelta(days=int(hi)))

                # The store mixes Vietnamese listings with global reference
                # series (SPX, gold, USDX, ...) whose history reaches back much
                # further. Report the Vietnamese range separately, since that is
                # what bounds a VN30 study.
                vn_lo = con.execute(
                    "SELECT MIN(h.TRADING_KEY) FROM HIST h "
                    "WHERE h.EID IN (SELECT DISTINCT EID FROM HIST WHERE TRADING_KEY >= ?)",
                    ((dt.date(2000, 1, 1) - epoch).days,),
                ).fetchone()[0]
                n_early = con.execute(
                    "SELECT COUNT(DISTINCT EID) FROM HIST WHERE TRADING_KEY < ?",
                    ((dt.date(1990, 1, 1) - epoch).days,),
                ).fetchone()[0]
                if n_early:
                    info["notes"].append(
                        f"{n_early} instrument(s) carry history before 1990. These are global "
                        "reference series (equity indices, metals, FX) rather than Vietnamese "
                        "listings; the VN30 universe is far shorter."
                    )
                info["date_min_vn_listings"] = str(epoch + dt.timedelta(days=int(vn_lo or lo)))
            except Exception:
                pass
            info["primary_table"] = "HIST"
        else:
            best = max(
                info["tables"].items(),
                key=lambda kv: kv[1].get("panel_score", 0.0),
                default=(None, {}),
            )
            if best[0] is not None and best[1].get("panel_score", 0) > 50:
                info["primary_table"] = best[0]
                entry = best[1]
                mapping = entry.get("column_map", {})
                info["n_tickers"] = entry.get("n_tickers")
                info["date_min"] = entry.get("date_min")
                info["date_max"] = entry.get("date_max")
                info["has_adjusted_price"] = "adjusted_close" in mapping
                info["has_volume"] = "volume" in mapping
                info["has_turnover"] = "turnover" in mapping
                info["has_sector"] = "sector" in mapping
                info["contains_index_symbol"] = bool(entry.get("contains_index_symbol"))
                info["matched_universe_tickers"] = int(entry.get("matched_universe_tickers", 0))
    finally:
        con.close()
    return info
