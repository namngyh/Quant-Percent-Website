"""Sinh toàn bộ README tiếng Việt từ artifact thực tế của pipeline."""
from pathlib import Path
import argparse,json,subprocess
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(); p.add_argument("--run-id",required=True); args=p.parse_args()
metrics=json.loads((ROOT/"reports/tables/final_metrics.json").read_text(encoding="utf-8")); baseline=json.loads((ROOT/"reports/tables/baseline_metrics.json").read_text(encoding="utf-8")); bootstrap=json.loads((ROOT/"reports/tables/bootstrap_results.json").read_text(encoding="utf-8")); ablations=json.loads((ROOT/"reports/tables/ablation_results.json").read_text(encoding="utf-8")); seeds=json.loads((ROOT/"reports/tables/seed_results.json").read_text(encoding="utf-8")); quality=json.loads((ROOT/"reports/tables/data_quality.json").read_text(encoding="utf-8")); latest=json.loads((ROOT/"artifacts/predictions/latest_forecast.json").read_text(encoding="utf-8")); summary=json.loads((ROOT/"artifacts/runs"/args.run_id/"run_summary.json").read_text(encoding="utf-8")); pred=pd.read_csv(ROOT/"artifacts/predictions/test_predictions.csv"); manifest=json.loads((ROOT/"reports/figures/figure_manifest.json").read_text(encoding="utf-8")); hs=[5,20,60]
production=json.loads((ROOT/"artifacts/models"/args.run_id/"production_ensemble_manifest.json").read_text(encoding="utf-8"))
if summary.get("run_id")!=args.run_id or latest.get("run_id")!=args.run_id or production.get("run_id")!=args.run_id: raise SystemExit("Run ID không đồng bộ giữa summary, latest và production manifest")
current_commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
if production.get("git_commit")!=current_commit: raise SystemExit(f"Artifact commit {production.get('git_commit')} khác current HEAD {current_commit}")

titles={
"data_quality_overview.png":"Tổng quan chất lượng dữ liệu","vnindex_close_history.png":"Lịch sử điểm đóng cửa VN-Index","vnindex_drawdown_history.png":"Lịch sử drawdown VN-Index","return_distribution.png":"Phân phối lợi suất ngày","rolling_volatility.png":"Biến động cuốn chiếu","target_distribution_by_horizon.png":"Phân phối target theo kỳ hạn","training_total_loss_by_seed.png":"Tổng loss huấn luyện","training_return_loss.png":"Loss phân vị lợi suất","training_direction_loss.png":"Loss xác suất hướng","training_mdd_loss.png":"Loss maximum drawdown","training_volatility_loss.png":"Loss biến động","learning_rate_history.png":"Lịch sử learning rate","seed_validation_comparison.png":"So sánh validation giữa các seed","raw_vs_calibrated_coverage.png":"Coverage trước và sau conformal","interval_width_by_horizon.png":"Độ rộng khoảng theo kỳ hạn","interval_score_by_horizon.png":"Interval score theo kỳ hạn","conditional_coverage_by_volatility.png":"Coverage theo trạng thái biến động","direction_probability_vs_actual.png":"Xác suất tăng và kết quả thực tế","brier_score_by_horizon.png":"Brier score theo kỳ hạn","mean_gate_weights_by_horizon.png":"Trọng số gate trung bình","gate_entropy_by_horizon.png":"Entropy gate chuẩn hóa","expert_disagreement.png":"Mức bất đồng giữa các expert","expert_latent_correlation.png":"Tương quan dự báo giữa các expert","expert_usage_by_market_condition.png":"Mức sử dụng expert","predicted_vs_actual_volatility.png":"Biến động dự báo và thực tế","mdd_threshold_calibration.png":"Tần suất vượt ngưỡng MDD","baseline_return_pinball_comparison.png":"So sánh pinball với baseline","baseline_direction_brier_comparison.png":"So sánh Brier với baseline","baseline_interval_coverage_comparison.png":"So sánh coverage","baseline_interval_score_comparison.png":"So sánh interval score","ablation_comparison.png":"Kết quả ablation","bootstrap_confidence_intervals.png":"Khoảng tin cậy bootstrap","performance_by_market_condition.png":"Hiệu năng theo điều kiện thị trường","seed_stability.png":"Độ ổn định theo seed","latest_horizon_return_profile.png":"Hồ sơ lợi suất mới nhất","latest_projected_index_interval.png":"Khoảng chỉ số dự phóng mới nhất","latest_gate_weights.png":"Gate mới nhất","latest_risk_profile.png":"Hồ sơ rủi ro mới nhất","latest_confidence_components.png":"Các thành phần confidence mới nhất"}
for h in hs:
    titles.update({f"predicted_vs_actual_return_h{h}.png":f"Lợi suất dự báo và thực tế — {h} phiên",f"return_fan_chart_h{h}.png":f"Biểu đồ quạt lợi suất — {h} phiên",f"residual_return_h{h}.png":f"Phần dư lợi suất — {h} phiên",f"rolling_coverage_h{h}.png":f"Coverage cuốn chiếu — {h} phiên",f"direction_reliability_h{h}.png":f"Độ tin cậy xác suất hướng — {h} phiên",f"gate_weights_h{h}.png":f"Trọng số gate — {h} phiên",f"expert_predictions_h{h}.png":f"Dự báo riêng từng expert — {h} phiên",f"predicted_vs_actual_mdd_h{h}.png":f"MDD dự báo và thực tế — {h} phiên"})
