"""Multi-horizon regime targets."""

from __future__ import annotations

import numpy as np
import pandas as pd

from raemf_mc import CLASS_ORDER, HORIZONS


def causal_target_volatility(close: pd.Series, window: int = 40, floor: float = 1e-4) -> pd.Series:
    """Estimate target scaling volatility from information available at time t."""
    ret = np.log(close / close.shift(1))
    ewma = ret.ewm(span=window, adjust=False, min_periods=max(5, window // 4)).std()
    rolling = ret.rolling(window=window, min_periods=max(5, window // 4)).std()
    sigma = ewma.fillna(rolling).fillna(ret.expanding(min_periods=5).std())
    return sigma.clip(lower=floor).fillna(floor)


def create_multihorizon_targets(
    df: pd.DataFrame,
    horizons: list[int] | None = None,
    bull_threshold: float = 0.5,
    bear_threshold: float = 0.5,
    stress_threshold: float = 1.5,
    volatility_window: int = 40,
) -> pd.DataFrame:
    """Create forward returns, path MAE, target end dates, and labels."""
    horizons = horizons or HORIZONS
    out = df.copy()
    close = out["close"].astype(float)
    sigma = causal_target_volatility(close, volatility_window)
    out["target_sigma"] = sigma
    for h in horizons:
        fwd = np.log(close.shift(-h) / close)
        path = pd.concat([np.log(close.shift(-k) / close) for k in range(1, h + 1)], axis=1)
        mae = path.min(axis=1)
        denom = sigma * np.sqrt(h) + 1e-9
        z = fwd / denom
        labels = np.full(len(out), "Sideway", dtype=object)
        labels[z > bull_threshold] = "Bull"
        labels[z < -bear_threshold] = "Bear"
        labels[mae < (-stress_threshold * denom)] = "Stress"
        labels[fwd.isna()] = None
        out[f"forward_return_{h}"] = fwd
        out[f"future_mae_{h}"] = mae
        out[f"target_{h}"] = pd.Categorical(labels, categories=CLASS_ORDER)
        out[f"target_end_date_{h}"] = out["date"].shift(-h)
    return out


def target_columns(horizons: list[int] | None = None) -> list[str]:
    """Columns that must never be model features."""
    from raemf_mc.targets.downside_targets import downside_target_columns

    horizons = horizons or HORIZONS
    cols = ["target_sigma"]
    for h in horizons:
        cols += [f"forward_return_{h}", f"future_mae_{h}", f"target_{h}", f"target_end_date_{h}"]
    return cols + downside_target_columns(horizons)
