# Phương pháp Variational Bayesian scenario layer

## Phạm vi mô hình

RAEMF-VB-MC giữ nguyên Filtered HMM, EGARCH Student-t, EBM đa horizon,
temperature calibration, explainability và backtest. Phần Bayesian chỉ là lớp
phân phối lợi suất có điều kiện, đặt sau filtered regime probabilities và
conditional volatility. Do đó đây không phải fully Bayesian HMM-EGARCH.

Với \(K\) regime, tại thời điểm \(t\):

- \(r_t\) là log-return đã quan sát;
- \(\pi_{tk}=P(S_t=k\mid\mathcal F_t)\) là xác suất **filtered**, không phải
  smoothed probability;
- \(\widehat\sigma_t>0\) là conditional volatility từ bộ lọc EGARCH chỉ dùng
  thông tin sẵn có đến \(t\).

Trong một evaluation fold, mọi đại lượng chuẩn hóa và posterior chỉ được fit
trên các hàng thuộc train. Train và validation tiếp tục thỏa
`target_end_date_h < boundary`.

## Prior và likelihood

Để prior có ý nghĩa ổn định giữa các giai đoạn biến động, return và EGARCH sigma
được chia cho độ lệch chuẩn return của **train fold**. Ký hiệu các đại lượng đã
chuẩn hóa là \(\widetilde r_t\) và \(\widetilde\sigma_t\).

```math
\begin{aligned}
\widetilde\mu_k &\sim \mathcal N(0, s_\mu),\\
\log c_k &\sim \mathcal N(0, s_c),\\
\nu_k - 2 &\sim \operatorname{Exponential}(\lambda_\nu),\\
\nu_k &= 2 + (\nu_k-2),\\
\widetilde r_t &\sim
\sum_{k=1}^{K}\pi_{tk}\,
\operatorname{StudentT}\left(
\nu_k,\widetilde\mu_k,c_k\widetilde\sigma_t
\right).
\end{aligned}
```

Default \(s_\mu=0.5\), \(s_c=0.3\), \(\lambda_\nu=0.1\) chỉ tồn tại tại
`raemf_mc.config.DEFAULT_BAYESIAN_CONFIG` và có thể override bằng YAML/CLI.
`shared_nu: true` dùng một \(\nu\) chung khi effective observations theo regime
không đủ nhận diện tail parameter riêng.

## Hierarchical shrinkage prior (mặc định trong profile VB)

Với `bayesian.hierarchical: true` (bật sẵn trong `configs/laptop_vb.yaml`
và `configs/gpu_research.yaml`), prior độc lập được thay bằng partial
pooling:

```math
\begin{aligned}
\mu_{\text{global}} &\sim \mathcal N(0, s_{\text{global}}),\\
\tau_\mu &\sim \operatorname{HalfNormal}(s_\tau),\\
\widetilde\mu_k &\sim \mathcal N(\mu_{\text{global}}, \tau_\mu),\\
\log c_{\text{global}} &\sim \mathcal N(0, s_{c,\text{global}}),\\
\tau_c &\sim \operatorname{HalfNormal}(s_{c,\tau}),\\
\log c_k &\sim \mathcal N(\log c_{\text{global}}, \tau_c),\\
\nu &= 2 + \operatorname{Exponential}(\lambda_\nu) \quad (\text{shared}).
\end{aligned}
```

Regime hiếm (Stress) được kéo về mức chung thay vì bị prior độc lập thả nổi.
`min_effective_observations` (mặc định 80 trong profile VB): nếu một regime
không đủ effective observations thì \(\nu\) riêng bị thay bằng \(\nu\) chung
kèm cảnh báo — không raise, không giả vờ posterior regime-specific đáng tin.

## Backend GPU-first và multi-seed

Backend chính là `pytorch_cuda` (`bayesian/torch_backend.py`): full-rank
ADVI với reparameterization \(\theta = \mu + L\varepsilon\), Adam + warm-up
+ cosine schedule, gradient clipping, early stopping theo moving-average
ELBO, retry ở learning rate thấp hơn, fallback mean-field rồi point
estimate (ghi ở `fallbacks.json`). PyMC được giữ làm backend tham chiếu và
để chạy NUTS kiểm chứng (`scripts/validate_advi_with_nuts.py`,
`docs/bayesian_validation.md`).

ADVI chạy nhiều seed (laptop 3, research 7); posterior dùng cho Monte Carlo
là mixture đều của các seed posterior; per-seed summary tại
`posterior_by_seed.csv`, khoảng cách giữa seed tại `seed_stability.json`.
Student-t log likelihood, KL, log-sum-exp và tail quantile luôn ở float32
trở lên; không dùng float16 cho phần Bayesian.

Sau inference, \(\mu_k=\widetilde\mu_k s_r\), với \(s_r\) là train return scale.
Hệ số \(c_k\) và \(\nu_k\) không đổi đơn vị.

## Variational family, KL và ELBO

Gọi \(\theta=(\widetilde\mu,\log c,\nu-2)\). Variational inference chọn
\(q_\phi(\theta)\) gần posterior \(p(\theta\mid r,\pi,\widehat\sigma)\) bằng
cách giảm:

