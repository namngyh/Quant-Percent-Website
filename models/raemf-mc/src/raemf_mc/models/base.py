"""Shared model helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd

from raemf_mc import CLASS_ORDER


def class_weights(y: pd.Series) -> np.ndarray:
    """Balanced sample weights clipped for sparse classes."""
    counts = y.value_counts()
    n = len(y)
    k = max(len(counts), 1)
    weights = y.map({cls: n / (k * cnt) for cls, cnt in counts.items()}).astype(float).to_numpy()
    return np.clip(weights, 0.25, 6.0)


def align_proba(classes: np.ndarray | list[object], proba: np.ndarray) -> np.ndarray:
    """Align predicted probabilities to CLASS_ORDER."""
    out = np.zeros((len(proba), len(CLASS_ORDER)), dtype=float)
    classes_str = [str(c) for c in classes]
    for j, cls in enumerate(classes_str):
        if cls in CLASS_ORDER:
            out[:, CLASS_ORDER.index(cls)] = proba[:, j]
    row_sum = out.sum(axis=1, keepdims=True)
    zero = row_sum[:, 0] <= 0
    out[zero] = 1.0 / len(CLASS_ORDER)
    out[~zero] = out[~zero] / row_sum[~zero]
    out = np.clip(out, 1e-9, 1.0)
    return out / out.sum(axis=1, keepdims=True)


def fill_features(train: pd.DataFrame, *others: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    """Median-impute features using train medians."""
    med = train.median(numeric_only=True).replace([np.inf, -np.inf], 0).fillna(0)
    frames = [train, *others]
    return tuple(f.replace([np.inf, -np.inf], np.nan).fillna(med).fillna(0) for f in frames)
