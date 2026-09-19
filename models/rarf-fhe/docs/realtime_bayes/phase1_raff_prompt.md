# Prompt: Real-time Bayesian online-update layer for RAFF (Phase 1 of 3)

Dán toàn bộ nội dung file này vào VS Code (Claude Code / Copilot Chat) để agent thực hiện.
Đây là **Phase 1** trong lộ trình 3 phase (RAFF → Dynamic Graph → MSDP). Chỉ làm RAFF trong
phase này; không động vào hai repo kia.

---

## 0. Bối cảnh — đọc trước khi code bất cứ thứ gì

Repo này (`vnindex_model`, tên thư mục `RARF-FHE-Regime-Aware-Random-Forest-Forecasting-Hybrid-Engine`)
là pipeline nghiên cứu VN-Index: Filtered HMM (regime) → EGARCH Student-t (volatility) →
regime-aware Random Forest (`SoftGatedForest`) → validation-gated center blend → sequential
conformal → Hybrid Monte Carlo → drawdown/VaR/ES.

**Hiện trạng:** mọi lệnh CLI (`train`, `backtest`, `forecast`, `report`, `run-all`) đều gọi
chung `run_pipeline()` trong `src/vnindex_model/pipeline.py` — tức là *mỗi lần chạy đều refit
lại toàn bộ từ đầu* trên `data/raw/VNINDEX_Daily.csv` (dữ liệu CSV tĩnh, không có kết nối DB).
Không có khái niệm "cập nhật 1 phiên mới" ở bất kỳ đâu trong code hiện tại.

**Mục tiêu Phase 1:** thêm một tầng "online update" chạy trong vài giây mỗi khi có **một phiên
giao dịch mới**, cập nhật các đại lượng vốn đã mang bản chất Bayesian/recursive (regime
posterior của HMM, conditional variance của EGARCH, conformal quantile) **mà không refit** HMM
(Baum-Welch), không refit EGARCH (MLE), không refit Random Forest. Việc refit nặng đó vẫn giữ
nguyên là `run-all` theo chu kỳ (ví dụ hàng tuần), và mỗi lần `run-all` sẽ **khởi tạo lại**
("reset") state online.

Đây là kiến trúc 2 tầng đã được xác nhận với người dùng:

- **Tầng online (giây, mỗi phiên mới):** 1 bước forward-filter cho HMM, 1 bước recursive
  variance update cho EGARCH, inference (không train) cho `SoftGatedForest` với regime
  posterior mới, 1 bước cập nhật conformal quantile, resample Monte Carlo paths từ state mới.
- **Tầng batch (không đổi, theo chu kỳ):** `run_pipeline()` hiện tại — Baum-Welch, MLE EGARCH,
  train RF, chọn lại conformal method/window. Mỗi lần chạy xong sẽ ghi ra một "online state"
  mới để tầng online tiếp tục từ đó.

**Ràng buộc bắt buộc phải tôn trọng** (văn hóa của repo này, xem README và test suite hiện có):

1. Không leakage/lookahead: mọi feature/label dùng cho state tại ngày `t` chỉ được dùng dữ liệu
   có sẵn đến hết ngày `t`. Bước online cũng phải giữ nguyên tính chất này.
2. Không âm thầm nội suy dữ liệu thiếu, không âm thầm sửa lỗi OHLC — nếu phiên mới bất thường
   (gap ngày, giá trị thiếu, vi phạm High/Low), phải log cảnh báo rõ ràng, không tự "vá".
3. Không tự động overwrite artifact cũ nếu state không nhất quán (giống nguyên tắc
   `run_manifest.json`/fingerprint bên Dynamic Graph) — mọi artifact online phải kèm
   `as_of_date`, data hash của phiên vừa nạp, và tham chiếu tới run batch gốc đã sinh ra state.
4. Toàn bộ test hiện có (`pytest -q`) phải tiếp tục pass. Test mới phải theo đúng convention
   hiện tại trong `tests/` (naming, fixtures, không dùng dữ liệu tương lai).
