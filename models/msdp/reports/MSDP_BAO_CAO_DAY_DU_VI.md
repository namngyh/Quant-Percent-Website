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
| 5 | 2.3250 | 0.7506 | 0.2463 | 87.8% | 90.2% | +0.0043 |
| 20 | 4.8486 | 1.5966 | 0.2496 | 86.7% | 88.6% | -0.0013 |
| 60 | 8.5669 | 2.8980 | 0.2477 | 86.1% | 88.0% | +0.1209 |

## Nhận xét

- Kỳ hạn 5: Spearman -0.011, MAE 2.325%, pinball 0.751. Pinball chưa thấp hơn ZeroReturn.
- Kỳ hạn 20: Spearman -0.041, MAE 4.849%, pinball 1.597. Pinball thấp hơn ZeroReturn.
- Kỳ hạn 60: Spearman -0.111, MAE 8.567%, pinball 2.898. Pinball chưa thấp hơn ZeroReturn.

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
