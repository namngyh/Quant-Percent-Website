"""Cross-sectional transformations applied per date.

Because these operate strictly *within* a date, they use no information from
other dates and therefore introduce no look-ahead, regardless of the train/test
split. That is why they can be applied before splitting; model-level scaling is
still fitted on training folds only (see `training.walk_forward`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS


def cross_sectional_rank(frame: pd.DataFrame) -> pd.DataFrame:
    """Dense rank within each date, 1 = smallest."""
    return frame.rank(axis=1, method="average", na_option="keep")


def cross_sectional_percentile(frame: pd.DataFrame) -> pd.DataFrame:
    """Rank scaled to [0, 1] within each date."""
    return frame.rank(axis=1, method="average", pct=True, na_option="keep")


def cross_sectional_robust_z(frame: pd.DataFrame, clip: float | None = 5.0) -> pd.DataFrame:
    r"""z_{i,t} = (x_{i,t} - median_t) / (1.4826 * MAD_t + eps), per date."""
    median = frame.median(axis=1)
    centered = frame.sub(median, axis=0)
    mad = centered.abs().median(axis=1)
    z = centered.div(1.4826 * mad + EPS, axis=0)
    return z.clip(-clip, clip) if clip is not None else z


def cross_sectional_zscore(frame: pd.DataFrame, clip: float | None = 5.0) -> pd.DataFrame:
    """Classic per-date z-score; kept for comparison with the robust version."""
    mean = frame.mean(axis=1)
    std = frame.std(axis=1, ddof=1)
    z = frame.sub(mean, axis=0).div(std + EPS, axis=0)
    return z.clip(-clip, clip) if clip is not None else z


def sector_relative_rank(frame: pd.DataFrame, sector_of: dict[str, str]) -> pd.DataFrame:
    """Percentile rank inside the ticker's own sector, per date."""
    out = pd.DataFrame(np.nan, index=frame.index, columns=frame.columns)
    sectors: dict[str, list[str]] = {}
    for ticker in frame.columns:
        sectors.setdefault(sector_of.get(ticker, "UNKNOWN"), []).append(ticker)
    for members in sectors.values():
        if len(members) < 2:
            out[members] = 0.5
            continue
        out[members] = frame[members].rank(axis=1, method="average", pct=True, na_option="keep")
    return out


def sector_demean(frame: pd.DataFrame, sector_of: dict[str, str]) -> pd.DataFrame:
    """Value minus its sector's cross-sectional median, per date."""
    out = frame.copy()
    sectors: dict[str, list[str]] = {}
    for ticker in frame.columns:
        sectors.setdefault(sector_of.get(ticker, "UNKNOWN"), []).append(ticker)
    for members in sectors.values():
        block = frame[members]
        out[members] = block.sub(block.median(axis=1), axis=0)
    return out


def winsorize_cross_section(frame: pd.DataFrame, lower: float = 0.01, upper: float = 0.99) -> pd.DataFrame:
    """Clip each date's cross-section to its own quantiles."""
    low = frame.quantile(lower, axis=1)
    high = frame.quantile(upper, axis=1)
    return frame.clip(lower=low, upper=high, axis=0)


def sector_one_hot(tickers: list[str], sector_of: dict[str, str]) -> pd.DataFrame:
    """ticker x sector indicator matrix (static, no dates involved)."""
    sectors = sorted({sector_of.get(t, "UNKNOWN") for t in tickers})
    frame = pd.DataFrame(0.0, index=tickers, columns=[f"sector_{s}" for s in sectors])
    for ticker in tickers:
        frame.loc[ticker, f"sector_{sector_of.get(ticker, 'UNKNOWN')}"] = 1.0
    return frame