5. DB kết nối phải là **read-only**. Không được ghi/UPDATE/DELETE vào DB nguồn dưới bất kỳ hình
   thức nào.

---

## 1. Việc đầu tiên: khảo sát trước khi thiết kế state schema

Trước khi viết code, agent phải tự đọc và xác nhận các điểm sau (đừng đoán):

1. Đọc toàn bộ `src/vnindex_model/pipeline.py` (2600+ dòng) để nắm chính xác thứ tự các bước
   trong `run_pipeline()`: `build_features` → `purged_train_validation_test` →
   `fit_filtered_hmm` → `fit_egarch_student_t` → `fit_soft_gated_forest`/`fit_forest_bundle` →
   `select_validation_gated_center` → `select_conformal_method`/`sequential_conformal` →
   `adaptive_simulate_paths`/hybrid Monte Carlo → drawdown layer. Xác nhận danh sách input mà
   mỗi bước cần từ bước trước, vì state online phải lưu đủ các input đó.
2. Đọc `src/vnindex_model/features.py` (`build_features`) để xác định **lookback tối đa** mà
   bất kỳ feature nào cần (rolling window dài nhất, ví dụ `rolling_volatility_20`,
   `cumulative_return_20`, v.v.). Đây là số ngày OHLCV thô tối thiểu phải giữ trong buffer để
   tính được feature row cho 1 phiên mới — **không thể tính feature của 1 ngày mới chỉ từ 1
   dòng dữ liệu mới**, cần một cửa sổ trailing.
3. Đọc `src/vnindex_model/hmm.py` (`forward_filter`, `_log_emissions`, `_economic_order`) —
   đã đọc kỹ trong phiên brainstorm, xem phần 2 dưới đây để biết hàm cần viết thêm.
4. Đọc `src/vnindex_model/volatility.py` (`fit_egarch_student_t`, `fit_arch_candidate`) — vòng
   lặp recursive tính `log_variance[row]` đã tồn tại sẵn trong hàm fit; chỉ cần trích xuất logic
   1 bước ra hàm riêng dùng chung cho cả fit (batch) và update (online).
5. Đọc `src/vnindex_model/random_forest.py` (`SoftGatedForest`, `predict_soft_gated`) — đã xác
   nhận: đây chính là Bayesian model averaging over regime experts, trọng số = regime
   posterior. Không cần sửa gì ở đây ngoài việc gọi `predict_soft_gated` với posterior mới.
6. Đọc `src/vnindex_model/conformal.py` (`sequential_conformal`, `finite_sample_quantile`,
   `signed_lower_quantile`, `_stratum_mask`) để hiểu cách score pool + stratum (regime ×
   volatility bin) hoạt động, vì bước online phải nuôi tiếp đúng cơ chế này thay vì thay bằng
   thứ khác.
7. Đọc `src/vnindex_model/persistence.py` (`save_model`, `write_json`, `run_metadata`) — dùng
   lại các helper này cho việc lưu state, đừng viết cơ chế serialize riêng.
8. Đọc `src/vnindex_model/data.py` (`discover_data_file`, `validate_and_save`) — hiện tại
   **không có** kết nối DB nào ở đây, chỉ đọc CSV cục bộ. Việc kết nối DB trên VPS là phần mới
   hoàn toàn (xem mục 4).
9. Tham khảo (KHÔNG copy nguyên, chỉ học cách làm) module
   `../../../Dynamic Graph/src/dynamicgraph/data/connectors.py` — repo Dynamic Graph đã có sẵn
   pattern kết nối SQLite/DuckDB **read-only** (`mode=ro`, write-denying authorizer). Port lại
   đúng tinh thần read-only đó cho RAFF thay vì viết lại từ đầu theo cách kém an toàn hơn.
