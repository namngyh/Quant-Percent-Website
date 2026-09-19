import numpy as np
import pandas as pd
import pytest

from vnindex_model.features import build_features
from vnindex_model.volatility import egarch_step, ewma_volatility_fallback, fit_egarch_student_t


@pytest.fixture
def fitted_volatility(synthetic_ohlcv):
    returns = build_features(synthetic_ohlcv)["log_return"]
    return returns.fillna(0.0).astype(float), fit_egarch_student_t(returns, np.arange(400))


def test_batch_fit_uses_a_recursive_parametric_branch(fitted_volatility):
    _, result = fitted_volatility
    assert not str(result.diagnostics["model"]).startswith("EWMA")


def test_stepwise_egarch_reproduces_batch_log_variance(fitted_volatility):
    values, result = fitted_volatility
    parameters = result.diagnostics["parameters"]
    model_name = str(result.diagnostics["model"])
    sigma = result.features["egarch_conditional_volatility"].to_numpy(dtype=float)
    log_variance = np.log(np.square(sigma * 100))
    for row in range(1, len(values)):
        stepped, standardized = egarch_step(
            parameters, float(log_variance[row - 1]), float(values.iloc[row - 1] * 100), model_name
        )
        assert stepped == pytest.approx(log_variance[row], abs=1e-10)
        assert standardized == pytest.approx(result.standardized_residuals[row - 1], abs=1e-10)


def test_egarch_step_follows_the_documented_recursion():
    parameters = {"omega": -0.1, "alpha[1]": 0.2, "gamma[1]": -0.05, "beta[1]": 0.9, "mu": 0.05}
    log_variance_previous = 0.5
    previous_return_percent = 1.25
    standardized_expected = (previous_return_percent - 0.05) / np.sqrt(np.exp(log_variance_previous))
    expected = (
        -0.1 + 0.9 * 0.5 + 0.2 * (abs(standardized_expected) - 0.8) + (-0.05) * standardized_expected
    )
    stepped, standardized = egarch_step(parameters, log_variance_previous, previous_return_percent, "EGARCH(1,1) Student-t")
    assert standardized == pytest.approx(standardized_expected)
    assert stepped == pytest.approx(expected)


def test_garch_step_follows_the_variance_recursion():
    parameters = {"omega": 0.02, "alpha[1]": 0.1, "beta[1]": 0.85, "mu": 0.0}
    variance = 0.02 + 0.1 * 1.5**2 + 0.85 * np.exp(0.4)
    stepped, _ = egarch_step(parameters, 0.4, 1.5, "GARCH(1,1) Student-t")
    assert stepped == pytest.approx(np.log(variance))


def test_egarch_step_clips_extreme_log_variance():
    parameters = {"omega": 500.0, "alpha[1]": 0.0, "gamma[1]": 0.0, "beta[1]": 0.9, "mu": 0.0}
    stepped, _ = egarch_step(parameters, 0.0, 0.0, "EGARCH(1,1) Student-t")
    assert stepped == 20.0


def test_ewma_fallback_helper_matches_the_inline_batch_expression():
    rng = np.random.default_rng(11)
    values = pd.Series(rng.normal(0, 0.01, 300))
    expected = (
        values.ewm(span=40, adjust=False, min_periods=5)
        .std()
        .fillna(values.expanding(2).std())
        .fillna(1e-4)
        .clip(lower=1e-6)
        .to_numpy()
    )
    assert np.allclose(ewma_volatility_fallback(values), expected, equal_nan=True)
