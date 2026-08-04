# Audit kiến trúc trước khi nâng cấp Variational Bayes

Tài liệu này ghi lại trạng thái repository **trước khi** tích hợp lớp
Variational Bayesian scenario. Việc khảo sát được thực hiện trên tên module,
class và function thực tế; không suy đoán tên file từ đặc tả nâng cấp.

## 1. Entry point và cấu hình

- Entry point CLI là `raemf_mc.cli:main`, được khai báo trong
  `src/raemf_mc/cli.py`. Các lệnh chính hiện có gồm `validate-data`, `run`,
  `report`, `plots`, `forecast-latest`, `current-report`, `reproduce`,
  `ingest-data` và `daily`.
- Entry point pipeline là
  `raemf_mc.pipeline.run_pipeline(data_path, config) -> pathlib.Path`.
  Hàm trả về thư mục run bất biến trong `outputs/runs/`; sau khi hoàn tất,
  nội dung được sao chép sang `outputs/latest`.
- Entry point smoke test là
  `raemf_mc.pipeline.run_smoke_pipeline(prices, seed) -> dict`.
- Cấu hình YAML được đọc bởi `raemf_mc.config.load_config` và snapshot bởi
  `write_config_snapshot`. Hai profile hiện có là `configs/laptop.yaml` và
  `configs/research.yaml`.
- Lệnh laptop chuẩn là `bash scripts/run_laptop.sh`; lệnh kiểm thử chuẩn theo
  `AGENTS.md` là `conda run -n eda python -m pytest -q`.

## 2. Cây kiến trúc và hợp đồng dữ liệu hiện tại

```text
CSV OHLCV
└─ data.loader.load_price_data -> DataFrame(date, open, high, low, close, volume), metadata
   ├─ targets.create_multihorizon_targets -> target_{20,40,60}, target_end_date_h
   ├─ features.technical.build_features -> causal feature DataFrame, FeatureRegistry
   ├─ regime.filtered_hmm.fit_filtered_hmm -> FilteredHMMResult
   │  ├─ filtered state probabilities P(S_t | F_t)
   │  ├─ aligned transition matrix
   │  └─ point estimates state_mean, state_volatility
   ├─ risk.egarch_t.fit_egarch_features -> EGARCHResult
   │  ├─ causal conditional sigma and standardized residual features
   │  └─ point estimates EGARCH parameters and Student-t nu
   ├─ features.selection.select_features (train rows only)
   ├─ tuning.optuna_tuner.tune_ebm_random_search (purged chronological folds)
   ├─ models.ebm_forecaster.EBMForecaster
   │  └─ class probabilities for each horizon
   ├─ calibration.temperature_scaling
   │  └─ validation-only temperature -> calibrated test/latest probabilities
   ├─ simulation.structural_mc.simulate_paths_detailed
   │  └─ paths, weighted quantiles, VaR/CVaR, drawdown, terminal states
   ├─ backtest.exposure/backtest.metrics
   │  └─ one-day-lag OOS exposure, equity, drawdown and metrics
   └─ reporting.plots/report_builder/current_monitor
      └─ CSV/JSON/PNG/Markdown artifacts
```

### Nạp và kiểm tra dữ liệu

- `data.loader.load_price_data(path)` nhận CSV DataPro/VN-Index, chuẩn hóa tên
  cột, số có dấu phân cách hàng nghìn, ngày và duplicate; trả về DataFrame tăng
  dần theo thời gian cùng metadata/checksum.
- `data.validation.validate_data_file(data_path, output_dir)` gọi loader, kiểm
  tra missing, duplicate, giá âm, quan hệ high/low và calendar gap; ghi CSV,
  JSON và Markdown.
- `ops.ingest.ingest_latest` quản lý cập nhật lịch sử từ `incoming/`; đây là
  luồng vận hành riêng, không tham gia fit mô hình.

### Target, feature và split

- `targets.regime_targets.create_multihorizon_targets` tạo nhãn đa lớp cho các
  horizon 20, 40, 60 và quan trọng nhất là `target_end_date_h`.
- `features.technical.build_features` chỉ dùng rolling/expanding/EWM và lag từ
  dữ liệu đến hàng hiện tại; trả về DataFrame và `FeatureRegistry`.
- `features.selection.select_features(features, train_index, ...)` ước lượng
  missing/constant/correlation chỉ trên train.
- `validation.purged_split.make_outer_split` tạo train/validation/test theo
  thời gian. Train thỏa `target_end_date_h < validation_start`; validation thỏa
  `target_end_date_h < test_start`.
- `PurgedWalkForwardSplit.split` cung cấp inner folds với điều kiện
  `target_end_date_h < fold_validation_start`.

### Filtered HMM