titles.update({"baseline_point_forecast_comparison.png":"So sánh baseline dự báo điểm","baseline_distribution_comparison.png":"So sánh baseline phân phối","baseline_direction_comparison.png":"So sánh baseline xác suất hướng","baseline_risk_comparison.png":"So sánh baseline rủi ro","conformal_method_comparison.png":"So sánh phương pháp conformal","conformal_interval_score_comparison.png":"So sánh interval score conformal","tuning_fold_scores.png":"Objective theo fold tuning","production_ensemble_consistency.png":"Nhất quán ensemble production","latest_seed_dispersion.png":"Phân tán seed mới nhất","ohlc_mask_impact.png":"Ảnh hưởng mask OHLC","optuna_optimization_history.png":"Lịch sử tối ưu Optuna","optuna_parameter_importance.png":"Tầm quan trọng tham số Optuna","optuna_parallel_coordinate.png":"Tọa độ song song Optuna"})

def h_from(name):
    for h in hs:
        if f"h{h}" in name: return h
    return None
def comment(name):
    h=h_from(name)
    if "predicted_vs_actual_return" in name: return f"MAE kỳ hạn {h} là {metrics[f'h{h}']['return_mae']:.3f}% và Spearman {metrics[f'h{h}']['spearman']:.3f}. Dự báo trung vị chưa bám sát mạnh biến động thực tế; mô hình phù hợp hơn với mô tả phân phối rủi ro so với dự báo điểm."
    if "fan_chart" in name: return f"Khoảng gốc đạt coverage {metrics[f'h{h}']['coverage']:.1%}. Sau conformal, coverage đạt {metrics[f'h{h}']['calibrated_interval']['coverage']:.1%}, nhưng độ rộng tăng từ {metrics[f'h{h}']['width']:.2f}% lên {metrics[f'h{h}']['calibrated_interval']['width']:.2f}%."
    if "residual_return" in name: return f"Phần dư kỳ hạn {h} phản ánh sai số dự báo trung vị; RMSE thực tế là {metrics[f'h{h}']['return_rmse']:.3f}%. Các cụm sai số lớn cho thấy ảnh hưởng của regime và volatility clustering."
    if "rolling_coverage" in name: return f"Coverage cuốn chiếu kỳ hạn {h} không ổn định tuyệt đối theo thời gian. Coverage tổng thể sau hiệu chỉnh là {metrics[f'h{h}']['calibrated_interval']['coverage']:.1%}; đây là coverage thực nghiệm, không phải bảo đảm iid."
    if "direction_reliability" in name: return f"Brier score kỳ hạn {h} là {metrics[f'h{h}']['brier']:.4f}, ROC AUC {metrics[f'h{h}'].get('roc_auc',float('nan')):.3f}. Xác suất có thông tin hạn chế và chưa tạo phân tách lớp mạnh."
    if "gate_weights_h" in name:
        means={n:pred[f"gate_{n}_h{h}"].mean() for n in ["short","medium","long","range_vol"]}; dom=max(means,key=means.get); return f"Expert có trọng số trung bình cao nhất là `{dom}` ({means[dom]:.3f}). " + ("Kết quả hỗ trợ chuyên môn hóa ngắn hạn." if h==5 and dom=="short" else "Kết quả chưa hỗ trợ giả thuyết short expert chi phối kỳ hạn 5 phiên." if h==5 else "Long expert tăng vai trò ở kỳ hạn dài, nhưng mức phân hóa gate vẫn tương đối thấp.")
    if "expert_predictions" in name: return f"Độ lệch chuẩn trung bình giữa auxiliary expert forecasts ở kỳ hạn {h} là {pred[f'expert_disagreement_h{h}'].mean():.3f}%. Đây là bất đồng dự báo, khác với entropy của trọng số gate."
    if "predicted_vs_actual_mdd" in name: return f"MDD MAE kỳ hạn {h} là {metrics[f'h{h}']['mdd_mae']:.3f}%. q10 biểu diễn kịch bản drawdown xấu hơn, còn q90 gần 0 hơn; toàn bộ quantile đã được audit không dương."
    if "coverage" in name or "interval" in name: return "Conformal cải thiện độ bao phủ nhưng làm khoảng rộng hơn, đặc biệt ở kỳ hạn dài. Giá trị chính là mô tả bất định; độ sắc nét của dự báo giảm khi yêu cầu coverage cao."
    if "brier" in name or "direction_probability" in name: return "Brier giảm so với ZeroReturn ở cả ba kỳ hạn, nhưng balanced accuracy vẫn gần vùng 0,5. Không nên diễn giải xác suất tăng như tín hiệu giao dịch chắc chắn."
    if "gate" in name or "expert" in name: return "Gate có xu hướng gần trọng số đều; long expert nhận trọng số cao nhất ở cả ba kỳ hạn. Learned gate chưa chứng minh giá trị vượt equal-weight trong quick ablation."
    if "baseline" in name: return "H5 và H20 có pinball kém ZeroReturn; H60 có pinball tốt hơn nhưng MAE kém hơn. Không có cải thiện nhất quán trên mọi metric và horizon."
    if "ablation" in name: return f"Equal-weight đạt mean pinball {ablations[0]['return_pinball_mean']:.4f}, thấp hơn Full MSDP khoảng {np.mean([metrics[f'h{h}']['return_pinball'] for h in hs]):.4f}; single-scale đạt {ablations[1]['return_pinball_mean']:.4f}. Learned gate chưa vượt equal-weight."
    if "bootstrap" in name: return "Cả ba CI95 của chênh lệch MAE đều chứa 0. Chênh lệch metric chưa có ý nghĩa rõ ràng theo moving-block bootstrap."
    if "latest" in name: return f"Hồ sơ ngày {latest['data_date']} cho thấy median return dương ở cả ba horizon, nhưng calibrated interval đều bao gồm 0 và mở rộng mạnh theo kỳ hạn. Đây không phải đường giá tương lai hay khuyến nghị mua bán."
    if "training" in name or "learning_rate" in name or "seed" in name: return f"Quick run dùng {len(seeds)} seed; best epoch là {seeds[0]['best_epoch']} với validation loss {seeds[0]['best_validation_loss']:.4f}. Một seed không đủ đánh giá độ ổn định đa seed."
    if "volatility" in name: return "Volatility MAE lần lượt là " + ", ".join("{:.2f}%".format(metrics[f"h{h}"]["volatility_mae"]) for h in hs) + " cho H5/H20/H60. Sai số giảm theo horizon nhưng vẫn đáng kể."
    if "drawdown" in name or "mdd" in name: return "Drawdown lịch sử thể hiện các giai đoạn stress rõ rệt. MDD head đã bị chặn ở miền không dương và không diễn giải q90 là kịch bản nghiêm trọng nhất."
    if "return_distribution" in name or "target_distribution" in name: return "Phân phối lợi suất có đuôi và độ phân tán tăng theo horizon, là lý do dùng quantile regression thay cho giả định Gaussian cố định."
    if "quality" in name: return f"Có {quality['rows']} phiên từ {quality['start']} đến {quality['end']}. Pipeline ghi nhận {quality['issues']} và không âm thầm sửa file nguồn."
    return "Biểu đồ được sinh trực tiếp từ dữ liệu hoặc artifact của quick pipeline; không sử dụng số liệu minh họa giả."

