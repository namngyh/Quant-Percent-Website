import numpy as np
import pandas as pd

from raemf_mc.regime.filtered_hmm import fit_filtered_hmm


def test_state_probability_hmm_sum_to_one():
    rng = np.random.default_rng(1)
    x = pd.DataFrame({"ret_1": rng.normal(0, 0.01, 160), "ewma_volatility": rng.random(160) / 100, "log_return_20": rng.normal(0, 0.04, 160)})
    res = fit_filtered_hmm(x, x["ret_1"], np.arange(100), n_states=3, seeds=[1])
    cols = [c for c in res.probabilities.columns if c.startswith("hmm_prob_state_")]
    assert np.allclose(res.probabilities[cols].sum(axis=1), 1.0)
