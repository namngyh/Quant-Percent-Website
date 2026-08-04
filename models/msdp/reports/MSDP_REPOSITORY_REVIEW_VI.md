# Review repository MSDP sau nâng cấp

## Phạm vi và bằng chứng

Review sau sửa dựa trên 19 test pass, quick pipeline end-to-end 129,31 giây, Optuna SQLite 3 trial thật, một seed quick, hai ablation, 50 moving-block bootstrap resamples và 63 biểu đồ. Default 20-trial/3-seed chưa chạy; mọi điểm liên quan multi-seed/full experiment bị giới hạn tương ứng.

## A. Cấu trúc code

Module data/features/targets/model/training/calibration/report vẫn tách biệt. Các class toán học mới có tên rõ ràng (`CausalConv1d`, `NegativeMonotonicMDDHead`, `MedianCenteredReturnQuantileHead`, `TargetScalerSet`). Windows chạy với `num_workers=0` và matplotlib Agg. Một số module pipeline/report vẫn dài và cần refactor thêm; type hints/docstring chưa đồng đều.

## B. Lý thuyết

- Target alignment return/MDD/volatility có test tính tay.
- Return quantiles lấy median làm tâm và luôn monotonic.
- MDD quantiles luôn `q10 <= q50 <= q90 <= 0`.
- CQR score là `max(lower-y, y-upper, 0)`, finite-sample rank và qhat riêng horizon.
- Expert dùng left-padded causal convolution.
- Gate dùng learned context + horizon embedding; embedding đi vào fused prediction state.
- Target scaling riêng từng type/horizon; volatility dùng log1p và Huber.
- Entropy không còn là regularizer chính; batch load balancing được log riêng.

## C. Thực nghiệm

Feature selection chỉ dùng development sau warm-up; tuning fold fit scaler riêng. Optuna không còn placeholder. Quick run chỉ một seed nên chưa kiểm chứng seed stability; default config đã định nghĩa ba seed nhưng chưa được thực thi. Baseline hiện chạy ZeroReturn; Ridge class tồn tại nhưng chưa đưa vào result table. Quick ablation chỉ equal/single. Bootstrap CI đều chứa 0.

## D. Deployment

Bundle lưu state, args, feature order/metadata, conformal state, config và version. Inference kiểm tra feature order và inverse target transforms. Evaluation/production có version khác nhau, nhưng production hiện là deployment member tách manifest chứ chưa phải retraining trên toàn bộ target history; điều này được ghi rõ trong bundle và limitations.

## E. Documentation

README_VI dùng UTF-8, có command thực tế, marker cập nhật metric tự động và tám ảnh đã audit tồn tại. Báo cáo/nhận xét tiếng Việt đọc artifact thật. Không tuyên bố vượt baseline. Default/full result không được trình bày như đã chạy.

## So sánh điểm trước và sau

| Hạng mục | Trước | Sau | Lý do thay đổi / giới hạn |
|---|---:|---:|---|
| Code quality | 5.0 | 7.0 | Class rõ hơn, guard NaN và CLI tốt hơn; pipeline còn dài. |
| Mathematical correctness | 3.0 | 8.5 | Sửa CQR, heads, causal conv, scaling/loss; test invariants pass. |
| Leakage control | 5.0 | 7.5 | Development-only selection và fold scalers; chưa có test instrument tuyệt đối mọi test access. |
| Model architecture | 4.0 | 8.0 | Context/gate/horizon/auxiliary/causal experts đúng đặc tả chính. |
| Experimental design | 2.5 | 5.5 | Optuna/ablation/bootstrap thật nhưng quick one-seed và baseline còn hạn chế. |
| Calibration | 2.0 | 8.5 | qhat không âm, order statistic, maturity API và artifacts; rolling test path chưa dùng làm headline. |
| Interpretability | 3.0 | 7.5 | Auxiliary disagreement, gate metrics và 63 figures; market-condition analysis còn proxy. |
| Reproducibility | 5.0 | 7.0 | SQLite resume, configs, scaler metadata; default three-seed chưa chạy. |
| Documentation | 4.0 | 8.0 | README/báo cáo Việt, auto-results và link audit; English README chưa chi tiết ngang bản Việt. |
| Deployment readiness | 3.5 | 6.0 | Bundle/inference nhất quán; production full retraining chưa hoàn tất. |

## Kết luận trung thực

Quick upgraded pipeline là implementation có thể chạy và kiểm chứng tốt hơn rõ rệt về tính đúng toán học. Tuy nhiên artifact hiện chưa đáp ứng nghiên cứu default/full ba seed. H5 và H20 có return pinball cao hơn ZeroReturn; H60 có pinball thấp hơn nhưng MAE cao hơn. Cả ba moving-block bootstrap CI cho chênh lệch MAE đều chứa 0.

**Trong cấu hình và giai đoạn dữ liệu hiện tại, chưa có bằng chứng cho thấy MSDP vượt baseline.** Giá trị chính quan sát được hiện nằm ở dự báo phân phối và hiệu chỉnh rủi ro, chưa phải ở dự báo điểm.
