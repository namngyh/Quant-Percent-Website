# Phân rã các nguồn bất định trong RAEMF-VB-MC

Tài liệu này định nghĩa chính xác từng nguồn bất định trong dự báo phân phối
và cách chúng được đưa vào Monte Carlo. Mục tiêu là tránh cộng nhiễu trùng
lặp (double counting) và tránh tuyên bố mô hình "đo được mọi bất định".

## 1. Bốn nguồn bất định được mô hình hóa

| # | Nguồn | Ký hiệu | Cách mô phỏng |
|---|---|---|---|
| 1 | Regime uncertainty | S_t ~ Categorical(π_t) | Trạng thái khởi đầu lấy từ filtered HMM probability π_t; state path mô phỏng bằng transition matrix |
| 2 | Parameter uncertainty | θ^(m) ~ q_φ(θ) | Mỗi path m lấy MỘT joint draw θ^(m) = (μ, c, ν) từ variational posterior và giữ cố định suốt path |
| 3 | Innovation uncertainty | ε_t ~ StudentT(ν) | Sốc chuẩn hóa Student-t tại từng bước, scale bởi σ_t (EGARCH recursion) × c_k |
| 4 | Path uncertainty | — | Tích lũy ngẫu nhiên qua nhiều bước: state path + volatility recursion + compounding |

Quy tắc bắt buộc (được kiểm tra bằng test `test_variational_mc_uses_exactly_one_joint_draw_per_path`):
**không** lấy θ mới tại từng ngày trong cùng một path — làm vậy sẽ trộn
parameter uncertainty vào innovation uncertainty và làm phồng variance sai.

## 2. Ba chế độ Monte Carlo

| Mode | Tham số | Nguồn bất định |
|---|---|---|
| M0 `point_estimate` | HMM state_mean + EGARCH ν point estimate | 1, 3, 4 |
| M1 `posterior_mean_mc` | E_q[μ], E_q[c], E_q[ν] plug-in | 1, 3, 4 |
| M2 `variational_posterior` | θ^(m) ~ q_φ mỗi path | 1, 2, 3, 4 |

Ba mode dùng cùng forecast origins, cùng số paths, cùng seed logic, cùng
HMM/EGARCH state — khác biệt duy nhất là nguồn tham số.

## 3. Các nguồn bất định KHÔNG được mô hình hóa đầy đủ

- **Bất định của HMM và EGARCH**: filtered probabilities π_t và σ_t được coi
  là đầu vào cố định. Mô hình do đó **không** phải full Bayesian
  HMM–EGARCH–EBM; posterior chỉ bao phủ (μ_k, c_k, ν).
- **Model uncertainty giữa EBM và Bayesian regime head**: được báo cáo riêng
  trong benchmark phân loại, không được trộn vào fan chart.
- **Data uncertainty**: moving block bootstrap chỉ dùng để ước lượng độ bất
  định của *metric đánh giá*, không đưa vào dự báo.

## 4. Phân rã phương sai trong dự báo live

`scripts/forecast_latest_vb.py` ghi `latest_uncertainty_decomposition.json`:

- `parameter_uncertainty_share ≈ 1 − Var[M1]/Var[M2]`: phần phương sai
  terminal return do posterior parameter draws đóng góp;
- `initial_regime_uncertainty_share ≈ 1 − Var[M2 | modal state]/Var[M2]`:
  phần do không chắc chắn về trạng thái hiện tại.

Đây là phép phân rã gần đúng (các nguồn không trực giao hoàn toàn); giá trị
chỉ mang tính diễn giải, không dùng làm metric đánh giá.

## 5. Độ chính xác số học

- Student-t log likelihood, KL/entropy, log-sum-exp, softmax, quantile đuôi,
  VaR/CVaR, ESS: float32 trở lên, không bao giờ float16.
- ELBO tích lũy ở float32; nếu xuất hiện NaN → retry learning rate thấp hơn
  → mean-field → point estimate (ghi tại `fallbacks.json`, không âm thầm).
