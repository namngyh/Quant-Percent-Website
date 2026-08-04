import numpy as np

from raemf_mc.simulation.structural_mc import simulate_paths


def test_monte_carlo_no_negative_prices_and_var_order():
    paths, summary = simulate_paths(1000, np.array([0.5, 0.5]), np.array([[0.9, 0.1], [0.2, 0.8]]), np.array([0.001, -0.001]), 0.01, 20, 100, 1)
    assert (paths > 0).all()
    assert summary.loc[0, "cvar_95"] >= summary.loc[0, "var_95"]
