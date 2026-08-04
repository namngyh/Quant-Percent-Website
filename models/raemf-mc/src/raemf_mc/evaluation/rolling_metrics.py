"""Rolling diagnostic metrics."""

from __future__ import annotations

import pandas as pd


def rolling_accuracy(y_true: pd.Series, y_pred: pd.Series, window: int = 120) -> pd.Series:
    """Rolling accuracy."""
    return (y_true.astype(str) == y_pred.astype(str)).rolling(window, min_periods=max(20, window // 4)).mean()
