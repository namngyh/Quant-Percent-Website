r"""Diebold-Yilmaz style volatility/return spillover layer (optional).

    y_t = c + sum_{l=1}^{p} A_l y_{t-l} + u_t

From the VAR, the generalised forecast-error variance decomposition at horizon H
gives theta_{ij}^{(H)}: the share of i's H-step forecast error variance
attributable to shocks in j. Normalising each row to sum to one and dropping the
diagonal gives the directed spillover matrix, and

    TCI^{(H)} = 100 * sum_{i != j} theta~_{ij} / N

is the total connectedness index.

With N=30 and a 120-day window an unregularised VAR(2) would need 61 coefficients
per equation from 120 observations -- hopeless. This module therefore *requires*
dimensionality control: ridge, lasso, or a PCA-VAR on the leading factors. An
unregularised 30-dimensional VAR is never fitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS
from dynamicgraph.graphs.base import DirectedSnapshot
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class VARFit:
    coefficients: np.ndarray   # (p, N, N)
    residual_covariance: np.ndarray
    lags: int
    estimator: str
    n_observations: int


def fit_regularized_var(
    data: np.ndarray,
    lags: int = 2,
    estimator: str = "ridge",
    alpha: float = 1.0,
    n_components: int = 5,
    seed: int = 42,
) -> tuple[VARFit, np.ndarray | None]:
    """Fit a regularised VAR. Returns `(fit, pca_loadings_or_None)`."""
    from sklearn.linear_model import Lasso, Ridge

    values = np.asarray(data, dtype=float)
    n_obs, n_series = values.shape
    loadings: np.ndarray | None = None

    if estimator == "pca":
        from sklearn.decomposition import PCA

        n_components = int(min(n_components, n_series, n_obs - lags - 2))
        pca = PCA(n_components=n_components, random_state=seed)
        scores = pca.fit_transform(values - values.mean(axis=0, keepdims=True))
        loadings = pca.components_          # (k, N)
        working = scores
    else:
        working = values - values.mean(axis=0, keepdims=True)

    k = working.shape[1]
    if n_obs <= lags + 5:
        raise ValueError("Window too short for the requested VAR order.")

    design = np.concatenate(
        [
            working[lags - lag_index - 1 : n_obs - lag_index - 1]
            for lag_index in range(lags)
        ],
        axis=1,
    )
    response = working[lags:]

    if estimator == "lasso":
        model = Lasso(alpha=alpha, max_iter=5000, random_state=seed)
    else:
        model = Ridge(alpha=alpha, random_state=seed)
    model.fit(design, response)

    beta = np.atleast_2d(model.coef_)      # (k, k*lags)
    coefficients = np.stack(
        [
            beta[:, lag_index * k : (lag_index + 1) * k]
            for lag_index in range(lags)
        ],
        axis=0,
    )
    residuals = response - model.predict(design)
    residual_covariance = np.cov(residuals, rowvar=False, ddof=1)
    if residual_covariance.ndim == 0:
        residual_covariance = residual_covariance.reshape(1, 1)

    return (
        VARFit(
            coefficients=coefficients,
            residual_covariance=np.atleast_2d(residual_covariance),
            lags=lags,
            estimator=estimator,
            n_observations=n_obs,
        ),
        loadings,
    )


def var_ma_representation(coefficients: np.ndarray, horizon: int) -> np.ndarray:
    """Wold MA coefficients Psi_0..Psi_{H-1} from the VAR coefficients."""
    lags, k, _ = coefficients.shape
    psi = np.zeros((horizon, k, k))
    psi[0] = np.eye(k)
    for h in range(1, horizon):
        total = np.zeros((k, k))
        for lag_index in range(1, min(lags, h) + 1):
            total += coefficients[lag_index - 1] @ psi[h - lag_index]
        psi[h] = total
    return psi


def generalized_fevd(fit: VARFit, horizon: int = 10) -> np.ndarray:
    r"""Generalised (Pesaran-Shin) FEVD, row-normalised.

        theta_ij^(H) = sigma_jj^{-1} sum_h (e_i' Psi_h Sigma e_j)^2
                       / sum_h (e_i' Psi_h Sigma Psi_h' e_i)
    """
    sigma = fit.residual_covariance
    k = sigma.shape[0]
    psi = var_ma_representation(fit.coefficients, horizon)
    sigma_diag = np.clip(np.diag(sigma), EPS, None)

    numerator = np.zeros((k, k))
    denominator = np.zeros(k)
    for h in range(horizon):
        step = psi[h] @ sigma
        numerator += step**2
        denominator += np.diag(psi[h] @ sigma @ psi[h].T)

    theta = (numerator / sigma_diag[None, :]) / np.clip(denominator[:, None], EPS, None)
    row_sums = np.clip(theta.sum(axis=1, keepdims=True), EPS, None)
    return theta / row_sums


def total_connectedness_index(theta: np.ndarray) -> float:
    r"""TCI^{(H)} = 100 * sum_{i != j} theta~_ij / N."""
    k = theta.shape[0]
    off_diagonal = theta.sum() - np.trace(theta)
    return float(100.0 * off_diagonal / k)


def build_spillover_snapshot(
    window_values: pd.DataFrame,
    date: pd.Timestamp,
    horizon: int = 10,
    lags: int = 2,
    estimator: str = "ridge",
    alpha: float = 1.0,
    n_components: int = 5,
    max_missing_ratio: float = 0.10,
    seed: int = 42,
) -> DirectedSnapshot | None:
    """Spillover graph for one trailing window of returns or volatilities."""
    coverage = window_values.notna().mean()
    valid = coverage[coverage >= (1.0 - max_missing_ratio)].index.tolist()
    block = window_values[valid].dropna(axis=0, how="any")
    if len(valid) < 5 or len(block) < max(40, lags * 10):
        return None

    try:
        fit, loadings = fit_regularized_var(
            block.to_numpy(), lags=lags, estimator=estimator, alpha=alpha,
            n_components=n_components, seed=seed,
        )
        theta = generalized_fevd(fit, horizon=horizon)
    except Exception as exc:
        logger.debug("Spillover VAR failed at %s: %s", date, exc)
        return None

    if loadings is not None:
        # Map factor-space connectedness back to asset space:
        #   theta_asset = |L'| theta_factor |L|, then row-normalise.
        weights = np.abs(loadings)
        theta = weights.T @ theta @ weights
        theta = theta / np.clip(theta.sum(axis=1, keepdims=True), EPS, None)

    # FEVD rows are receivers and columns are shock sources:
    # theta[i, j] = variance of i attributable to shock j.
    # DirectedSnapshot uses rows as sources, so transpose to obtain j -> i.
    directed = theta.T.copy()
    np.fill_diagonal(directed, 0.0)
    directional_sum = float(directed.sum())

    return DirectedSnapshot(
        date=pd.Timestamp(date),
        nodes=list(valid),
        adjacency=directed,
        layer="spillover",
        window=len(block),
        metadata={
            "horizon": horizon,
            "lags": lags,
            "estimator": estimator,
            "total_connectedness": total_connectedness_index(theta),
            "directional_spillover_sum": directional_sum,
            "fevd_convention": "theta[i,j] = variance of i due to shock j",
            "adjacency_convention": "adjacency[j,i] = theta[i,j]",
            "diagonal_policy": "self-spillovers retained for TCI and removed from adjacency",
            "n_observations": len(block),
            "nodes": list(valid),
            "note": (
                "Generalised FEVD from a regularised VAR. Adjacency is theta.T so row sums "
                "are transmitter strength and column sums are receiver strength. Shares of "
                "forecast-error variance are predictive attributions, not identified causal effects."
            ),
        },
    )


def build_spillover_series(
    values: pd.DataFrame,
    config: Any,
    stride: int = 5,
) -> list[DirectedSnapshot]:
    graph = config.graph
    window = int(graph.spillover_window)
    values = values.sort_index()
    index = values.index
    snapshots: list[DirectedSnapshot] = []
    for position in range(window - 1, len(index), max(1, stride)):
        snapshot = build_spillover_snapshot(
            values.iloc[position - window + 1 : position + 1],
            index[position],
            horizon=int(graph.spillover_horizon),
            lags=int(graph.spillover_lags),
            estimator=str(graph.spillover_estimator),
            alpha=float(graph.spillover_ridge_alpha),
            n_components=int(graph.spillover_pca_components),
            max_missing_ratio=float(config.data.max_missing_ratio_per_window),
            seed=int(config.project.seed),
        )
        if snapshot is not None:
            snapshots.append(snapshot)
    logger.info("Built %d spillover snapshot(s).", len(snapshots))
    return snapshots