```math
\operatorname{KL}\!\left(q_\phi(\theta)\,\|\,p(\theta\mid
r,\pi,\widehat\sigma)\right).
```

Tương đương, ADVI tối đa hóa evidence lower bound:

```math
\operatorname{ELBO}(\phi)
=
\mathbb E_{q_\phi}\!\left[\log p(r,\theta\mid\pi,\widehat\sigma)\right]
-
\mathbb E_{q_\phi}\!\left[\log q_\phi(\theta)\right].
```

`meanfield_advi` giả định covariance chéo bằng 0, nhanh hơn nhưng thường đánh
giá thấp uncertainty khi posterior tương quan. `fullrank_advi` học covariance
đầy đủ trong không gian biến đổi, tốn thời gian/bộ nhớ hơn nhưng là mặc định.
ELBO moving average của hai cửa sổ cuối được so sánh với tolerance cấu hình.
ELBO hữu hạn và ổn định là điều kiện cần, không phải bằng chứng mô hình đúng.

## Posterior predictive

Phân phối posterior predictive là:

```math
p(r_{\mathrm{new}}\mid D)
=
\int
\left[
\sum_k \pi_{\mathrm{new},k}
\operatorname{StudentT}(
\nu_k,\mu_k,c_k\widehat\sigma_{\mathrm{new}})
\right]
p(\theta\mid D)\,d\theta.
```

Repository kiểm tra prior/posterior predictive cho mean, standard deviation,
skewness, kurtosis, quantile hai đuôi, tỷ lệ return dưới -2%, proxy volatility
clustering và thống kê theo regime. Plot gồm ELBO, marginal posterior,
correlation, histogram, lower-tail QQ, regime scale, prior-vs-posterior và
credible interval theo regime.

## Posterior-predictive Monte Carlo

Với path \(m\), lấy **một** joint draw:

```math
\theta_m=\{\mu_{km},c_{km},\nu_{km}\}_{k=1}^{K}
\sim q_\phi(\theta).
```

Draw này được giữ cố định trong toàn bộ horizon. State đầu lấy từ filtered
probability tại forecast origin; state sau lấy bằng transition point estimate
của HMM. EGARCH point-estimate recursion cho \(\widehat\sigma_{mt}\), sau đó:

```math
\begin{aligned}
\sigma_{mt} &= c_{S_{mt},m}\widehat\sigma_{mt},\\
z_{mt} &\sim t_{\nu_{S_{mt},m}}
\sqrt{\frac{\nu_{S_{mt},m}-2}{\nu_{S_{mt},m}}},\\
r_{mt} &= \mu_{S_{mt},m}+\sigma_{mt}z_{mt},\\
P_{mt} &= P_{m,t-1}\exp(r_{mt}).
\end{aligned}
```

Ba ablation mode:

1. `point_estimate`: logic RAEMF-MC gốc;
2. `posterior_mean_mc`: dùng posterior mean cố định, đo tác dụng regularization;
3. `variational_posterior`: joint draw riêng cho mỗi path, đo thêm propagation
   của parameter uncertainty.

## Drawdown và risk quantities

Với running peak \(M_{mt}=\max_{u\le t}P_{mu}\):

```math
DD_{mt}=\frac{P_{mt}}{M_{mt}}-1,\qquad
MDD_m=\min_t DD_{mt}.
```

Simulator báo cáo terminal-return quantiles, VaR/Expected Shortfall 95% và 99%,
maximum drawdown quantiles, xác suất vượt drawdown threshold, time under water
và first-passage dưới ngưỡng -10%.

## Đánh giá

So sánh distribution forecast phải dùng các forecast origin ngoài mẫu theo
thời gian. Metrics gồm negative log predictive density, CRPS, PIT, coverage và
width ở 50/80/90/95%, interval score, VaR exceedance, Kupiec và Christoffersen
conditional coverage. Point/classification metrics cũ được giữ nguyên.

Chênh lệch metric giữa hai cấu hình dùng moving block bootstrap. Nếu interval
chứa 0, báo cáo phải ghi “chưa có bằng chứng ổn định về cải thiện”. Interval
rộng hơn không tự động là tốt hơn: coverage phải gần nominal hơn trong khi
CRPS/log score và tail calibration không xấu đi đáng kể.

## MCMC benchmark

`scripts/compare_advi_nuts.py` chỉ chạy trên synthetic/window nhỏ để so sánh
mean-field ADVI, full-rank ADVI và NUTS về posterior mean, standard deviation,
interval width, correlation và tail parameter. NUTS không được gọi trong
production pipeline hoặc mọi walk-forward fold.

## Giới hạn

- HMM transition/filter, EGARCH recursion, EBM và calibration vẫn là point
  estimate; uncertainty của chúng chưa được marginalize.
- Fixed-weight mixture có thể nhận diện kém khi regime probabilities khuếch tán
  hoặc một regime có effective sample size nhỏ.
- ADVI, đặc biệt mean-field, có thể làm posterior quá hẹp hoặc mô tả kém tail.
- Posterior predictive check không chứng minh tính đúng của model; cần kiểm tra
  OOS calibration qua nhiều fold, seed và giai đoạn thị trường.
- Các output là kết quả nghiên cứu, không phải khuyến nghị đầu tư.
