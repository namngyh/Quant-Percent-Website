# Quy trình kiểm chứng tầng Bayesian của RAEMF-VB-MC

## 1. Hai backend, một mô hình

| Backend | Vai trò | Engine |
|---|---|---|
| `pytorch_cuda` | Backend chính (GPU-first) | Full-rank ADVI tự cài đặt: θ = μ + Lε, reparameterization gradient, Adam + warm-up + cosine schedule, gradient clipping, early stopping theo moving-average ELBO |
| `pymc` | Backend tham chiếu | PyMC `fullrank_advi` và NUTS |

Hai backend dùng cùng likelihood (mixture Student-t với trọng số HMM cố
định), cùng prior, cùng biến đổi tham số (c = exp(log c), ν = 2 + exp(raw)),
cùng chuẩn hóa return theo train.

## 2. Multi-seed ADVI

- Laptop: seeds `[11, 42, 73]`; GPU research: 7 seeds.
- Mỗi seed fit độc lập; per-seed mean/sd/CI/ELBO/steps/convergence được lưu
  tại `posterior_by_seed.csv`; khoảng cách posterior mean lớn nhất giữa các
  seed tại `seed_stability.json`.
- Posterior dùng cho Monte Carlo là **mixture đều** của các seed posterior
  (mỗi seed đóng góp đúng `posterior_draws / n_seeds` draws) — không giữ
  riêng seed có ELBO tốt nhất, không bỏ seed thất bại (seed thất bại làm
  toàn bộ fit fail có ghi nhận).

## 3. Chuỗi fallback (không âm thầm)

1. `fullrank_advi` @ learning_rate cấu hình;
2. retry với từng learning rate trong `retry_learning_rates`;
3. `meanfield_advi` (nếu `fallback_to_meanfield`);
4. point estimate (nếu `fallback_to_point_estimate`).

Mọi lần rơi bậc được ghi vào `fallbacks.json` của artifact posterior và vào
`warnings` của kết quả fit.

## 4. Kiểm chứng ADVI bằng NUTS

`scripts/validate_advi_with_nuts.py` fit cùng mô hình 2-regime trên dữ liệu
tổng hợp có tham số đã biết bằng ba engine (torch ADVI, PyMC ADVI, PyMC
NUTS) và ghi:

- `engine_comparison.csv`: mean/sd/CI từng tham số theo engine;
- `advi_vs_nuts_ratios.csv`: `sd_ratio_vs_nuts` — giá trị nhỏ hơn 1 rõ rệt
  là dấu hiệu ADVI đánh giá thấp uncertainty.

NUTS **không** được dùng trong pipeline production; chỉ dùng làm reference
trên bài toán nhỏ. Kết quả gần nhất được lưu tại
`outputs/latest/advi_nuts_validation/`.

## 5. Ranh giới leakage

- Posterior chỉ fit trên positional train index; fingerprint dữ liệu train
  được lưu và kiểm tra bằng test `test_posterior_uses_only_train_rows`.
- Posterior deployment (fit trên toàn bộ lịch sử trong
  `forecast_latest_vb.py`) chỉ dùng cho dự báo live, không bao giờ dùng để
  chấm điểm quá khứ.
- Temperature calibration fit trên validation; test set không tham gia
  tuning ở bất kỳ tầng nào.
