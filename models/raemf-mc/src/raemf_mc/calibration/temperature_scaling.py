"""Multiclass temperature scaling."""

from __future__ import annotations

import numpy as np
import pandas as pd

from raemf_mc.calibration.metrics import safe_log_loss


def apply_temperature(proba: np.ndarray, temperature: float) -> np.ndarray:
    clipped = np.clip(proba, 1e-9, 1.0)
    logits = np.log(clipped) / max(temperature, 1e-6)
    logits = logits - logits.max(axis=1, keepdims=True)
    out = np.exp(logits)
    return out / out.sum(axis=1, keepdims=True)


def fit_temperature(proba_val: np.ndarray, y_val: pd.Series) -> tuple[float, float, bool]:
    """Choose T on validation only; use calibration only if validation log loss improves."""
    base = safe_log_loss(y_val, proba_val)
    candidates = np.linspace(0.6, 2.4, 19)
    losses = [safe_log_loss(y_val, apply_temperature(proba_val, float(t))) for t in candidates]
    best_idx = int(np.argmin(losses))
    best_t = float(candidates[best_idx])
    best = float(losses[best_idx])
    return best_t, best, best < base
