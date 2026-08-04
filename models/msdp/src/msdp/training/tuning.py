"""Điều phối Optuna có resume theo đúng dữ liệu và lưu đầy đủ bằng chứng."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import time
from typing import Any, Callable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import optuna
import pandas as pd
import yaml


MODEL_VERSION = "v3"
FEATURE_VERSION = "v1"


def make_study_name(config: dict[str, Any], data_hash: str) -> str:
    """Tên study cách ly theo model, mức cấu hình, dữ liệu và feature."""
    return f"msdp_{MODEL_VERSION}_{config.get('run_label','run')}_{data_hash[:8]}_{FEATURE_VERSION}"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _pruner(tuning: dict[str, Any]) -> optuna.pruners.BasePruner:
    if tuning.get("pruner") == "hyperband":
        return optuna.pruners.HyperbandPruner(min_resource=8, max_resource=int(tuning["max_epochs"]), reduction_factor=3)
    return optuna.pruners.MedianPruner(n_startup_trials=1, n_warmup_steps=8)


def _simple_plots(study: optuna.Study, directory: Path) -> None:
    complete=[t for t in study.trials if t.state==optuna.trial.TrialState.COMPLETE and t.value is not None]
    fig,ax=plt.subplots(figsize=(8,4)); ax.plot([t.number for t in complete],[t.value for t in complete],"o-",color="black"); ax.set(xlabel="Lần thử",ylabel="Mục tiêu",title="Lịch sử tối ưu Optuna"); fig.tight_layout(); fig.savefig(directory/"optimization_history.png",dpi=180); plt.close(fig)
    try: importance=optuna.importance.get_param_importances(study)
    except Exception: importance={}
    fig,ax=plt.subplots(figsize=(8,4)); ax.barh(list(importance),list(importance.values()),color="0.35"); ax.set(xlabel="Mức quan trọng",title="Tầm quan trọng tham số"); fig.tight_layout(); fig.savefig(directory/"parameter_importance.png",dpi=180); plt.close(fig)
    numeric=sorted({k for t in complete for k,v in t.params.items() if isinstance(v,(int,float))})[:8]
    fig,ax=plt.subplots(figsize=(9,5));
    if numeric and complete:
        for t in complete:
            vals=np.array([float(t.params.get(k,np.nan)) for k in numeric]); ax.plot(range(len(numeric)),vals,color="0.6",alpha=.35)
        ax.set_xticks(range(len(numeric)),numeric,rotation=35,ha="right")
    ax.set_title("Tọa độ song song tham số"); fig.tight_layout(); fig.savefig(directory/"parallel_coordinate.png",dpi=180); plt.close(fig)
    fig,axes=plt.subplots(max(1,len(numeric)),1,figsize=(8,max(3,2*len(numeric))),squeeze=False)
    for ax,key in zip(axes[:,0],numeric): ax.scatter([t.params.get(key) for t in complete],[t.value for t in complete],s=18,color="black"); ax.set(xlabel=key,ylabel="Mục tiêu")
    fig.tight_layout(); fig.savefig(directory/"slice_parameters.png",dpi=180); plt.close(fig)


def run_optuna(objective: Callable[[optuna.Trial], float], config: dict[str, Any], out_dir: str | Path,
                *, data_hash: str, fold_definitions: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any],optuna.Study]:
    tuning=config.get("tuning",{}); root=Path(out_dir); root.mkdir(parents=True,exist_ok=True)
    study_name=make_study_name(config,data_hash); directory=root/study_name; directory.mkdir(parents=True,exist_ok=True)
    storage_path=Path(tuning.get("storage",root/"msdp_optuna.db"))
    if not storage_path.is_absolute(): storage_path=Path.cwd()/storage_path
    storage_path.parent.mkdir(parents=True,exist_ok=True); storage=f"sqlite:///{storage_path.resolve().as_posix()}"
    study=optuna.create_study(study_name=study_name,direction="minimize",storage=storage,load_if_exists=True,pruner=_pruner(tuning),sampler=optuna.samplers.TPESampler(seed=int(tuning.get("seed",42))))
    requested=int(tuning.get("n_trials",config["training"]["trials"])); remaining=max(0,requested-len(study.trials)); started=time.time()
    if tuning.get("enabled",True) and remaining:
        study.optimize(objective,n_trials=remaining,n_jobs=int(tuning.get("n_jobs",1)),catch=(FloatingPointError,ValueError,RuntimeError))
    runtime=time.time()-started; trials=study.trials_dataframe(); trials.to_csv(directory/"trials.csv",index=False)
    complete=[t for t in study.trials if t.state==optuna.trial.TrialState.COMPLETE]
    if not complete: raise RuntimeError("Optuna không có trial hoàn tất")
    best={**config["model"],**study.best_params}; (directory/"best_params.yaml").write_text(yaml.safe_dump(best,sort_keys=False),encoding="utf-8")
    (directory/"best_trial.json").write_text(json.dumps({"number":study.best_trial.number,"value":study.best_value,"params":study.best_params,"user_attrs":study.best_trial.user_attrs},indent=2,ensure_ascii=False),encoding="utf-8")
    fold_rows=[]
    for t in study.trials:
        for row in t.user_attrs.get("fold_metrics",[]): fold_rows.append({"trial":t.number,**row})
    pd.DataFrame(fold_rows).to_csv(directory/"fold_metrics.csv",index=False)
    states={state.name.lower():sum(t.state==state for t in study.trials) for state in optuna.trial.TrialState}
    metadata={"study_name":study_name,"model_version":MODEL_VERSION,"feature_version":FEATURE_VERSION,"git_commit":_git_commit(),"data_hash":data_hash,"config":config.get("run_label"),"seed":tuning.get("seed",42),"runtime_seconds":runtime,"trial_counts":states,"fold_definitions":fold_definitions or [],"python":platform.python_version(),"platform":platform.platform(),"created_at":datetime.now(timezone.utc).isoformat(),"storage":str(storage_path)}
    (directory/"tuning_metadata.json").write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding="utf-8"); _simple_plots(study,directory)
    (directory/"tuning_summary_VI.md").write_text(f"# Kết quả tinh chỉnh Optuna\n\nStudy: `{study_name}`. Hoàn tất: {states['complete']}; cắt sớm: {states['pruned']}; lỗi: {states['fail']}. Mục tiêu tốt nhất: {study.best_value:.6f}.\n",encoding="utf-8")
    return best,study
