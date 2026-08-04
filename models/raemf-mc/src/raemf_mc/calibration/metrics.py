"""Probability metrics and calibration diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from raemf_mc import CLASS_ORDER


def multiclass_brier(y_true: pd.Series, proba: np.ndarray) -> float:
    y = pd.Categorical(y_true.astype(str), categories=CLASS_ORDER).codes
    onehot = np.eye(len(CLASS_ORDER))[y]
    return float(np.mean(np.sum((proba - onehot) ** 2, axis=1)))


def safe_log_loss(y_true: pd.Series, proba: np.ndarray) -> float:
    codes = pd.Categorical(y_true.astype(str), categories=CLASS_ORDER).codes
    p = np.clip(proba, 1e-9, 1.0)
    return float(-np.log(p[np.arange(len(codes)), codes]).mean())


def expected_calibration_error(y_true: pd.Series, proba: np.ndarray, bins: int = 10) -> float:
    y_code = pd.Categorical(y_true.astype(str), categories=CLASS_ORDER).codes
    conf = proba.max(axis=1)
    pred = proba.argmax(axis=1)
    ece = 0.0
    for lo, hi in zip(np.linspace(0, 1, bins, endpoint=False), np.linspace(0.1, 1.0, bins)):
        mask = (conf > lo) & (conf <= hi)
        if mask.any():
            acc = (pred[mask] == y_code[mask]).mean()
            ece += mask.mean() * abs(acc - conf[mask].mean())
    return float(ece)


def assert_probability_matrix(proba: np.ndarray) -> None:
    if not np.all((proba >= -1e-9) & (proba <= 1 + 1e-9)):
        raise AssertionError("Probability outside [0,1]")
    if not np.allclose(proba.sum(axis=1), 1.0, atol=1e-6):
        raise AssertionError("Probability rows do not sum to 1")
