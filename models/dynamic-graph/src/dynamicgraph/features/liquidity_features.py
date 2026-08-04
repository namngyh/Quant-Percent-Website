r"""Liquidity features.

`turnover` (value traded) is used when the source provides it. When only volume
and price exist, value traded is approximated by `close * volume`; that
approximation is recorded as an assumption because it ignores intraday price
paths and any block/put-through convention differences.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def value_traded(
    close: pd.DataFrame, volume: pd.DataFrame | None, turnover: pd.DataFrame | None
) -> tuple[pd.DataFrame, bool]:
    """Return (value traded, is_approximation)."""
    if turnover is not None and turnover.notna().any().any():
        return turnover, False
    if volume is None:
        raise ValueError("Neither turnover nor volume is available; cannot build liquidity features.")
    logger.warning(
        "No turnover column in the source; approximating value traded as close * volume. "
        "Amihud illiquidity and turnover z-scores inherit this approximation."
    )
    return close * volume, True


def log_volume(volume: pd.DataFrame) -> pd.DataFrame:
    return np.log1p(volume.clip(lower=0.0))


def volume_change(volume: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    previous = volume.shift(periods)
    return (volume - previous) / (previous.abs() + EPS)


def rolling_zscore(frame: pd.DataFrame, window: int = 20, min_periods: int | None = None) -> pd.DataFrame:
    """Time-series z-score against the ticker's own trailing distribution."""
    min_periods = min_periods or max(5, window // 2)
    mean = frame.rolling(window, min_periods=min_periods).mean()
    std = frame.rolling(window, min_periods=min_periods).std(ddof=1)
    return (frame - mean) / (std + EPS)


def amihud_illiquidity(
    returns: pd.DataFrame, traded_value: pd.DataFrame, window: int = 20
) -> pd.DataFrame:
    r"""ILLIQ^{(k)}_{i,t} = (1/k) * sum_{u=t-k+1}^{t} |r_{i,u}| / ValueTraded_{i,u}.

    Scaled by 1e6 to keep the numbers in a readable range; the scale is a
    monotone transform and does not change any ranking.
    """
    denominator = traded_value.where(traded_value > 0)
    ratio = returns.abs() / denominator
    illiq = ratio.rolling(window, min_periods=max(3, window // 2)).mean()
    return illiq * 1e6


def liquidity_shock(traded_value: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Deviation of today's log value traded from its trailing mean, in sigmas."""
    log_value = np.log1p(traded_value.clip(lower=0.0))
    return rolling_zscore(log_value, window=window)


def turnover_ratio(traded_value: pd.DataFrame, market_cap: pd.DataFrame | None) -> pd.DataFrame:
    """Value traded relative to market cap; NaN when cap is unavailable."""
    if market_cap is None:
        return pd.DataFrame(np.nan, index=traded_value.index, columns=traded_value.columns)
    return traded_value / (market_cap.where(market_cap > 0))


def volume_volatility_interaction(
    volume_z: pd.DataFrame, volatility: pd.DataFrame
) -> pd.DataFrame:
    """Interaction term: unusual volume during unusual volatility."""
    return volume_z * volatility


def build_liquidity_features(
    close: pd.DataFrame,
    returns: pd.DataFrame,
    volume: pd.DataFrame | None,
    turnover: pd.DataFrame | None,
    market_cap: pd.DataFrame | None = None,
    volatility_20d: pd.DataFrame | None = None,
    window: int = 20,
) -> tuple[dict[str, pd.DataFrame], bool]:
    """Return (feature name -> date x ticker frame, value_traded_is_approximate)."""
    traded_value, approximated = value_traded(close, volume, turnover)
    features: dict[str, pd.DataFrame] = {}

    if volume is not None:
        features["log_volume"] = log_volume(volume)
        features["volume_change_1d"] = volume_change(volume, 1)
        features["volume_zscore_20d"] = rolling_zscore(np.log1p(volume.clip(lower=0.0)), window)

    features["log_turnover"] = np.log1p(traded_value.clip(lower=0.0))
    features["turnover_zscore_20d"] = rolling_zscore(features["log_turnover"], window)
    features["amihud_illiquidity"] = amihud_illiquidity(returns, traded_value, window)
    features["liquidity_shock"] = liquidity_shock(traded_value, window)

    if market_cap is not None:
        features["turnover_ratio"] = turnover_ratio(traded_value, market_cap)

    if volatility_20d is not None and "volume_zscore_20d" in features:
        features["volume_volatility_interaction"] = volume_volatility_interaction(
            features["volume_zscore_20d"], volatility_20d
        )
    return features, approximated
