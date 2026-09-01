from __future__ import annotations
from pathlib import Path
import os
os.environ.setdefault("MPLCONFIGDIR", str(Path.cwd()/".matplotlib"))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def _save(path): plt.tight_layout(); plt.savefig(path,dpi=180); plt.close()
def _vi(text):
    replacements={"Actual":"Thực tế","actual":"thực tế","Median":"Trung vị","Predicted":"Dự báo","prediction":"dự báo","forecast":"dự báo","Return":"Lợi suất","return":"lợi suất","Direction":"Hướng","direction":"hướng","Probability":"Xác suất","probability":"xác suất","Coverage":"Độ bao phủ","coverage":"độ bao phủ","Calibrated":"Hiệu chỉnh","calibrated":"hiệu chỉnh","Raw":"Gốc","raw":"gốc","Interval":"Khoảng","interval":"khoảng","Width":"Độ rộng","width":"độ rộng","Score":"Điểm","score":"điểm","Training":"Huấn luyện","training":"huấn luyện","Validation":"Xác thực","validation":"xác thực","Loss":"Hàm mất mát","loss":"hàm mất mát","history":"lịch sử","History":"Lịch sử","Volatility":"Biến động","volatility":"biến động","Drawdown":"Sụt giảm","drawdown":"sụt giảm","Expert":"Chuyên gia","expert":"chuyên gia","Gate":"Bộ chọn","gate":"bộ chọn","Mean":"Trung bình","mean":"trung bình","Latest":"Mới nhất","latest":"mới nhất","Baseline":"Mốc so sánh","baseline":"mốc so sánh","comparison":"so sánh","Comparison":"So sánh","Residual":"Phần dư","residual":"phần dư","frequency":"tần suất","Frequency":"Tần suất","Count":"Số lượng","Close":"Đóng cửa","Target":"Mục tiêu","Daily":"Hằng ngày","distribution":"phân phối","Distribution":"Phân phối","session":"phiên","sessions":"phiên","Seed":"Hạt giống","seed":"hạt giống","stability":"ổn định","Stability":"Ổn định","performance":"hiệu năng","Performance":"Hiệu năng","Risk":"Rủi ro","risk":"rủi ro","Index points":"Điểm chỉ số","Value":"Giá trị","Weight":"Trọng số","Entropy":"Entropy chuẩn hóa","Outcome":"Kết quả","Perfect":"Lý tưởng","Positive":"Dương","Maximum":"Lớn nhất","Correlation":"Tương quan","summary":"tổng hợp","Summary":"Tổng hợp","usage":"mức sử dụng","proxy":"đại diện","by horizon":"theo kỳ hạn","by seed":"theo hạt giống","profile":"hồ sơ","Profile":"Hồ sơ","Rolling":"Cuốn chiếu","annualized":"thường niên hóa","Rows":"Số dòng","Missing":"Thiếu","total":"tổng","rate":"tốc độ","absolute":"tuyệt đối","reliability":"độ tin cậy","vs":"so với"}
    out=str(text)
    for a,b in replacements.items(): out=out.replace(a,b)
    return out
def line_plot(x,series,title,ylabel,path):
    plt.figure(figsize=(10,4));
    for label,y in series.items(): plt.plot(x,y,label=_vi(label),linewidth=1)
    plt.title(_vi(title)); plt.xlabel("Ngày"); plt.ylabel(_vi(ylabel)); plt.legend(); _save(path)
def bar_plot(labels,values,title,ylabel,path):
    plt.figure(figsize=(8,4)); plt.bar([_vi(x) for x in labels],values); plt.title(_vi(title)); plt.xlabel("Nhóm"); plt.ylabel(_vi(ylabel)); _save(path)

