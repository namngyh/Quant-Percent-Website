import numpy as np
import pandas as pd

from raemf_mc.features.technical import build_features
from raemf_mc.regime.filtered_hmm import fit_filtered_hmm


def _prices(n: int = 240) -> pd.DataFrame:
    rng = np.random.default_rng(4)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n)))
    return pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=n),
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.integers(1000, 5000, n),
        }
    )


def test_future_prices_do_not_change_past_features():
    base = _prices()
    changed = base.copy()
    changed.loc[180:, "close"] *= 1.8
    original_features, _ = build_features(base)
    changed_features, _ = build_features(changed)
    pd.testing.assert_frame_equal(original_features.iloc[:180], changed_features.iloc[:180])


def test_future_features_do_not_change_past_filtered_probabilities():
    base = _prices()
    features, _ = build_features(base)
    returns = np.log(base["close"] / base["close"].shift(1))
    changed = features.copy()
    changed.loc[180:, "ret_1"] += 2.0
    first = fit_filtered_hmm(features, returns, np.arange(120), n_states=3, seeds=[9])
    second = fit_filtered_hmm(changed, returns, np.arange(120), n_states=3, seeds=[9])
    columns = [column for column in first.probabilities if column.startswith("hmm_prob_state_")]
    assert np.allclose(first.probabilities.loc[:179, columns], second.probabilities.loc[:179, columns])
