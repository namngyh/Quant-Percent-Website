"""EBM-reweighted Monte Carlo helpers."""

from __future__ import annotations

import numpy as np


def effective_sample_size(weights: np.ndarray) -> float:
    weights = weights / np.maximum(weights.sum(), 1e-12)
    return float(1.0 / np.sum(weights**2))


def tempered_class_weights(
    terminal_classes: np.ndarray,
    target_probabilities: np.ndarray,
    n_classes: int,
    min_ess_fraction: float = 0.35,
    clip_ratio: float = 8.0,
) -> tuple[np.ndarray, float, float, np.ndarray]:
    """Importance weights with clipping and tempering when ESS is too low."""
    terminal_classes = np.asarray(terminal_classes, dtype=int)
    target = np.asarray(target_probabilities, dtype=float)
    target = np.clip(target, 1e-8, None)
    target /= target.sum()
    proposal = np.bincount(terminal_classes, minlength=n_classes).astype(float)
    proposal = np.clip(proposal / max(proposal.sum(), 1.0), 1e-8, None)
    raw = np.clip(target[terminal_classes] / proposal[terminal_classes], 1.0 / clip_ratio, clip_ratio)
    power = 1.0
    weights = raw.copy()
    target_ess = min_ess_fraction * len(weights)
    while effective_sample_size(weights) < target_ess and power > 0.20:
        power *= 0.85
        weights = raw**power
    weights = 0.95 * weights + 0.05
    weights /= weights.sum()
    return weights, effective_sample_size(weights), power, proposal


def weighted_quantile(values: np.ndarray, quantiles: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted quantiles for one-dimensional values."""
    values = np.asarray(values, dtype=float)
    quantiles = np.asarray(quantiles, dtype=float)
    weights = np.asarray(weights, dtype=float)
    order = np.argsort(values)
    sorted_values = values[order]
    sorted_weights = weights[order]
    cumulative = np.cumsum(sorted_weights)
    cumulative /= max(float(cumulative[-1]), 1e-12)
    return np.interp(quantiles, cumulative, sorted_values)
