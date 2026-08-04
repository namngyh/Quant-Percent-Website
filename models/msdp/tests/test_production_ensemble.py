import json
from pathlib import Path

import numpy as np
import pytest

from msdp.inference import predict_latest_ensemble


def current_manifest():
    path=Path("artifacts/models/production_ensemble_manifest.json")
    return path,json.loads(path.read_text(encoding="utf-8")) if path.exists() else (None,None)


def test_production_manifest_has_one_model_for_every_seed():
    path,manifest=current_manifest()
    if not path.exists(): pytest.skip("Chưa có production manifest")
    required={"artifact_role","run_id","git_commit","data_hash","model_paths","seeds","feature_scaler_path","target_scalers_path","calibrator_path","created_at"}
    assert required<=set(manifest) and manifest["artifact_role"]=="production"
    assert len(manifest["model_paths"])==len(manifest["seeds"])
    assert all(Path(model_path).exists() for model_path in manifest["model_paths"])


def test_predict_latest_matches_run_all_latest():
    path,manifest=current_manifest()
    if not path.exists(): pytest.skip("Chưa có production manifest")
    expected=json.loads(Path("artifacts/predictions/latest_forecast.json").read_text(encoding="utf-8")); actual,_=predict_latest_ensemble("VNINDEX_Daily.csv",path)
    assert expected["run_id"]==actual["run_id"]
    for left,right in zip(expected["horizons"],actual["horizons"]):
        for key in ("return_quantiles","calibrated_interval","mdd_quantiles","expert_weights"):
            assert np.allclose(left[key],right[key],atol=1e-7)
