"""Capital allocation: turn the estimated dependence structure into weights.

This package answers a different question from `models/`. The predictive layer
asked "will the market be stressed in h days?" and the walk-forward evaluation
answered no -- expected returns are not estimable from this data. Allocation
asks "given that returns are unforecastable, how should capital be spread?",
which depends on the covariance matrix rather than on the mean vector.

That distinction matters because covariance is a far easier estimation problem:
realised correlation structure is persistent across months, whereas the
signal-to-noise ratio of expected returns is close to zero. A graph layer that
fails at the first task may still succeed at the second, and the two claims must
be tested separately.
"""

from dynamicgraph.allocation.covariance import (
    COVARIANCE_ESTIMATORS,
    estimate_allocation_covariance,
)
from dynamicgraph.allocation.diagnostics import (
    diversification_ratio,
    effective_number_of_bets,
    weight_concentration,
)
from dynamicgraph.allocation.portfolios import (
    PORTFOLIO_RULES,
    build_weights,
    equal_weight,
    inverse_volatility,
    minimum_variance,
    risk_parity,
)

__all__ = [
    "COVARIANCE_ESTIMATORS",
    "PORTFOLIO_RULES",
    "build_weights",
    "diversification_ratio",
    "effective_number_of_bets",
    "equal_weight",
    "estimate_allocation_covariance",
    "inverse_volatility",
    "minimum_variance",
    "risk_parity",
    "weight_concentration",
]
