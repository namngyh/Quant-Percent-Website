import numpy as np

from raemf_mc.simulation.structural_mc import simulate_paths


def test_monte_carlo_repeats_with_same_seed():
    args = (100.0, np.array([0.6, 0.4]), np.array([[0.9, 0.1], [0.2, 0.8]]), np.array([0.001, -0.001]), 0.01, 20, 100, 17)
    first, summary_first = simulate_paths(*args)
    second, summary_second = simulate_paths(*args)
    assert np.array_equal(first, second)
    assert summary_first.equals(summary_second)
