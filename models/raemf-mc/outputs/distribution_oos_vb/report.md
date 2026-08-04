# Báo cáo benchmark phân phối OOS — RAEMF-VB-MC v0.3.0 (2026-07-23)

## Thiết lập

- Dữ liệu: chuỗi hợp nhất `canonical_vnindex.csv`, 6.306 phiên,
  2000-07-28 → 2026-07-13 (ưu tiên VNINDEX_Daily.csv; 2 xung đột volume,
  giá khớp hoàn toàn — xem `outputs/latest/data_merge_report.md`).
- 3 expanding-window fold không chồng lấn, purge bằng
  `target_end_date_h < boundary`; horizon 20/40/60; 3 MC seed [11, 42, 73];
  300 paths/origin; **5.640 forecast origin duy nhất, 50.760 dòng metric**.
- Posterior: PyTorch full-rank ADVI trên CUDA (RTX 4060), hierarchical
  shrinkage prior, shared ν, 3 ADVI seed/fold, pooled mixture. **Cả 9
  fold-fit đều `converged`** (khác run cũ: 9/9 not_converged sau 800 bước
  mean-field). Không có fallback nào được kích hoạt.
- Ba chế độ dùng cùng origin, cùng paths, cùng seed, cùng HMM/EGARCH state.

## Kết quả chính (trung bình 3 seed)

| Horizon | Mode | CRPS | WIS | Coverage 90% | Coverage 95% | Width 90% | VaR95 viol. |
|---|---|---|---|---|---|---|---|
| 20 | point_estimate | 0.0362 | 0.0297 | 96.4% | 98.9% | 0.461 | 2.0% |
| 20 | posterior_mean | 0.0335 | 0.0239 | 78.8% | 86.1% | 0.145 | 11.6% |
| 20 | variational | **0.0335** | **0.0239** | 79.1% | 86.2% | 0.148 | 11.4% |
| 40 | point_estimate | 0.0605 | 0.0568 | 99.0% | 99.9% | 1.108 | 0.3% |
| 40 | posterior_mean | 0.0477 | 0.0348 | 80.0% | 86.4% | 0.230 | 12.3% |
| 40 | variational | **0.0476** | **0.0347** | 80.7% | 87.1% | 0.236 | 12.3% |
| 60 | point_estimate | 0.0784 | 0.0796 | 98.7% | 99.5% | 1.700 | 0.1% |
| 60 | posterior_mean | 0.0540 | 0.0395 | 80.3% | 85.5% | 0.233 | 11.7% |
| 60 | variational | **0.0537** | **0.0390** | **81.7%** | 87.1% | 0.245 | 11.3% |

Paired moving-block bootstrap (500 replicate, block 20), VB trừ point:

| Horizon | ΔCRPS [CI 95%] | ΔWIS [CI 95%] | Δ|cov90 err| | Δ|cov95 err| |
|---|---|---|---|---|
| 20 | −0.0027 [−0.0039, −0.0013] ✓ | −0.0058 [−0.0081, −0.0032] ✓ | +0.045 (ns) | +0.049 ✗ (VB xấu hơn, có ý nghĩa) |
| 40 | −0.0129 [−0.0176, −0.0078] ✓ | −0.0222 [−0.0284, −0.0155] ✓ | +0.003 (ns) | +0.031 (ns) |
| 60 | −0.0247 [−0.0314, −0.0182] ✓ | −0.0406 [−0.0488, −0.0324] ✓ | −0.003 (ns) | +0.034 (ns) |

✓ = CI loại 0 theo hướng VB tốt hơn; ✗ = CI loại 0 theo hướng VB xấu hơn; ns = CI chứa 0.

## Diễn giải

1. **VB (M2) cải thiện proper score rõ rệt và có ý nghĩa thống kê** ở cả ba
   horizon: CRPS giảm 7,5% / 21,3% / 31,5%; WIS giảm 19,7% / 39,0% / 51,0%
   so với point estimate.
2. **Nhưng khoảng dự báo của M2 quá hẹp** (under-coverage ~79–87% cho mức
   danh nghĩa 90–95%; VaR95 violation ~11% so với 5% danh nghĩa), trong khi
   M0 quá rộng theo hướng ngược lại (over-coverage 96–99,9%, VaR violation
   0,1–2%). Không mode nào calibrated tốt — hai kiểu misspecification
   ngược chiều.
3. **M2 ≈ M1**: với posterior đã hội tụ trên >3.700 quan sát, parameter
   uncertainty đóng góp rất nhỏ vào phân phối OOS (cũng nhất quán với phân
   rã phương sai live: ~0%/5%/14% ở h20/40/60). Phần lớn cải thiện so với
   M0 đến từ **Bayesian regularization của drift/multiplier** (posterior
   mean), không phải từ propagation của parameter uncertainty.
4. **Khác biệt với run cũ (v0.2.0)**: coverage "đẹp" của VB trong run cũ là
   sản phẩm phụ của posterior CHƯA hội tụ (800 bước mean-field) — posterior
   khuếch tán làm interval rộng ra một cách tình cờ. Khi posterior hội tụ
   thực sự, kết quả trung thực hơn: proper score tốt hơn, coverage kém đi.
   Đây là lý do phải có multi-seed + convergence diagnostics.

## Quyết định theo quy tắc đăng ký trước (`scripts/summarize_vb_results.py`)

- Điều kiện chọn VB: cải thiện CRPS/WIS **và** coverage không xấu hơn.
- Kết quả bỏ phiếu theo horizon: h20 → point_estimate, h40 →
  point_estimate, h60 → variational_posterior.
- **Mặc định production: `point_estimate`.** VB outputs (M1, M2) tiếp tục
  được xuất bản như phân tích nghiên cứu.

## Kết luận (dạng B)

Variational Bayes **cải thiện một số khía cạnh** của dự báo phân phối ngoài
mẫu (CRPS, WIS, NLPD tại h20; Brier drawdown 10% tại h20/h40) **nhưng chưa
ổn định về calibration**: khoảng dự báo hẹp hơn thực tế ở h20/h40 và tỷ lệ
vi phạm VaR95 vượt danh nghĩa. Không đủ bằng chứng để thay point estimate
làm mặc định. Hướng cải thiện đã xác định: nguồn under-dispersion nằm ở
structural MC (EGARCH point recursion + clip state_scale), không nằm ở
posterior — cần Bayesian hóa hoặc widen tầng volatility trước khi kỳ vọng
coverage tốt hơn.

## Runtime

- Tổng: ~7.560s cho 27 fold-seed files (9 fold × [ADVI 3 seeds trên CUDA
  ~40–90s + MC ~200s]) + 35s tổng hợp; chạy nền song song với benchmark
  regime head (453s) trên cùng máy.
- ADVI-vs-NUTS validation: torch ADVI ≈ PyMC ADVI ≈ NUTS
  (sd ratio 0,95–1,03) — xem `outputs/latest/advi_nuts_validation/`.
