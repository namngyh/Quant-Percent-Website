import numpy as np

from raemf_mc.evaluation.distribution import evaluate_distribution_forecast, evaluate_point_forecast
from raemf_mc.evaluation.risk_backtests import christoffersen_conditional_coverage_test, kupiec_test


def test_distribution_metrics_are_finite_and_coverage_is_bounded():
    rng = np.random.default_rng(4)
    realized = rng.normal(0, 0.01, size=30)
    samples = rng.normal(realized[:, None], 0.01, size=(30, 200))
    summary, rows = evaluate_distribution_forecast(realized, samples)
    assert np.isfinite(list(summary.values())).all()
    assert rows["pit"].between(0, 1).all()
    assert all(0 <= summary[f"coverage_{level}"] <= 1 for level in (50, 80, 90, 95))


def test_point_forecast_metrics():
    metrics = evaluate_point_forecast(np.array([0.01, -0.02]), np.array([0.02, -0.01]))
    assert np.isclose(metrics["mae"], 0.01)
    assert metrics["directional_accuracy"] == 1.0


def test_var_coverage_tests_return_valid_p_values():
    hits = np.array([0] * 18 + [1] + [0] * 20 + [1] + [0] * 10)
    kupiec = kupiec_test(hits, 0.05)
    conditional = christoffersen_conditional_coverage_test(hits, 0.05)
    assert 0 <= kupiec["p_value_uc"] <= 1
    assert 0 <= conditional["p_value_conditional_coverage"] <= 1
