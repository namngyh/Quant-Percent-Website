r"""Lead-lag directed layer.

    rho_{i->j,t}(k) = Corr(r_{i,t-k}, r_{j,t})

    LL_{i->j,t} = max_k |Corr(r_{i,t-k}, r_{j,t})| / max_k |Corr(r_{j,t-k}, r_{i,t})|

A directed edge i -> j is created when `LL > threshold` and the forward
correlation clears a minimum magnitude.

CAVEATS (repeated verbatim in the reports and the website payload):
  * lead-lag correlation is an association, NOT causation;
  * with N=30 there are 870 ordered pairs x 4 lags, so multiple testing alone
    produces spurious edges -- Benjamini-Hochberg FDR control is applied;
  * daily data on a market with a T+2.5 settlement cycle and a +/-7% band gives
    limited power to detect genuine lead-lag structure.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS
from dynamicgraph.graphs.base import DirectedSnapshot
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

LEAD_LAG_DISCLAIMER = (
    "Lead-lag edges are lagged correlations, not causal effects. They are subject to "
    "multiple-testing artefacts and to non-synchronous trading; treat them as descriptive."
)


def lagged_correlation_matrix(window_returns: pd.DataFrame, lag: int) -> np.ndarray:
    r"""C[i, j] = Corr(r_i(t-lag), r_j(t)) over the window."""
    values = window_returns.to_numpy(dtype=float)
    if lag <= 0:
        raise ValueError("`lag` must be positive.")
    if values.shape[0] <= lag + 3:
        return np.full((values.shape[1], values.shape[1]), np.nan)

    past = values[:-lag]
    present = values[lag:]
    past = past - past.mean(axis=0, keepdims=True)
    present = present - present.mean(axis=0, keepdims=True)
    past_std = past.std(axis=0, ddof=1)
    present_std = present.std(axis=0, ddof=1)

    n = past.shape[0]
    covariance = past.T @ present / (n - 1)
    return covariance / (np.outer(past_std, present_std) + EPS)


def fisher_z_pvalues(correlations: np.ndarray, n_obs: int) -> np.ndarray:
    """Two-sided p-values from Fisher's z-transform."""
    from scipy.stats import norm

    r = np.clip(correlations, -0.999999, 0.999999)
    z = np.arctanh(r) * np.sqrt(max(n_obs - 3, 1))
    return 2.0 * (1.0 - norm.cdf(np.abs(z)))


def benjamini_hochberg(pvalues: np.ndarray, alpha: float = 0.10) -> np.ndarray:
    """Boolean mask of hypotheses that survive BH-FDR control at `alpha`."""
    flat = pvalues.ravel()
    finite = np.isfinite(flat)
    mask = np.zeros_like(flat, dtype=bool)
    if finite.sum() == 0:
        return mask.reshape(pvalues.shape)

    values = flat[finite]
    order = np.argsort(values)
    ranked = values[order]
    m = ranked.size
    thresholds = alpha * np.arange(1, m + 1) / m
    passed = ranked <= thresholds
    if not passed.any():
        return mask.reshape(pvalues.shape)
    cutoff = ranked[np.max(np.where(passed)[0])]
    selected = np.zeros_like(mask)
    selected[np.where(finite)[0]] = values <= cutoff
    return selected.reshape(pvalues.shape)


def build_lead_lag_snapshot(
    window_returns: pd.DataFrame,
    date: pd.Timestamp,
    lags: Sequence[int] = (1, 2, 3, 5),
    threshold: float = 1.25,
    min_abs_corr: float = 0.05,
    fdr_alpha: float = 0.10,
    max_missing_ratio: float = 0.10,
) -> DirectedSnapshot | None:
    r"""Directed lead-lag graph for one trailing window."""
    coverage = window_returns.notna().mean()
    valid = coverage[coverage >= (1.0 - max_missing_ratio)].index.tolist()
    block = window_returns[valid].dropna(axis=0, how="any")
    if len(valid) < 5 or len(block) < 30:
        return None

    n = len(valid)
    best_forward = np.zeros((n, n))
    best_lag = np.zeros((n, n), dtype=int)
    best_pvalue = np.ones((n, n))

    for lag in lags:
        correlation = lagged_correlation_matrix(block, lag)
        if not np.isfinite(correlation).any():
            continue
        pvalues = fisher_z_pvalues(correlation, len(block) - lag)
        stronger = np.abs(correlation) > np.abs(best_forward)
        best_forward = np.where(stronger, correlation, best_forward)
        best_lag = np.where(stronger, lag, best_lag)
        best_pvalue = np.where(stronger, pvalues, best_pvalue)

    np.fill_diagonal(best_forward, 0.0)
    magnitude = np.abs(best_forward)
    reverse = magnitude.T

    ratio = magnitude / (reverse + EPS)
    significant = benjamini_hochberg(best_pvalue, alpha=fdr_alpha)

    keep = (ratio > threshold) & (magnitude >= min_abs_corr) & significant
    np.fill_diagonal(keep, False)

    adjacency = np.where(keep, best_forward, 0.0)
    n_edges = int(np.count_nonzero(adjacency))

    return DirectedSnapshot(
        date=pd.Timestamp(date),
        nodes=list(valid),
        adjacency=adjacency,
        layer="lead_lag",
        window=len(block),
        metadata={
            "lags": list(lags),
            "threshold": threshold,
            "min_abs_corr": min_abs_corr,
            "fdr_alpha": fdr_alpha,
            "n_edges": n_edges,
            "n_tests": int(n * (n - 1) * len(lags)),
            "n_significant_after_fdr": int(significant.sum()),
            "best_lag_median": float(np.median(best_lag[keep])) if n_edges else float("nan"),
            "disclaimer": LEAD_LAG_DISCLAIMER,
            "nodes": list(valid),
        },
    )


def build_lead_lag_series(
    returns: pd.DataFrame,
    window: int = 120,
    lags: Sequence[int] = (1, 2, 3, 5),
    threshold: float = 1.25,
    min_abs_corr: float = 0.05,
    fdr_alpha: float = 0.10,
    stride: int = 1,
    max_missing_ratio: float = 0.10,
) -> list[DirectedSnapshot]:
    returns = returns.sort_index()
    index = returns.index
    snapshots: list[DirectedSnapshot] = []
    for position in range(window - 1, len(index), max(1, stride)):
        snapshot = build_lead_lag_snapshot(
            returns.iloc[position - window + 1 : position + 1],
            index[position],
            lags=lags,
            threshold=threshold,
            min_abs_corr=min_abs_corr,
            fdr_alpha=fdr_alpha,
            max_missing_ratio=max_missing_ratio,
        )
        if snapshot is not None:
            snapshots.append(snapshot)
    logger.info("Built %d lead-lag snapshot(s) (window=%d, lags=%s).", len(snapshots), window, list(lags))
    if snapshots:
        mean_edges = np.mean([s.metadata["n_edges"] for s in snapshots])
        logger.info("Mean directed edges per lead-lag snapshot: %.1f. %s", mean_edges, LEAD_LAG_DISCLAIMER)
    return snapshots
