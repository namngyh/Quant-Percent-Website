import json

import pandas as pd
import pytest
import yaml

from vnindex_model.online import (
    AbnormalSessionError,
    initialize_online_state,
    save_batch_handoff,
    update_latest,
)
from vnindex_model.online_state import OnlineStateSchemaError, online_state_paths

# Exact header `run_pipeline` writes for artifacts/forecasts/latest_forecast.csv.
BATCH_FORECAST_COLUMNS = [
    "step",
    "estimated_trading_date",
    "mean",
    "median",
    "lower_50",
    "upper_50",
    "lower_80",
    "upper_80",
    "lower_90",
    "upper_90",
    "lower_95",
    "upper_95",
    "expected_volatility",
    "probability_bull",
    "probability_sideway",
    "probability_bear",
    "probability_stress",
]

CONFIG = {
    "project": {"seed": 55, "data_path": "data/prices.csv", "output_root": "."},
    "data": {
        "train_fraction": 0.6,
        "validation_fraction": 0.2,
        "horizons": [20],
        "embargo": 20,
        "source": {"backend": "csv", "path": "data/prices.csv"},
    },
    "hmm": {"candidate_states": [2], "seeds": [55], "n_iter": 50},
    "random_forest": {"n_estimators": 40},
    "simulation": {"paths": 400, "horizon": 20, "student_weight": 0.35, "sample_paths": 50},
    "conformal": {"alpha_levels": [0.50, 0.20, 0.10, 0.05], "minimum_stratum_size": 80},
    "online": {"enabled": True, "lookback_buffer_days": None, "simulation_paths": None},
}


def _write_prices(root, frame: pd.DataFrame) -> None:
    out = frame.copy()
    # The defensive CSV loader parses the local vendor day-first format.
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%d/%m/%Y")
    (root / "data").mkdir(parents=True, exist_ok=True)
    out.to_csv(root / "data/prices.csv", index=False)


@pytest.fixture
def workspace(tmp_path, synthetic_handoff, batch_frame, monkeypatch):
    synthetic_handoff.run_metadata["last_data_date"] = str(batch_frame["date"].iloc[-1].date())
    _write_prices(tmp_path, batch_frame)
    (tmp_path / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "configs/online.yaml").write_text(yaml.safe_dump(CONFIG, sort_keys=False), encoding="utf-8")
    save_batch_handoff(tmp_path, synthetic_handoff)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_init_online_state_seeds_from_the_batch_handoff(workspace, batch_frame):
    result = initialize_online_state("configs/online.yaml")
    assert result["status"] == "initialized"
    assert result["as_of_date"] == str(batch_frame["date"].iloc[-1].date())
    assert result["buffer_rows"] == len(batch_frame)
    assert online_state_paths(workspace)["state"].exists()
    assert online_state_paths(workspace)["manifest"].exists()


def test_init_online_state_refuses_to_run_before_a_batch_run(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir(parents=True)
    (tmp_path / "configs/online.yaml").write_text(yaml.safe_dump(CONFIG, sort_keys=False), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(OnlineStateSchemaError, match="run-all"):
        initialize_online_state("configs/online.yaml")


def test_update_latest_applies_every_new_session_and_republishes_artifacts(
    workspace, synthetic_ohlcv, batch_frame
):
    initialize_online_state("configs/online.yaml")
    _write_prices(workspace, synthetic_ohlcv.iloc[:603].reset_index(drop=True))
    result = update_latest("configs/online.yaml")
    assert result["status"] == "updated"
    assert result["sessions_applied"] == 3
    assert result["as_of_date"] == str(synthetic_ohlcv["date"].iloc[602].date())
    forecast = pd.read_csv(workspace / "artifacts/forecasts/latest_forecast.csv")
    # Downstream consumers read this file; the online tier must not change its schema.
    assert list(forecast.columns) == BATCH_FORECAST_COLUMNS
    assert len(forecast) == CONFIG["simulation"]["horizon"]
    summary = json.loads(
        (workspace / "artifacts/forecasts/latest_forecast_summary.json").read_text(encoding="utf-8")
    )
    assert summary["update_mode"] == "online"
    assert summary["forecast_origin"] == result["as_of_date"]
    assert summary["source_run_metadata"]["data_hash"] == "test"


def test_update_latest_is_idempotent_when_the_source_has_no_new_session(workspace, synthetic_ohlcv):
    initialize_online_state("configs/online.yaml")
    _write_prices(workspace, synthetic_ohlcv.iloc[:602].reset_index(drop=True))
    update_latest("configs/online.yaml")
    artifact = workspace / "artifacts/forecasts/latest_forecast.csv"
    stamp = artifact.stat().st_mtime_ns
    payload = artifact.read_bytes()
    second = update_latest("configs/online.yaml")
    assert second["status"] == "no_new_sessions"
    assert artifact.stat().st_mtime_ns == stamp
    assert artifact.read_bytes() == payload


def test_update_latest_refuses_a_source_whose_history_was_rewritten(workspace, synthetic_ohlcv):
    initialize_online_state("configs/online.yaml")
    rewritten = synthetic_ohlcv.iloc[:603].reset_index(drop=True).copy()
    rewritten.loc[500, "close"] = float(rewritten.loc[500, "close"]) * 1.5
    _write_prices(workspace, rewritten)
    with pytest.raises(AbnormalSessionError, match="đóng cửa"):
        update_latest("configs/online.yaml")


def test_update_latest_runs_a_session_within_the_real_time_budget(workspace, synthetic_ohlcv):
    initialize_online_state("configs/online.yaml")
    _write_prices(workspace, synthetic_ohlcv.iloc[:601].reset_index(drop=True))
    result = update_latest("configs/online.yaml")
    assert result["elapsed_seconds"] < 30
    manifest = json.loads(online_state_paths(workspace)["manifest"].read_text(encoding="utf-8"))
    assert manifest["sessions_applied"] == 1
    assert manifest["as_of_date"] == result["as_of_date"]
