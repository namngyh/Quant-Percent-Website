"""Normalisation of a raw panel onto the DynamicGraph data contract.

Responsibilities:
  * rename the index symbol to the canonical `VN30`;
  * apply the adjusted-price policy (never silently substitute `close`);
  * apply the optional sector override file;
  * deduplicate, sort, clip the date range.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.constants import DATA_CONTRACT_COLUMNS, EXTENDED_COLUMNS, UNKNOWN_SECTOR
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class NormalizationReport:
    n_rows_in: int = 0
    n_rows_out: int = 0
    n_duplicates_dropped: int = 0
    index_ticker: str | None = None
    used_unadjusted_price: bool = False
    adjusted_price_available: bool = False
    sector_source: str = "none"
    n_sector_overrides: int = 0
    n_unknown_sector: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


def load_sector_overrides(path: Path | None) -> dict[str, str]:
    if path is None or not Path(path).exists():
        return {}
    frame = pd.read_csv(path, comment="#")
    frame.columns = [c.strip().lower() for c in frame.columns]
    if "ticker" not in frame.columns or "sector" not in frame.columns:
        logger.warning("Sector map %s ignored: needs `ticker` and `sector` columns.", path)
        return {}
    frame = frame.dropna(subset=["ticker", "sector"])
    return {
        str(t).strip().upper(): str(s).strip()
        for t, s in zip(frame["ticker"], frame["sector"])
    }


def normalize_panel(
    panel: pd.DataFrame,
    config: Any,
    index_source_symbol: str | None = None,
    sector_map_path: Path | None = None,
) -> tuple[pd.DataFrame, NormalizationReport]:
    """Bring a raw connector frame onto the contract. Returns (panel, report)."""
    report = NormalizationReport(n_rows_in=len(panel))
    frame = panel.copy()

    # ---- canonical index ticker --------------------------------------
    canonical_index = str(config.data.index_symbol or "VN30").upper()
    source = (index_source_symbol or config.data.index_source_symbol or "").upper()
    if source and source in set(frame["ticker"]):
        frame.loc[frame["ticker"] == source, "ticker"] = canonical_index
        frame.loc[frame["ticker"] == canonical_index, "is_index"] = True
        report.index_ticker = canonical_index
    elif canonical_index in set(frame["ticker"]):
        frame.loc[frame["ticker"] == canonical_index, "is_index"] = True
        report.index_ticker = canonical_index
    else:
        report.warnings.append(
            f"Index symbol `{source or canonical_index}` not found in the panel; "
            "market residualization and index targets will be unavailable."
        )

    # ---- duplicates ---------------------------------------------------
    before = len(frame)
    frame = frame.sort_values(["ticker", "date"], kind="stable")
    frame = frame.drop_duplicates(subset=["ticker", "date"], keep="last")
    report.n_duplicates_dropped = before - len(frame)
    if report.n_duplicates_dropped:
        report.warnings.append(
            f"Dropped {report.n_duplicates_dropped} duplicate (ticker, date) row(s), keeping the last."
        )

    # ---- adjusted price policy ---------------------------------------
    has_adjusted = "adjusted_close" in frame.columns and frame["adjusted_close"].notna().any()
    report.adjusted_price_available = bool(has_adjusted)

    if has_adjusted:
        # An adjusted series identical to the raw close is legitimate (no
        # corporate actions in the period, or an index series) but worth
        # flagging, since it is also what a mis-wired connector would produce.
        both = frame[["adjusted_close", "close"]].dropna()
        if len(both) and np.allclose(both["adjusted_close"], both["close"]):
            report.warnings.append(
                "`adjusted_close` is identical to `close` on every row. That is expected only if "
                "the period contains no dividends, splits or rights issues; otherwise the source "
                "is not actually adjusted and returns will contain corporate-action jumps."
            )
        # Fill isolated gaps in the adjusted series from close (rare vendor gaps).
        gaps = frame["adjusted_close"].isna() & frame["close"].notna()
        if gaps.any():
            report.warnings.append(
                f"{int(gaps.sum())} row(s) had no adjusted price; the raw close was used for "
                "those rows only."
            )
            frame.loc[gaps, "adjusted_close"] = frame.loc[gaps, "close"]
    else:
        if config.data.allow_unadjusted_price:
            frame["adjusted_close"] = frame["close"]
            report.used_unadjusted_price = True
            report.warnings.append(
                "NO ADJUSTED PRICE IN SOURCE. `data.allow_unadjusted_price` is true, so raw close "
                "is used as adjusted_close. Returns around dividends, splits and rights issues "
                "will contain artificial jumps; every downstream correlation, graph and stress "
                "statistic inherits that contamination."
            )
            logger.warning("Using UNADJUSTED close prices - results are contaminated by corporate actions.")
        else:
            raise ValueError(
                "The source has no adjusted price and `data.allow_unadjusted_price` is false. "
                "Set it to true to proceed with raw close (results will be contaminated by "
                "corporate actions), or point the pipeline at an adjusted source."
            )

    # ---- sectors ------------------------------------------------------
    if "sector" not in frame.columns:
        frame["sector"] = UNKNOWN_SECTOR
    frame["sector"] = frame["sector"].fillna(UNKNOWN_SECTOR).astype(str).replace("", UNKNOWN_SECTOR)
    if frame["sector"].ne(UNKNOWN_SECTOR).any():
        report.sector_source = "database_classification"

    overrides = load_sector_overrides(sector_map_path)
    if overrides:
        mask = frame["ticker"].isin(overrides)
        frame.loc[mask, "sector"] = frame.loc[mask, "ticker"].map(overrides)
        report.n_sector_overrides = int(frame.loc[mask, "ticker"].nunique())
        report.sector_source = (
            "override_file" if report.sector_source == "none" else "database+override"
        )

    unknown = frame.loc[frame["sector"] == UNKNOWN_SECTOR, "ticker"].nunique()
    report.n_unknown_sector = int(unknown)
    if unknown:
        report.warnings.append(
            f"{unknown} ticker(s) have sector = UNKNOWN. Sectors are never guessed from the "
            "company name; add them to config/sector_map.csv if you need sector features."
        )

    # ---- date range ---------------------------------------------------
    if config.data.start_date:
        frame = frame[frame["date"] >= pd.Timestamp(config.data.start_date)]
    if config.data.end_date:
        frame = frame[frame["date"] <= pd.Timestamp(config.data.end_date)]

    # ---- non-positive prices -----------------------------------------
    price_columns = [c for c in ("open", "high", "low", "close", "adjusted_close") if c in frame.columns]
    for column in price_columns:
        bad = frame[column] <= 0
        if bad.any():
            report.warnings.append(f"{int(bad.sum())} non-positive value(s) in `{column}` set to NaN.")
            frame.loc[bad, column] = np.nan

    if "volume" in frame.columns:
        negative = frame["volume"] < 0
        if negative.any():
            report.warnings.append(f"{int(negative.sum())} negative volume value(s) set to NaN.")
            frame.loc[negative, "volume"] = np.nan

    extras = [c for c in EXTENDED_COLUMNS + ["adjustment_factor", "is_filled"] if c in frame.columns]
    frame = frame[DATA_CONTRACT_COLUMNS + extras]
    frame = frame.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)

    report.n_rows_out = len(frame)
    for message in report.warnings:
        logger.warning("%s", message)
    return frame, report