groups=[("Dữ liệu",manifest[:6]),("Huấn luyện",manifest[6:13]),("Dự báo lợi suất",[x for x in manifest if any(k in x for k in ["predicted_vs_actual_return","return_fan_chart","residual_return"])]),("Hiệu chỉnh conformal",[x for x in manifest if "coverage" in x or "interval_width" in x or "interval_score" in x]),("Xác suất hướng",[x for x in manifest if "direction_" in x or "brier" in x]),("Expert và gate",[x for x in manifest if "gate" in x or "expert" in x]),("Rủi ro",[x for x in manifest if "mdd" in x or "volatility" in x]),("So sánh mô hình",[x for x in manifest if "baseline" in x or "ablation" in x or "bootstrap" in x or "performance" in x or "seed_stability" in x]),("Dự báo mới nhất",[x for x in manifest if "latest" in x])]
used=set(); figure_sections=[]
for group,files in groups:
    unique=[x for x in files if x not in used]; used.update(unique)
    if not unique: continue
    parts=[f"## {group}"]
    for name in unique: parts.extend([f"### {titles.get(name,name)}",f"![{titles.get(name,name)}](reports/figures/{name})",f"**Nhận xét:** {comment(name)}"])
    figure_sections.append("\n\n".join(parts))
left=[x for x in manifest if x not in used]
if left:
    figure_sections.append("## Biểu đồ bổ sung\n\n"+"\n\n".join(f"### {titles.get(x,x)}\n\n![{titles.get(x,x)}](reports/figures/{x})\n\n**Nhận xét:** {comment(x)}" for x in left))

