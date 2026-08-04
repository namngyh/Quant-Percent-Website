"""Small statistical comparison helpers."""

from __future__ import annotations

import numpy as np


def paired_difference_summary(reference: np.ndarray, benchmark: np.ndarray) -> dict[str, float]:
    """Summarize paired observation-level differences before bootstrap."""
    difference = np.asarray(reference, dtype=float) - np.asarray(benchmark, dtype=float)
    if difference.ndim != 1 or len(difference) == 0:
        raise ValueError("Paired metric vectors must be non-empty and one-dimensional")
    return {
        "mean_difference": float(difference.mean()),
        "median_difference": float(np.median(difference)),
        "standard_error": float(difference.std(ddof=1) / np.sqrt(len(difference))) if len(difference) > 1 else 0.0,
    }
