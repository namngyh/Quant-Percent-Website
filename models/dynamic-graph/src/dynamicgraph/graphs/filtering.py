r"""Edge filtering.

Three methods, all applied to the *signed* adjacency but thresholding on |w|:

`absolute`
    keep |rho| >= tau.
`quantile`
    keep the top q share of edges by |rho| within each snapshot. Self-scaling,
    so density stays comparable through time - which matters because a
    fixed tau silently makes graphs denser in high-correlation regimes.
`stability`
    keep edges whose bootstrap selection frequency exceeds a threshold
    (see `stability.py`).

A density cap is applied last so that no snapshot can become effectively
complete and destroy the interpretability of the centrality measures.
"""

from __future__ import annotations

import numpy as np

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def apply_absolute_threshold(adjacency: np.ndarray, tau: float) -> np.ndarray:
    out = adjacency.copy()
    out[np.abs(out) < tau] = 0.0
    np.fill_diagonal(out, 0.0)
    return out


def apply_quantile_threshold(adjacency: np.ndarray, keep_fraction: float) -> np.ndarray:
    """Keep the strongest `keep_fraction` of edges by absolute weight."""
    n = adjacency.shape[0]
    if n < 2 or keep_fraction >= 1.0:
        return adjacency.copy()
    i, j = np.triu_indices(n, k=1)
    weights = np.abs(adjacency[i, j])
    nonzero = weights[weights > 0]
    if nonzero.size == 0:
        return np.zeros_like(adjacency)

    keep_n = max(1, int(round(keep_fraction * nonzero.size)))
    cutoff = np.partition(nonzero, -keep_n)[-keep_n]
    out = adjacency.copy()
    out[np.abs(out) < cutoff] = 0.0
    np.fill_diagonal(out, 0.0)
    return out


def apply_stability_threshold(
    adjacency: np.ndarray, stability: np.ndarray, threshold: float
) -> np.ndarray:
    out = adjacency.copy()
    out[stability < threshold] = 0.0
    np.fill_diagonal(out, 0.0)
    return out


def enforce_max_density(adjacency: np.ndarray, max_density: float) -> np.ndarray:
    """Trim the weakest edges until density <= `max_density`."""
    n = adjacency.shape[0]
    if n < 2:
        return adjacency
    i, j = np.triu_indices(n, k=1)
    weights = np.abs(adjacency[i, j])
    n_edges = int((weights > 0).sum())
    n_possible = weights.size
    if n_possible == 0 or n_edges / n_possible <= max_density:
        return adjacency
    keep_n = max(1, int(np.floor(max_density * n_possible)))
    nonzero = weights[weights > 0]
    cutoff = np.partition(nonzero, -keep_n)[-keep_n]
    out = adjacency.copy()
    out[np.abs(out) < cutoff] = 0.0
    np.fill_diagonal(out, 0.0)
    return out


def filter_adjacency(
    adjacency: np.ndarray,
    method: str = "quantile",
    absolute_threshold: float = 0.10,
    keep_fraction: float = 0.25,
    stability: np.ndarray | None = None,
    stability_threshold: float = 0.60,
    max_density: float = 0.60,
) -> tuple[np.ndarray, dict]:
    """Apply the configured filter, then the density cap. Returns (A, info)."""
    method = str(method).lower()
    if method == "none":
        filtered = adjacency.copy()
    elif method == "absolute":
        filtered = apply_absolute_threshold(adjacency, absolute_threshold)
    elif method == "quantile":
        filtered = apply_quantile_threshold(adjacency, keep_fraction)
    elif method == "stability":
        if stability is None:
            logger.warning(
                "Stability filtering requested but no bootstrap stability matrix was supplied; "
                "falling back to quantile filtering."
            )
            filtered = apply_quantile_threshold(adjacency, keep_fraction)
            method = "quantile_fallback"
        else:
            filtered = apply_stability_threshold(adjacency, stability, stability_threshold)
    else:
        raise ValueError(f"Unknown edge filter method `{method}`.")

    before = int(np.count_nonzero(np.triu(filtered, k=1)))
    filtered = enforce_max_density(filtered, max_density)
    after = int(np.count_nonzero(np.triu(filtered, k=1)))

    n = adjacency.shape[0]
    n_possible = n * (n - 1) // 2
    return filtered, {
        "filter_method": method,
        "n_edges": after,
        "density": (after / n_possible) if n_possible else 0.0,
        "n_edges_removed_by_density_cap": before - after,
    }
