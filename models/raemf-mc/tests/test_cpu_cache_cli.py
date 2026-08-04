import json
import os

import pandas as pd
import pytest

from raemf_mc.cli import build_parser, main
from raemf_mc.config import bayesian_config, load_config
from raemf_mc.evaluation.downside_experiment import (
    REQUIRED_DOWNSIDE_ARTIFACTS,
    validate_downside_artifacts,
)
from raemf_mc.reporting.downside_report import _interrupted_runtime_rows
from raemf_mc.runtime.cache import ArtifactCache, cache_key
from raemf_mc.runtime.cpu import configure_cpu_runtime


def test_cpu_runtime_does_not_require_cuda(monkeypatch):
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    result = configure_cpu_runtime({"runtime": {"device": "cpu", "max_threads": 2}})
    assert result["cuda_used"] is False
    assert result["device"] == "cpu"
    assert os.environ["OMP_NUM_THREADS"] == "2"


def test_cache_key_invalidates_on_data_config_and_boundary(tmp_path):
    base = {
        "data_checksum": "a",
        "feature_config": {"x": 1},
        "artifact": "features",
        "horizon": 20,
        "split_boundaries": {"test": "2020-01-01"},
    }
    key = cache_key(**base)
    assert key != cache_key(**{**base, "data_checksum": "b"})
    assert key != cache_key(**{**base, "feature_config": {"x": 2}})
    assert key != cache_key(**{**base, "horizon": 40})
    assert key != cache_key(**{**base, "split_boundaries": {"test": "2021-01-01"}})
    calls = []
    cache = ArtifactCache(tmp_path)
    first, status_first = cache.get_or_compute(key, lambda: calls.append(1) or {"value": 3})
    second, status_second = cache.get_or_compute(key, lambda: calls.append(2) or {"value": 4})
    assert first == second == {"value": 3}
    assert (status_first, status_second) == ("miss", "hit")
    assert calls == [1]


def test_cpu_config_inheritance_and_pytorch_cpu_alias():
    smoke = load_config("configs/cpu_smoke.yaml")
    experiment = load_config("configs/cpu_experiment.yaml")
    cpu_vb = load_config("configs/cpu_vb.yaml")
    assert smoke["runtime"]["mode"] == "cpu-smoke"
    assert experiment["risk_off"]["threshold_selection"]["min_precision"] == 0.25
    assert cpu_vb["bayesian"]["backend"] == "pytorch_cpu"
    assert bayesian_config(cpu_vb)["backend"] == "pytorch_cpu"


def test_downside_cli_smoke_dispatch(monkeypatch, tmp_path, capsys):
    output = tmp_path / "run"
    output.mkdir()
    monkeypatch.setattr(
        "raemf_mc.evaluation.downside_experiment.run_downside_experiment",
        lambda data, config: output,
    )
    main(
        [
            "downside-experiment",
            "--data",
            "VNINDEX_Daily.csv",
            "--config",
            "configs/cpu_smoke.yaml",
        ]
    )
    assert str(output) in capsys.readouterr().out
    args = build_parser().parse_args(["shadow-update", "--config", "configs/cpu_final.yaml"])
    assert args.cmd == "shadow-update"
    assert json.loads(json.dumps({"command": args.cmd}))["command"] == "shadow-update"


def test_required_artifact_schema(tmp_path):
    for name in REQUIRED_DOWNSIDE_ARTIFACTS:
        (tmp_path / name).write_text("{}\n" if name.endswith(".json") else "placeholder\n")
    pd.DataFrame(
        [
            {
                "stage": "outer_fold",
                "horizon": 20,
                "fold": 0,
                "wall_time": 1.0,
                "cpu_time": 1.0,
                "peak_rss": "not_available",
                "cache_status": "miss",
                "thread_count": 2,
            }
        ]
    ).to_csv(tmp_path / "runtime_benchmark.csv", index=False)
    pd.DataFrame(
        [
            {
                "model": "candidate_risk_off",
                "horizon": 20,
                "fold": 0,
                "recall": 0.5,
                "precision": 0.5,
                "pr_auc": 0.5,
                "expected_cost": 0.1,
            }
        ]
    ).to_csv(tmp_path / "risk_off_metrics_by_fold.csv", index=False)
    pd.DataFrame(
        [
            {
                "date": "2020-01-02",
                "horizon": 20,
                "fold": 0,
                "actual_class": "Bear",
                "predicted_class": "Bear",
                "raw_prob_bull": 0.10,
                "raw_prob_sideway": 0.20,
                "raw_prob_bear": 0.60,
                "raw_prob_stress": 0.10,
                "prob_bull": 0.15,
                "prob_sideway": 0.20,
                "prob_bear": 0.55,
                "prob_stress": 0.10,
                "candidate_risk_off_probability": 0.70,
            }
        ]
    ).to_csv(tmp_path / "multiclass_oos_probabilities.csv", index=False)
    validate_downside_artifacts(tmp_path)
    (tmp_path / "report.md").unlink()
    with pytest.raises(AssertionError, match="missing required artifacts"):
        validate_downside_artifacts(tmp_path)


def test_runtime_report_flags_likely_sleep_or_suspend():
    runtime = pd.DataFrame(
        [
            {
                "stage": "outer_fold",
                "horizon": 20,
                "fold": 0,
                "wall_time": 5_670.0,
                "cpu_time": 658.0,
            },
            {
                "stage": "outer_fold",
                "horizon": 20,
                "fold": 1,
                "wall_time": 1_235.0,
                "cpu_time": 1_312.0,
            },
        ]
    )
    interrupted = _interrupted_runtime_rows(runtime)
    assert interrupted[["horizon", "fold"]].to_records(index=False).tolist() == [(20, 0)]
