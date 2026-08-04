"""Probability utilities."""

from __future__ import annotations

import numpy as np


def entropy(proba: np.ndarray) -> np.ndarray:
    """Row-wise entropy."""
    p = np.clip(proba, 1e-12, 1.0)
    return -(p * np.log(p)).sum(axis=1)
