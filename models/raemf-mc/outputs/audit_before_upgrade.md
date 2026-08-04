# Audit trước nâng cấp RAEMF-VB-MC (2026-07-23)

Commit gốc tại thời điểm audit: `8c02b44` ("Add variational Bayesian OOS distribution benchmark").
Môi trường thực thi: Windows 11, Python 3.12 (conda env `project`), GPU NVIDIA RTX 4060 8GB, CUDA 12.1 (PyTorch 2.5.1).

## 1. Thành phần ĐÃ hoạt động

| Thành phần | Vị trí | Trạng thái |
|---|---|---|
| Loader CSV chống lỗi phẩy nghìn | `src/raemf_mc/data/loader.py` | Hoạt động, có checksum + metadata |
| Targets đa horizon + `target_end_date_h` | `src/raemf_mc/targets/regime_targets.py` | Hoạt động, hỗ trợ purge |
| Filtered HMM (không smoothing) | `src/raemf_mc/regime/filtered_hmm.py` | Hoạt động |
| EGARCH(1,1,1) Student-t causal | `src/raemf_mc/risk/egarch_t.py` | Hoạt động |
| EBM + temperature scaling (validation-only) | `models/ebm_forecaster.py`, `calibration/` | Hoạt động |
| Structural MC với 3 scenario modes | `simulation/structural_mc.py` | `point_estimate`, `posterior_mean_mc`, `variational_posterior` đều được cài; mỗi path giữ đúng MỘT joint draw θ^(m) cố định |
| VariationalScenarioModel (PyMC ADVI) | `bayesian/variational.py` | Fit train-only, save/load, PPC in-sample, prior predictive |
| Workflow fit posterior deployment | `bayesian/workflow.py` | Hoạt động (`outputs/bayesian_smoke`) |
| OOS distribution benchmark | `evaluation/oos_distribution_benchmark.py` | 3 fold expanding + purged, 3 horizon, 3 MC seed; CRPS, NLPD, PIT, coverage 50/80/90/95, interval score, VaR/ES 95/99, Kupiec, Christoffersen, drawdown coverage, bootstrap ghép cặp moving-block |
| Kết quả benchmark hiện có | `outputs/distribution_oos_laptop/` | 5.634 origin duy nhất, dữ liệu đến 2026-07-01, runtime 4.040s |
| Script ADVI-vs-NUTS synthetic | `scripts/compare_advi_nuts.py` | Có sẵn, chưa có kết quả lưu trong repo |
| Leakage checks + purged split | `validation/` | Hoạt động, có test |

## 2. Thành phần được fit nhưng CHƯA được dùng / còn thiếu

1. **Bayesian mode tắt trong cấu hình mặc định**: `configs/laptop.yaml` và `configs/research.yaml` đặt `bayesian.enabled: false`, `monte_carlo.scenario_mode: point_estimate`. Pipeline chính (`pipeline.run_pipeline`) và dự báo hiện tại (`forecast-latest`, `current-report`) KHÔNG dùng posterior — posterior chỉ được dùng trong benchmark riêng (`benchmark_distribution_laptop.yaml`).
2. **Prior hoàn toàn độc lập**: `mu_std ~ N(0, s)`, `log_c ~ N(0, s)` theo từng regime, không có hierarchical shrinkage (`mu_global`, `tau_mu`, `log_c_global`, `tau_c`).
3. **Một seed ADVI duy nhất**: `bayesian.random_seed` đơn; `mc_seeds` chỉ đổi seed Monte Carlo, KHÔNG đổi seed ADVI ⇒ chưa có multi-seed posterior stability diagnostics.
4. **Fallback chưa được cài**: cấu hình có `fallback_to_point_estimate` nhưng `fit()` chỉ raise; không có retry learning-rate thấp hơn, không fallback mean-field, không có `bayesian_fallbacks.json`.
5. **`min_effective_observations` raise thay vì fallback shared-ν**: regime thiếu quan sát làm hỏng cả fit thay vì tự động dùng ν chung + cảnh báo. `shared_nu` mặc định `false`.
6. **Không có Bayesian regime head**: chưa có mô hình ablation nào kiểm tra VB có cải thiện phân loại Bull/Sideway/Bear/Stress hay không.
7. **Thiếu metric**: chưa có WIS tổng hợp (chỉ có interval score theo từng level), chưa có Brier score OOS cho các sự kiện forward return < 0 và drawdown > 5/10/15% (xác suất drawdown đã được lưu per-origin nhưng chưa được chấm).
8. **Không dùng GPU**: toàn bộ pipeline NumPy/PyMC CPU; không có backend PyTorch CUDA, không có hardware report, không có benchmark CPU-vs-GPU.
9. **Hai file dữ liệu chưa hợp nhất**: `data.csv` (đến 2026-07-01) dùng cho research; `VNINDEX_Daily.csv` (đến 2026-07-13) dùng cho monitoring. Không có báo cáo xung đột giữa hai file; benchmark hiện tại chạy trên dữ liệu cũ hơn 9 phiên.
10. **Thiếu cấu hình**: chưa có `configs/laptop_vb.yaml`, `configs/gpu_research.yaml`.
11. **Thiếu tài liệu**: chưa có `docs/uncertainty_decomposition.md`, `docs/bayesian_validation.md`, `docs/nontechnical_outlook.md`.
12. **NUTS reference chưa có kết quả lưu**: script tồn tại nhưng chưa chạy/lưu output.