10. Hỏi người dùng (qua issue/TODO comment nếu không chắc, đừng tự bịa): connection string / DB
    engine thật của VPS (Postgres? MySQL? SQLite file mount qua SSH?), tên bảng, tên cột OHLCV.
    Nếu chưa biết, implement connector cho **SQLite/DuckDB trước** (đã có tiền lệ ở Dynamic
    Graph) đằng sau một interface `MarketDataSource` để dễ thay driver sau, và để cấu hình
    connection string qua biến môi trường/`config/local.yaml`, không hardcode.

---

## 2. Module mới: `src/vnindex_model/online_state.py`

Tạo dataclass trung tâm lưu toàn bộ trạng thái cần cho bước online. Đừng nhồi vào
`pipeline.py` — tách riêng để dễ test.

```python
@dataclass
class HMMOnlineState:
    model: GaussianHMM              # đã fit, không đổi giữa 2 lần batch refit
    scaler: StandardScaler          # đã fit trên train, không đổi
    feature_names: list[str]
    economic_order: np.ndarray      # mapping raw state index -> economic-ordered index
    economic_labels: list[str]
    transition_matrix: np.ndarray   # đã economic-ordered, không đổi
    log_alpha: np.ndarray           # forward variable (log, normalized) tại as_of_date — ĐÂY LÀ STATE THAY ĐỔI MỖI NGÀY

@dataclass
class EGARCHOnlineState:
    model_name: str                 # "EGARCH(1,1) Student-t" | "GARCH(1,1) Student-t" | "EWMA" | fallback variants
    parameters: dict[str, float]    # omega, alpha[1], gamma[1], beta[1], mu, nu — không đổi giữa 2 lần refit
    log_variance: float             # state thay đổi mỗi ngày
    ewma_state: float | None        # nếu đang ở nhánh fallback EWMA, lưu variance EWMA hiện tại

@dataclass
class ConformalOnlineState:
    # mỗi horizon (5,20,60,...) có 1 entry
    pools: dict[int, dict[str, list[float]]]   # horizon -> stratum_label -> danh sách signed scores (rolling/growing theo config)
    pending: list[PendingScore]                # forecast đã phát ra nhưng target chưa "chín" (chưa đủ horizon phiên)
    selected_method: dict[int, str]             # method đã khóa từ lần batch refit gần nhất (giữ nguyên, không chọn lại online)
    selected_window: dict[int, int | None]

@dataclass
class OnlineState:
    schema_version: int
    as_of_date: str
    last_close: float
    raw_ohlcv_buffer: pd.DataFrame   # N ngày gần nhất, đủ cho lookback dài nhất trong build_features
    hmm: HMMOnlineState
    egarch: EGARCHOnlineState
    forest: SoftGatedForest          # không đổi giữa 2 lần refit — inference-only ở tầng online
    forest_feature_names: list[str]
    conformal: ConformalOnlineState
    source_run_metadata: dict        # run_metadata() của lần batch refit đã sinh ra state này (data_hash, git commit nếu có, config path)
```

`PendingScore` = dataclass nhỏ: `{origin_date, horizon, target_end_date, center, sigma, regime, vol_bin}`
— dùng để biết khi nào 1 forecast "chín" (target_end_date <= as_of_date mới) và tính score thật
để đẩy vào `pools`.

Lưu bằng `joblib.dump`/`persistence.save_model` vào
`artifacts/online_state/online_state.joblib`, kèm 1 file `online_state_manifest.json` (dùng
`write_json`) ghi `as_of_date`, `schema_version`, `source_run_metadata`, checksum của
`raw_ohlcv_buffer`.

---

## 3. Hàm cần thêm vào các module hiện có

### 3.1 `hmm.py` — thêm `forward_filter_step`

Tách phần thân vòng lặp trong `forward_filter` ra một hàm 1-bước dùng chung:

