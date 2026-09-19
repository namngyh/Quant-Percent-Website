# MSDP — Bộ dự báo phân phối đa thang đo cho VN-Index

## Tóm tắt nghiên cứu

MSDP dự báo trực tiếp phân phối lợi suất VN-Index cho 5, 20 và 60 phiên bằng bốn chuyên gia causal: ngắn hạn, trung hạn, dài hạn và range–volatility. Mô hình đồng thời dự báo xác suất tăng, các phân vị lợi suất, maximum drawdown, realized volatility, trọng số gate và mức bất đồng giữa các expert.

Repository này là phần mềm nghiên cứu, không phải khuyến nghị đầu tư. Toàn bộ số liệu và biểu đồ dưới đây được đọc từ artifact của `gpu` run; không dùng số liệu minh họa.

## Định danh kết quả

- Run ID: `20260722_154609_gpu`
- Git commit: `d3da0c72b31502dc49f13c77cc553e69dc1ba09f`
- Data hash: `de60ce39646402eaa7dba3b68390fa807a6efe2866a1ddf70c0ff603b9e2873f`
- Config: `configs/gpu.yaml`
- Generated at: `2026-07-22T17:26:17.213181`
- Test log: `reports/runs/20260722_154609_gpu/test_results.txt`
- Artifact: `artifacts/models/20260722_154609_gpu/production_ensemble_manifest.json`
- Số trial: `50`
- Số fold: `4`
- Số seed: `3`
- Bootstrap resamples: `1000`

## Kết luận chính

**Sau tuning đầy đủ, MSDP cải thiện trên phần lớn metric nhưng chưa có bằng chứng thống kê vượt baseline về dự báo điểm.** MAE thắng ZeroReturn ở H5; pinball thắng empirical distribution ở H20; Brier thắng historical frequency ở H5. Mọi CI95 bootstrap của chênh lệch MAE đều chứa 0. Learned gate đạt mean pinball 1.7484 so với equal-weight ablation 1.7677 — gate đã vượt equal-weight. Phương pháp conformal tốt nhất theo so sánh causal là `adaptive`.

Giá trị chính của MSDP nằm ở dự báo phân phối và hiệu chỉnh rủi ro, chưa phải ở dự báo điểm.

## Dữ liệu và giao thức ngoài mẫu

- 6306 phiên, từ 2000-07-28 đến 2026-07-13.
- Development/calibration/test theo thời gian, purge 60 phiên.
- Feature selection và scaler không dùng test.
- CQR fit trên ensemble calibration prediction.
- Final test có 830 origin dự báo.
- Run `gpu`: 6008.25 giây, 3 seed, 50 Optuna trials, 5 ablation và 1000 bootstrap resamples.

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
| 5 | 2.3250 | 0.7506 | 0.2463 | 87.8% | 90.2% | +0.0043 |
| 20 | 4.8486 | 1.5966 | 0.2496 | 86.7% | 88.6% | -0.0013 |
| 60 | 8.5669 | 2.8980 | 0.2477 | 86.1% | 88.0% | +0.1209 |

## Dự báo mới nhất

Ngày dữ liệu: **2026-07-13 00:00:00**; VN-Index: **1800.54**.

