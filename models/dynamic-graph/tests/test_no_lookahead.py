"""Look-ahead leakage tests.

The strategy is empirical rather than by inspection: perturb the future, then
assert that no past value moves. A feature that silently uses `P_{t+1}` fails
immediately.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.features import returns as R
from dynamicgraph.features.market_features import build_market_features
from dynamicgraph.features.node_features import build_node_features
from dynamicgraph.features.residualization import residualize_returns, rolling_beta
from dynamicgraph.features.targets import build_targets, label_by_train_quantile


def _perturb_tail(panel: pd.DataFrame, cut: pd.Timestamp, factor: float = 1.5) -> pd.DataFrame:
    """Multiply every price after `cut` by `factor`."""
    out = panel.copy()
    mask = out["date"] > cut
    for column in ("open", "high", "low", "close", "adjusted_close"):
        out.loc[mask, column] = out.loc[mask, column] * factor
    return out


def test_log_return_does_not_use_future(synthetic_returns: pd.DataFrame):
    """r_t = log(P_t / P_{t-1}) must be unchanged by anything after t."""
    prices = pd.DataFrame(
        np.exp(np.cumsum(synthetic_returns.to_numpy(), axis=0)), index=synthetic_returns.index,
        columns=synthetic_returns.columns,
    )
    baseline = R.compute_log_returns(prices, 1)

    perturbed = prices.copy()
    perturbed.iloc[500:] *= 2.0
    after = R.compute_log_returns(perturbed, 1)

    pd.testing.assert_frame_equal(baseline.iloc[:500], after.iloc[:500])


@pytest.mark.parametrize("window", [5, 20, 60])
def test_rolling_features_do_not_use_future(synthetic_returns: pd.DataFrame, window: int):
    baseline = R.rolling_volatility(synthetic_returns, window)
    perturbed = synthetic_returns.copy()
    perturbed.iloc[800:] *= 3.0
    after = R.rolling_volatility(perturbed, window)
    pd.testing.assert_frame_equal(baseline.iloc[:800], after.iloc[:800])


def test_drawdown_uses_only_past_peak(synthetic_returns: pd.DataFrame):
    prices = pd.DataFrame(
        np.exp(np.cumsum(synthetic_returns.to_numpy(), axis=0)), index=synthetic_returns.index,
        columns=synthetic_returns.columns,
    )
    baseline = R.drawdown_series(prices)
    perturbed = prices.copy()
    perturbed.iloc[600:] *= 5.0          # a huge future peak
    after = R.drawdown_series(perturbed)
    pd.testing.assert_frame_equal(baseline.iloc[:600], after.iloc[:600])


def test_rolling_beta_does_not_use_future(synthetic_returns: pd.DataFrame):
    market = synthetic_returns.mean(axis=1)
    _, baseline = rolling_beta(synthetic_returns, market, 60)

    perturbed_market = market.copy()
    perturbed_market.iloc[700:] *= 4.0
    _, after = rolling_beta(synthetic_returns, perturbed_market, 60)

    pd.testing.assert_frame_equal(baseline.iloc[:700], after.iloc[:700])


def test_residual_returns_do_not_use_future(synthetic_returns: pd.DataFrame):
    market = synthetic_returns.mean(axis=1)
    baseline = residualize_returns(synthetic_returns, market, window=60).residuals

    perturbed = synthetic_returns.copy()
    perturbed.iloc[900:] += 0.05
    after = residualize_returns(perturbed, market, window=60).residuals

    np.testing.assert_allclose(
        baseline.iloc[:900].to_numpy(), after.iloc[:900].to_numpy(), rtol=1e-9, atol=1e-12
    )


def test_full_node_feature_set_has_no_lookahead(synthetic_panel: pd.DataFrame, base_config, sector_map):
    """End-to-end: perturbing the last 300 days must not move any earlier feature."""
    cut = synthetic_panel["date"].drop_duplicates().sort_values().iloc[-300]
    baseline = build_node_features(synthetic_panel, base_config, "VN30", sector_map)
    perturbed = build_node_features(_perturb_tail(synthetic_panel, cut), base_config, "VN30", sector_map)

    offenders = []
    for name in baseline.frames:
        a = baseline.frames[name].loc[baseline.frames[name].index <= cut]
        b = perturbed.frames[name].loc[perturbed.frames[name].index <= cut]
        if a.shape != b.shape:
            offenders.append(f"{name}: shape changed")
            continue
        difference = np.nanmax(np.abs(a.to_numpy() - b.to_numpy())) if a.size else 0.0
        if np.isfinite(difference) and difference > 1e-8:
            offenders.append(f"{name}: max abs diff {difference:.3e}")
    assert not offenders, "Look-ahead detected in node features: " + "; ".join(offenders)


def test_market_features_have_no_lookahead(synthetic_panel: pd.DataFrame, base_config):
    cut = synthetic_panel["date"].drop_duplicates().sort_values().iloc[-300]
    baseline = build_market_features(synthetic_panel, base_config, "VN30")
    perturbed = build_market_features(_perturb_tail(synthetic_panel, cut), base_config, "VN30")

    a = baseline.loc[baseline.index <= cut]
    b = perturbed.loc[perturbed.index <= cut]
    difference = np.nanmax(np.abs(a.to_numpy() - b.to_numpy()))
    assert difference < 1e-8, f"Look-ahead in market features: max abs diff {difference:.3e}"


def test_graph_snapshot_uses_only_trailing_window(synthetic_returns: pd.DataFrame, base_config):
    from dynamicgraph.graphs.snapshots import SnapshotBuildConfig, build_snapshot

    build = SnapshotBuildConfig.from_config(base_config, "partial_correlation", 60, "residual")
    date = synthetic_returns.index[400]
    window = synthetic_returns.iloc[341:401]
    baseline = build_snapshot(window, date, build)

    perturbed_full = synthetic_returns.copy()
    perturbed_full.iloc[401:] *= 10.0
    after = build_snapshot(perturbed_full.iloc[341:401], date, build)

    np.testing.assert_allclose(baseline.adjacency, after.adjacency, rtol=1e-10, atol=1e-12)


def test_targets_are_forward_looking_and_features_are_not(synthetic_panel, base_config):
    """Sanity check on the split of concerns: targets DO use the future."""
    targets = build_targets(synthetic_panel, base_config, "VN30")
    cut = synthetic_panel["date"].drop_duplicates().sort_values().iloc[-300]
    perturbed = build_targets(_perturb_tail(synthetic_panel, cut, 0.5), base_config, "VN30")

    column = "future_drawdown_20d"
    before_cut = targets.forward[column].loc[targets.forward.index < cut - pd.Timedelta(days=60)]
    after_before_cut = perturbed.forward[column].loc[before_cut.index]
    # Far enough before the cut the target is unaffected ...
    assert np.allclose(before_cut.dropna(), after_before_cut.reindex(before_cut.dropna().index), atol=1e-8)
    # ... but right at the cut it must change, proving it looks forward.
    near = targets.forward[column].loc[
        (targets.forward.index >= cut - pd.Timedelta(days=10)) & (targets.forward.index <= cut)
    ].dropna()
    if len(near):
        assert not np.allclose(near, perturbed.forward[column].reindex(near.index), atol=1e-8)


def test_no_target_column_leaks_into_features(synthetic_panel, base_config, sector_map):
    features = build_node_features(synthetic_panel, base_config, "VN30", sector_map)
    forbidden = ("future_", "_target", "label", "stress_abs", "y_true")
    leaked = [n for n in features.frames if any(f in n.lower() for f in forbidden)]
    assert not leaked, f"Target-like columns present in the feature set: {leaked}"

    market = build_market_features(synthetic_panel, base_config, "VN30")
    leaked = [c for c in market.columns if any(f in c.lower() for f in forbidden)]
    assert not leaked, f"Target-like columns present in market features: {leaked}"


def test_quantile_threshold_uses_training_rows_only(synthetic_panel, base_config):
    targets = build_targets(synthetic_panel, base_config, "VN30")
    values = targets.forward["future_drawdown_20d"]
    index = values.index

    train_mask = pd.Series(False, index=index)
    train_mask.iloc[: len(index) // 2] = True

    _, threshold_a = label_by_train_quantile(values, train_mask, 0.10)

    # Corrupt the test half only; the threshold must not move.
    corrupted = values.copy()
    corrupted.iloc[len(index) // 2 :] = -0.99
    _, threshold_b = label_by_train_quantile(corrupted, train_mask, 0.10)

    assert threshold_a == pytest.approx(threshold_b), (
        "Target quantile changed when only test-period values changed - leakage."
    )
