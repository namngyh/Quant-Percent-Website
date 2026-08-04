"""Optional Variational Bayesian scenario layer.

PyMC and ArviZ are imported lazily by :class:`VariationalScenarioModel`, so
the original RAEMF-MC pipeline has no Bayesian runtime dependency when the
feature is disabled.
"""

from raemf_mc.bayesian.variational import VariationalPosteriorResult, VariationalScenarioModel


def create_scenario_model(config=None):
    """Lazy factory so importing this package never pulls torch or PyMC."""
    from raemf_mc.bayesian.model import create_scenario_model as _factory

    return _factory(config)


__all__ = ["VariationalPosteriorResult", "VariationalScenarioModel", "create_scenario_model"]
