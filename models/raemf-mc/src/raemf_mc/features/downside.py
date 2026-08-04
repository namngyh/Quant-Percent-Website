"""CPU-efficient causal features dedicated to downside and Risk-off events."""

from __future__ import annotations

import numpy as np
import pandas as pd

from raemf_mc.features.registry import FeatureRegistry


def _minimum_periods(window: int) -> int:
    return max(5, window // 3)


def build_downside_features(
    prices: pd.DataFrame,
    *,
    hmm_probabilities: pd.DataFrame | None = None,
    egarch_features: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, FeatureRegistry]:
    """Build vectorized, close-of-day features using information through t only."""
    output = pd.DataFrame(index=prices.index)
    registry = FeatureRegistry()
    close = prices["close"].astype(float)
    log_close = np.log(close.clip(lower=1e-12))
    returns = log_close.diff()
    negative_return = (-returns).clip(lower=0)

    for window in (20, 60, 120, 252):
        minimum = _minimum_periods(window)
        rolling_high = close.rolling(window, min_periods=minimum).max()
        output[f"downside_drawdown_{window}"] = close / rolling_high - 1.0
        output[f"downside_distance_to_high_{window}"] = np.log(close / rolling_high)
        registry.add(f"downside_drawdown_{window}", "downside_price", window, "close")
        registry.add(f"downside_distance_to_high_{window}", "downside_price", window, "close")

    negative = returns.lt(0)
    run_id = negative.ne(negative.shift()).cumsum()
    negative_streak = negative.groupby(run_id).cumcount().add(1).where(negative, 0)
    output["downside_negative_return_streak"] = negative_streak.astype(float)
    registry.add("downside_negative_return_streak", "downside_momentum", 1, "close")

    for window in (5, 10, 20, 60):
        minimum = _minimum_periods(window)
        output[f"downside_negative_day_ratio_{window}"] = negative.rolling(window, min_periods=minimum).mean()
        output[f"downside_semivariance_{window}"] = (
            returns.where(returns < 0, 0.0).pow(2).rolling(window, min_periods=minimum).mean()
        )
        output[f"downside_lpm1_{window}"] = negative_return.rolling(window, min_periods=minimum).mean()
        output[f"downside_lpm2_{window}"] = negative_return.pow(2).rolling(window, min_periods=minimum).mean()
        output[f"downside_cumulative_negative_return_{window}"] = (
            returns.where(returns < 0, 0.0).rolling(window, min_periods=minimum).sum()
        )
        output[f"downside_log_price_slope_{window}"] = returns.rolling(window, min_periods=minimum).mean().clip(upper=0)
        registry.add(f"downside_negative_day_ratio_{window}", "downside_frequency", window, "close")
        registry.add(f"downside_semivariance_{window}", "downside_dispersion", window, "close")
        registry.add(f"downside_lpm1_{window}", "downside_partial_moment", window, "close")
        registry.add(f"downside_lpm2_{window}", "downside_partial_moment", window, "close")
        registry.add(f"downside_cumulative_negative_return_{window}", "downside_momentum", window, "close")
        registry.add(f"downside_log_price_slope_{window}", "downside_momentum", window, "close")

    for window in (20, 60):
        minimum = _minimum_periods(window)
        for quantile in (0.01, 0.05, 0.10):
            suffix = int(quantile * 100)
            name = f"downside_return_q{suffix:02d}_{window}"
            output[name] = returns.rolling(window, min_periods=minimum).quantile(quantile)
            registry.add(name, "downside_tail", window, "close")
        output[f"downside_return_skew_{window}"] = returns.rolling(window, min_periods=minimum).skew()
        output[f"downside_return_kurtosis_{window}"] = returns.rolling(window, min_periods=minimum).kurt()
        registry.add(f"downside_return_skew_{window}", "downside_tail", window, "close")
        registry.add(f"downside_return_kurtosis_{window}", "downside_tail", window, "close")

    output["downside_return_acceleration"] = (
        returns.rolling(5, min_periods=3).mean() - returns.rolling(20, min_periods=7).mean()
    )
    registry.add("downside_return_acceleration", "downside_momentum", 20, "close")

    if "open" in prices:
        gap = np.log(prices["open"].astype(float).clip(lower=1e-12) / close.shift(1).clip(lower=1e-12))
        output["downside_negative_gap"] = gap.clip(upper=0)
        output["downside_negative_gap_magnitude"] = (-gap).clip(lower=0)
        registry.add("downside_negative_gap", "downside_gap", 1, "open,close", requires_ohlc=True)
        registry.add("downside_negative_gap_magnitude", "downside_gap", 1, "open,close", requires_ohlc=True)

    if "volume" in prices and not prices["volume"].isna().all():
        volume = prices["volume"].astype(float).clip(lower=0)
        negative_volume = volume.where(negative, 0.0)
        for window in (20, 60):
            minimum = _minimum_periods(window)
            volume_sum = volume.rolling(window, min_periods=minimum).sum()
            name = f"downside_negative_volume_ratio_{window}"
            output[name] = negative_volume.rolling(window, min_periods=minimum).sum() / volume_sum.replace(0, np.nan)
            registry.add(name, "downside_volume", window, "close,volume", requires_volume=True)
        mean_volume = volume.rolling(20, min_periods=7).mean()
        std_volume = volume.rolling(20, min_periods=7).std()
        output["downside_negative_volume_shock"] = (
            ((volume - mean_volume) / std_volume.replace(0, np.nan)).where(negative, 0.0)
        )
        registry.add("downside_negative_volume_shock", "downside_volume", 20, "close,volume", requires_volume=True)

    if egarch_features is not None and "egarch_sigma" in egarch_features:
        sigma = egarch_features["egarch_sigma"].astype(float).reindex(output.index)
        output["downside_sigma_change"] = sigma.diff()
        output["downside_sigma_pct_change"] = sigma.pct_change(fill_method=None)
        sigma_mean = sigma.rolling(60, min_periods=20).mean()
        sigma_std = sigma.rolling(60, min_periods=20).std()
        output["downside_sigma_zscore"] = (sigma - sigma_mean) / sigma_std.replace(0, np.nan)
        registry.add("downside_sigma_change", "downside_conditional_volatility", 2, "egarch_sigma")
        registry.add("downside_sigma_pct_change", "downside_conditional_volatility", 2, "egarch_sigma")
        registry.add("downside_sigma_zscore", "downside_conditional_volatility", 60, "egarch_sigma")

    if hmm_probabilities is not None:
        probabilities = hmm_probabilities.reindex(output.index)
        contraction = probabilities.get("hmm_prob_state_2", pd.Series(0.0, index=output.index)).astype(float)
        turbulence = probabilities.get("hmm_prob_state_3", pd.Series(0.0, index=output.index)).astype(float)
        risk_probability = contraction + turbulence
        output["downside_hmm_risk_probability"] = risk_probability
        probability_columns = [column for column in probabilities if column.startswith("hmm_prob_state_")]
        if probability_columns:
            matrix = probabilities[probability_columns].clip(lower=1e-12)
            output["downside_hmm_entropy"] = -(matrix * np.log(matrix)).sum(axis=1)
        else:
            output["downside_hmm_entropy"] = np.nan
        output["downside_hmm_turbulence_change"] = turbulence.diff()
        output["downside_hmm_transition_pressure"] = risk_probability - risk_probability.ewm(
            span=10,
            adjust=False,
            min_periods=3,
        ).mean()
        registry.add("downside_hmm_risk_probability", "downside_hmm", 1, "filtered_hmm")
        registry.add("downside_hmm_entropy", "downside_hmm", 1, "filtered_hmm")
        registry.add("downside_hmm_turbulence_change", "downside_hmm", 2, "filtered_hmm")
        registry.add("downside_hmm_transition_pressure", "downside_hmm", 10, "filtered_hmm")

    return output.replace([np.inf, -np.inf], np.nan), registry
