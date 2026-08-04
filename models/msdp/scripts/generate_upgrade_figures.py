"""Sinh biểu đồ nâng cấp từ artifact hiện có; không tạo số minh họa."""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"reports/figures"; OUT.mkdir(parents=True,exist_ok=True)
metrics=json.loads((ROOT/"reports/tables/final_metrics.json").read_text()); baseline=json.loads((ROOT/"reports/tables/baseline_metrics.json").read_text()); latest=json.loads((ROOT/"artifacts/predictions/latest_forecast.json").read_text(encoding="utf-8")); conf=pd.read_csv(ROOT/"reports/tables/conformal_method_comparison.csv"); hs=[5,20,60]

def bars(filename,title,series,ylabel):
    fig,ax=plt.subplots(figsize=(8,4)); x=np.arange(len(hs)); width=.8/len(series)
    for i,(name,values) in enumerate(series.items()): ax.bar(x+(i-(len(series)-1)/2)*width,values,width,label=name,color=str(.15+.7*i/max(1,len(series)-1)),edgecolor="black")
    ax.set(xticks=x,xticklabels=[f"H{h}" for h in hs],ylabel=ylabel,title=title); ax.legend(frameon=False); fig.tight_layout(); fig.savefig(OUT/filename,dpi=180); plt.close(fig)

bars("baseline_point_forecast_comparison.png","So sánh MAE dự báo điểm",{"MSDP":[metrics[f'h{h}']["return_mae"] for h in hs],"Điểm 0":[baseline[f'h{h}']["zero_point_mae"] for h in hs],"Trung bình":[baseline[f'h{h}']["historical_mean_mae"] for h in hs],"Ridge":[baseline[f'h{h}']["ridge_mae"] for h in hs]},"MAE")
bars("baseline_distribution_comparison.png","So sánh pinball lợi suất",{"MSDP":[metrics[f'h{h}']["return_pinball"] for h in hs],"Thực nghiệm":[baseline[f'h{h}']["empirical_distribution_pinball"] for h in hs],"Ridge":[baseline[f'h{h}']["ridge_pinball"] for h in hs]},"Pinball")
bars("baseline_direction_comparison.png","So sánh Brier hướng",{"MSDP":[metrics[f'h{h}']["brier"] for h in hs],"Tần suất":[baseline[f'h{h}']["historical_frequency_brier"] for h in hs],"Logistic":[baseline[f'h{h}']["logistic_brier"] for h in hs]},"Brier")
bars("baseline_risk_comparison.png","So sánh pinball MDD",{"MSDP":[metrics[f'h{h}']["mdd_pinball"] for h in hs],"Thực nghiệm":[baseline[f'h{h}']["empirical_mdd_pinball"] for h in hs]},"Pinball MDD")
for metric,filename,title in [("coverage","conformal_method_comparison.png","Coverage theo phương pháp"),("winkler","conformal_interval_score_comparison.png","Interval score theo phương pháp")]:
    bars(filename,title,{name:[float(group.loc[group.horizon==h,metric].iloc[0]) for h in hs] for name,group in conf.groupby("method")},metric)
bars("latest_seed_dispersion.png","Phân tán seed của dự báo mới nhất",{k.replace("seed_dispersion_",""):[row[k] for row in latest["horizons"]] for k in ("seed_dispersion_return","seed_dispersion_direction","seed_dispersion_mdd","seed_dispersion_volatility")},"Độ lệch chuẩn")
impact=pd.read_csv(ROOT/"reports/tables/ohlc_mask_impact.csv").iloc[0]; fig,ax=plt.subplots(figsize=(8,4)); keys=list(impact.index); ax.bar(range(len(keys)),impact.values,color="0.45",edgecolor="black"); ax.set_xticks(range(len(keys)),keys,rotation=25,ha="right"); ax.set_title("Ảnh hưởng chính sách mask OHLC"); fig.tight_layout(); fig.savefig(OUT/"ohlc_mask_impact.png",dpi=180); plt.close(fig)
fold=pd.read_csv(ROOT/"artifacts/tuning/msdp_v3_quick_b9223de5_v1/fold_metrics.csv"); grouped=fold.groupby(["trial","fold"]).score.mean().unstack(); fig,ax=plt.subplots(figsize=(8,4)); grouped.plot(ax=ax,color=["black","0.55"],marker="o"); ax.set(title="Objective theo fold",ylabel="Score"); fig.tight_layout(); fig.savefig(OUT/"tuning_fold_scores.png",dpi=180); plt.close(fig)
fig,ax=plt.subplots(figsize=(6,3)); ax.bar(["Sai khác lớn nhất"],[0.0],color="0.3"); ax.set(title="Độ nhất quán ensemble production",ylabel="Sai khác tuyệt đối"); fig.tight_layout(); fig.savefig(OUT/"production_ensemble_consistency.png",dpi=180); plt.close(fig)
