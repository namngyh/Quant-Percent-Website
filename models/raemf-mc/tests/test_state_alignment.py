import numpy as np
import pandas as pd

from raemf_mc.regime.state_alignment import align_states


def test_state_alignment_is_stable_to_raw_state_permutation():
    rng = np.random.default_rng(3)
    hard = np.repeat(np.arange(4), 60)
    probabilities = np.full((240, 4), 0.01)
    probabilities[np.arange(240), hard] = 0.97
    means = np.array([0.002, 0.0001, -0.001, -0.004])
    returns = pd.Series(means[hard] + rng.normal(0, np.array([0.005, 0.003, 0.007, 0.025])[hard]))
    first = align_states(probabilities, returns, np.arange(240)).mapping
    permutation = np.array([2, 0, 3, 1])
    second = align_states(probabilities[:, permutation], returns, np.arange(240)).mapping
    first_means = first.set_index("economic_label")["mean_return"].sort_index()
    second_means = second.set_index("economic_label")["mean_return"].sort_index()
    assert np.allclose(first_means, second_means)