## 3. Nguy cơ leakage — đánh giá

- Posterior fit dùng đúng positional train index; `_train_positions` reject index ngoài phạm vi. Benchmark purge bằng `target_end_date < validation_start/test_start` và có `assert_target_end_before_boundary`. **Không phát hiện leakage** trong luồng benchmark.
- `workflow.fit_variational_from_data` fit posterior deployment trên TOÀN BỘ dữ liệu (train_index = toàn bộ) — chấp nhận được cho *live forecast* nhưng KHÔNG được dùng posterior này để chấm điểm lịch sử. Hiện chưa có chỗ nào dùng sai, cần giữ ranh giới này khi thêm evaluate_live_history.
- Temperature scaling fit trên validation-only. HMM/EGARCH/EBM/feature selection đều fit train-only trong benchmark.

## 4. Nguy cơ double-counting uncertainty

- Trong `variational_posterior` mode: θ^(m) cố định theo path, innovation Student-t theo bước, state path theo transition matrix — 4 nguồn bất định tách bạch, không cộng trùng.
- **Lưu ý**: `posterior_mean_mc` dùng E_q[ν] làm df của Student-t — đúng thiết kế "posterior mean plug-in", không truyền parameter uncertainty (đúng như định nghĩa M1).
- EGARCH sigma và c_k cùng scale volatility: c_k là multiplier có prior quanh 1 (log_c ~ N(0, 0.3)), σ_t từ EGARCH — cấu trúc σ_t·c_k là có chủ đích, không phải double counting, nhưng phải ghi rõ trong tài liệu.

## 5. Thiếu sót trong đánh giá

- Chưa có so sánh EBM vs Bayesian regime head (macro F1, balanced accuracy, MCC, Brier, log loss, ECE, recall Bear/Stress).
- Chưa có WIS tổng hợp và Brier cho sự kiện đuôi (drawdown/negative return).
- Chưa có multi-seed ADVI stability; chưa có ADVI-vs-NUTS kết quả thực tế.
- PPC out-of-sample có (qua benchmark PIT/coverage) nhưng chưa được tổng hợp thành báo cáo riêng.

## 6. Thiếu sót trong documentation

- README chưa mô tả tầng VB là gì/không là gì (thành phần nào vẫn point estimate).
- Chưa ghi rõ HMM probabilities + EGARCH sigma là đầu vào cố định ⇒ mô hình KHÔNG phải full Bayesian HMM–EGARCH–EBM.

## 7. File sẽ được sửa/thêm

**Sửa:** `bayesian/variational.py` (hierarchical prior, multi-seed, fallback, shared-ν tự động), `config.py` (schema Bayesian mở rộng), `evaluation/oos_distribution_benchmark.py` (WIS, Brier đuôi, backend GPU), `simulation/structural_mc.py` (không đổi hành vi, chỉ tái sử dụng), `pyproject.toml`, `README.md`.

**Thêm:** `bayesian/torch_backend.py` (full-rank ADVI PyTorch CUDA — backend chính GPU-first; PyMC giữ làm reference), `bayesian/priors.py`, `models/bayesian_regime_head.py`, `runtime/hardware.py`, `data/merge.py`, `evaluation/regime_head_benchmark.py`, `configs/laptop_vb.yaml`, `configs/gpu_research.yaml`, tests mới, docs mới (`uncertainty_decomposition.md`, `bayesian_validation.md`, `nontechnical_outlook.md`), scripts (`run_gpu_research.sh`, `evaluate_live_history.py`).

**Không xóa** code cũ; pipeline point-estimate phải tiếp tục chạy khi `bayesian.enabled: false`.

## 8. Kết quả OOS hiện có (baseline, dữ liệu đến 2026-07-01, 300 paths, 3 seeds)

Từ `outputs/distribution_oos_laptop/distribution_metrics_summary.csv`, horizon 20:

| Metric | point_estimate | posterior_mean_mc | variational_posterior |
|---|---|---|---|
| CRPS | 0.03489 | 0.03232 | **0.03203** |
| Coverage 90% (nominal 0.90) | 0.966 (quá rộng) | 0.822 (quá hẹp) | **0.899** |
| Coverage 95% | 0.992 | 0.888 | **0.944** |
| VaR95 violation (nominal 5%) | 1.36% | 11.2% | **7.0%** |
| Width 90% | 0.450 | 0.159 | 0.197 |

⇒ Baseline cho thấy variational posterior đã cải thiện CRPS và calibration so với cả hai mode còn lại ở h=20; horizon dài hơn cần xem lại sau khi rerun với prior hierarchical + dữ liệu mới. Kết luận cuối cùng chỉ đưa ra sau khi chạy lại có kiểm soát.
