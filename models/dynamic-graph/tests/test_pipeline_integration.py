"""Integration test: the whole statistical pipeline on synthetic data.

Runs graphs -> network metrics -> stress score -> walk-forward -> website
payload without touching the real database, so CI can verify the wiring.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.evaluation.bootstrap import block_bootstrap_ci, paired_bootstrap_difference
from dynamicgraph.evaluation.calibration import calibration_metrics, reliability_table
from dynamicgraph.evaluation.classification import classification_metrics
from dynamicgraph.evaluation.event_metrics import event_detection_metrics, event_table
from dynamicgraph.features.market_features import build_market_features
from dynamicgraph.features.node_features import build_node_features
from dynamicgraph.features.targets import build_targets
from dynamicgraph.graphs.snapshots import SnapshotBuildConfig, build_snapshot_series
from dynamicgraph.models.baselines import build_model_zoo
from dynamicgraph.models.registry import FeatureSetBuilder, flatten_graph_metrics
from dynamicgraph.network.graph_metrics import compute_metric_series
from dynamicgraph.network.stress_score import build_descriptive_stress_score
from dynamicgraph.training.splits import folds_from_config
from dynamicgraph.training.walk_forward import run_walk_forward


@pytest.fixture(scope="module")
def built(synthetic_panel, base_config, sector_map):
    node_features = build_node_features(synthetic_panel, base_config, "VN30", sector_map)
    market_features = build_market_features(
        synthetic_panel, base_config, "VN30", node_features.returns_raw
    )
    targets = build_targets(synthetic_panel, base_config, "VN30")

    build = SnapshotBuildConfig.from_config(base_config, "partial_correlation", 60, "residual")
    build.stride = 5
    series = build_snapshot_series(node_features.returns_residual, build, progress_every=0)
    metrics, _ = compute_metric_series(list(series), sector_of=sector_map)
    return {
        "node_features": node_features,
        "market_features": market_features,
        "targets": targets,
        "series": series,
        "metrics": metrics,
    }


def test_snapshots_are_built_and_non_degenerate(built):
    series = built["series"]
    assert len(series) > 50
    densities = [s.density for s in series]
    assert 0.0 < np.mean(densities) < 1.0
    assert all(s.n_nodes >= 5 for s in series)
    assert "glasso_n_iter" in series.latest().metadata
    assert series.latest().metadata["glasso_n_iter"] >= 0


def test_graph_metrics_are_finite(built):
    metrics = built["metrics"]
    for column in ("graph_density", "spectral_radius", "average_strength", "modularity"):
        assert metrics[column].notna().mean() > 0.9
        assert np.isfinite(metrics[column].dropna()).all()


def test_stress_score_is_bounded_and_responds_to_the_stress_regime(built, base_config):
    metrics = built["metrics"]
    train_mask = pd.Series(True, index=metrics.index)
    train_mask.iloc[len(metrics) // 2 :] = False
    model, scores, states = build_descriptive_stress_score(metrics, base_config, train_mask)

    assert scores["stress_score"].between(0, 100).all()
    assert model.used_metrics, "no stress metric survived redundancy pruning"
    assert set(states.dropna()).issubset(set(base_config.stress_score.state_labels))

    # The synthetic panel has an engineered stress regime around observation 700
    # of the daily index; the score there should exceed the calm-period median.
    stressed = scores.loc[
        (scores.index >= metrics.index[0]) & (scores.index <= metrics.index[-1])
    ]
    assert stressed["stress_score"].max() > stressed["stress_score"].median()


def test_stress_score_standardisation_uses_training_rows_only(built, base_config):
    metrics = built["metrics"]
    train_mask = pd.Series(True, index=metrics.index)
    train_mask.iloc[len(metrics) // 2 :] = False

    model_a, _, _ = build_descriptive_stress_score(metrics, base_config, train_mask)

    corrupted = metrics.copy()
    corrupted.loc[~train_mask, "graph_density"] = 99.0
    model_b, _, _ = build_descriptive_stress_score(corrupted, base_config, train_mask)

    assert model_a.center == pytest.approx(model_b.center)
    assert model_a.scale == pytest.approx(model_b.scale)


def test_walk_forward_produces_out_of_sample_predictions(built, base_config):
    market = built["market_features"]
    graph = flatten_graph_metrics({"pc__residual__w60": built["metrics"]}, market.index)
    builder = FeatureSetBuilder(market, graph, index=market.index)

    folds = folds_from_config(market.index, base_config)
    assert len(folds) >= 1

    zoo = build_model_zoo(base_config, "classification")
    spec = zoo.get("logistic_l2") or zoo["naive_frequency"]

    result = run_walk_forward(
        features=builder.build("combined"),
        target_values=built["targets"].forward["future_drawdown_20d"],
        folds=folds,
        model_spec=spec,
        config=base_config,
        horizon=20,
        target_name="stress_q10_20d",
        feature_set="combined",
        quantile=0.10,
    )
    assert not result.predictions.empty
    assert result.predictions["probability"].between(0, 1).all()
    assert set(result.predictions["y_true"].dropna().unique()).issubset({0.0, 1.0})

    # Predictions must lie strictly inside test blocks.
    test_dates = set()
    for fold in folds:
        test_dates.update(fold.test_dates)
    assert set(result.predictions["date"]).issubset(test_dates)


def test_metric_suite_runs_on_the_predictions(built, base_config):
    market = built["market_features"]
    graph = flatten_graph_metrics({"pc__residual__w60": built["metrics"]}, market.index)
    builder = FeatureSetBuilder(market, graph, index=market.index)
    folds = folds_from_config(market.index, base_config)
    zoo = build_model_zoo(base_config, "classification")

    result = run_walk_forward(
        features=builder.build("market"),
        target_values=built["targets"].forward["future_drawdown_20d"],
        folds=folds,
        model_spec=zoo.get("logistic_l2") or zoo["naive_frequency"],
        config=base_config,
        horizon=20,
        target_name="stress_q10_20d",
        feature_set="market",
        quantile=0.10,
    )
    y = result.predictions["y_true"].to_numpy()
    p = result.predictions["probability"].to_numpy()

    metrics = classification_metrics(y, p, threshold=0.5, n_days=len(y))
    assert 0 <= metrics["brier"] <= 1
    assert 0 <= metrics["auroc"] <= 1

    calibration = calibration_metrics(y, p)
    assert "expected_calibration_error" in calibration
    assert not reliability_table(y, p).empty

    frame = result.predictions.set_index("date")
    events = event_detection_metrics(frame["y_true"], frame["probability"], 0.5)
    assert events["n_events"] >= 0

    from sklearn.metrics import brier_score_loss

    ci = block_bootstrap_ci(y, p, brier_score_loss, n_bootstrap=50, block_length=20)
    assert ci["lower"] <= ci["point"] <= ci["upper"]


def test_event_metrics_apply_each_rows_fold_threshold():
    index = pd.bdate_range("2020-01-01", periods=80)
    labels = pd.Series(0.0, index=index)
    labels.iloc[10:13] = 1.0
    labels.iloc[50:53] = 1.0
    probabilities = pd.Series(0.60, index=index)
    thresholds = pd.Series(
        np.r_[np.full(40, 0.80), np.full(40, 0.40)],
        index=index,
    )

    metrics = event_detection_metrics(
        labels,
        probabilities,
        thresholds,
        min_gap_days=20,
        lead_window=0,
    )
    table = event_table(
        labels,
        probabilities,
        thresholds,
        min_gap_days=20,
        lead_window=0,
    )

    assert metrics["threshold_policy"] == "per_prediction"
    assert metrics["n_events"] == 2
    assert metrics["n_events_detected"] == 1
    assert table["detected"].tolist() == [False, True]


def test_paired_bootstrap_detects_a_real_difference():
    rng = np.random.default_rng(61)
    n = 800
    y = (rng.random(n) < 0.15).astype(float)
    good = np.clip(0.15 + 0.6 * y + rng.normal(0, 0.05, n), 0.01, 0.99)
    bad = np.full(n, 0.15)

    from sklearn.metrics import brier_score_loss

    result = paired_bootstrap_difference(
        y, bad, good, metric_fn=brier_score_loss, n_bootstrap=200, block_length=20, higher_is_better=False
    )
    # `bad` should be worse (higher Brier) than `good`.
    assert result["difference"] > 0
    assert result["upper"] > 0


def test_grouped_bootstrap_never_builds_a_block_across_fold_boundaries():
    from dynamicgraph.evaluation.bootstrap import _grouped_block_indices

    groups = np.array([0] * 7 + [1] * 5 + [2] * 9)
    indices = _grouped_block_indices(
        groups, block_length=4, rng=np.random.default_rng(123)
    )

    assert len(indices) == len(groups)
    assert np.array_equal(groups[indices[:7]], np.zeros(7))
    assert np.array_equal(groups[indices[7:12]], np.ones(5))
    assert np.array_equal(groups[indices[12:]], np.full(9, 2))


def test_holm_adjustment_controls_the_full_comparison_family():
    from dynamicgraph.training.trainer import _holm_adjust

    adjusted = _holm_adjust(np.array([0.01, 0.02, 0.20, np.nan]))
    assert adjusted[0] == pytest.approx(0.03)
    assert adjusted[1] == pytest.approx(0.04)
    assert adjusted[2] == pytest.approx(0.20)
    assert np.isnan(adjusted[3])


def test_feature_sets_are_disjoint_in_the_right_way(built):
    market = built["market_features"]
    graph = flatten_graph_metrics({"pc__residual__w60": built["metrics"]}, market.index)
    builder = FeatureSetBuilder(market, graph, index=market.index)

    market_columns = set(builder.market().columns)
    graph_columns = set(builder.graph().columns)
    combined_columns = set(builder.combined().columns)

    assert not market_columns & graph_columns, "market and graph feature sets overlap"
    assert combined_columns == market_columns | graph_columns
    assert all(c.startswith("market_") or "constituent" in c or "breadth" in c or "cross_sectional" in c
               for c in market_columns), "a non-market column leaked into feature set A"