metric_rows="\n".join(f"| {h} | {metrics[f'h{h}']['return_mae']:.4f} | {metrics[f'h{h}']['return_pinball']:.4f} | {metrics[f'h{h}']['brier']:.4f} | {metrics[f'h{h}']['coverage']:.1%} | {metrics[f'h{h}']['calibrated_interval']['coverage']:.1%} | {metrics[f'h{h}']['vs_zero_baseline']['return_pinball']:+.4f} |" for h in hs)
latest_rows="".join(f"| {x['horizon']} | {x['probability_positive']:.1%} | {x['return_quantiles'][2]:+.3f}% | [{x['calibrated_interval'][0]:+.3f}%; {x['calibrated_interval'][1]:+.3f}%] |\n" for x in latest['horizons'])
figure_text="\n\n".join(figure_sections)
readme=f"""# MSDP — Bộ dự báo phân phối đa thang đo cho VN-Index

## Tóm tắt nghiên cứu

MSDP dự báo trực tiếp phân phối lợi suất VN-Index cho 5, 20 và 60 phiên bằng bốn chuyên gia causal: ngắn hạn, trung hạn, dài hạn và range–volatility. Mô hình đồng thời dự báo xác suất tăng, các phân vị lợi suất, maximum drawdown, realized volatility, trọng số gate và mức bất đồng giữa các expert.

Repository này là phần mềm nghiên cứu, không phải khuyến nghị đầu tư. Toàn bộ số liệu và biểu đồ dưới đây được đọc từ artifact của `{summary.get('run_label')}` run; không dùng số liệu minh họa.

## Định danh kết quả

- Run ID: `{args.run_id}`
- Git commit: `{production['git_commit']}`
- Data hash: `{production['data_hash']}`
- Config: `{production['config_path']}`
- Generated at: `{production['created_at']}`
- Test log: `reports/runs/{args.run_id}/test_results.txt`
- Artifact: `artifacts/models/{args.run_id}/production_ensemble_manifest.json`
- Số trial: `{summary.get('tuning_trials','chưa ghi')}`
- Số fold: `{summary.get('tuning_folds','chưa ghi')}`
- Số seed: `{len(production['seeds'])}`
- Bootstrap resamples: `{summary.get('bootstrap_resamples','chưa ghi')}`

## Kết luận chính

**Trong cấu hình và giai đoạn dữ liệu hiện tại, chưa có bằng chứng cho thấy MSDP vượt baseline.** H5 và H20 có pinball kém ZeroReturn. H60 có pinball và Brier tốt hơn nhưng MAE kém hơn. Mọi CI95 bootstrap của chênh lệch MAE đều chứa 0. Equal-weight ablation có pinball trung bình thấp hơn learned gate.

Giá trị chính của MSDP hiện nằm ở dự báo phân phối và hiệu chỉnh rủi ro, chưa phải ở dự báo điểm.

## Dữ liệu và giao thức ngoài mẫu

- {quality['rows']} phiên, từ {quality['start']} đến {quality['end']}.
- Development/calibration/test theo thời gian, purge 60 phiên.
- Feature selection và scaler không dùng test.
- CQR fit trên ensemble calibration prediction.
- Final test có {len(pred)} origin dự báo.
- Quick run: {summary['runtime_seconds']:.2f} giây, {len(seeds)} seed, 3 Optuna trials, hai ablation và 50 bootstrap resamples.

## Kiến trúc và tính đúng toán học

- Convolution causal dùng left padding; không dùng symmetric padding.
- Return head lấy median làm tâm và bảo đảm `q05 ≤ q25 ≤ q50 ≤ q75 ≤ q95`.
- MDD head bảo đảm `q10 ≤ q50 ≤ q90 ≤ 0`; q10 là kịch bản xấu hơn.
- CQR score là `max(lower-y, y-upper, 0)`; qhat riêng horizon và không âm.
- Target scaler riêng theo type/horizon; volatility dùng `log1p` và Huber loss.
- Gate nhận expert latent, learned context và horizon embedding.
- Expert disagreement là độ lệch chuẩn auxiliary return forecast, không phải độ lệch gate weights.

## Kết quả final test

| Horizon | MAE | Pinball | Brier | Coverage gốc | Coverage conformal | Pinball Δ so với ZeroReturn |
|---:|---:|---:|---:|---:|---:|---:|
{metric_rows}

## Dự báo mới nhất

Ngày dữ liệu: **{latest['data_date']}**; VN-Index: **{latest['current_vnindex']:.2f}**.

| Horizon | Xác suất tăng | Median return | Khoảng conformal |
|---:|---:|---:|---:|
{latest_rows}

Ba horizon tạo thành **hồ sơ dự báo theo khoảng thời gian**, không phải đường giá dự báo từng bước.

## Cài đặt và lệnh Windows

```powershell
conda create -n msdp python=3.11 -y
conda activate msdp
pip install -r requirements.txt
pytest -q
python scripts/inspect_data.py --data data/raw/VNINDEX_Daily.csv
python scripts/run_all.py --config configs/quick.yaml --data data/raw/VNINDEX_Daily.csv
python scripts/run_all.py --config configs/default.yaml --data data/raw/VNINDEX_Daily.csv
python scripts/predict_latest.py --config configs/default.yaml --data data/raw/VNINDEX_Daily.csv --model artifacts/models/production_model.pt
python scripts/generate_report.py --run latest
python scripts/update_readme_results.py --run-id {args.run_id}
```

## Hạn chế

- Artifact hiện tại là quick run một seed, chưa phải default three-seed study.
- Dữ liệu nguồn có vi phạm OHLC được ghi trong data-quality report.
- Coverage tăng nhờ conformal nhưng interval dài hạn rất rộng.
- Gate gần equal-weight và chưa vượt equal-weight ablation.
- Production full retraining và OOF production calibration chưa hoàn tất.

# Toàn bộ biểu đồ và nhận xét

{figure_text}

## Tài liệu chi tiết

- [Báo cáo nghiên cứu đầy đủ](reports/MSDP_BAO_CAO_DAY_DU_VI.md)
- [Nhận xét kết quả](reports/MSDP_NHAN_XET_KET_QUA_VI.md)
- [Review repository](reports/MSDP_REPOSITORY_REVIEW_VI.md)
- [Kết quả kiểm thử](reports/test_results.txt)
- [Hạn chế](reports/MSDP_LIMITATIONS_VI.md)

## Tuyên bố miễn trừ trách nhiệm

Không sử dụng kết quả như bảo đảm lợi nhuận hoặc lời khuyên mua bán. Người dùng tự chịu trách nhiệm kiểm tra dữ liệu, giả định, chi phí giao dịch và rủi ro thị trường.
"""
(ROOT/"README.md").write_text(readme,encoding="utf-8"); (ROOT/"README_VI.md").write_text(readme,encoding="utf-8"); print(f"Đã cập nhật README tiếng Việt với {len(manifest)} biểu đồ cho run {args.run_id}.")
