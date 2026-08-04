r"""Rolling correlation layer.

    rho^{(W)}_{ij,t} = Corr(r_{i, t-W+1:t}, r_{j, t-W+1:t})
    A^{corr,W}_{ij,t} = rho (signed) or |rho| (absolute)

The window ends at t, so the layer is causal by construction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dynamicgraph.graphs.shrinkage import estimate_covariance
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def correlation_matrix(
    window_returns: pd.DataFrame, estimator: str = "ledoit_wolf"
) -> tuple[np.ndarray, dict]:
    """Correlation matrix of a trailing return window.

    Returns `(correlation, info)`. `info` carries the shrinkage intensity and
    the condition number so that snapshot metadata can record them.
    """
    values = window_returns.to_numpy(dtype=float)
    estimate = estimate_covariance(values, estimator=estimator)
    info = {
        "estimator": estimate.estimator,
        "shrinkage": estimate.shrinkage,
        "condition_number": estimate.condition_number,
        "n_observations": estimate.n_observations,
    }
    return estimate.correlation, info


def average_absolute_correlation(correlation: np.ndarray) -> float:
    """Mean |rho| over the off-diagonal entries."""
    n = correlation.shape[0]
    if n < 2:
        return float("nan")
    i, j = np.triu_indices(n, k=1)
    return float(np.abs(correlation[i, j]).mean())


def market_mode_share(correlation: np.ndarray) -> float:
    r"""MMS_t = lambda_1(C_t) / trace(C_t).

    The share of total cross-sectional variance explained by the first
    eigenvector - the standard "everything moves together" statistic.
    """
    eigenvalues = np.linalg.eigvalsh(correlation)
    total = float(np.sum(eigenvalues))
    if total <= 0:
        return float("nan")
    return float(eigenvalues[-1] / total)


def eigenvalue_concentration(correlation: np.ndarray) -> float:
    """Herfindahl index of the normalised eigenvalue spectrum."""
    eigenvalues = np.clip(np.linalg.eigvalsh(correlation), 0.0, None)
    total = eigenvalues.sum()
    if total <= 0:
        return float("nan")
    shares = eigenvalues / total
    return float(np.sum(shares**2))


def diversification_ratio(correlation: np.ndarray) -> float:
    r"""Equal-weight diversification ratio.

        DR = sqrt(N) / sqrt(1' C 1 / N)

    DR = sqrt(N) when assets are uncorrelated and 1 when they are perfectly
    correlated, so `1 - 1/DR` is a natural "diversification decay" proxy.
    """
    n = correlation.shape[0]
    if n < 2:
        return float("nan")
    ones = np.ones(n)
    portfolio_variance = float(ones @ correlation @ ones) / (n * n)
    if portfolio_variance <= 0:
        return float("nan")
    return float(np.sqrt(1.0 / portfolio_variance))


def negative_diversification_proxy(correlation: np.ndarray) -> float:
    """1 - DR / sqrt(N): 0 when fully diversifiable, 1 when fully concentrated."""
    n = correlation.shape[0]
    ratio = diversification_ratio(correlation)
    if not np.isfinite(ratio) or n < 2:
        return float("nan")
    return float(np.clip(1.0 - ratio / np.sqrt(n), 0.0, 1.0))


def rolling_correlation_series(
    returns: pd.DataFrame, window: int, estimator: str = "ledoit_wolf", stride: int = 1
) -> dict[pd.Timestamp, np.ndarray]:
    """Correlation matrix for every (strided) date with a full trailing window."""
    out: dict[pd.Timestamp, np.ndarray] = {}
    dates = returns.index
    for position in range(window - 1, len(dates), stride):
        block = returns.iloc[position - window + 1 : position + 1].dropna(axis=1, how="any")
        if block.shape[1] < 3:
            continue
        correlation, _ = correlation_matrix(block, estimator)
        out[dates[position]] = correlation
    return out
