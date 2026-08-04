"""Causal risk filters."""

from __future__ import annotations

import pandas as pd


def ewma_volatility(returns: pd.Series, span: int = 40) -> pd.Series:
    """Causal EWMA volatility."""
    return returns.ewm(span=span, adjust=False, min_periods=max(5, span // 4)).std()
