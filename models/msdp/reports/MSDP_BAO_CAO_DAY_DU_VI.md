# Báo cáo nghiên cứu đầy đủ MSDP

## Tóm tắt

MSDP dự báo phân phối lợi suất VN-Index ở 5, 20 và 60 phiên bằng bốn chuyên gia causal. Trong cấu hình và giai đoạn dữ liệu hiện tại, chưa có bằng chứng cho thấy MSDP vượt baseline.

## Dữ liệu

Dữ liệu có 6306 phiên, từ 2000-07-28 đến 2026-07-13. Cảnh báo chất lượng: ['OHLC constraint violations: high=27, low=15'].

## Cơ sở toán học

Target lợi suất là `100 log(C[t+h]/C[t])`. MDD là drawdown nhỏ nhất của path tương lai và luôn không dương. Return head lấy median làm tâm; MDD head tạo severity dương rồi đổi dấu. CQR dùng `max(lower-y, y-upper, 0)` và order statistic riêng từng kỳ hạn.

## Kiến trúc

Input đi qua chuyên gia ngắn, trung, dài và range–volatility độc lập. Mỗi expert dùng projection, LayerNorm, GELU và causal residual Conv1d. Context kết hợp feature cuối với các latent; gate nhận context, latent và horizon embedding. Auxiliary head tạo dự báo riêng để đo bất đồng expert.

## Scaling, loss và chống leakage

Feature/target scaler chỉ fit train hoặc development thích hợp. Return, MDD severity và log-volatility có scaler riêng theo horizon. Loss gồm pinball, BCE-with-logits, Huber, batch load balancing và auxiliary MAE. Split theo thời gian có purge 60 phiên; conformal chỉ fit calibration prediction.

## Kết quả final test

| Kỳ hạn | MAE | Pinball | Brier | Coverage gốc | Coverage conformal | Pinball Δ so với ZeroReturn |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 2.3688 | 0.7731 | 0.2563 | 80.4% | 91.4% | +0.0267 |
| 20 | 5.0055 | 1.7032 | 0.2620 | 73.9% | 86.1% | +0.1053 |
| 60 | 8.8100 | 3.0273 | 0.2515 | 76.6% | 86.4% | +0.2502 |

## Nhận xét

- Kỳ hạn 5: Spearman 0.051, MAE 2.369%, pinball 0.773. Pinball chưa thấp hơn ZeroReturn.
  Conformal nâng coverage từ 80.4% lên 91.4%, đồng thời tăng độ rộng từ 7.32% lên 10.16%.
- Kỳ hạn 20: Spearman 0.087, MAE 5.005%, pinball 1.703. Pinball chưa thấp hơn ZeroReturn.
  Conformal nâng coverage từ 73.9% lên 86.1%, đồng thời tăng độ rộng từ 14.07% lên 20.73%.
- Kỳ hạn 60: Spearman 0.010, MAE 8.810%, pinball 3.027. Pinball chưa thấp hơn ZeroReturn.
  Conformal nâng coverage từ 76.6% lên 86.4%, đồng thời tăng độ rộng từ 27.72% lên 39.23%.

## Dự báo mới nhất

Ngày 2026-07-13 00:00:00, VN-Index 1800.54. Đây là hồ sơ dự báo theo khoảng thời gian, không phải đường giá tương lai và không phải khuyến nghị mua bán.

## Hạn chế và kết luận

Artifact quick hiện chỉ dùng một seed và ba trial. Dữ liệu nguồn có vi phạm OHLC; interval dài hạn rộng; gate gần equal-weight. Trong cấu hình và giai đoạn dữ liệu hiện tại, chưa có bằng chứng cho thấy MSDP vượt baseline. Giá trị chính hiện nằm ở mô tả phân phối và hiệu chỉnh rủi ro, chưa phải dự báo điểm.

## Ánh xạ công thức–code–test

| Công thức | File | Thành phần | Test |
|---|---|---|---|
| CQR score không âm | `calibration.py` | `conformity_scores` | `test_calibration.py` |
| Return quantile có tâm median | `heads.py` | `MedianCenteredReturnQuantileHead` | `test_quantile_order.py` |
| MDD quantile âm | `heads.py` | `NegativeMonotonicMDDHead` | `test_quantile_order.py` |
| Convolution causal | `blocks.py` | `CausalConv1d` | `test_causal_conv.py` |
| Gate theo horizon | `gate.py` | `HorizonGate` | `test_horizon_gate.py` |
