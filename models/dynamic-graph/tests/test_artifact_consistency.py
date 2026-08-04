"""Artifacts from one pipeline run must be mutually consistent.

A stale file left behind by a previous run is dangerous precisely because it
looks plausible: a metrics table from an older feature space merges silently
with a fresh summary and the reported numbers no longer describe any single
experiment. These checks make that failure loud.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"


def _skip_without(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} not present; run the pipeline first")


def test_oos_metrics_and_fold_metrics_agree_on_keys():
    metrics_path = ARTIFACTS / "predictions" / "oos_metrics.csv"
    folds_path = ARTIFACTS / "predictions" / "fold_metrics.csv"
    _skip_without(metrics_path)
    _skip_without(folds_path)

    metrics = pd.read_csv(metrics_path)
    folds = pd.read_csv(folds_path)
    expected = {
        f"{r.target}__{r.feature_set}__{r.model}" for r in metrics.itertuples()
    }
    actual = set(folds["key"].unique())
    assert actual <= expected, (
        f"fold_metrics contains keys absent from oos_metrics: {sorted(actual - expected)[:5]} "
        "- the two files come from different runs"
    )


def test_fold_metrics_records_post_selection_feature_count():
    folds_path = ARTIFACTS / "predictions" / "fold_metrics.csv"
    _skip_without(folds_path)
    folds = pd.read_csv(folds_path)
    assert "n_features_selected" in folds.columns, (
        "fold_metrics is missing `n_features_selected`; it predates the feature-selection "
        "stage and is therefore stale"
    )


def test_reported_feature_count_respects_the_budget():
    metrics_path = ARTIFACTS / "predictions" / "oos_metrics.csv"
    _skip_without(metrics_path)
    metrics = pd.read_csv(metrics_path)
    if "n_features_candidate" not in metrics.columns:
        pytest.skip("metrics predate the candidate/selected split")

    from dynamicgraph.config import load_config

    budget = int(load_config("config/default.yaml").training.max_features)
    over = metrics[metrics["n_features"] > budget + 1]
    assert over.empty, (
        f"{len(over)} row(s) report more features than the selection budget of {budget}"
    )


def test_run_summary_matches_the_published_payload():
    summary_path = ARTIFACTS / "reports" / "run_summary.json"
    payload_path = ARTIFACTS / "latest" / "latest_dynamicgraph.json"
    _skip_without(summary_path)
    _skip_without(payload_path)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    verdict = (summary.get("verdict") or {}).get("verdict")
    published = payload.get("model_quality", {}).get("graph_incremental_value")
    if verdict and published:
        assert verdict == published, (
            f"run_summary verdict `{verdict}` disagrees with the published payload "
            f"`{published}` - the artifacts come from different runs"
        )


def test_ablation_variants_are_distinct_experiments():
    ablation_path = ARTIFACTS / "metrics" / "ablation.csv"
    _skip_without(ablation_path)
    ablation = pd.read_csv(ablation_path)
    if "n_features_candidate" not in ablation.columns:
        pytest.skip("ablation predates the candidate/selected split")

    # Variants that isolate different layers must not share an identical
    # candidate space; if they do, a filter silently matched nothing.
    layer_variants = ablation[
        ablation["variant"].isin(["raw_return_graph", "residual_return_graph"])
    ]
    if len(layer_variants) == 2:
        counts = layer_variants["n_features_candidate"].tolist()
        graph_only = ablation[ablation["variant"] == "graph_only"]
        if not graph_only.empty:
            full = int(graph_only["n_features_candidate"].iloc[0])
            assert all(c < full for c in counts), (
                "a return-type ablation kept the full feature space, meaning its filter "
                "matched nothing and the row is not the experiment its label claims"
            )
