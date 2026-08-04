"""Market-level (index) features - the "Feature set A" baseline.

These deliberately contain no network information, so that any incremental
out-of-sample value from graph features can be attributed to the graph.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS
from dynamicgraph.features import returns as R
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def build_market_features(
    panel: pd.DataFrame,
    config: Any,
    index_ticker: str = "VN30",
    stock_returns: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Date-indexed frame of VN30-level features."""
    index_rows = panel[panel["ticker"] == index_ticker].sort_values("date")
    if index_rows.empty:
        raise ValueError(f"Index `{index_ticker}` not present in the panel.")

    price = index_rows.set_index("date")["adjusted_close"].astype(float)
    frame = pd.DataFrame(index=price.index)
    returns = np.log(price / price.shift(1))
    frame["market_return_1d"] = returns

    for window in (5, 10, 20, 60, 120):
        frame[f"market_return_{window}d"] = np.log(price / price.shift(window))
    for window in (5, 20, 60):
        frame[f"market_volatility_{window}d"] = (
            returns.rolling(window, min_periods=max(3, window // 2)).std(ddof=1) * np.sqrt(252)
        )
    frame["market_ewma_volatility"] = (
        np.sqrt(returns.pow(2).ewm(alpha=0.06, adjust=False, min_periods=5).mean()) * np.sqrt(252)
    )
    frame["market_volatility_ratio_5_20"] = frame["market_volatility_5d"] / (
        frame["market_volatility_20d"] + EPS
    )
    frame["market_volatility_ratio_20_60"] = frame["market_volatility_20d"] / (
        frame["market_volatility_60d"] + EPS
    )
    frame["market_downside_volatility_20d"] = (
        np.sqrt(returns.clip(upper=0).pow(2).rolling(20, min_periods=10).mean()) * np.sqrt(252)
    )

    frame["market_drawdown"] = price / price.cummax() - 1.0
    for window in (20, 60, 252):
        frame[f"market_max_drawdown_{window}d"] = (
            R.rolling_max_drawdown(price.to_frame("m"), window)["m"]
        )
    frame["market_days_since_peak"] = R.days_since_peak(price.to_frame("m"))["m"]
    frame["market_recovery_ratio_60d"] = R.recovery_ratio(price.to_frame("m"), 60)["m"]

    frame["market_skewness_60d"] = returns.rolling(60, min_periods=30).skew()
    frame["market_excess_kurtosis_60d"] = returns.rolling(60, min_periods=30).kurt()
    frame["market_var_60d"] = -returns.rolling(60, min_periods=30).quantile(0.05)
    frame["market_rsi_14"] = _rsi(price, 14)
    frame["market_price_to_ma50"] = price / price.rolling(50, min_periods=25).mean() - 1.0
    frame["market_price_to_ma200"] = price / price.rolling(200, min_periods=100).mean() - 1.0
    frame["market_ma50_to_ma200"] = (
        price.rolling(50, min_periods=25).mean() / price.rolling(200, min_periods=100).mean() - 1.0
    )

    # Volume / turnover of the index, when the source carries it.
    for column, prefix in (("volume", "market_volume"), ("turnover", "market_turnover")):
        if column in index_rows.columns and index_rows[column].notna().any():
            series = index_rows.set_index("date")[column].astype(float)
            log_series = np.log1p(series.clip(lower=0))
            frame[f"{prefix}_log"] = log_series
            frame[f"{prefix}_zscore_20d"] = (
                log_series - log_series.rolling(20, min_periods=10).mean()
            ) / (log_series.rolling(20, min_periods=10).std(ddof=1) + EPS)

    # Cross-sectional aggregates of the constituents - still "market only":
    # they are pooled stock statistics, with no pairwise dependence structure.
    if stock_returns is not None and not stock_returns.empty:
        aligned = stock_returns.reindex(frame.index)
        frame["breadth_advance_ratio"] = (aligned > 0).sum(axis=1) / aligned.notna().sum(axis=1).replace(0, np.nan)
        frame["cross_sectional_dispersion"] = aligned.std(axis=1, ddof=1)
        frame["cross_sectional_dispersion_20d"] = (
            frame["cross_sectional_dispersion"].rolling(20, min_periods=10).mean()
        )
        stock_vol = aligned.rolling(20, min_periods=10).std(ddof=1) * np.sqrt(252)
        frame["mean_constituent_volatility_20d"] = stock_vol.mean(axis=1)
        frame["median_constituent_volatility_20d"] = stock_vol.median(axis=1)
        frame["mean_constituent_beta_proxy"] = (
            aligned.rolling(60, min_periods=30).cov(frame["market_return_1d"]).mean(axis=1)
            / (frame["market_return_1d"].rolling(60, min_periods=30).var(ddof=1) + EPS)
        )

    frame = frame.replace([np.inf, -np.inf], np.nan)
    logger.info("Built %d market features.", frame.shape[1])
    return frame


def _rsi(price: pd.Series, window: int = 14) -> pd.Series:
    delta = price.diff()
    gain = delta.clip(lower=0).rolling(window, min_periods=window // 2).mean()
    loss = (-delta.clip(upper=0)).rolling(window, min_periods=window // 2).mean()
    rs = gain / (loss + EPS)
    return 100.0 - 100.0 / (1.0 + rs)