```python
def forward_filter_step(
    model: GaussianHMM,
    previous_log_alpha: np.ndarray,   # log_alpha tại t-1, đã normalize (logsumexp = 0)
    new_observation_scaled: np.ndarray,  # 1 vector, đã transform bằng scaler đã fit
) -> tuple[np.ndarray, np.ndarray]:
    """1 bước forward recursion. Trả về (log_alpha_t mới, probabilities_t)."""
    emission = _log_emissions(model, new_observation_scaled[None, :])[0]  # cần refactor _log_emissions nhận 1 hàng
    transition = np.log(np.maximum(model.transmat_, 1e-12))
    log_alpha = emission + logsumexp(previous_log_alpha[:, None] + transition, axis=0)
    log_alpha -= logsumexp(log_alpha)
    return log_alpha, np.exp(log_alpha)
```

**Bắt buộc viết test** (`tests/test_online_hmm.py`): chạy `forward_filter` batch trên toàn bộ
chuỗi quan sát, sau đó chạy `forward_filter_step` tuần tự từng bước từ cùng điểm khởi đầu —
so sánh `probabilities` ra khớp nhau trong tolerance `1e-8`. Đây là gate chấp nhận quan trọng
nhất của Phase 1: nếu online step không tái tạo đúng batch forward-filter thì toàn bộ thiết kế
sai.

Lưu ý: `log_alpha` ban đầu (để khởi tạo state ngay sau 1 lần `run-all`) chính là hàng cuối của
mảng log-alpha nội bộ trong `forward_filter` — hiện hàm này không trả log_alpha ra ngoài, chỉ
trả `probabilities` (đã exp và normalize). Cần sửa `forward_filter` để trả thêm log_alpha cuối
cùng (hoặc thêm hàm `forward_filter_with_state` trả `(probabilities, final_log_alpha)`), rồi cho
`fit_filtered_hmm` lưu lại giá trị này vào diagnostics để `online_state.py` lấy ra khi khởi tạo
state sau batch refit. Giữ nguyên chữ ký `forward_filter` cũ để không phá test hiện có; thêm hàm
mới thay vì sửa signature.

### 3.2 `volatility.py` — thêm `egarch_step`

Trích xuất đúng công thức đã có trong vòng lặp của `fit_egarch_student_t`:

```python
def egarch_step(
    parameters: dict[str, float],
    log_variance_prev: float,
    mean: float,
    previous_return_percent: float,   # (r_{t-1} - mu) * 100, đã trừ mean
    model_name: str,
) -> tuple[float, float]:
    """Trả về (log_variance_t, standardized_residual_{t-1})."""
    ...  # y hệt logic trong fit_egarch_student_t, tách ra dùng chung
```

Viết test tương tự: fit batch trên N ngày, rồi replay tuần tự bằng `egarch_step` từ cùng
`log_variance` khởi tạo — `sigma`/`log_variance` phải khớp batch trong tolerance số học hợp lý
(dùng `np.allclose` với `atol` phù hợp, vì đây là công thức tất định không có randomness).

Nếu model đang ở nhánh fallback EWMA (không hội tụ khi refit), bước online dùng công thức EWMA
tương ứng (`span=40` như trong code hiện tại) thay vì công thức EGARCH — đọc kỹ nhánh fallback
trong `fit_egarch_student_t` để implement đúng logic tương đương ở dạng 1-bước.

### 3.3 `conformal.py` — thêm cơ chế online

Hai việc:

1. **Nuôi score pool online**: hàm `mature_pending_scores(state: ConformalOnlineState, as_of_date, realized_lookup)`
   — với mỗi `PendingScore` có `target_end_date <= as_of_date`, tính
   `score = (realized - center) / max(sigma, epsilon)`, xác định `stratum` bằng đúng logic
   `_stratum_mask`/method đã khóa (`state.selected_method[horizon]`), append vào
   `state.pools[horizon][stratum]`, rồi loại khỏi `pending`. Nếu config có window (rolling), cắt
   bớt đầu pool khi vượt window — y hệt logic trong `sequential_conformal`.
