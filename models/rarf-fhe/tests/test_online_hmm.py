import numpy as np
import pytest

from vnindex_model.features import build_features
from vnindex_model.hmm import (
    fit_filtered_hmm,
    forward_filter,
    forward_filter_step,
    forward_filter_with_state,
)


@pytest.fixture
def fitted_hmm(synthetic_ohlcv):
    features = build_features(synthetic_ohlcv)
    result = fit_filtered_hmm(
        features, features["log_return"], features["current_drawdown"], np.arange(400), [2], [55], 50
    )
    observations = features[result.feature_names].ffill().fillna(0)
    return result, result.scaler.transform(observations)


def test_forward_filter_with_state_matches_forward_filter(fitted_hmm):
    result, scaled = fitted_hmm
    probabilities, log_alpha = forward_filter_with_state(result.model, scaled)
    assert np.allclose(probabilities, forward_filter(result.model, scaled))
    assert np.allclose(np.exp(log_alpha), probabilities[-1], atol=1e-12)


def test_stepwise_forward_filter_reproduces_batch(fitted_hmm):
    result, scaled = fitted_hmm
    baseline = forward_filter(result.model, scaled)
    _, log_alpha = forward_filter_with_state(result.model, scaled[:400])
    for position in range(400, len(scaled)):
        log_alpha, probabilities = forward_filter_step(result.model, log_alpha, scaled[position])
        assert np.allclose(probabilities, baseline[position], atol=1e-8)


def test_forward_filter_step_returns_normalized_posterior(fitted_hmm):
    result, scaled = fitted_hmm
    _, log_alpha = forward_filter_with_state(result.model, scaled[:100])
    log_alpha, probabilities = forward_filter_step(result.model, log_alpha, scaled[100])
    assert probabilities.shape == (result.model.n_components,)
    assert probabilities.sum() == pytest.approx(1.0)
    assert np.exp(log_alpha).sum() == pytest.approx(1.0)


def test_economic_order_maps_raw_filter_onto_published_probabilities(fitted_hmm):
    result, scaled = fitted_hmm
    order = np.asarray(result.diagnostics["economic_order"], dtype=int)
    assert sorted(order.tolist()) == list(range(result.model.n_components))
    columns = [f"hmm_probability_{index}" for index in range(result.model.n_components)]
    published = result.probabilities[columns].to_numpy()
    assert np.allclose(forward_filter(result.model, scaled)[:, order], published, atol=1e-12)
