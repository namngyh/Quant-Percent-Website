import numpy as np
import pandas as pd

from raemf_mc.risk.egarch_t import fit_egarch_features


def test_egarch_filter_outputs_positive_sigma():
    rng = np.random.default_rng(2)
    ret = pd.Series(rng.normal(0, 0.01, 180))
    res = fit_egarch_features(ret, np.arange(120))
    assert (res.features["egarch_sigma"] > 0).all()
