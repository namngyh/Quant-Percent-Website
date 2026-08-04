import numpy as np
import pandas as pd
import pytest

from raemf_mc.models.risk_off import (
    BinaryTemperatureCalibrator,
    RiskOffHead,
    aggregate_multiclass_risk_off,
    downside_sample_weights,
)
from raemf_mc.risk.threshold_selection import select_threshold, threshold_sweep


def test_multiclass_risk_off_probability_aggregation():
    probability = np.array([[0.1, 0.2, 0.3, 0.4], [0.7, 0.1, 0.1, 0.1]])
    np.testing.assert_allclose(aggregate_multiclass_risk_off(probability), [0.7, 0.2])
    with pytest.raises(ValueError):
        aggregate_multiclass_risk_off(np.ones((2, 3)))


def test_magnitude_aware_threshold_cost_and_constraint_fallback():
    target = np.array([1, 1, 0, 0])
    probability = np.array([0.9, 0.3, 0.8, 0.1])
    forward = np.array([-0.1, -0.1, 0.2, -0.1])
    mae = np.array([-0.1, -0.4, -0.01, -0.01])
    config = {
        "start": 0.5,
        "stop": 0.5,
        "step": 0.01,
        "min_precision": 0.9,
        "min_recall": 0.9,
        "fn_cost_multiplier": 3.0,
        "fp_cost_multiplier": 1.0,
    }
    curve = threshold_sweep(target, probability, forward, mae, config)
    assert curve.loc[0, "false_negative_loss"] == pytest.approx(0.4)
    assert curve.loc[0, "false_positive_opportunity_cost"] == pytest.approx(0.2)
    assert curve.loc[0, "expected_cost"] == pytest.approx((3 * 0.4 + 0.2) / 4)
    selected = select_threshold(curve, config)
    assert not selected.constraint_satisfied
    assert selected.reason == "constraint_failure_minimum_expected_cost"


def test_severity_weighting_is_clipped_and_normalized():
    weights = downside_sample_weights(
        np.array([0, 0, 1, 1]),
        np.array([-0.01, -0.01, -0.02, -2.0]),
        np.full(4, 0.01),
        20,
        {
            "positive_cost": 2.0,
            "negative_cost": 1.0,
            "severity_lambda": 1.0,
            "severity_cap": 2.0,
            "min_weight": 0.25,
            "max_weight": 5.0,
        },
    )
    assert weights[-1] > weights[0]
    assert weights.mean() == pytest.approx(1.0)
    assert np.all(np.isfinite(weights))


def test_calibration_and_single_class_fallback_are_deterministic(tmp_path):
    target = np.array([0, 0, 0, 1, 1, 1])
    probability = np.array([0.05, 0.15, 0.8, 0.2, 0.85, 0.95])
    first = BinaryTemperatureCalibrator().fit(probability, target)
    second = BinaryTemperatureCalibrator().fit(probability, target)
    assert first.temperature == second.temperature
    np.testing.assert_allclose(first.transform(probability), second.transform(probability))

    features = pd.DataFrame({"x": [0.0, 1.0, 2.0]})
    with pytest.warns(RuntimeWarning, match="one class"):
        model = RiskOffHead("logistic", random_state=4).fit(features, np.ones(3, dtype=int))
    np.testing.assert_allclose(model.predict_proba(features), model.predict_proba(features))
    destination = model.save(tmp_path / "head.joblib")
    loaded = RiskOffHead.load(destination)
    np.testing.assert_allclose(model.predict_proba(features), loaded.predict_proba(features))
