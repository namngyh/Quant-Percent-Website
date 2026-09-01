"""Tests for the frozen stress models and the online republish of `artifacts/latest/`.

`latest.py` had no test coverage before this file, which is how it stayed
possible for the published payload to depend on a refit that ran at publication
time. The properties asserted here are the ones that make the online tier safe
to let near `artifacts/latest/`:

* scoring a frozen model never fits anything;
* the payload schema is produced by one function, so the two tiers cannot drift;
* a handoff without frozen models refuses to publish rather than overwriting a
  good batch payload with a partial one;
* an online state from the previous schema is refused, not silently upgraded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import pytest

from dynamicgraph.latest import FrozenStressModel, predict_stress_probabilities
from dynamicgraph.online.publish import PublicationUnavailable, publish_latest
from dynamicgraph.online.state import SCHEMA_VERSION

AS_OF = pd.Timestamp("2026-08-26")


class _StubModel:
    """Minimal stand-in with the surface `predict_stress_probabilities` uses."""

    def __init__(self, probability: float = 0.42, method: str = "isotonic") -> None:
        self.probability = probability
        self.method = method
        self.decision_threshold = 0.3
        self.feature_names = ["a", "b"]
        self.seen_columns: list[str] | None = None

    def predict_proba(self, frame: pd.DataFrame):
        self.seen_columns = list(frame.columns)
        return [self.probability]


@dataclass
class _StubBuilder:
    """Returns a fixed feature frame for any feature set."""

    frame: pd.DataFrame
    calls: list[str]

    def build(self, feature_set: str) -> pd.DataFrame:
        self.calls.append(feature_set)
        return self.frame


def _frame(index=(AS_OF,), columns=("a", "b", "c")) -> pd.DataFrame:
    return pd.DataFrame(
        [[1.0] * len(columns)] * len(index), index=pd.DatetimeIndex(index), columns=list(columns)
    )


def _frozen(model: _StubModel, horizon: int = 20, **overrides) -> FrozenStressModel:
    defaults = dict(
        horizon=horizon,
        model=model,
        model_name="gradient_boosting",
        feature_set="market_and_graph",
        feature_names=["a", "b"],
        label_threshold=-0.0812,
        train_end=pd.Timestamp("2026-05-01"),
        quality={
            "brier_score": 0.08,
            "auprc": 0.31,
            "brier_skill_score": 0.12,
            "n_oos_observations": 900,
        },
        stress_quantile=0.10,
        verdict="incremental_value",
    )
    defaults.update(overrides)
    return FrozenStressModel(**defaults)


# ---------------------------------------------------------------------------
# Scoring the frozen models
# ---------------------------------------------------------------------------
def test_prediction_projects_onto_the_columns_the_model_was_fitted_on():
    """`fit_final_model` may narrow the feature space. Feeding the live row's
    full column set would hand the model a different matrix from the one it
    learned on, and sklearn would not necessarily complain."""
    model = _StubModel()
    builder = _StubBuilder(_frame(columns=("a", "b", "c")), calls=[])
    predict_stress_probabilities({20: _frozen(model)}, builder, AS_OF)
    assert model.seen_columns == ["a", "b"]


def test_prediction_never_fits(monkeypatch):
    """The whole point of freezing: publishing must not touch `fit_final_model`."""
    import dynamicgraph.training.walk_forward as walk_forward

    def explode(*args, **kwargs):
        raise AssertionError("fit_final_model must not be called when scoring frozen models")

    monkeypatch.setattr(walk_forward, "fit_final_model", explode)
    out = predict_stress_probabilities(
        {20: _frozen(_StubModel())}, _StubBuilder(_frame(), calls=[]), AS_OF
    )
    assert out["20d"]["probability"] == pytest.approx(0.42)


def test_payload_carries_the_full_documented_schema():
    out = predict_stress_probabilities(
        {20: _frozen(_StubModel())}, _StubBuilder(_frame(), calls=[]), AS_OF
    )
    entry = out["20d"]
    assert set(entry) == {
        "probability", "calibrated", "calibration_method", "model_name", "feature_set",
        "label_definition", "oos_brier_score", "oos_auprc", "oos_brier_skill_score",
        "sample_size", "last_retraining_date", "decision_threshold", "confidence_warning",
    }
    assert entry["last_retraining_date"] == "2026-05-01"
    assert "10th percentile" in entry["label_definition"]


def test_probability_is_clamped_away_from_certainty():
    """Publishing 0.0 would assert a drawdown is impossible; no model here can."""
    out = predict_stress_probabilities(
        {20: _frozen(_StubModel(probability=0.0))}, _StubBuilder(_frame(), calls=[]), AS_OF
    )
    assert 0.0 < out["20d"]["probability"] < 1.0


def test_a_model_with_no_oos_skill_is_published_with_a_warning():
    frozen = _frozen(_StubModel(), quality={"brier_skill_score": -0.02, "brier_score": 0.2})
    out = predict_stress_probabilities({20: frozen}, _StubBuilder(_frame(), calls=[]), AS_OF)
    assert "did not beat a constant base-rate forecast" in out["20d"]["confidence_warning"]


def test_no_incremental_value_warns_only_for_graph_feature_sets():
    graph = _frozen(_StubModel(), verdict="no_incremental_value", feature_set="market_and_graph")
    market = _frozen(_StubModel(), verdict="no_incremental_value", feature_set="market")
    graph_out = predict_stress_probabilities({20: graph}, _StubBuilder(_frame(), calls=[]), AS_OF)
    market_out = predict_stress_probabilities({20: market}, _StubBuilder(_frame(), calls=[]), AS_OF)
    assert "incremental value" in graph_out["20d"]["confidence_warning"]
    assert market_out["20d"]["confidence_warning"] is None


def test_a_date_the_features_do_not_cover_is_skipped_not_guessed():
    builder = _StubBuilder(_frame(index=(pd.Timestamp("2026-08-25"),)), calls=[])
    assert predict_stress_probabilities({20: _frozen(_StubModel())}, builder, AS_OF) == {}


def test_an_all_missing_live_row_is_skipped():
    frame = _frame()
    frame.loc[:, :] = float("nan")
    assert predict_stress_probabilities(
        {20: _frozen(_StubModel())}, _StubBuilder(frame, calls=[]), AS_OF
    ) == {}


def test_every_horizon_is_scored():
    out = predict_stress_probabilities(
        {5: _frozen(_StubModel(), horizon=5), 20: _frozen(_StubModel(), horizon=20)},
        _StubBuilder(_frame(), calls=[]),
        AS_OF,
    )
    assert sorted(out) == ["20d", "5d"]


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------
@dataclass
class _StubState:
    stress_forecast_models: dict[int, Any]
    publication: dict[str, Any]
    core_key: str = "core"
    snapshots: dict[str, Any] = None
    communities: dict[str, Any] = None

    def __post_init__(self):
        self.snapshots = self.snapshots or {}
        self.communities = self.communities or {}


def test_publish_refuses_without_frozen_models():
    """Overwriting a good batch payload with a partial one is worse than not
    writing: the refusal is the feature."""
    state = _StubState(stress_forecast_models={}, publication={})
    with pytest.raises(PublicationUnavailable, match="chưa có model dự báo stress"):
        publish_latest(
            state, config=None, record={}, market_features=pd.DataFrame(),
            node_features=None, panel_last_date=AS_OF,
        )


def test_publish_refuses_without_a_snapshot():
    state = _StubState(stress_forecast_models={20: _frozen(_StubModel())}, publication={})
    with pytest.raises(PublicationUnavailable, match="không dựng được snapshot"):
        publish_latest(
            state, config=None, record={"core_snapshot": None}, market_features=pd.DataFrame(),
            node_features=None, panel_last_date=AS_OF,
        )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def test_schema_version_was_bumped_for_the_new_state_fields():
    """`metric_history_by_key` cannot be reconstructed from a version-1 state,
    so loading one has to fail rather than silently produce a narrower feature
    matrix than the stress models were fitted on."""
    assert SCHEMA_VERSION == 2


def test_loading_a_previous_schema_state_is_refused(tmp_path):
    import joblib

    from dynamicgraph.online.handoff import STATE_DIRECTORY
    from dynamicgraph.online.persistence import load_online_state
    from dynamicgraph.online.state import OnlineState, OnlineStateError

    directory = tmp_path / STATE_DIRECTORY
    directory.mkdir(parents=True)
    stale = OnlineState(
        schema_version=1,
        as_of_date="2026-08-25",
        returns=pd.DataFrame({"AAA": [0.01]}, index=pd.DatetimeIndex(["2026-08-25"])),
        market_returns=pd.Series([0.01], index=pd.DatetimeIndex(["2026-08-25"])),
        residual_window=60,
        build_configs={},
        core_key="core",
        source_run_metadata={},
    )
    joblib.dump(stale, directory / "online_state.joblib")
    with pytest.raises(OnlineStateError, match="schema 1"):
        load_online_state(tmp_path)
