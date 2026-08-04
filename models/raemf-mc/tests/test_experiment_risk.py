import numpy as np
import pytest

from raemf_mc.risk.experiment_risk import (
    calculate_exposure_cap,
    evaluate_distribution_risk,
    risk_multiplier,
    validate_probability_bands,
)


def _bands():
    return [
        {"max_probability": 0.25, "multiplier": 1.0},
        {"max_probability": 0.50, "multiplier": 0.6},
        {"max_probability": 1.00, "multiplier": 0.2},
    ]


def test_exposure_cap_and_monotone_risk_multiplier():
    cap = calculate_exposure_cap(
        100_000,
        0.03,
        0.10,
        portfolio_beta=1.0,
        transaction_cost_fraction=0.001,
        slippage_fraction=0.001,
        max_exposure=0.5,
    )
    assert cap == pytest.approx(0.28)
    multipliers = risk_multiplier(np.array([0.1, 0.3, 0.8]), _bands())
    assert np.all(np.diff(multipliers) <= 0)
    with pytest.raises(ValueError):
        validate_probability_bands(
            [
                {"max_probability": 0.5, "multiplier": 0.5},
                {"max_probability": 1.0, "multiplier": 0.8},
            ]
        )


def test_distribution_risk_metrics_cover_tail_and_calibration():
    realized = np.array([-0.08, -0.01, 0.01, 0.03])
    intervals = {
        level: (np.full(4, -0.10), np.full(4, 0.10))
        for level in (0.50, 0.80, 0.90, 0.95)
    }
    result = evaluate_distribution_risk(
        realized,
        intervals,
        var_95=np.full(4, -0.05),
        cvar_95=np.full(4, -0.08),
        future_mae=np.array([-0.12, -0.03, -0.01, -0.02]),
        drawdown_probabilities={
            0.05: np.full(4, 0.25),
            0.10: np.full(4, 0.25),
            0.15: np.full(4, 0.10),
            0.20: np.full(4, 0.05),
        },
        effective_sample_size=np.array([100.0, 80.0]),
        tail_estimates_by_seed=np.array([-0.10, -0.11, -0.09]),
    )
    assert result["coverage_95"] == 1.0
    assert result["var_95_exception_rate"] == 0.25
    assert result["effective_sample_size_min"] == 80.0
    assert result["tail_stability_range"] == pytest.approx(0.02)
