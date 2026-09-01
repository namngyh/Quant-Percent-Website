r"""Covariance estimators competing for the allocation input.

Each estimator maps a `(T, N)` trailing return window to a covariance matrix.
They differ only in how the *correlation* structure is regularised, because the
marginal variances are the easy part: a 60-day variance estimate is noisy but
unbiased, while a 60-day correlation matrix on 30 assets has 435 free parameters
estimated from 1,800 numbers and is severely over-fitted.

So every estimator here follows the same split::

    Sigma = D R D,    D = diag(sample standard deviations)

and only `R` changes. This isolates the question the project actually needs to
answer -- does the graph layer estimate correlation better? -- from the
unrelated question of variance estimation, and it means a win cannot come from
accidentally shrinking the overall risk level.

`ledoit_wolf` shrinks R toward the identity by a data-driven amount.
`glasso` inverts a sparse precision matrix: it sets conditional dependencies to
exactly zero rather than shrinking every entry uniformly, which is the whole
premise of the network layer.
`diagonal` throws the correlation structure away entirely (R = I). It is the
null model: if it wins, dependence estimation is not adding anything.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dynamicgraph.constants import EPS
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

COVARIANCE_ESTIMATORS: tuple[str, ...] = (
    "sample",
    "ledoit_wolf",
    "ewma",
    "glasso",
    "diagonal",
)


@dataclass
class AllocationCovariance:
    """A covariance matrix plus the diagnostics needed to judge it."""

    covariance: np.ndarray
    correlation: np.ndarray
    estimator: str
    n_observations: int
    condition_number: float
    off_diagonal_zeros: float = 0.0
    shrinkage: float | None = None
    note: str = ""


def _sample_moments(returns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Sample standard deviations and the sample correlation matrix."""
    deviation = returns.std(axis=0, ddof=1)
    deviation = np.clip(deviation, EPS, None)
    standardized = (returns - returns.mean(axis=0)) / deviation
    correlation = standardized.T @ standardized / (returns.shape[0] - 1)
    correlation = 0.5 * (correlation + correlation.T)
    np.fill_diagonal(correlation, 1.0)
    return deviation, correlation


def _to_unit_diagonal(matrix: np.ndarray) -> np.ndarray:
    """Rescale a covariance-shaped matrix to a correlation matrix."""
    deviation = np.sqrt(np.clip(np.diag(matrix), EPS, None))
    out = matrix / np.outer(deviation, deviation)
    np.fill_diagonal(out, 1.0)
    return 0.5 * (out + out.T)