- `regime.filtered_hmm.fit_filtered_hmm(base_features, returns, train_idx,
  n_states, seeds)` fit `StandardScaler` và `GaussianHMM` chỉ trên `train_idx`.
- `forward_filter` tính đúng đại lượng nhân quả `P(S_t | F_t)` bằng forward
  recursion; không gọi smoothed posterior.
- Output `FilteredHMMResult` gồm:
  - `probabilities`: các cột `hmm_prob_state_k`, entropy, expected return,
    expected volatility, duration và label;
  - `diagnostics`: transition matrix, `state_mean`, `state_volatility`, labels,
    warnings và feature columns;
  - `state_mapping`: ánh xạ raw state sang economic state ổn định.

### EGARCH Student-t

- `risk.egarch_t.fit_egarch_features(returns, train_idx)` fit
  `arch_model(..., vol="EGARCH", dist="StudentsT")` trên train.
- Sau fit, hàm chạy recursion một chiều qua chuỗi return để tạo
  `egarch_sigma`, log variance, standardized residual, negative shock,
  volatility percentile/change và tail-risk score. Nếu optimizer lỗi, hàm ghi
  warning và dùng EWMA fallback.
- `EGARCHResult.diagnostics` giữ point estimates `omega`, `alpha[1]`,
  `gamma[1]`, `beta[1]`, mean và `nu`.

### EBM, calibration và explainability

- `models.ebm_forecaster.EBMForecaster.fit/predict_proba/importance` triển khai
  multiclass EBM, với sklearn fallback khi cần.
- Tuning dùng `tuning.optuna_tuner.tune_ebm_random_search`; objective được tính
  qua purged walk-forward folds, không dùng final test.
- `calibration.temperature_scaling.fit_temperature` chỉ nhận validation
  probabilities và validation labels; `apply_temperature` áp cùng nhiệt độ
  cho test/latest.
- Explainability hiện gồm feature importance, EBM shape probes và local
  median-counterfactual contributions, được ghi trong `pipeline.py`.

### Monte Carlo, bootstrap và backtest

- `simulation.structural_mc.simulate_paths_detailed` nhận:
  `last_price`, state probability hiện tại, transition matrix, state drift,
  sigma hiện tại, horizon, số path/seed, state volatility, EGARCH parameters,
  Student-t `nu` và calibrated EBM class probabilities.
- Hàm lấy state đầu từ filtered probability mới nhất, chuyển state bằng
  transition matrix, cập nhật EGARCH log variance, sinh standardized Student-t
  shock, tạo log-return và price path. EBM probabilities chỉ reweight terminal
  paths với ESS safeguard.
- Output `SimulationOutput` gồm price paths, weights, terminal states, fan-chart
  quantiles, risk summary và state distribution. Summary hiện có terminal
  return quantiles, xác suất lời/lỗ, VaR 95%, CVaR 95%, drawdown threshold,
  mean maximum drawdown và ESS.
- `uncertainty.block_bootstrap.bootstrap_prediction_differences` tạo moving
  block bootstrap CI cho chênh lệch metric phân loại.
- `backtest.exposure.backtest_exposure` áp exposure trễ một phiên và chi phí
  giao dịch; `backtest.metrics.backtest_metrics` tổng hợp kết quả OOS.

### Reporting và test suite

- `reporting.plots.generate_all_plots` dựng lại hình từ artifact đã lưu.
- `reporting.report_builder.build_run_report` và `build_docs_and_readme` dựng
  báo cáo/README; `reporting.current_monitor.generate_current_monitor` là luồng
  theo dõi vận hành.
- Test suite hiện bao phủ loader/ingest, causal features, filtered HMM, EGARCH,
  purged split, calibration, Monte Carlo, bootstrap, backtest lag,
  reproducibility, Markdown và smoke pipeline.

## 3. Nguồn point estimate đi vào Monte Carlo hiện tại

Tại cuối `run_pipeline`, simulator dùng **deployment fit**:

| Đại lượng | Nguồn thực tế | Trạng thái hiện tại |
|---|---|---|
| Starting regime probability | hàng cuối của `deployment_hmm.probabilities[hmm_prob_state_*]` | filtered, point vector |
| Transition | `deployment_hmm.diagnostics["transition_matrix"]` | HMM point estimate |
| Expected return theo regime | `deployment_hmm.diagnostics["state_mean"]` | weighted point estimate |
| Volatility theo regime | `deployment_hmm.diagnostics["state_volatility"]` | weighted point estimate |
| Conditional volatility | hàng cuối `deployment_risk.features["egarch_sigma"]` | EGARCH filtered point estimate |
| EGARCH recursion | `deployment_risk.diagnostics["params"]` | optimizer point estimate |
| Residual distribution | Student-t với `deployment_risk.diagnostics["nu"]` | một point estimate chung |
| Horizon class probability | calibrated EBM probability trong `latest_outlook` | point probability, dùng reweighting |