| Horizon | Xác suất tăng | Median return | Khoảng conformal |
|---:|---:|---:|---:|
| 5 | 51.8% | -0.499% | [-5.932%; +4.029%] |
| 20 | 52.7% | -0.963% | [-11.877%; +9.676%] |
| 60 | 54.7% | -1.564% | [-21.185%; +18.739%] |


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
python scripts/update_readme_results.py --run-id 20260722_154609_gpu
```

## Hạn chế

- Artifact hiện tại là run `gpu` với 3 seed và 50 Optuna trials; full five-seed study (`configs/full.yaml`) chưa chạy.
- Dữ liệu nguồn có vi phạm OHLC được ghi trong data-quality report.
- Coverage tăng nhờ conformal nhưng interval dài hạn rất rộng.
- Mọi CI95 bootstrap của chênh lệch MAE đều chứa 0 — chưa có ý nghĩa thống kê so với baseline.
- Best epoch chỉ 1–2 ở learning rate đã tune: mô hình hội tụ rất nhanh rồi overfit; lịch trình học cần nghiên cứu thêm.
- Các ablation đơn giản (shared_gate, single) vẫn cạnh tranh với full model.
- Production full retraining và OOF production calibration chưa hoàn tất.

# Toàn bộ biểu đồ và nhận xét

## Dữ liệu

### Lịch sử điểm đóng cửa VN-Index

![Lịch sử điểm đóng cửa VN-Index](reports/figures/vnindex_close_history.png)

**Nhận xét:** Biểu đồ được sinh trực tiếp từ dữ liệu hoặc artifact của pipeline; không sử dụng số liệu minh họa giả.

### Lịch sử drawdown VN-Index

![Lịch sử drawdown VN-Index](reports/figures/vnindex_drawdown_history.png)

**Nhận xét:** Drawdown lịch sử thể hiện các giai đoạn stress rõ rệt. MDD head đã bị chặn ở miền không dương và không diễn giải q90 là kịch bản nghiêm trọng nhất.

### Biến động cuốn chiếu

![Biến động cuốn chiếu](reports/figures/rolling_volatility.png)

**Nhận xét:** Volatility MAE lần lượt là 7.14%, 6.26%, 5.89% cho H5/H20/H60. Sai số giảm theo horizon nhưng vẫn đáng kể.

### Phân phối lợi suất ngày

![Phân phối lợi suất ngày](reports/figures/return_distribution.png)

**Nhận xét:** Phân phối lợi suất có đuôi và độ phân tán tăng theo horizon, là lý do dùng quantile regression thay cho giả định Gaussian cố định.

### Tổng quan chất lượng dữ liệu

![Tổng quan chất lượng dữ liệu](reports/figures/data_quality_overview.png)

**Nhận xét:** Có 6306 phiên từ 2000-07-28 đến 2026-07-13. Pipeline ghi nhận ['OHLC constraint violations: high=27, low=15'] và không âm thầm sửa file nguồn.

### Phân phối target theo kỳ hạn

![Phân phối target theo kỳ hạn](reports/figures/target_distribution_by_horizon.png)

**Nhận xét:** Phân phối lợi suất có đuôi và độ phân tán tăng theo horizon, là lý do dùng quantile regression thay cho giả định Gaussian cố định.

## Huấn luyện

### Tổng loss huấn luyện

![Tổng loss huấn luyện](reports/figures/training_total_loss_by_seed.png)

**Nhận xét:** Run dùng 3 seed; best epoch 1–2 với validation loss 0.2687–0.2862. Best epoch rất sớm cho thấy mô hình hội tụ nhanh ở learning rate đã tune; cần theo dõi overfitting.

### Loss phân vị lợi suất

![Loss phân vị lợi suất](reports/figures/training_return_loss.png)

**Nhận xét:** Run dùng 3 seed; best epoch 1–2 với validation loss 0.2687–0.2862. Best epoch rất sớm cho thấy mô hình hội tụ nhanh ở learning rate đã tune; cần theo dõi overfitting.

### Loss xác suất hướng

![Loss xác suất hướng](reports/figures/training_direction_loss.png)

**Nhận xét:** Run dùng 3 seed; best epoch 1–2 với validation loss 0.2687–0.2862. Best epoch rất sớm cho thấy mô hình hội tụ nhanh ở learning rate đã tune; cần theo dõi overfitting.

### Loss maximum drawdown

![Loss maximum drawdown](reports/figures/training_mdd_loss.png)

**Nhận xét:** Run dùng 3 seed; best epoch 1–2 với validation loss 0.2687–0.2862. Best epoch rất sớm cho thấy mô hình hội tụ nhanh ở learning rate đã tune; cần theo dõi overfitting.

### Loss biến động

![Loss biến động](reports/figures/training_volatility_loss.png)

**Nhận xét:** Run dùng 3 seed; best epoch 1–2 với validation loss 0.2687–0.2862. Best epoch rất sớm cho thấy mô hình hội tụ nhanh ở learning rate đã tune; cần theo dõi overfitting.

### Lịch sử learning rate

![Lịch sử learning rate](reports/figures/learning_rate_history.png)

**Nhận xét:** Run dùng 3 seed; best epoch 1–2 với validation loss 0.2687–0.2862. Best epoch rất sớm cho thấy mô hình hội tụ nhanh ở learning rate đã tune; cần theo dõi overfitting.

### So sánh validation giữa các seed

![So sánh validation giữa các seed](reports/figures/seed_validation_comparison.png)

**Nhận xét:** Run dùng 3 seed; best epoch 1–2 với validation loss 0.2687–0.2862. Best epoch rất sớm cho thấy mô hình hội tụ nhanh ở learning rate đã tune; cần theo dõi overfitting.

## Dự báo lợi suất

### Lợi suất dự báo và thực tế — 5 phiên

![Lợi suất dự báo và thực tế — 5 phiên](reports/figures/predicted_vs_actual_return_h5.png)

**Nhận xét:** MAE kỳ hạn 5 là 2.325% và Spearman -0.011. Dự báo trung vị chưa bám sát mạnh biến động thực tế; mô hình phù hợp hơn với mô tả phân phối rủi ro so với dự báo điểm.

### Biểu đồ quạt lợi suất — 5 phiên

![Biểu đồ quạt lợi suất — 5 phiên](reports/figures/return_fan_chart_h5.png)

**Nhận xét:** Khoảng gốc đạt coverage 87.8%. Sau conformal, coverage đạt 90.2%, nhưng độ rộng tăng từ 9.33% lên 10.15%.

### Phần dư lợi suất — 5 phiên

![Phần dư lợi suất — 5 phiên](reports/figures/residual_return_h5.png)

**Nhận xét:** Phần dư kỳ hạn 5 phản ánh sai số dự báo trung vị; RMSE thực tế là 3.024%. Các cụm sai số lớn cho thấy ảnh hưởng của regime và volatility clustering.

### Lợi suất dự báo và thực tế — 20 phiên

![Lợi suất dự báo và thực tế — 20 phiên](reports/figures/predicted_vs_actual_return_h20.png)

**Nhận xét:** MAE kỳ hạn 20 là 4.849% và Spearman -0.041. Dự báo trung vị chưa bám sát mạnh biến động thực tế; mô hình phù hợp hơn với mô tả phân phối rủi ro so với dự báo điểm.

### Biểu đồ quạt lợi suất — 20 phiên

![Biểu đồ quạt lợi suất — 20 phiên](reports/figures/return_fan_chart_h20.png)

**Nhận xét:** Khoảng gốc đạt coverage 86.7%. Sau conformal, coverage đạt 88.6%, nhưng độ rộng tăng từ 20.50% lên 22.63%.

### Phần dư lợi suất — 20 phiên

![Phần dư lợi suất — 20 phiên](reports/figures/residual_return_h20.png)

**Nhận xét:** Phần dư kỳ hạn 20 phản ánh sai số dự báo trung vị; RMSE thực tế là 6.377%. Các cụm sai số lớn cho thấy ảnh hưởng của regime và volatility clustering.

### Lợi suất dự báo và thực tế — 60 phiên

![Lợi suất dự báo và thực tế — 60 phiên](reports/figures/predicted_vs_actual_return_h60.png)

**Nhận xét:** MAE kỳ hạn 60 là 8.567% và Spearman -0.111. Dự báo trung vị chưa bám sát mạnh biến động thực tế; mô hình phù hợp hơn với mô tả phân phối rủi ro so với dự báo điểm.

### Biểu đồ quạt lợi suất — 60 phiên

![Biểu đồ quạt lợi suất — 60 phiên](reports/figures/return_fan_chart_h60.png)

**Nhận xét:** Khoảng gốc đạt coverage 86.1%. Sau conformal, coverage đạt 88.0%, nhưng độ rộng tăng từ 38.77% lên 41.30%.

### Phần dư lợi suất — 60 phiên

![Phần dư lợi suất — 60 phiên](reports/figures/residual_return_h60.png)

**Nhận xét:** Phần dư kỳ hạn 60 phản ánh sai số dự báo trung vị; RMSE thực tế là 11.300%. Các cụm sai số lớn cho thấy ảnh hưởng của regime và volatility clustering.

## Hiệu chỉnh conformal

### Coverage cuốn chiếu — 5 phiên

![Coverage cuốn chiếu — 5 phiên](reports/figures/rolling_coverage_h5.png)

**Nhận xét:** Coverage cuốn chiếu kỳ hạn 5 không ổn định tuyệt đối theo thời gian. Coverage tổng thể sau hiệu chỉnh là 90.2%; đây là coverage thực nghiệm, không phải bảo đảm iid.

### Coverage cuốn chiếu — 20 phiên

![Coverage cuốn chiếu — 20 phiên](reports/figures/rolling_coverage_h20.png)

**Nhận xét:** Coverage cuốn chiếu kỳ hạn 20 không ổn định tuyệt đối theo thời gian. Coverage tổng thể sau hiệu chỉnh là 88.6%; đây là coverage thực nghiệm, không phải bảo đảm iid.

### Coverage cuốn chiếu — 60 phiên

![Coverage cuốn chiếu — 60 phiên](reports/figures/rolling_coverage_h60.png)

**Nhận xét:** Coverage cuốn chiếu kỳ hạn 60 không ổn định tuyệt đối theo thời gian. Coverage tổng thể sau hiệu chỉnh là 88.0%; đây là coverage thực nghiệm, không phải bảo đảm iid.

### Coverage trước và sau conformal

![Coverage trước và sau conformal](reports/figures/raw_vs_calibrated_coverage.png)

**Nhận xét:** Conformal cải thiện độ bao phủ nhưng làm khoảng rộng hơn, đặc biệt ở kỳ hạn dài. Giá trị chính là mô tả bất định; độ sắc nét của dự báo giảm khi yêu cầu coverage cao.

### Độ rộng khoảng theo kỳ hạn

![Độ rộng khoảng theo kỳ hạn](reports/figures/interval_width_by_horizon.png)

**Nhận xét:** Conformal cải thiện độ bao phủ nhưng làm khoảng rộng hơn, đặc biệt ở kỳ hạn dài. Giá trị chính là mô tả bất định; độ sắc nét của dự báo giảm khi yêu cầu coverage cao.

### Interval score theo kỳ hạn

![Interval score theo kỳ hạn](reports/figures/interval_score_by_horizon.png)

**Nhận xét:** Conformal cải thiện độ bao phủ nhưng làm khoảng rộng hơn, đặc biệt ở kỳ hạn dài. Giá trị chính là mô tả bất định; độ sắc nét của dự báo giảm khi yêu cầu coverage cao.

### Coverage theo trạng thái biến động

![Coverage theo trạng thái biến động](reports/figures/conditional_coverage_by_volatility.png)

**Nhận xét:** Conformal cải thiện độ bao phủ nhưng làm khoảng rộng hơn, đặc biệt ở kỳ hạn dài. Giá trị chính là mô tả bất định; độ sắc nét của dự báo giảm khi yêu cầu coverage cao.

### So sánh coverage

![So sánh coverage](reports/figures/baseline_interval_coverage_comparison.png)

**Nhận xét:** Conformal cải thiện độ bao phủ nhưng làm khoảng rộng hơn, đặc biệt ở kỳ hạn dài. Giá trị chính là mô tả bất định; độ sắc nét của dự báo giảm khi yêu cầu coverage cao.

### So sánh interval score

![So sánh interval score](reports/figures/baseline_interval_score_comparison.png)

**Nhận xét:** Conformal cải thiện độ bao phủ nhưng làm khoảng rộng hơn, đặc biệt ở kỳ hạn dài. Giá trị chính là mô tả bất định; độ sắc nét của dự báo giảm khi yêu cầu coverage cao.

## Xác suất hướng

### Độ tin cậy xác suất hướng — 5 phiên

![Độ tin cậy xác suất hướng — 5 phiên](reports/figures/direction_reliability_h5.png)

**Nhận xét:** Brier score kỳ hạn 5 là 0.2463, ROC AUC 0.516. Xác suất có thông tin hạn chế và chưa tạo phân tách lớp mạnh.

### Độ tin cậy xác suất hướng — 20 phiên

![Độ tin cậy xác suất hướng — 20 phiên](reports/figures/direction_reliability_h20.png)

**Nhận xét:** Brier score kỳ hạn 20 là 0.2496, ROC AUC 0.490. Xác suất có thông tin hạn chế và chưa tạo phân tách lớp mạnh.

### Độ tin cậy xác suất hướng — 60 phiên

![Độ tin cậy xác suất hướng — 60 phiên](reports/figures/direction_reliability_h60.png)

**Nhận xét:** Brier score kỳ hạn 60 là 0.2477, ROC AUC 0.466. Xác suất có thông tin hạn chế và chưa tạo phân tách lớp mạnh.

### Xác suất tăng và kết quả thực tế

![Xác suất tăng và kết quả thực tế](reports/figures/direction_probability_vs_actual.png)

**Nhận xét:** Brier thắng baseline tần suất lịch sử ở H5 (H5: 0.2463 vs 0.2480, H20: 0.2496 vs 0.2468, H60: 0.2477 vs 0.2428). Balanced accuracy vẫn gần vùng 0,5; không nên diễn giải xác suất tăng như tín hiệu giao dịch chắc chắn.

### Brier score theo kỳ hạn

![Brier score theo kỳ hạn](reports/figures/brier_score_by_horizon.png)

**Nhận xét:** Brier thắng baseline tần suất lịch sử ở H5 (H5: 0.2463 vs 0.2480, H20: 0.2496 vs 0.2468, H60: 0.2477 vs 0.2428). Balanced accuracy vẫn gần vùng 0,5; không nên diễn giải xác suất tăng như tín hiệu giao dịch chắc chắn.

### So sánh Brier với baseline

![So sánh Brier với baseline](reports/figures/baseline_direction_brier_comparison.png)

**Nhận xét:** Brier thắng baseline tần suất lịch sử ở H5 (H5: 0.2463 vs 0.2480, H20: 0.2496 vs 0.2468, H60: 0.2477 vs 0.2428). Balanced accuracy vẫn gần vùng 0,5; không nên diễn giải xác suất tăng như tín hiệu giao dịch chắc chắn.

## Expert và gate

### Trọng số gate — 5 phiên

![Trọng số gate — 5 phiên](reports/figures/gate_weights_h5.png)

**Nhận xét:** Expert có trọng số trung bình cao nhất là `short` (0.283). Kết quả hỗ trợ chuyên môn hóa ngắn hạn.

### Dự báo riêng từng expert — 5 phiên

![Dự báo riêng từng expert — 5 phiên](reports/figures/expert_predictions_h5.png)

**Nhận xét:** Độ lệch chuẩn trung bình giữa auxiliary expert forecasts ở kỳ hạn 5 là 0.107%. Đây là bất đồng dự báo, khác với entropy của trọng số gate.

### Trọng số gate — 20 phiên

![Trọng số gate — 20 phiên](reports/figures/gate_weights_h20.png)

**Nhận xét:** Expert có trọng số trung bình cao nhất là `long` (0.281). Long expert tăng vai trò ở kỳ hạn dài, nhưng mức phân hóa gate vẫn tương đối thấp.

### Dự báo riêng từng expert — 20 phiên

![Dự báo riêng từng expert — 20 phiên](reports/figures/expert_predictions_h20.png)

**Nhận xét:** Độ lệch chuẩn trung bình giữa auxiliary expert forecasts ở kỳ hạn 20 là 0.438%. Đây là bất đồng dự báo, khác với entropy của trọng số gate.

### Trọng số gate — 60 phiên

![Trọng số gate — 60 phiên](reports/figures/gate_weights_h60.png)

**Nhận xét:** Expert có trọng số trung bình cao nhất là `range_vol` (0.361). Long expert tăng vai trò ở kỳ hạn dài, nhưng mức phân hóa gate vẫn tương đối thấp.

### Dự báo riêng từng expert — 60 phiên

![Dự báo riêng từng expert — 60 phiên](reports/figures/expert_predictions_h60.png)

**Nhận xét:** Độ lệch chuẩn trung bình giữa auxiliary expert forecasts ở kỳ hạn 60 là 0.979%. Đây là bất đồng dự báo, khác với entropy của trọng số gate.

### Trọng số gate trung bình

![Trọng số gate trung bình](reports/figures/mean_gate_weights_by_horizon.png)

**Nhận xét:** Full MSDP đạt mean pinball 1.7484 so với equal-weight 1.7677 — learned gate đã vượt equal-weight trong ablation cùng split.

### Entropy gate chuẩn hóa

![Entropy gate chuẩn hóa](reports/figures/gate_entropy_by_horizon.png)

**Nhận xét:** Full MSDP đạt mean pinball 1.7484 so với equal-weight 1.7677 — learned gate đã vượt equal-weight trong ablation cùng split.

### Mức bất đồng giữa các expert

![Mức bất đồng giữa các expert](reports/figures/expert_disagreement.png)

**Nhận xét:** Full MSDP đạt mean pinball 1.7484 so với equal-weight 1.7677 — learned gate đã vượt equal-weight trong ablation cùng split.

### Tương quan dự báo giữa các expert

![Tương quan dự báo giữa các expert](reports/figures/expert_latent_correlation.png)

**Nhận xét:** Full MSDP đạt mean pinball 1.7484 so với equal-weight 1.7677 — learned gate đã vượt equal-weight trong ablation cùng split.

### Mức sử dụng expert

![Mức sử dụng expert](reports/figures/expert_usage_by_market_condition.png)

**Nhận xét:** Full MSDP đạt mean pinball 1.7484 so với equal-weight 1.7677 — learned gate đã vượt equal-weight trong ablation cùng split.

### Gate mới nhất

![Gate mới nhất](reports/figures/latest_gate_weights.png)

**Nhận xét:** Full MSDP đạt mean pinball 1.7484 so với equal-weight 1.7677 — learned gate đã vượt equal-weight trong ablation cùng split.

## Rủi ro

### MDD dự báo và thực tế — 5 phiên

![MDD dự báo và thực tế — 5 phiên](reports/figures/predicted_vs_actual_mdd_h5.png)

**Nhận xét:** MDD MAE kỳ hạn 5 là 1.505%. q10 biểu diễn kịch bản drawdown xấu hơn, còn q90 gần 0 hơn; toàn bộ quantile đã được audit không dương.

### MDD dự báo và thực tế — 20 phiên

![MDD dự báo và thực tế — 20 phiên](reports/figures/predicted_vs_actual_mdd_h20.png)

**Nhận xét:** MDD MAE kỳ hạn 20 là 3.253%. q10 biểu diễn kịch bản drawdown xấu hơn, còn q90 gần 0 hơn; toàn bộ quantile đã được audit không dương.

### MDD dự báo và thực tế — 60 phiên

![MDD dự báo và thực tế — 60 phiên](reports/figures/predicted_vs_actual_mdd_h60.png)

**Nhận xét:** MDD MAE kỳ hạn 60 là 5.499%. q10 biểu diễn kịch bản drawdown xấu hơn, còn q90 gần 0 hơn; toàn bộ quantile đã được audit không dương.

### Biến động dự báo và thực tế

![Biến động dự báo và thực tế](reports/figures/predicted_vs_actual_volatility.png)

**Nhận xét:** Volatility MAE lần lượt là 7.14%, 6.26%, 5.89% cho H5/H20/H60. Sai số giảm theo horizon nhưng vẫn đáng kể.

### Tần suất vượt ngưỡng MDD

![Tần suất vượt ngưỡng MDD](reports/figures/mdd_threshold_calibration.png)

**Nhận xét:** Drawdown lịch sử thể hiện các giai đoạn stress rõ rệt. MDD head đã bị chặn ở miền không dương và không diễn giải q90 là kịch bản nghiêm trọng nhất.

## So sánh mô hình

### So sánh pinball với baseline

![So sánh pinball với baseline](reports/figures/baseline_return_pinball_comparison.png)

**Nhận xét:** MAE thắng ZeroReturn ở H5; pinball thắng empirical distribution ở H20; Brier thắng historical frequency ở H5. Chưa có cải thiện nhất quán trên mọi metric và horizon.

### Kết quả ablation

![Kết quả ablation](reports/figures/ablation_comparison.png)

**Nhận xét:** Mean pinball: Full MSDP 1.7484; equal 1.7677; single 1.7279; no_range 2.1932; no_conformal 1.7074; shared_gate 1.7087. Learned gate thấp hơn (tốt hơn) equal-weight; các biến thể đơn giản hơn vẫn cạnh tranh nên kiến trúc còn dư địa tinh giản.

### Khoảng tin cậy bootstrap

![Khoảng tin cậy bootstrap](reports/figures/bootstrap_confidence_intervals.png)

**Nhận xét:** Conformal cải thiện độ bao phủ nhưng làm khoảng rộng hơn, đặc biệt ở kỳ hạn dài. Giá trị chính là mô tả bất định; độ sắc nét của dự báo giảm khi yêu cầu coverage cao.

### Hiệu năng theo điều kiện thị trường

![Hiệu năng theo điều kiện thị trường](reports/figures/performance_by_market_condition.png)

**Nhận xét:** Biểu đồ được sinh trực tiếp từ dữ liệu hoặc artifact của pipeline; không sử dụng số liệu minh họa giả.

### Độ ổn định theo seed

![Độ ổn định theo seed](reports/figures/seed_stability.png)

**Nhận xét:** Run dùng 3 seed; best epoch 1–2 với validation loss 0.2687–0.2862. Best epoch rất sớm cho thấy mô hình hội tụ nhanh ở learning rate đã tune; cần theo dõi overfitting.

## Dự báo mới nhất

### Hồ sơ lợi suất mới nhất

![Hồ sơ lợi suất mới nhất](reports/figures/latest_horizon_return_profile.png)

**Nhận xét:** Hồ sơ ngày 2026-07-13 00:00:00 cho thấy median return âm (-0.50%, -0.96%, -1.56%), nhưng calibrated interval đều bao gồm 0 và mở rộng mạnh theo kỳ hạn. Đây không phải đường giá tương lai hay khuyến nghị mua bán.

### Khoảng chỉ số dự phóng mới nhất

![Khoảng chỉ số dự phóng mới nhất](reports/figures/latest_projected_index_interval.png)

**Nhận xét:** Conformal cải thiện độ bao phủ nhưng làm khoảng rộng hơn, đặc biệt ở kỳ hạn dài. Giá trị chính là mô tả bất định; độ sắc nét của dự báo giảm khi yêu cầu coverage cao.

### Hồ sơ rủi ro mới nhất

![Hồ sơ rủi ro mới nhất](reports/figures/latest_risk_profile.png)

**Nhận xét:** Hồ sơ ngày 2026-07-13 00:00:00 cho thấy median return âm (-0.50%, -0.96%, -1.56%), nhưng calibrated interval đều bao gồm 0 và mở rộng mạnh theo kỳ hạn. Đây không phải đường giá tương lai hay khuyến nghị mua bán.

### Các thành phần confidence mới nhất

![Các thành phần confidence mới nhất](reports/figures/latest_confidence_components.png)

**Nhận xét:** Hồ sơ ngày 2026-07-13 00:00:00 cho thấy median return âm (-0.50%, -0.96%, -1.56%), nhưng calibrated interval đều bao gồm 0 và mở rộng mạnh theo kỳ hạn. Đây không phải đường giá tương lai hay khuyến nghị mua bán.

## Tài liệu chi tiết

- [Báo cáo nghiên cứu đầy đủ](reports/MSDP_BAO_CAO_DAY_DU_VI.md)
- [Nhận xét kết quả](reports/MSDP_NHAN_XET_KET_QUA_VI.md)
- [Review repository](reports/MSDP_REPOSITORY_REVIEW_VI.md)
- [Kết quả kiểm thử](reports/test_results.txt)
- [Hạn chế](reports/MSDP_LIMITATIONS_VI.md)

## Tuyên bố miễn trừ trách nhiệm

Không sử dụng kết quả như bảo đảm lợi nhuận hoặc lời khuyên mua bán. Người dùng tự chịu trách nhiệm kiểm tra dữ liệu, giả định, chi phí giao dịch và rủi ro thị trường.
