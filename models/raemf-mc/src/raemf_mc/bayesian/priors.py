"""Prior specifications shared by the PyTorch and PyMC Bayesian backends.

Two prior families are supported for the regime-conditional scenario model:

* ``independent`` — the original RAEMF-MC priors: each regime drift and log
  volatility multiplier has its own zero-centred Normal prior.
* ``hierarchical`` — partial pooling: regime drifts shrink towards a global
  drift with a HalfNormal-scaled spread, and log multipliers shrink towards
  a global log multiplier. The Student-t tail is ``nu = 2 + Exponential``.

All densities are defined on the *standardized* return scale (returns divided
by the train standard deviation), matching both backends.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScenarioPriors:
    hierarchical: bool
    # independent-family scales
    mu_scale: float
    log_c_sd: float
    # hierarchical-family scales
    mu_global_sd: float
    mu_tau_sd: float
    log_c_global_sd: float
    log_c_tau_sd: float
    # shared tail
    nu_rate: float
    shared_nu: bool

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "ScenarioPriors":
        priors = dict(cfg.get("priors", {}))
        return cls(
            hierarchical=bool(cfg.get("hierarchical", False)),
            mu_scale=float(cfg.get("prior_mu_scale", 0.5)),
            log_c_sd=float(cfg.get("prior_log_scale_sd", 0.3)),
            mu_global_sd=float(priors.get("mu_global_sd", 0.25)),
            mu_tau_sd=float(priors.get("mu_tau_sd", 0.25)),
            log_c_global_sd=float(priors.get("log_c_global_sd", 0.25)),
            log_c_tau_sd=float(priors.get("log_c_tau_sd", 0.20)),
            nu_rate=float(priors.get("nu_rate", cfg.get("prior_nu_rate", 0.1))),
            shared_nu=bool(cfg.get("shared_nu", True)),
        )

    def validate(self) -> None:
        for name in ("mu_scale", "log_c_sd", "mu_global_sd", "mu_tau_sd", "log_c_global_sd", "log_c_tau_sd", "nu_rate"):
            if getattr(self, name) <= 0:
                raise ValueError(f"Prior hyperparameter {name} must be positive")

    def n_parameters(self, n_regimes: int) -> int:
        """Dimension of the unconstrained parameter vector."""
        nu_dim = 1 if self.shared_nu else n_regimes
        if self.hierarchical:
            # mu_global, log_tau_mu, mu_k..., log_c_global, log_tau_c, log_c_k..., nu raw
            return 2 + n_regimes + 2 + n_regimes + nu_dim
        return n_regimes + n_regimes + nu_dim
