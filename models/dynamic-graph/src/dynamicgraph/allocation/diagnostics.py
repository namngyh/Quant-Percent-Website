r"""How diversified is a portfolio, really?

Counting positions overstates diversification whenever the positions are
correlated, which in a 30-name single-country index they always are. These three
measures say different things and are reported together on purpose:

`weight_concentration`
    ignores the covariance entirely -- it is the naive count, `1 / sum(w^2)`.
`diversification_ratio`
    weighted average volatility divided by portfolio volatility. Equals 1 when
    everything is perfectly correlated.
`effective_number_of_bets`
    the entropy of risk spread across principal components. This is the strict
    one: it counts *independent* sources of risk, so it collapses toward 1 when a
    single market factor dominates no matter how many names are held.
"""

from __future__ import annotations

import numpy as np

from dynamicgraph.constants import EPS


def weight_concentration(weights: np.ndarray) -> float:
    """Inverse Herfindahl index of the weights -- the naive effective count."""
    weights = np.asarray(weights, dtype=float)
    total = float((weights**2).sum())
    return float(1.0 / total) if total > EPS else np.nan


def diversification_ratio(weights: np.ndarray, covariance: np.ndarray) -> float:
    """`(w' sigma) / sqrt(w' Sigma w)`; 1.0 means no diversification benefit."""
    weights = np.asarray(weights, dtype=float)
    covariance = np.asarray(covariance, dtype=float)
    deviation = np.sqrt(np.clip(np.diag(covariance), EPS, None))
    portfolio_variance = float(weights @ covariance @ weights)
    if portfolio_variance <= EPS:
        return np.nan
    return float((weights @ deviation) / np.sqrt(portfolio_variance))


def effective_number_of_bets(weights: np.ndarray, covariance: np.ndarray) -> float:
    r"""Exponential entropy of the principal-component risk decomposition.

    With eigenpairs `(lambda_k, v_k)` of `Sigma`, the share of portfolio variance
    carried by component `k` is

        p_k = lambda_k (v_k' w)^2 / (w' Sigma w),

    and the effective number of bets is `exp(-sum p_k log p_k)`. A portfolio
    whose risk sits entirely in the first principal component scores 1 regardless
    of how many names it holds.
    """
    weights = np.asarray(weights, dtype=float)
    covariance = np.asarray(covariance, dtype=float)
    portfolio_variance = float(weights @ covariance @ weights)
    if portfolio_variance <= EPS:
        return np.nan

    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.clip(eigenvalues, 0.0, None)
    projections = eigenvectors.T @ weights
    contributions = eigenvalues * projections**2
    total = contributions.sum()
    if total <= EPS:
        return np.nan
    shares = contributions / total
    shares = shares[shares > EPS]
    entropy = float(-(shares * np.log(shares)).sum())
    return float(np.exp(entropy))


def risk_contributions(weights: np.ndarray, covariance: np.ndarray) -> np.ndarray:
    """Per-asset share of portfolio variance, `w_i (Sigma w)_i / (w' Sigma w)`."""
    weights = np.asarray(weights, dtype=float)
    covariance = np.asarray(covariance, dtype=float)
    marginal = covariance @ weights
    total = float(weights @ marginal)
    if total <= EPS:
        return np.full(weights.size, np.nan)
    return weights * marginal / total


def portfolio_diagnostics(weights: np.ndarray, covariance: np.ndarray) -> dict[str, float]:
    """All four diagnostics at once, for one rebalance date."""
    contributions = risk_contributions(weights, covariance)
    finite = contributions[np.isfinite(contributions)]
    return {
        "effective_n_weights": weight_concentration(weights),
        "effective_n_bets": effective_number_of_bets(weights, covariance),
        "diversification_ratio": diversification_ratio(weights, covariance),
        "max_weight": float(np.max(weights)) if weights.size else np.nan,
        "max_risk_contribution": float(np.max(finite)) if finite.size else np.nan,
        "ex_ante_volatility_annual": float(
            np.sqrt(max(float(weights @ covariance @ weights), 0.0) * 252.0)
        ),
    }
