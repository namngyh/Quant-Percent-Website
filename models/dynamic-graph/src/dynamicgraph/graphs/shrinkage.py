r"""Covariance estimation with shrinkage.

With ~30 assets and rolling windows as short as 20 days the sample covariance
is badly conditioned (it is singular whenever W <= N). Ledoit-Wolf shrinkage,

    Sigma_hat = (1 - delta) S + delta F,

with `delta` estimated from the data, is therefore the default estimator for
both the correlation layer and the graphical-lasso input.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dynamicgraph.constants import EPS
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CovarianceEstimate:
    covariance: np.ndarray
    correlation: np.ndarray
    shrinkage: float | None
    n_observations: int
    estimator: str
    condition_number: float


def _to_correlation(covariance: np.ndarray) -> np.ndarray:
    deviation = np.sqrt(np.clip(np.diag(covariance), EPS, None))
    correlation = covariance / np.outer(deviation, deviation)
    np.fill_diagonal(correlation, 1.0)
    return np.clip(correlation, -1.0, 1.0)


def sample_covariance(returns: np.ndarray) -> np.ndarray:
    return np.cov(returns, rowvar=False, ddof=1)


def ledoit_wolf_covariance(returns: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf shrinkage toward a scaled identity.

    Uses scikit-learn when available; otherwise falls back to a direct
    implementation of the 2004 estimator so the core pipeline keeps working.
    """
    try:
        from sklearn.covariance import ledoit_wolf

        covariance, delta = ledoit_wolf(returns, assume_centered=False)
        return np.asarray(covariance), float(delta)
    except Exception:  # pragma: no cover - sklearn is a core dependency
        n, p = returns.shape
        centered = returns - returns.mean(axis=0, keepdims=True)
        sample = centered.T @ centered / n
        mu = np.trace(sample) / p
        target = mu * np.eye(p)

        delta_squared = ((sample - target) ** 2).sum()
        beta_squared = 0.0
        for i in range(n):
            outer = np.outer(centered[i], centered[i])
            beta_squared += ((outer - sample) ** 2).sum()
        beta_squared /= n**2
        shrinkage = float(np.clip(beta_squared / (delta_squared + EPS), 0.0, 1.0))
        covariance = shrinkage * target + (1.0 - shrinkage) * sample
        return covariance, shrinkage


def estimate_covariance(
    returns: np.ndarray, estimator: str = "ledoit_wolf"
) -> CovarianceEstimate:
    """Estimate covariance + correlation from a `(T, N)` return window."""
    returns = np.asarray(returns, dtype=float)
    if returns.ndim != 2:
        raise ValueError("`returns` must be a 2-D (observations x assets) array.")
    n_obs, n_assets = returns.shape
    if n_obs < 3:
        raise ValueError(f"Need at least 3 observations, got {n_obs}.")

    estimator = str(estimator).lower()
    if estimator == "ledoit_wolf":
        covariance, shrinkage = ledoit_wolf_covariance(returns)
    elif estimator == "sample":
        covariance, shrinkage = sample_covariance(returns), None
        if n_obs <= n_assets:
            logger.warning(
                "Sample covariance with T=%d <= N=%d is singular; consider ledoit_wolf.",
                n_obs,
                n_assets,
            )
    else:
        raise ValueError(f"Unknown covariance estimator `{estimator}`.")

    covariance = 0.5 * (covariance + covariance.T)
    eigenvalues = np.linalg.eigvalsh(covariance)
    condition = float(
        np.abs(eigenvalues).max() / max(np.abs(eigenvalues).min(), EPS)
    )
    return CovarianceEstimate(
        covariance=covariance,
        correlation=_to_correlation(covariance),
        shrinkage=shrinkage,
        n_observations=n_obs,
        estimator=estimator,
        condition_number=condition,
    )


def nearest_positive_definite(matrix: np.ndarray, epsilon: float = 1e-8) -> np.ndarray:
    """Project a symmetric matrix onto the PD cone by clipping eigenvalues."""
    symmetric = 0.5 * (matrix + matrix.T)
    values, vectors = np.linalg.eigh(symmetric)
    values = np.clip(values, epsilon, None)
    return vectors @ np.diag(values) @ vectors.T