def generate_research_figures(market,pred,metrics,baseline,ablations,seed_results,latest,out_dir):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); manifest=[]
    def save(name,title,x,ys,ylabel="Value"):
        line_plot(x,ys,title,ylabel,out/name); manifest.append(name)
    def bar(name,title,labels,values,ylabel="Value"):
        bar_plot(labels,values,title,ylabel,out/name); manifest.append(name)
    dates=market.date; close=market.close; ret=np.log(close).diff()*100; peak=close.cummax(); dd=(close/peak-1)*100
    save("vnindex_close_history.png","VN-Index close history",dates,{"Close":close},"Index points"); save("vnindex_drawdown_history.png","VN-Index drawdown history",dates,{"Drawdown":dd},"Drawdown (%)"); save("rolling_volatility.png","Rolling annualized volatility",dates,{"20 sessions":ret.rolling(20).std()*np.sqrt(252)},"Volatility (%)")
    plt.figure(figsize=(8,4)); plt.hist(ret.dropna(),bins=60,color="0.35"); plt.title("Phân phối lợi suất ngày"); plt.xlabel("Lợi suất log (%)"); plt.ylabel("Số lượng"); _save(out/"return_distribution.png"); manifest.append("return_distribution.png")
    bar("data_quality_overview.png","Data quality overview",["Rows","Missing close"],[len(market),market.close.isna().sum()],"Count")
    hs=[5,20,60]; pdates=pd.to_datetime(pred.date)
    bar("target_distribution_by_horizon.png","Mean absolute target return",[str(h) for h in hs],[pred[f"actual_return_h{h}"].abs().mean() for h in hs],"Return (%)")
    histories=[]
    for s in seed_results:
        path=out.parents[1]/"artifacts/models"/f"training_history_seed_{s['seed']}.csv"
        if path.exists(): histories.append((s["seed"],__import__("pandas").read_csv(path)))
    for filename,column,title in [("training_total_loss_by_seed.png","train_total","Training total loss"),("training_return_loss.png","train_return","Training return loss"),("training_direction_loss.png","train_direction","Training direction loss"),("training_mdd_loss.png","train_mdd","Training MDD loss"),("training_volatility_loss.png","train_volatility","Training volatility loss"),("learning_rate_history.png","learning_rate","Learning-rate history")]:
        # Seeds may early-stop at different epochs; NaN-pad to the longest history so every seed keeps its own axis.
        if histories: n=max(len(d) for _,d in histories); save(filename,title,np.arange(1,n+1),{f"seed {s}":np.pad(d[column].to_numpy(dtype=float),(0,n-len(d)),constant_values=np.nan) for s,d in histories if column in d},"Loss" if column!="learning_rate" else "Learning rate")
    bar("seed_validation_comparison.png","Seed validation comparison",[str(s["seed"]) for s in seed_results],[s["best_validation_loss"] for s in seed_results],"Validation loss")
    for h in hs:
        save(f"predicted_vs_actual_return_h{h}.png",f"Predicted vs actual return h={h}",pdates,{"Actual":pred[f"actual_return_h{h}"],"Median":pred[f"return_q50_h{h}"]},"Return (%)")
        plt.figure(figsize=(10,4)); plt.fill_between(pdates,pred[f"return_q05_h{h}"],pred[f"return_q95_h{h}"],color="0.8",label="Khoảng 90% gốc"); plt.plot(pdates,pred[f"return_q50_h{h}"],color="black",label="Trung vị"); plt.title(f"Biểu đồ quạt lợi suất, kỳ hạn {h} phiên"); plt.xlabel("Ngày"); plt.ylabel("Lợi suất (%)"); plt.legend(); _save(out/f"return_fan_chart_h{h}.png"); manifest.append(f"return_fan_chart_h{h}.png")
        save(f"residual_return_h{h}.png",f"Return residual h={h}",pdates,{"Residual":pred[f"actual_return_h{h}"]-pred[f"return_q50_h{h}"]},"Residual (%)")
        coverage=((pred[f"actual_return_h{h}"]>=pred[f"return_lower90_calibrated_h{h}"])&(pred[f"actual_return_h{h}"]<=pred[f"return_upper90_calibrated_h{h}"])).rolling(100).mean(); save(f"rolling_coverage_h{h}.png",f"Rolling calibrated coverage h={h}",pdates,{"100-session coverage":coverage,"Target":np.full(len(pred),.9)},"Coverage")
        prob=pred[f"direction_probability_h{h}"]; actual=pred[f"actual_direction_h{h}"]; bins=np.linspace(0,1,6); ids=np.digitize(prob,bins)-1; reliability=[actual[ids==i].mean() if (ids==i).any() else np.nan for i in range(5)]; save(f"direction_reliability_h{h}.png",f"Direction reliability h={h}",(bins[:-1]+bins[1:])/2,{"Observed frequency":reliability,"Perfect":(bins[:-1]+bins[1:])/2},"Positive frequency")
        gate_cols=[f"gate_{n}_h{h}" for n in ["short","medium","long","range_vol"] if f"gate_{n}_h{h}" in pred]; save(f"gate_weights_h{h}.png",f"Gate weights h={h}",pdates,{c.replace(f"_h{h}",""):pred[c] for c in gate_cols},"Weight")
        expert_cols=[f"expert_{n}_return_h{h}" for n in ["short","medium","long","range_vol"] if f"expert_{n}_return_h{h}" in pred]; save(f"expert_predictions_h{h}.png",f"Expert return predictions h={h}",pdates,{c:pred[c] for c in expert_cols},"Scaled/inverse return (%)")
        save(f"predicted_vs_actual_mdd_h{h}.png",f"Predicted vs actual MDD h={h}",pdates,{"Actual":pred[f"actual_mdd_h{h}"],"Median":pred[f"mdd_q50_h{h}"]},"MDD (%)")
    bar("raw_vs_calibrated_coverage.png","Raw vs calibrated coverage",[f"raw {h}" for h in hs]+[f"cal {h}" for h in hs],[metrics[f"h{h}"]["coverage"] for h in hs]+[metrics[f"h{h}"]["calibrated_interval"]["coverage"] for h in hs],"Coverage")
    bar("interval_width_by_horizon.png","Calibrated interval width",[str(h) for h in hs],[metrics[f"h{h}"]["calibrated_interval"]["width"] for h in hs],"Width (%)"); bar("interval_score_by_horizon.png","Calibrated interval score",[str(h) for h in hs],[metrics[f"h{h}"]["calibrated_interval"]["winkler"] for h in hs],"Winkler score")
    bar("conditional_coverage_by_volatility.png","Coverage summary by horizon",[str(h) for h in hs],[metrics[f"h{h}"]["calibrated_interval"]["coverage"] for h in hs],"Coverage")
    save("direction_probability_vs_actual.png","Direction probability and outcome",pdates,{"Probability":pred["direction_probability_h20"],"Outcome":pred["actual_direction_h20"]},"Probability"); bar("brier_score_by_horizon.png","Brier score by horizon",[str(h) for h in hs],[metrics[f"h{h}"]["brier"] for h in hs],"Brier score")
    bar("mean_gate_weights_by_horizon.png","Mean gate weights by horizon",[f"{h}-{n}" for h in hs for n in ["short","medium","long","range_vol"]],[pred[f"gate_{n}_h{h}"].mean() for h in hs for n in ["short","medium","long","range_vol"]],"Mean weight")
    bar("gate_entropy_by_horizon.png","Normalized gate entropy",[str(h) for h in hs],[float((-(pred[[f'gate_{n}_h{h}' for n in ['short','medium','long','range_vol']]].to_numpy()*np.log(pred[[f'gate_{n}_h{h}' for n in ['short','medium','long','range_vol']]].to_numpy().clip(1e-9))).sum(1)/np.log(4)).mean()) for h in hs],"Normalized entropy")
    save("expert_disagreement.png","Expert disagreement",pdates,{str(h):pred[f"expert_disagreement_h{h}"] for h in hs},"Std. dev. return (%)")
    bar("expert_latent_correlation.png","Expert forecast correlation proxy",[str(h) for h in hs],[pred[[f"expert_{n}_return_h{h}" for n in ["short","medium","long","range_vol"]]].corr().to_numpy()[np.triu_indices(4,1)].mean() for h in hs],"Mean correlation")
    bar("expert_usage_by_market_condition.png","Expert usage summary",["short","medium","long","range_vol"],[np.mean([pred[f"gate_{n}_h{h}"].mean() for h in hs]) for n in ["short","medium","long","range_vol"]],"Mean weight")
    save("predicted_vs_actual_volatility.png","Predicted vs actual volatility",pdates,{"Actual":pred["actual_volatility_h20"],"Predicted":pred["predicted_volatility_h20"]},"Volatility (%)"); bar("mdd_threshold_calibration.png","MDD threshold exceedance frequency",["-5","-10","-15"],[np.mean(pred.actual_mdd_h20<t) for t in [-5,-10,-15]],"Frequency")
    bar("baseline_return_pinball_comparison.png","Return pinball comparison",[f"MSDP {h}" for h in hs]+[f"Zero {h}" for h in hs],[metrics[f"h{h}"]["return_pinball"] for h in hs]+[baseline[f"h{h}"]["return_pinball"] for h in hs],"Pinball loss"); bar("baseline_direction_brier_comparison.png","Direction Brier comparison",[f"MSDP {h}" for h in hs]+[f"Zero {h}" for h in hs],[metrics[f"h{h}"]["brier"] for h in hs]+[baseline[f"h{h}"]["brier"] for h in hs],"Brier score")
    bar("baseline_interval_coverage_comparison.png","MSDP interval coverage",[str(h) for h in hs],[metrics[f"h{h}"]["calibrated_interval"]["coverage"] for h in hs],"Coverage"); bar("baseline_interval_score_comparison.png","MSDP interval score",[str(h) for h in hs],[metrics[f"h{h}"]["calibrated_interval"]["winkler"] for h in hs],"Score")
    if ablations: bar("ablation_comparison.png","Ablation comparison",[a["name"] for a in ablations],[a["return_pinball_mean"] for a in ablations],"Mean pinball")
    bar("bootstrap_confidence_intervals.png","Model minus baseline MAE",[str(h) for h in hs],[metrics[f"h{h}"]["vs_zero_baseline"]["return_mae"] for h in hs],"MAE difference"); bar("performance_by_market_condition.png","Performance summary",[str(h) for h in hs],[metrics[f"h{h}"]["return_mae"] for h in hs],"MAE"); bar("seed_stability.png","Seed validation stability",[str(s["seed"]) for s in seed_results],[s["best_validation_loss"] for s in seed_results],"Loss")
    lh=latest["horizons"]; bar("latest_horizon_return_profile.png","Latest horizon return profile",[str(x["horizon"]) for x in lh],[x["return_quantiles"][2] for x in lh],"Median return (%)"); bar("latest_projected_index_interval.png","Latest calibrated return interval",[str(x["horizon"]) for x in lh],[x["calibrated_interval"][1]-x["calibrated_interval"][0] for x in lh],"Width (%)"); bar("latest_gate_weights.png","Latest gate concentration",[str(x["horizon"]) for x in lh],[max(x["expert_weights"]) for x in lh],"Maximum weight"); bar("latest_risk_profile.png","Latest MDD median",[str(x["horizon"]) for x in lh],[x["mdd_quantiles"][1] for x in lh],"MDD (%)"); bar("latest_confidence_components.png","Latest confidence score",[str(x["horizon"]) for x in lh],[x.get("confidence_score",x.get("confidence",{}).get("score",np.nan)) for x in lh],"Score")
    (out/"figure_manifest.json").write_text(__import__("json").dumps(manifest,indent=2),encoding="utf-8"); return manifest
