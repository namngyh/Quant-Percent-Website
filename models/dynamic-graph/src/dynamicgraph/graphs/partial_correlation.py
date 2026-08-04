r"""Partial correlation - the core DynamicGraph layer.

From a precision matrix Theta,

    rho^{partial}_{ij} = -Theta_{ij} / sqrt(Theta_{ii} Theta_{jj})

A partial correlation measures dependence between i and j *after conditioning
on every other stock in the universe*, so it strips out the chains of indirect
association that make raw correlation graphs nearly complete.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS


def partial_correlation_from_precision(precision: np.ndarray) -> np.ndarray:
    r"""rho^{partial}_{ij} = -Theta_{ij} / sqrt(Theta_ii Theta_jj), zero diagonal."""
    precision = np.asarray(precision, dtype=float)
    diagonal = np.clip(np.diag(precision), EPS, None)
    scale = np.sqrt(np.outer(diagonal, diagonal))
    partial = -precision / scale
    np.fill_diagonal(partial, 0.0)
    return np.clip(0.5 * (partial + partial.T), -1.0, 1.0)


def partial_correlation_from_covariance(covariance: np.ndarray) -> np.ndarray:
    """Unregularised partial correlation via the pseudo-inverse.

    Only appropriate when T >> N; the graphical-lasso path is the default.
    """
    precision = np.linalg.pinv(0.5 * (covariance + covariance.T))
    return partial_correlation_from_precision(precision)


def average_absolute_partial_correlation(partial: np.ndarray) -> float:
    n = partial.shape[0]
    if n < 2:
        return float("nan")
    i, j = np.triu_indices(n, k=1)
    return float(np.abs(partial[i, j]).mean())


def signed_edge_shares(adjacency: np.ndarray) -> tuple[float, float]:
    """(positive share, negative share) among the non-zero upper-triangular edges."""
    n = adjacency.shape[0]
    if n < 2:
        return float("nan"), float("nan")
    i, j = np.triu_indices(n, k=1)
    weights = adjacency[i, j]
    nonzero = weights[weights != 0]
    if nonzero.size == 0:
        return 0.0, 0.0
    positive = float(np.mean(nonzero > 0))
    return positive, 1.0 - positive


def to_frame(matrix: np.ndarray, nodes: list[str]) -> pd.DataFrame:
    return pd.DataFrame(matrix, index=nodes, columns=nodes)
