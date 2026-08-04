"""Monte Carlo path risk metrics."""

from __future__ import annotations

import numpy as np


def max_drawdown(paths: np.ndarray) -> np.ndarray:
    peak = np.maximum.accumulate(paths, axis=1)
    return (paths / peak - 1.0).min(axis=1)
