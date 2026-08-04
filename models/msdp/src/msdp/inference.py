from __future__ import annotations
from pathlib import Path
import json,joblib,numpy as np,torch
from .calibration import StaticCQRCalibrator
from .data_io import load_market_data
from .features import build_features
from .interpretation import artifact_confidence,latest_seed_dispersions,percentile_rank
from .models import MSDP
from .training.ensemble import average_predictions

def _repo_root(model_path):
    path=Path(model_path).resolve()
    for parent in path.parents:
        if (parent/"pyproject.toml").exists() and (parent/"src/msdp").exists(): return parent
    raise ValueError(f"Không tìm được repository root từ {path}")
def _resolve(root,path):
    p=Path(path); return p if p.is_absolute() else root/p

def load_production_bundle(model_or_manifest):
    path=Path(model_or_manifest); root=_repo_root(path)
    if path.suffix.lower()==".json":
        manifest=json.loads(path.read_text(encoding="utf-8")); states=[]
        for model_path in manifest["model_paths"]: states.append(torch.load(_resolve(root,model_path),map_location="cpu",weights_only=False)["state_dict"])
    else:
        bundle=torch.load(path,map_location="cpu",weights_only=False); manifest={k:v for k,v in bundle.items() if k!="ensemble_state_dicts"}
        if "ensemble_state_dicts" not in bundle: raise ValueError("Production bundle must contain ensemble_state_dicts; a single seed is not an ensemble")
        states=[bundle["ensemble_state_dicts"][str(seed)] for seed in manifest["seeds"]]
    if manifest.get("artifact_role")!="production": raise ValueError("Expected production artifact_role")
    if len(states)!=len(manifest["seeds"]): raise ValueError("Production manifest seed/model count mismatch")
    return manifest,states,root

def predict_latest_ensemble(data_path,model_or_manifest):
    manifest,states,root=load_production_bundle(model_or_manifest); df=load_market_data(data_path); features,_=build_features(df); expected=manifest["feature_order"]
    if any(c not in features for c in expected): raise ValueError("Feature order mismatch; required feature is absent")
    features=features[expected]; lookback=int(manifest["lookback"])
    if features.iloc[-lookback:].isna().any().any(): raise ValueError("Latest lookback contains missing features")
    feature_scaler=joblib.load(_resolve(root,manifest["feature_scaler_path"])); target_scalers=joblib.load(_resolve(root,manifest["target_scalers_path"])); x=torch.tensor(feature_scaler.transform(features)[-lookback:][None],dtype=torch.float32); seed_predictions=[]
    for state in states:
        model=MSDP(**manifest["model_args"]); model.load_state_dict(state); model.eval()
        with torch.no_grad(): scaled={k:v.numpy() for k,v in model(x).items() if k not in {"expert_latents","context","direction_logits"}}
        seed_predictions.append(target_scalers.inverse_predictions(scaled))
    ensemble=average_predictions(seed_predictions); calibrator=joblib.load(_resolve(root,manifest["calibration_path"])); lower,upper=calibrator.transform_all_horizons(ensemble["return_quantiles"][:,:,0],ensemble["return_quantiles"][:,:,-1]); dispersions=latest_seed_dispersions(seed_predictions); reference=joblib.load(_resolve(root,manifest["confidence_reference_path"])); latest_feature=features.iloc[-1]; distance=float(np.sqrt(np.nanmean(((latest_feature-reference["development_median"])/reference["development_iqr"])**2))); drift=percentile_rank(distance,reference["development_distance"]); horizons=[]
    for j,h in enumerate(manifest["model_args"]["horizons"]):
        seed_ranks=[percentile_rank(dispersions[j][k],reference["calibration_seed_dispersion"][j][k]) for k in ("return","direction","mdd","volatility")]; seed_u=None if all(x is None for x in seed_ranks) else float(np.mean([x for x in seed_ranks if x is not None])); components={"interval":percentile_rank(float(upper[0,j]-lower[0,j]),reference["calibrated_width"][:,j]),"coverage":min(abs(float(reference["calibrated_coverage"][j])-reference["target_coverage"])/.20,1.),"disagreement":percentile_rank(float(ensemble["expert_disagreement"][0,j]),reference["calibration_disagreement"][:,j]),"seed":seed_u,"drift":drift}; sources={"interval":"calibration interval-width percentile","coverage":"calibration coverage","disagreement":"calibration auxiliary disagreement percentile","seed":"calibration seed-dispersion percentiles","drift":"development robust-distance percentile"}; conf=artifact_confidence(components,sources); q=ensemble["return_quantiles"][0,j]; horizons.append({"horizon":h,"probability_positive":float(ensemble["direction_prob"][0,j]),"return_quantiles":q.tolist(),"raw_interval":[float(q[0]),float(q[-1])],"calibrated_interval":[float(lower[0,j]),float(upper[0,j])],"projected_index_quantiles":[float(df.close.iloc[-1]*np.exp(q[k]/100)) for k in [0,2,4]],"mdd_quantiles":ensemble["mdd_quantiles"][0,j].tolist(),"volatility":float(ensemble["volatility"][0,j]),"expert_weights":ensemble["gate_weights"][0,j].tolist(),"expert_disagreement":float(ensemble["expert_disagreement"][0,j]),**{f"seed_dispersion_{k}":v for k,v in dispersions[j].items()},"confidence_score":conf["score"],"confidence_label":conf["label"],"confidence_components":conf["components"],"confidence_component_sources":conf["component_sources"],"confidence_missing_components":conf["missing_components"],"confidence_components_used":conf["used_components"]})
    return {"run_id":manifest["run_id"],"artifact_role":"production","data_date":str(df.date.iloc[-1]),"current_vnindex":float(df.close.iloc[-1]),"horizons":horizons},seed_predictions

def predict_latest(data_path,model_path,scaler_path=None,target_scaler_path=None):
    payload,seeds=predict_latest_ensemble(data_path,model_path); return load_market_data(data_path).iloc[-1],payload,payload