def estimate_allocation_covariance(
    returns: np.ndarray,
    estimator: str = "ledoit_wolf",
    alpha: float = 0.02,
    ridge: float = 1e-6,
) -> AllocationCovariance:
    """Estimate `Sigma` from a `(T, N)` window using only that window's data.

    `alpha` is the graphical-lasso penalty and is only consulted by the `glasso`
    estimator. It must be chosen on training data and then frozen; nothing here
    tunes it, precisely so that a backtest cannot leak the test period into the
    penalty.
    """
    returns = np.asarray(returns, dtype=float)
    if returns.ndim != 2:
        raise ValueError("`returns` must be a 2-D (observations x assets) array.")
    n_obs, n_assets = returns.shape
    if n_obs < 3:
        raise ValueError(f"Need at least 3 observations, got {n_obs}.")

    estimator = str(estimator).lower()
    if estimator not in COVARIANCE_ESTIMATORS:
        raise ValueError(
            f"Unknown covariance estimator `{estimator}`; "
            f"expected one of {COVARIANCE_ESTIMATORS}."
        )

    deviation, sample_correlation = _sample_moments(returns)
    shrinkage: float | None = None
    note = ""

    if estimator == "sample":
        correlation = sample_correlation
        if n_obs <= n_assets:
            note = f"singular by construction (T={n_obs} <= N={n_assets})"

    elif estimator == "diagonal":
        correlation = np.eye(n_assets)

    elif estimator == "ledoit_wolf":
        from dynamicgraph.graphs.shrinkage import ledoit_wolf_covariance

        # Shrink on the standardised data so the intensity applies to the
        # correlation structure and not to the variance level.
        standardized = (returns - returns.mean(axis=0)) / deviation
        shrunk, shrinkage = ledoit_wolf_covariance(standardized)
        correlation = _to_unit_diagonal(shrunk)

    elif estimator == "ewma":
        decay = 0.94
        standardized = (returns - returns.mean(axis=0)) / deviation
        ages = np.arange(n_obs - 1, -1, -1)
        weights = decay**ages
        weights = weights / weights.sum()
        weighted_mean = weights @ standardized
        centered = standardized - weighted_mean
        weighted_covariance = centered.T @ (centered * weights[:, None])
        correlation = _to_unit_diagonal(weighted_covariance)
        note = f"EWMA correlation with lambda={decay:.2f}; sample marginal variances retained"

    else:  # glasso
        from dynamicgraph.graphs.graphical_lasso import fit_graphical_lasso

        fit = fit_graphical_lasso(sample_correlation, float(alpha))
        precision = np.asarray(fit.precision, dtype=float)
        try:
            implied = np.linalg.inv(precision)
        except np.linalg.LinAlgError:
            implied = np.linalg.pinv(precision)
            note = "precision inversion fell back to the pseudo-inverse"
        # The implied matrix is a covariance on the standardised scale; its
        # diagonal drifts from 1 by the amount the penalty distorted the
        # variances. Renormalising keeps the sample variances -- which are not
        # what the penalty was meant to regularise -- and takes only the
        # correlation structure from the graph.
        correlation = _to_unit_diagonal(implied)
        if not fit.converged:
            note = (note + "; " if note else "") + "graphical lasso did not converge"

    correlation = np.clip(correlation, -1.0, 1.0)
    np.fill_diagonal(correlation, 1.0)
    covariance = correlation * np.outer(deviation, deviation)
    # A small ridge keeps the matrix invertible for the optimiser without
    # materially changing it; on daily variances of ~1e-4 this is a 1e-2
    # relative perturbation at most.
    covariance = covariance + ridge * np.trace(covariance) / n_assets * np.eye(n_assets)
    covariance = 0.5 * (covariance + covariance.T)

    eigenvalues = np.linalg.eigvalsh(covariance)
    condition = float(np.abs(eigenvalues).max() / max(np.abs(eigenvalues).min(), EPS))

    upper = np.triu_indices(n_assets, k=1)
    if estimator == "glasso":
        zeros = float(np.mean(np.abs(precision[upper]) <= 1e-10))
    elif estimator == "diagonal":
        zeros = 1.0
    else:
        zeros = 0.0

    return AllocationCovariance(
        covariance=covariance,
        correlation=correlation,
        estimator=estimator,
        n_observations=n_obs,
        condition_number=condition,
        off_diagonal_zeros=zeros,
        shrinkage=shrinkage,
        note=note,
    )


def covariance_forecast_error(
    predicted: np.ndarray, realized_returns: np.ndarray
) -> dict[str, float]:
    r"""Score a covariance forecast against the returns that followed it.

    Two complementary scores, both computed on data strictly after the window
    that produced `predicted`:

    `frobenius`
        :math:`\|\Sigma - rr^\top\|_F` against the realised outer product. Scale
        dependent, so only comparable between estimators on the same date.
    `log_likelihood`
        Gaussian log-likelihood of the realised returns under `predicted`. This
        is the proper scoring rule for a covariance forecast -- it penalises
        both over- and under-stating risk, whereas Frobenius distance to a rank-1
        outer product is dominated by idiosyncratic noise.
    """
    predicted = np.asarray(predicted, dtype=float)
    realized = np.asarray(realized_returns, dtype=float)
    if realized.ndim == 1:
        realized = realized.reshape(1, -1)
    n_obs, n_assets = realized.shape
    if n_obs == 0 or predicted.shape != (n_assets, n_assets):
        return {
            "frobenius": np.nan,
            "log_likelihood": np.nan,
            "qlike": np.nan,
            "n": 0,
        }

    realized_covariance = realized.T @ realized / max(n_obs, 1)
    frobenius = float(np.linalg.norm(predicted - realized_covariance, ord="fro"))

    try:
        cholesky = np.linalg.cholesky(predicted)
    except np.linalg.LinAlgError:
        return {
            "frobenius": frobenius,
            "log_likelihood": np.nan,
            "qlike": np.nan,
            "n": int(n_obs),
        }
    log_determinant = 2.0 * float(np.log(np.diag(cholesky)).sum())
    solved = np.linalg.solve(predicted, realized.T)
    quadratic = float(np.einsum("ij,ji->", realized, solved)) / n_obs
    log_likelihood = -0.5 * (log_determinant + quadratic + n_assets * np.log(2 * np.pi))
    realized_covariance = realized.T @ realized / max(n_obs, 1)
    qlike = float(log_determinant + np.trace(solved @ realized / n_obs))

    return {
        "frobenius": frobenius,
        "log_likelihood": float(log_likelihood),
        "qlike": qlike,
        "n": int(n_obs),
    }
