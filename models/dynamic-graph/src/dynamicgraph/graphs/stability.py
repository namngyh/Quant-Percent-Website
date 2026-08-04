r"""Bootstrap edge-stability selection.

    Stability_{ij,t} = (1/B) sum_b 1[(i,j) in E_t^{(b)}]

Financial returns are serially dependent, so resampling individual rows i.i.d.
would destroy the autocorrelation and volatility clustering that drive the
covariance estimate. Both resamplers here are block bootstraps:

`moving_block`
    contiguous blocks of fixed length, sampled with replacement;
`stationary`
    Politis-Romano, geometric block lengths -- the resampled series is
    stationary, which matters when the block length is comparable to the window.
"""

from __future__ import annotations

import numpy as np

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def auto_block_length(n_obs: int) -> int:
    """Rule-of-thumb block length ~ n^(1/3), clipped to [5, 20] as configured."""
    return int(np.clip(round(n_obs ** (1 / 3)), 5, 20))


def moving_block_indices(n_obs: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    """Indices of a moving-block bootstrap resample of length `n_obs`."""
    block_length = max(1, min(block_length, n_obs))
    n_blocks = int(np.ceil(n_obs / block_length))
    starts = rng.integers(0, n_obs - block_length + 1, size=n_blocks)
    indices = np.concatenate([np.arange(s, s + block_length) for s in starts])
    return indices[:n_obs]


def stationary_bootstrap_indices(
    n_obs: int, mean_block_length: float, rng: np.random.Generator
) -> np.ndarray:
    """Politis-Romano stationary bootstrap with geometric block lengths."""
    p = 1.0 / max(1.0, mean_block_length)
    indices = np.empty(n_obs, dtype=int)
    current = int(rng.integers(0, n_obs))
    for t in range(n_obs):
        indices[t] = current
        if rng.random() < p:
            current = int(rng.integers(0, n_obs))
        else:
            current = (current + 1) % n_obs
    return indices


def edge_stability(
    window_returns: np.ndarray,
    build_adjacency,
    n_bootstrap: int = 100,
    block_length: int | str = "auto",
    method: str = "moving_block",
    seed: int = 42,
    n_jobs: int = 1,
) -> np.ndarray:
    r"""Selection frequency of every edge across block-bootstrap resamples.

    `build_adjacency(returns) -> adjacency` must return the *filtered* signed
    adjacency for a resampled window; an edge counts as selected when its weight
    is non-zero.
    """
    n_obs, n_assets = window_returns.shape
    if n_bootstrap <= 0:
        return np.ones((n_assets, n_assets))

    if block_length == "auto":
        block = auto_block_length(n_obs)
    else:
        block = int(block_length)

    rng = np.random.default_rng(seed)
    seeds = rng.integers(0, 2**31 - 1, size=n_bootstrap)

    def _one(bootstrap_seed: int) -> np.ndarray:
        local = np.random.default_rng(int(bootstrap_seed))
        if method == "stationary":
            indices = stationary_bootstrap_indices(n_obs, block, local)
        else:
            indices = moving_block_indices(n_obs, block, local)
        resample = window_returns[indices]
        try:
            adjacency = build_adjacency(resample)
        except Exception:
            return np.zeros((n_assets, n_assets))
        return (np.abs(adjacency) > 0).astype(float)

    if n_jobs != 1:
        try:
            from joblib import Parallel, delayed

            counts = Parallel(n_jobs=n_jobs, prefer="threads")(
                delayed(_one)(s) for s in seeds
            )
        except Exception:
            counts = [_one(s) for s in seeds]
    else:
        counts = [_one(s) for s in seeds]

    stability = np.mean(counts, axis=0)
    np.fill_diagonal(stability, 1.0)
    return stability


def centrality_rank_stability(current: "np.ndarray | dict", previous: "np.ndarray | dict") -> float:
    """Spearman rank correlation between two centrality vectors."""
    import pandas as pd
    from scipy.stats import spearmanr

    if isinstance(current, dict) and isinstance(previous, dict):
        shared = sorted(set(current) & set(previous))
        if len(shared) < 3:
            return float("nan")
        a = np.array([current[k] for k in shared])
        b = np.array([previous[k] for k in shared])
    else:
        a, b = np.asarray(current), np.asarray(previous)
        if a.shape != b.shape or a.size < 3:
            return float("nan")

    if np.allclose(a, a[0]) or np.allclose(b, b[0]):
        return float("nan")
    rho, _ = spearmanr(a, b)
    return float(rho) if pd.notna(rho) else float("nan")


def edge_survival(current: np.ndarray, previous: np.ndarray) -> float:
    r"""|E_t ∩ E_{t-1}| / |E_{t-1}|."""
    n = current.shape[0]
    i, j = np.triu_indices(n, k=1)
    now = np.abs(current[i, j]) > 0
    before = np.abs(previous[i, j]) > 0
    if before.sum() == 0:
        return float("nan")
    return float((now & before).sum() / before.sum())


def edge_turnover(current: np.ndarray, previous: np.ndarray) -> float:
    r"""1 - |E_t ∩ E_{t-1}| / |E_t ∪ E_{t-1}| (Jaccard distance)."""
    n = current.shape[0]
    i, j = np.triu_indices(n, k=1)
    now = np.abs(current[i, j]) > 0
    before = np.abs(previous[i, j]) > 0
    union = (now | before).sum()
    if union == 0:
        return float("nan")
    return float(1.0 - (now & before).sum() / union)