2. **(Khuyến nghị) Adaptive Conformal Inference (ACI)** để interval tự nới/co theo thời gian
   thực thay vì chỉ dựa vào quantile tĩnh của pool — đây là phương pháp online-conformal chuẩn
   trong literature (Gibbs & Candès, 2021), rất khớp với yêu cầu "cập nhật kiểu Bayes mỗi
   phiên": mỗi khi một forecast "chín", cập nhật

   ```text
   alpha_{t+1} = clip(alpha_t + gamma * (alpha_target - miscoverage_indicator_t), eps, 1-eps)
   ```

   trong đó `miscoverage_indicator_t = 1` nếu outcome thật nằm ngoài interval vừa dự báo. Dùng
   `alpha_{t+1}` (thay vì `alpha_target` cố định) khi gọi `finite_sample_quantile`/
   `signed_lower_quantile` cho lần dự báo tiếp theo. Thêm `gamma` (learning rate, ví dụ 0.01–0.05)
   vào config `conformal:` section trong `configs/*.yaml`. Đây là phần **duy nhất** trong Phase 1
   có tham số mới cần chọn — mặc định để tắt được (`aci_enabled: false`) để không đổi hành vi
   `run-all` hiện có, chỉ bật cho pipeline online.

Viết `tests/test_online_conformal.py`: kiểm tra maturity bookkeeping không leak (một
`PendingScore` không bao giờ được dùng để tính chính interval của chính nó), và ACI coverage
hội tụ về gần `1 - alpha_target` trên dữ liệu synthetic dài.

### 3.4 `random_forest.py` — không cần hàm mới

`predict_soft_gated(model.forest, x_row, new_regime_probabilities)` đã đủ. Chỉ cần đảm bảo
`x_row` build đúng từ `raw_ohlcv_buffer` + feature pipeline (dùng lại `build_features`, cắt lấy
đúng hàng ngày mới nhất — **không refit `select_train_features`/`SimpleImputer`**, dùng lại
`forest.global_bundle.imputer`/`forest.experts[*].imputer` đã fit sẵn qua `.transform()` chỉ).

---

## 4. Module mới: `src/vnindex_model/data_source.py`

Interface tối thiểu, tách khỏi implementation cụ thể để dễ đổi driver:

```python
class MarketDataSource(Protocol):
    def latest_date(self) -> pd.Timestamp: ...
    def fetch_since(self, since: pd.Timestamp, lookback_buffer_days: int) -> pd.DataFrame:
        """Trả OHLCV read-only, index theo date, đủ buffer để build_features tính được."""
```

Implement `SQLiteMarketDataSource`/`DuckDBMarketDataSource` trước (theo pattern read-only đã có
ở Dynamic Graph — xem mục 1.9), cấu hình qua `config/local.yaml` (thêm section `data.source`
tương tự cách Dynamic Graph định nghĩa `data.database_path`/`data.backend`/`data.column_map`).
Nếu VPS thực tế dùng Postgres/MySQL, thêm driver tương ứng sau khi đã biết chắc schema thật —
đừng đoán schema, để `column_map` cấu hình được như bên Dynamic Graph.

