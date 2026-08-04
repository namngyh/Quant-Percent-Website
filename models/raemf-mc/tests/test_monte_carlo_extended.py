import numpy as np

from raemf_mc.simulation.reweighting import effective_sample_size
from raemf_mc.simulation.structural_mc import simulate_paths_detailed


def _simulate(current, **kwargs):
    return simulate_paths_detailed(
        100.0,
        np.asarray(current, dtype=float),
        np.eye(2),
        np.array([0.01, -0.01]),
        1e-5,
        5,
        500,
        11,
        state_volatility=np.array([0.01, 0.02]),
        egarch_params={"omega": -0.1, "alpha[1]": 0.1, "gamma[1]": -0.05, "beta[1]": 0.9, "nu": 9.0},
        nu=9.0,
        state_to_class=np.array([0, 3]),
        **kwargs,
    )


def test_state_dependent_mean_changes_distribution():
    expansion = _simulate([1.0, 0.0])
    contraction = _simulate([0.0, 1.0])
    assert expansion.summary.loc[0, "expected_return"] > 0
    assert contraction.summary.loc[0, "expected_return"] < 0


def test_recursive_volatility_parameters_change_paths_and_fitted_nu_is_used():
    first = _simulate([0.5, 0.5])
    second = simulate_paths_detailed(
        100.0,
        np.array([0.5, 0.5]),
        np.eye(2),
        np.array([0.01, -0.01]),
        0.01,
        5,
        500,
        11,
        state_volatility=np.array([0.01, 0.02]),
        egarch_params={"omega": -0.5, "alpha[1]": 0.4, "gamma[1]": -0.2, "beta[1]": 0.5, "nu": 13.0},
        nu=13.0,
        state_to_class=np.array([0, 3]),
    )
    assert not np.allclose(first.paths, second.paths)
    assert second.summary.loc[0, "student_t_nu"] == 13.0


def test_ebm_probability_reweighting_and_ess():
    simulation = _simulate([0.5, 0.5], target_class_probabilities=np.array([0.92, 0.02, 0.02, 0.04]))
    states = simulation.state_distribution.set_index("state")
    assert states.loc[0, "weighted_probability"] > states.loc[0, "raw_probability"]
    assert np.isclose(simulation.summary.loc[0, "ess"], effective_sample_size(simulation.weights))
    assert simulation.summary.loc[0, "ess"] <= len(simulation.weights) + 1e-8


def test_lightweight_mode_preserves_terminal_distribution():
    regular = _simulate([0.5, 0.5])
    lightweight = _simulate([0.5, 0.5], lightweight=True)
    assert np.array_equal(regular.terminal_returns, lightweight.terminal_returns)
    assert np.array_equal(regular.weights, lightweight.weights)
    assert lightweight.quantiles.empty
