"""Forward target construction."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.features.targets import (
    build_targets,
    future_drawdown,
    future_realized_volatility,
    future_return,
    label_by_train_quantile,
    label_volatility_regime,
    stress_events,
)


def test_future_drawdown_formula():
    prices = pd.Series([100.0, 90.0, 95.0, 80.0, 120.0])
    drawdown = future_drawdown(prices, 3)
    # From t=0, min over t=1..3 is 80 -> 80/100 - 1 = -0.20
    assert drawdown.iloc[0] == pytest.approx(-0.20)
    # From t=1, min over t=2..4 is 80 -> 80/90 - 1
    assert drawdown.iloc[1] == pytest.approx(80 / 90 - 1)
    assert np.isnan(drawdown.iloc[-1])


def test_future_drawdown_is_non_positive_when_prices_only_fall():
    prices = pd.Series(np.linspace(100, 50, 40))
    drawdown = future_drawdown(prices, 10).dropna()
    assert (drawdown < 0).all()


def test_future_drawdown_is_zero_when_prices_only_rise():
    prices = pd.Series(np.linspace(50, 100, 40))
    drawdown = future_drawdown(prices, 10).dropna()
    assert (drawdown > 0).all()          # min future price still exceeds P_t


def test_future_drawdown_excludes_the_current_date():
    """A crash at t itself must not appear in the target dated t."""
    prices = pd.Series([100.0, 50.0, 51.0, 52.0, 53.0])
    drawdown = future_drawdown(prices, 2)
    # From t=1 (price 50) the future is 51, 52 -> positive, not the -50% at t=1.
    assert drawdown.iloc[1] > 0


def test_future_return_is_log_and_signed():
    prices = pd.Series([100.0, 110.0, 121.0])
    result = future_return(prices, 2)
    assert result.iloc[0] == pytest.approx(np.log(121 / 100))


def test_future_realized_volatility_annualises():
    returns = pd.Series([0.01] * 60)
    volatility = future_realized_volatility(returns, 20)
    assert volatility.iloc[0] == pytest.approx(np.sqrt(252 / 20 * 20 * 0.01**2))


def test_targets_have_the_expected_columns(synthetic_panel, base_config):
    targets = build_targets(synthetic_panel, base_config, "VN30")
    for horizon in base_config.targets.horizons:
        assert f"future_drawdown_{horizon}d" in targets.forward.columns
        assert f"future_return_{horizon}d" in targets.forward.columns
        assert f"future_volatility_{horizon}d" in targets.forward.columns
        assert f"stress_abs_{horizon}d" in targets.labels.columns


def test_absolute_labels_are_binary(synthetic_panel, base_config):
    targets = build_targets(synthetic_panel, base_config, "VN30")
    for column in targets.labels.columns:
        values = targets.labels[column].dropna().unique()
        assert set(values).issubset({0.0, 1.0})


def test_longer_horizons_have_higher_positive_rates(synthetic_panel, base_config):
    """More time to fall -> more stress days, for a fixed threshold family."""
    targets = build_targets(synthetic_panel, base_config, "VN30")
    rate_5 = targets.labels["stress_abs_5d"].mean()
    rate_40 = targets.labels["stress_abs_40d"].mean()
    assert rate_40 > rate_5


def test_node_targets_are_built(synthetic_panel, base_config):
    targets = build_targets(synthetic_panel, base_config, "VN30", build_node_targets=True)
    assert targets.node_forward is not None
    assert "future_drawdown_20d" in targets.node_forward.columns
    assert targets.node_forward.index.names == ["date", "ticker"]


def test_quantile_labels_hit_the_requested_rate():
    rng = np.random.default_rng(41)
    values = pd.Series(rng.normal(-0.02, 0.05, 1000))
    train_mask = pd.Series([True] * 700 + [False] * 300, index=values.index)
    labels, threshold = label_by_train_quantile(values, train_mask, 0.10)
    train_rate = labels[train_mask].mean()
    assert train_rate == pytest.approx(0.10, abs=0.02)
    assert threshold == pytest.approx(np.quantile(values[train_mask], 0.10), rel=1e-9)


def test_volatility_regime_label_uses_the_upper_tail():
    rng = np.random.default_rng(42)
    volatility = pd.Series(np.abs(rng.normal(0.2, 0.08, 800)))
    train_mask = pd.Series([True] * 600 + [False] * 200, index=volatility.index)
    labels, threshold = label_volatility_regime(volatility, train_mask, 0.90)
    assert labels[train_mask].mean() == pytest.approx(0.10, abs=0.03)
    assert (volatility[labels == 1] >= threshold).all()


def test_stress_events_collapse_consecutive_days():
    index = pd.bdate_range("2020-01-01", periods=100)
    labels = pd.Series(0.0, index=index)
    labels.iloc[10:20] = 1.0
    labels.iloc[60:65] = 1.0
    events = stress_events(labels, min_gap_days=20)
    assert len(events) == 2
    assert events[0][0] == index[10]
    assert events[0][1] == index[19]


def test_stress_events_merge_when_close_together():
    index = pd.bdate_range("2020-01-01", periods=100)
    labels = pd.Series(0.0, index=index)
    labels.iloc[10:15] = 1.0
    labels.iloc[18:22] = 1.0        # gap of 3 days < min_gap 20
    assert len(stress_events(labels, min_gap_days=20)) == 1


def test_empty_training_slice_raises():
    values = pd.Series([1.0, 2.0, 3.0])
    with pytest.raises(ValueError):
        label_by_train_quantile(values, pd.Series([False, False, False]), 0.1)
