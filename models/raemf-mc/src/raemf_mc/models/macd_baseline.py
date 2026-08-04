"""MACD probabilistic rule baseline."""

from __future__ import annotations

import numpy as np
import pandas as pd

from raemf_mc import CLASS_ORDER


def macd_deterministic(close: pd.Series, volatility: pd.Series) -> pd.Series:
    """Transparent MACD state rule used as the signal source for the probabilistic mapping.

    This rule is not reported as a standalone benchmark; it only feeds
    `fit_macd_probability_table`/`apply_macd_probability_table`.
    """
    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    hist = macd - signal
    hist_z = hist / (hist.rolling(60, min_periods=20).std() + 1e-12)
    vol_z = volatility / (volatility.rolling(252, min_periods=40).median() + 1e-12)
    pred = np.full(len(close), "Sideway", dtype=object)
    pred[(hist_z > 0.35) & (macd > signal)] = "Bull"
    pred[(hist_z < -0.35)] = "Bear"
    pred[(hist_z < -0.80) & (vol_z > 1.15)] = "Stress"
    return pd.Series(pred, index=close.index, name="macd_signal")


def fit_macd_probability_table(signals: pd.Series, y_validation: pd.Series, alpha: float = 1.0) -> pd.DataFrame:
    """Estimate P(target class | MACD signal) on validation with Laplace smoothing."""
    table = pd.DataFrame(alpha, index=CLASS_ORDER, columns=CLASS_ORDER, dtype=float)
    for signal, actual in zip(signals.astype(str), y_validation.astype(str), strict=False):
        if signal in CLASS_ORDER and actual in CLASS_ORDER:
            table.loc[signal, actual] += 1.0
    return table.div(table.sum(axis=1), axis=0)


def apply_macd_probability_table(signals: pd.Series, table: pd.DataFrame) -> pd.DataFrame:
    """Convert deterministic signals using a validation-fitted probability table."""
    probabilities = np.vstack(
        [table.loc[signal].to_numpy(dtype=float) if signal in table.index else np.full(4, 0.25) for signal in signals.astype(str)]
    )
    return pd.DataFrame(probabilities, index=signals.index, columns=[f"prob_{c}" for c in CLASS_ORDER])


def macd_probabilities(
    close: pd.Series,
    volatility: pd.Series,
    validation_idx: np.ndarray | None = None,
    y_validation: pd.Series | None = None,
) -> pd.DataFrame:
    """Validation-calibrated MACD probabilities.

    Without validation labels the function returns a neutral one-hot encoding;
    production comparisons should always supply validation_idx and labels.
    """
    signals = macd_deterministic(close, volatility)
    if validation_idx is None or y_validation is None:
        return pd.DataFrame(
            np.eye(len(CLASS_ORDER))[[CLASS_ORDER.index(x) for x in signals]],
            index=close.index,
            columns=[f"prob_{c}" for c in CLASS_ORDER],
        )
    table = fit_macd_probability_table(signals.iloc[validation_idx], y_validation)
    return apply_macd_probability_table(signals, table)
