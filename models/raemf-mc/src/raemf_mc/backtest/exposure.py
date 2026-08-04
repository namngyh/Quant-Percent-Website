"""Exposure mapping and backtest."""

from __future__ import annotations

import numpy as np
import pandas as pd


EXPOSURE_MAP = {"Risk-on": 1.0, "Neutral": 0.5, "Risk-off": 0.0, "Uncertain": 0.25}


def labels_to_exposure(labels: pd.Series) -> pd.Series:
    return labels.map(EXPOSURE_MAP).astype(float)


def backtest_exposure(close: pd.Series, exposure: pd.Series, cost_bps: float = 10) -> pd.DataFrame:
    """Apply a close-of-day signal to the following session's return."""
    ret = np.log(close / close.shift(1)).fillna(0.0)
    signal = exposure.reindex(close.index).fillna(0.0).clip(0.0, 1.0)
    position = signal.shift(1).fillna(0.0)
    turnover = position.diff().abs().fillna(position.abs())
    transaction_cost = turnover * (cost_bps / 10000.0)
    strategy = position * ret - transaction_cost
    return pd.DataFrame(
        {
            "return": ret,
            "signal": signal,
            "exposure": position,
            "turnover": turnover,
            "transaction_cost": transaction_cost,
            "strategy_return": strategy,
        }
    )