Như vậy HMM, EGARCH, EBM và calibration đều vẫn là point-estimate components.
Simulator hiện chỉ truyền innovation risk với một `nu`; chưa truyền uncertainty
của drift, scale hoặc tail parameter.

## 4. Điểm cần kiểm soát leakage

1. `target_end_date_h < boundary` đã được enforce cho outer train và validation;
   mọi posterior fit mới phải nhận đúng `train_index`, không tự tạo random
   split và không mở rộng đến validation/test.
2. HMM dùng filtered probability, không dùng smoothed state. Lớp mới chỉ được
   nhận các cột `hmm_prob_state_*`; cấm nhận future state/label.
3. Scaler của HMM và EGARCH parameters được fit trên train, nhưng recursion sau
   fit dùng realized return theo thứ tự thời gian. Điều này hợp lệ để tạo feature
   tại từng thời điểm khi observation đó đã có; không được lấy hàng sau forecast
   origin làm đầu vào cho một forecast trước đó.
4. **Rủi ro hiện hữu trong inner tuning:** `evaluation_hmm` và
   `evaluation_risk` được fit một lần trên outer-train tham chiếu horizon 60,
   sau đó các feature này được tái sử dụng trong inner walk-forward folds.
   Point estimates đó có thể đã thấy phần outer-train nằm sau boundary của một
   inner fold sớm. Việc nâng cấp VB không được sao chép pattern này; posterior
   diagnostics theo fold phải được fit từ observations của chính fold.
5. Deployment HMM/EGARCH dùng toàn bộ lịch sử hiện có. Điều này chỉ hợp lệ cho
   forecast mới nhất sau khi hyperparameter/calibration đã khóa; tuyệt đối không
   dùng deployment artifacts để chấm final test.
6. Temperature được chọn trên validation và áp lên test; không được dùng test
   để chọn prior, ADVI steps, convergence threshold hoặc fallback.
7. `fill_features` và feature selection phải tiếp tục chỉ học fill values/danh
   sách feature từ train.
8. Warm start, nếu bổ sung sau này, chỉ được truyền từ fold trước sang fold sau
   theo chiều thời gian.

## 5. Kế hoạch tích hợp theo file thực tế

1. Thêm `raemf_mc.bayesian` với `VariationalScenarioModel` và
   `VariationalPosteriorResult`. PyMC/ArviZ được lazy-import để
   `bayesian.enabled: false` không khởi tạo backend.
2. Mô hình mới nhận return, đúng các filtered state probabilities,
   `egarch_sigma`, date/train index và cấu hình. Nó chuẩn hóa return/sigma chỉ
   bằng train, kiểm tra alignment, simplex, scale, effective regime counts và
   fingerprint trước khi xây mixture Student-t likelihood.
3. Full-rank ADVI là mặc định; mean-field ADVI là lựa chọn nhanh. ELBO,
   posterior constraints và finite-value checks là điều kiện trước khi phát
   posterior draws.
4. Mở rộng `simulation.structural_mc` bằng ba mode:
   `point_estimate`, `posterior_mean_mc`, `variational_posterior`. Mode cũ giữ
   nguyên code path. Trong VB mode, mỗi path lấy đúng một bộ
   `(mu_k, c_k, nu_k)` và giữ cố định trên toàn horizon.
5. `pipeline.run_pipeline` chỉ lazy-import/fit posterior khi config bật
   Bayesian; artifact đặt dưới `run_dir/bayesian`. Evaluation fit chỉ dùng
   training rows của split tương ứng; deployment fit dùng lịch sử đến forecast
   origin sau khi cấu hình đã khóa.
6. CLI giữ lệnh cũ và bổ sung option/lệnh VB nhất quán. Save/load phải cho phép
   forecast không refit.
7. Bổ sung posterior predictive metrics/plots, so sánh ba MC mode, runtime,
   memory/artifact metadata và optional MCMC benchmark tách khỏi production.
8. Bổ sung test cho validation, constraints, seed, serialization, sampling
   shape, một parameter draw/path, disabled mode, fallback và no-leakage.

## 6. Phạm vi Bayesian hóa

Phiên bản đầu chỉ Bayesian hóa **scenario return layer có điều kiện trên
filtered HMM probabilities và EGARCH sigma**. HMM transition/filter, EGARCH
recursion, EBM, calibration và backtest vẫn là point-estimate components.
Vì vậy tên mô tả đúng là RAEMF-VB-MC hoặc “Variational Bayesian scenario
layer”; đây không phải fully Bayesian HMM-EGARCH và Variational Bayes không
thay thế Monte Carlo.
