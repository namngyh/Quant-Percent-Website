r"""Weight construction rules.

Every rule here is a function of the covariance matrix alone. None of them takes
an expected-return vector, and that is deliberate: the walk-forward evaluation
in `training/` established that this data does not support return forecasting,
so a rule that needed `mu` would be building on a result we disproved.

The rules span a deliberate range of how much dependence structure they use:

`equal_weight`
    uses nothing. The benchmark that is famously hard to beat.
`inverse_volatility`
    uses the diagonal only.
`risk_parity`
    uses the full matrix, equalising each asset's marginal risk contribution.
`minimum_variance`
    uses the full matrix and is the most sensitive to estimation error -- it is
    where a better covariance estimate should show up first, and also where a
    worse one does the most damage.
`community_risk_parity`
    uses the graph's community partition to build risk-parity sleeves inside
    communities and then equalise risk across sleeve returns. This is the only
    rule whose input the network layer uniquely provides.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

import numpy as np

from dynamicgraph.constants import EPS
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

PORTFOLIO_RULES: tuple[str, ...] = (
    "equal_weight",
    "inverse_volatility",
    "risk_parity",
    "minimum_variance",
    "community_risk_parity",
)


def _validate(covariance: np.ndarray) -> np.ndarray:
    covariance = np.asarray(covariance, dtype=float)
    if covariance.ndim != 2 or covariance.shape[0] != covariance.shape[1]:
        raise ValueError("`covariance` must be a square matrix.")
    return 0.5 * (covariance + covariance.T)


def _normalize(weights: np.ndarray) -> np.ndarray:
    weights = np.clip(np.asarray(weights, dtype=float), 0.0, None)
    total = weights.sum()
    if total <= EPS:
        return np.full(weights.size, 1.0 / weights.size)
    return weights / total


def equal_weight(covariance: np.ndarray, **_: Any) -> np.ndarray:
    n = _validate(covariance).shape[0]
    return np.full(n, 1.0 / n)


def inverse_volatility(covariance: np.ndarray, **_: Any) -> np.ndarray:
    deviation = np.sqrt(np.clip(np.diag(_validate(covariance)), EPS, None))
    return _normalize(1.0 / deviation)


def minimum_variance(
    covariance: np.ndarray,
    max_weight: float = 0.20,
    min_weight: float = 0.0,
    **_: Any,
) -> np.ndarray:
    r"""Long-only minimum-variance weights.

        min_w  w' Sigma w   s.t.  sum(w) = 1,  min_weight <= w_i <= max_weight

    The box constraint is not cosmetic. Unconstrained minimum variance on an
    estimated covariance concentrates into whichever assets the estimation error
    happened to make look uncorrelated, which is why the textbook version
    underperforms so reliably out of sample. Capping at `max_weight` is the
    standard remedy and is applied identically to every estimator, so the
    comparison between them stays fair.
    """
    covariance = _validate(covariance)
    n = covariance.shape[0]
    cap = float(max(max_weight, 1.0 / n))
    floor = float(np.clip(min_weight, 0.0, 1.0 / n))

    try:
        from scipy.optimize import minimize

        result = minimize(
            fun=lambda w: float(w @ covariance @ w),
            x0=np.full(n, 1.0 / n),
            jac=lambda w: 2.0 * covariance @ w,
            method="SLSQP",
            bounds=[(floor, cap)] * n,
            constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
            options={"maxiter": 200, "ftol": 1e-12},
        )
        if result.success and np.all(np.isfinite(result.x)):
            return _normalize(np.clip(result.x, floor, cap))
        logger.debug("SLSQP minimum variance did not converge: %s", result.message)
    except ImportError:
        logger.debug("SciPy unavailable; using the projected-gradient fallback.")

    return _projected_gradient_min_variance(covariance, floor, cap)


def _projected_gradient_min_variance(
    covariance: np.ndarray, floor: float, cap: float, n_iter: int = 2000
) -> np.ndarray:
    """Fallback optimiser so the module works without SciPy."""
    n = covariance.shape[0]
    weights = np.full(n, 1.0 / n)
    step = 1.0 / (2.0 * max(float(np.linalg.eigvalsh(covariance).max()), EPS))
    for _ in range(n_iter):
        gradient = 2.0 * covariance @ weights
        candidate = _project_to_capped_simplex(weights - step * gradient, floor, cap)
        if np.abs(candidate - weights).max() < 1e-12:
            weights = candidate
            break
        weights = candidate
    return weights


def _project_to_capped_simplex(
    vector: np.ndarray, floor: float, cap: float, tolerance: float = 1e-12
) -> np.ndarray:
    """Euclidean projection onto {w : sum(w)=1, floor <= w <= cap} by bisection."""
    vector = np.asarray(vector, dtype=float)
    _validate_constraint_feasibility(vector.size, floor, cap, tolerance)
    low, high = float(vector.min() - cap), float(vector.max() - floor)
    for _ in range(100):
        theta = 0.5 * (low + high)
        clipped = np.clip(vector - theta, floor, cap)
        total = clipped.sum()
        if abs(total - 1.0) < tolerance:
            break
        if total > 1.0:
            low = theta
        else:
            high = theta
    return np.clip(vector - theta, floor, cap)


def _validate_constraint_feasibility(
    n_assets: int,
    floor: float,
    cap: float,
    tolerance: float = 1e-12,
) -> None:
    """Reject a box-simplex intersection that has no feasible portfolio."""
    if n_assets <= 0:
        raise ValueError("At least one asset is required.")
    if not np.isfinite(floor) or not np.isfinite(cap):
        raise ValueError("Weight bounds must be finite.")
    if floor < 0.0 or cap > 1.0 or floor > cap:
        raise ValueError("Weight bounds must satisfy 0 <= min_weight <= max_weight <= 1.")
    if n_assets * floor > 1.0 + tolerance:
        raise ValueError(
            f"Infeasible min_weight={floor:g}: {n_assets} assets require total floor "
            f"{n_assets * floor:g} > 1."
        )
    if n_assets * cap < 1.0 - tolerance:
        raise ValueError(
            f"Infeasible max_weight={cap:g}: {n_assets} assets provide total capacity "
            f"{n_assets * cap:g} < 1."
        )


def risk_parity(
    covariance: np.ndarray,
    budgets: np.ndarray | None = None,
    n_iter: int = 500,
    tolerance: float = 1e-10,
    **_: Any,
) -> np.ndarray:
    r"""Equal-risk-contribution weights by cyclical coordinate descent.

    Solves for `y > 0` with `y_i (Sigma y)_i = b_i`. Each coordinate update is
    the positive root of

        Sigma_ii y_i^2 + y_i * sum_{j != i} Sigma_ij y_j - b_i = 0,

    which is the standard Spinu / Griveau-Billion formulation and converges
    monotonically for any positive-definite `Sigma`.

    The iteration runs on the **unnormalised** `y`. Rescaling to sum to one
    inside the loop would break the fixed point: the budget equation is not
    scale-invariant, so a sweep that renormalises never reaches equal risk
    contributions and quietly returns something close to inverse volatility
    instead. Normalisation happens once, at the end, where it is harmless
    because risk contributions are scale-invariant.
    """
    covariance = _validate(covariance)
    n = covariance.shape[0]
    budget = (
        np.full(n, 1.0 / n)
        if budgets is None
        else _normalize(np.asarray(budgets, dtype=float))
    )

    deviation = np.sqrt(np.clip(np.diag(covariance), EPS, None))
    weights = _normalize(1.0 / deviation)
    for _ in range(n_iter):
        previous = _normalize(weights)
        for i in range(n):
            a = float(covariance[i, i])
            if a <= EPS:
                continue
            b = float(covariance[i] @ weights) - a * weights[i]
            c = -float(budget[i])
            weights[i] = (-b + np.sqrt(max(b * b - 4.0 * a * c, 0.0))) / (2.0 * a)
        if np.abs(_normalize(weights) - previous).max() < tolerance:
            break
    return _normalize(weights)


def community_risk_parity(
    covariance: np.ndarray,
    communities: Sequence[int] | None = None,
    **_: Any,
) -> np.ndarray:
    """Hierarchical equal-risk allocation within and across communities.

    Naive equal weighting across 30 VN30 tickers is not 30 independent bets when
    a dozen of them form one banking cluster. This rule spends the risk budget
    across the *clusters* the graph found, which is the allocation-side use of
    community detection.

    Falls back to plain inverse volatility when no partition is supplied, so a
    missing community label degrades the rule rather than breaking the run.
    """
    covariance = _validate(covariance)
    n = covariance.shape[0]
    if communities is None or len(communities) != n:
        return inverse_volatility(covariance)

    labels = np.asarray(communities)
    unique = np.unique(labels)
    if unique.size <= 1:
        return inverse_volatility(covariance)

    # First form a risk-parity sleeve inside every community.
    sleeves = np.zeros((n, unique.size))
    for column, label in enumerate(unique):
        positions = np.flatnonzero(labels == label)
        local = risk_parity(covariance[np.ix_(positions, positions)])
        sleeves[positions, column] = local

    # Then equalise risk between the sleeve returns. This is materially
    # different from assigning equal *capital* to each cluster when clusters
    # have different sizes or covariance structures.
    sleeve_covariance = sleeves.T @ covariance @ sleeves
    sleeve_weights = risk_parity(sleeve_covariance)
    return _normalize(sleeves @ sleeve_weights)


_RULES: Mapping[str, Callable[..., np.ndarray]] = {
    "equal_weight": equal_weight,
    "inverse_volatility": inverse_volatility,
    "risk_parity": risk_parity,
    "minimum_variance": minimum_variance,
    "community_risk_parity": community_risk_parity,
}


def build_weights(rule: str, covariance: np.ndarray, **kwargs: Any) -> np.ndarray:
    """Dispatch to a named rule, returning long-only weights summing to one."""
    covariance = _validate(covariance)
    n = covariance.shape[0]
    cap = float(kwargs.get("max_weight", 1.0))
    floor = float(kwargs.get("min_weight", 0.0))
    _validate_constraint_feasibility(n, floor, cap)
    try:
        function = _RULES[str(rule)]
    except KeyError:
        raise ValueError(
            f"Unknown portfolio rule `{rule}`; expected one of {tuple(_RULES)}."
        ) from None
    weights = _normalize(function(covariance, **kwargs))
    if not np.all(np.isfinite(weights)):
        logger.warning("Rule `%s` produced non-finite weights; falling back to equal weight.", rule)
        weights = equal_weight(covariance)
    projected = _project_to_capped_simplex(weights, floor, cap)
    if (
        not np.isclose(projected.sum(), 1.0, atol=1e-10)
        or (projected < floor - 1e-10).any()
        or (projected > cap + 1e-10).any()
    ):
        raise ArithmeticError("Capped-simplex projection violated the allocation constraints.")
    return projected