**Không** implement writer/poller như một daemon phức tạp ở giai đoạn này — chỉ cần
`fetch_since` gọi được từ CLI command mới (mục 5). Việc lặp định kỳ (poll mỗi N phút) để ngoài
phạm vi code Python: dùng Windows Task Scheduler/cron gọi CLI, đúng như README hiện tại đã làm
với `run-all` ("Chưa có scheduler tích hợp; có thể dùng Windows Task Scheduler, cron hoặc
orchestration bên ngoài" — giữ nguyên triết lý này, không tự chế scheduler trong Python).

---

## 5. CLI mới trong `cli.py` / hàm mới trong `pipeline.py`

Thêm 2 command, không đổi command cũ:

- `init-online-state --config configs/default.yaml`
  - Chạy sau (hoặc như bước cuối của) `run-all`. Lấy toàn bộ object đã fit trong
    `run_pipeline()` (HMM model+scaler, EGARCH params, `SoftGatedForest`, conformal
    method/window đã chọn, score pool ban đầu từ validation+test) và ghi thành `OnlineState`
    (mục 2). Đây là điểm nối giữa tầng batch và tầng online.
- `update-latest --config configs/default.yaml`
  - Load `OnlineState` đã lưu.
  - Gọi `MarketDataSource.fetch_since(state.as_of_date, lookback_buffer_days)`.
  - Nếu không có ngày mới: log và thoát, không ghi gì (idempotent).
  - Nếu có **đúng 1** ngày mới: chạy chuỗi bước ở mục 3 (HMM step → EGARCH step → build feature
    row → RF inference → point-forecast blend bằng alpha đã khóa → resample Monte Carlo → mature
    conformal scores → cập nhật interval), ghi `OnlineState` mới + artifact "latest" (giữ đúng
    schema `artifacts/forecasts/latest_forecast.csv` / `latest_forecast_summary.json` /
    `latest_drawdown_*` hiện có, để không phá downstream nào đang đọc các file này).
  - Nếu có **nhiều hơn 1** ngày mới (ví dụ máy tắt vài hôm): lặp tuần tự từng ngày một qua đúng
    state machine trên (không "nhảy cóc"), để giữ tính đúng của forward-filter/EGARCH recursion.
  - Nếu dữ liệu ngày mới bất thường (gap lịch, NaN, vi phạm OHLC): log cảnh báo rõ, **không**
    tự động chạy tiếp — dừng và yêu cầu xem xét thủ công (đúng triết lý "không âm thầm sửa" của
    repo).

---

## 6. Testing & acceptance criteria cho Phase 1

1. `pytest -q` toàn bộ suite hiện có (bao gồm test mới) pass, 0 warning — giữ chuẩn đã có
   (297/297-style discipline bên Dynamic Graph, RAFF cũng nên theo).
2. Test tương đương batch-vs-online cho HMM (`forward_filter` vs chuỗi `forward_filter_step`) —
   khớp trong `atol=1e-8`.
3. Test tương đương batch-vs-online cho EGARCH (`log_variance`/`sigma` recursion) — khớp trong
   tolerance số học hợp lý.
4. Test conformal maturity bookkeeping không leak tương lai (dùng `target_end_date` y hệt cách
   `eligible_score_indices`/`sequential_conformal` đã kiểm soát trong code batch).
5. Test end-to-end nhỏ: giả lập 20 phiên liên tiếp qua `update-latest` trên dữ liệu tổng hợp,
   so sánh state cuối cùng với việc chạy `run_pipeline` batch trên đúng 20 phiên đó cộng thêm —
   không cần khớp tuyệt đối (vì batch còn refit HMM/EGARCH/RF) nhưng phải khớp về quy mô
   (probabilities hợp lệ, sigma dương hữu hạn, interval width tăng theo horizon).
6. `update-latest` chạy trong vài giây trên máy dev thông thường (không load lại toàn bộ CSV,
   không refit gì) — đo và ghi log runtime để xác nhận mục tiêu "real-time theo phiên" đạt được.
7. Chạy được `update-latest` hai lần liên tiếp trong cùng ngày (không có dữ liệu mới) mà không
   sinh ra artifact trùng/hỏng — idempotent.

## 7. Việc KHÔNG làm trong Phase 1

- Không sửa `Dynamic Graph/` hay `MSDP/` (đó là Phase 2, Phase 3 — sẽ có prompt riêng).
- Không refit HMM/EGARCH/RF/chọn lại conformal method trong `update-latest`.
- Không tự viết scheduler/daemon Python chạy nền — chỉ cung cấp CLI command để hệ thống ngoài
  (Task Scheduler/cron) gọi.
- Không đổi format của các artifact "latest" hiện có mà hệ thống khác có thể đang đọc.
