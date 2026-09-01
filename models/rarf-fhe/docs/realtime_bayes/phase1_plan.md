# Phase 1 — kế hoạch thực thi (RAFF online Bayesian layer)

Nguồn yêu cầu: [`phase1_raff_prompt.md`](phase1_raff_prompt.md). Tài liệu này ghi lại kết quả
khảo sát mục 1 và thứ tự thực thi TDD.

## Kết quả khảo sát (mục 1 của prompt)

| Câu hỏi | Kết luận |
| --- | --- |
| Lookback tối đa của `build_features` | Rolling dài nhất là 252 (`historical_var_95`, `historical_es_95`, `rolling_max_drawdown`, `distance_peak_252`). **Nhưng** còn feature *expanding*: `current_drawdown` (`close.cummax()` toàn chuỗi), `drawdown_duration`/`days_since_peak`, `obv` (cumsum), và EWM `adjust=False` (`ewma_volatility`, `distance_ema_*`, `macd*`) về lý thuyết có bộ nhớ vô hạn. ⇒ buffer phải là **toàn bộ lịch sử** nếu muốn feature online khớp batch tuyệt đối. |
| Chi phí | `build_features` trên 6306 phiên = **4.07 s**; trên 600 phiên = 0.39 s. 4 s vẫn đạt mục tiêu "vài giây/phiên" ⇒ chọn full-history buffer, đổi lấy tính đúng tuyệt đối. `online.lookback_buffer_days` vẫn cấu hình được (null = full). |
| `forward_filter` | Trả `probabilities` theo **raw state order**; `fit_filtered_hmm` mới hoán vị sang economic order sau đó. State online vì vậy phải giữ `log_alpha` ở raw order + mảng `economic_order`. `fit_filtered_hmm` hiện **không** lưu `order` ⇒ thêm vào diagnostics. |
| `fit_egarch_student_t` | Vòng lặp recursive đã có sẵn; `standardized[t] = (r_t*100 - mu)/sqrt(exp(lv_t))` với mọi t. Nhánh fallback EWMA dùng `ewm(span=40, adjust=False, min_periods=5).std()` — không có dạng 1 bước đơn giản chính xác, nhưng vì buffer là full history nên tính lại nguyên biểu thức là O(n) và **chính xác tuyệt đối** (không refit gì cả). |
| `predict_soft_gated` | Đủ dùng, không sửa. Input là `augmented_full` = `features[selected_technical]` + `hmm.probabilities.drop("hmm_state")` + `volatility.features` ⇒ online phải dựng lại cả cột phái sinh của HMM (`hmm_entropy`, `hmm_state_duration`, `hmm_expected_duration`, `hmm_transition_probability`) và của EGARCH. |
| Conformal | `sequential_conformal` "chín" theo vị trí (`position - horizon + 1`); online chuyển sang `target_end_date`. Realized return lấy từ buffer giá: `log(close_t / close_{t-h})`. |
| Persistence | Dùng `save_model` / `write_json` / `run_metadata` sẵn có. |
| DB | `data.py` chỉ đọc CSV. Connector mới port tinh thần read-only của `Dynamic Graph/src/dynamicgraph/data/connectors.py` (`?mode=ro` + `set_authorizer` từ chối mọi opcode ghi; DuckDB `read_only=True`). |

## Sai lệch có chủ ý so với prompt

1. `egarch_step` bỏ tham số `mean` rời — `mu` đã nằm trong `parameters`, và chú thích của prompt
   (`(r_{t-1} - mu) * 100`) không khớp code thật (`r_{t-1}*100 - mu`, vì `mu` của `arch` ở đơn vị
   phần trăm). Giữ đúng công thức code để test tương đương batch pass được.
2. Logic online nằm ở module mới `online.py` thay vì nhồi thêm vào `pipeline.py` (đã 2611 dòng).
   `run_pipeline` chỉ thêm một bước ghi `BatchHandoff` — nhờ vậy `init-online-state` chạy nhanh và
   test được mà không cần chạy toàn pipeline.

## Thứ tự thực thi (TDD, mỗi bước: test đỏ → code → test xanh)

1. `hmm.forward_filter_with_state` + `forward_filter_step` — gate quan trọng nhất (atol 1e-8).
2. `volatility.egarch_step` + refactor `fit_egarch_student_t` gọi lại nó.
3. `conformal`: `PendingScore`, `mature_pending_scores`, `AdaptiveConformalState` (ACI).
4. `data_source.py`: `MarketDataSource` + CSV/SQLite/DuckDB read-only.
5. `online_state.py`: dataclass + save/load + manifest.
6. `online.py`: `build_online_state`, `advance_one_session`, `update_latest`.
7. `pipeline.py` ghi handoff; `cli.py` thêm `init-online-state` / `update-latest`; config mới.
8. README + docs.

---

## Kết quả thực thi (hoàn tất)

### Acceptance criteria (mục 6 của prompt)

| # | Tiêu chí | Kết quả |
| --- | --- | --- |
| 1 | `pytest -q` pass, 0 warning | **98 passed, 0 warning, 113 s** (baseline trước Phase 1: 45 passed). `ruff check src tests scripts` clean. |
| 2 | HMM batch vs online khớp `atol=1e-8` | Đạt ở `atol=1e-10` — `tests/test_online_hmm.py` (chuỗi `forward_filter_step`) và `tests/test_online_update.py` (posterior online so với `forward_filter` chạy lại trên chuỗi mở rộng). |
| 3 | EGARCH batch vs online khớp | Đạt ở `abs=1e-10`. Đảm bảo bằng cấu trúc: `fit_egarch_student_t` gọi đúng `egarch_step`, nên chỉ có **một** implementation. |
| 4 | Conformal maturity không leak tương lai | `tests/test_online_conformal.py::test_pending_score_never_contributes_to_its_own_interval` — mỗi origin đều assert mọi pending còn lại có `target_end_date` > ngày hiện tại. |
| 5 | End-to-end 20 phiên | `test_twenty_sessions_keep_every_published_quantity_well_formed`: probabilities hợp lệ, sigma dương hữu hạn, interval 95% rộng hơn 50%, center nằm trong interval. |
| 6 | `update-latest` chạy trong vài giây | **4.15 s/phiên** trên dữ liệu thật 6306 phiên (2000-07-28 → 2026-07-13); riêng `build_features` chiếm 4.06 s. Runtime được log và trả về trong `elapsed_seconds`. |
| 7 | Idempotent | `test_update_latest_is_idempotent_when_the_source_has_no_new_session`: lần chạy thứ hai trả `no_new_sessions`, mtime và nội dung artifact không đổi. |

### Quyết định thiết kế phát sinh trong lúc làm

1. **`ConformalPool` giữ 3 mảng song song, không bucket theo stratum label** như prompt phác.
   Lý do: `_stratum_mask` giải quyết một stratum bằng cách *hợp* các cell theo thác fallback
   (`regime_x_volatility` → `volatility` → `regime` → `global`), và `window` cắt trên chuỗi đã
   pool — cả hai đều không biểu diễn được trên list đã bucket sẵn.
2. **`interval_from_scores` được tách từ thân vòng lặp của `sequential_conformal`** và cả hai tầng
   dùng chung. Nhờ vậy online == batch theo cấu trúc, không phải theo may mắn.
3. **Buffer = toàn bộ lịch sử.** `build_features` có cột expanding (`current_drawdown` dùng
   `close.cummax()`, `obv`, `drawdown_duration`) nên buffer cắt ngắn sẽ đổi giá trị feature.
   `online.lookback_buffer_days` vẫn cấu hình được nếu chấp nhận sai lệch để đổi tốc độ.
4. **Score pool khởi tạo = validation + test.** Batch chỉ dùng validation cho `latest_conformal`
   vì phải giữ vệ sinh backtest. Ở thời điểm production, target của giai đoạn test đều đã hiện
   thực hoá nên dùng chúng không phải leakage — chỉ là nhiều dữ liệu calibration hơn.
5. **`n_jobs = 1` cho forest ở tầng online.** Batch train với `n_jobs=-1` (đúng cho fit), nhưng
   inference 1 dòng/phiên thì dispatch song song là overhead thuần: đo được nhanh hơn ~28% và
   xoá sạch warning `sklearn.utils.parallel.delayed` (385 s → 92 s cho module test).
6. **`egarch_step` bỏ tham số `mean` rời** — `mu` đã nằm trong `parameters`, và chú thích của
   prompt (`(r_{t-1} - mu) * 100`) không khớp code thật (`r_{t-1}*100 - mu`).
7. **Không ghi `latest_drawdown_*` ở tầng online.** Drawdown layer mặc định tắt và là một tầng
   riêng nặng; ghi ra bản một phần sẽ tệ hơn là để nguyên artifact của run batch gần nhất.
   `latest_forecast_summary.json` ghi rõ `update_mode: "online"` và liệt kê các khối chỉ có ở batch.

### Ghi nhận để làm sau (ngoài phạm vi Phase 1)

- 98% chi phí một phiên online là `build_features`, và phần lớn trong đó là `_rolling_slope`
  (`rolling().apply(linregress)`) cùng `_historical_es`. Vector hoá hai hàm này sẽ tăng tốc **cả**
  tầng batch, nhưng chạm vào feature đã dùng cho kết quả nghiên cứu đã commit — nên tách thành
  thay đổi riêng có so sánh số trước/sau, không gộp vào Phase 1.
- `load_price_data` parse với `dayfirst=True` (đúng cho định dạng vendor `dd/mm/yyyy`), nên nó sẽ
  hiểu sai ngày ISO `YYYY-MM-DD` khi phần ngày <= 12. Connector SQLite/DuckDB không đi qua đường
  này (dùng `pd.to_datetime` chuẩn), nhưng cần nhớ nếu sau này đổi nguồn CSV sang định dạng ISO.
- Chưa có driver Postgres/MySQL: chờ xác nhận connection string, tên bảng, tên cột OHLCV thật của
  VPS rồi mới thêm, thay vì đoán schema.

### Hai bug chỉ lộ ra khi chạy end-to-end thật (đã sửa, đã có test)

1. **`hmm_state_duration` lệch 1 phiên.** `_hmm_feature_row` dùng `state.hmm.state_duration` (giá
   trị của phiên *trước*) thay vì run length tính cả phiên hiện tại, trong khi
   `fit_filtered_hmm` dùng `groupby(runs).cumcount()+1` — tức là bao gồm hàng hiện tại. Forest do
   đó nhận sai một feature ở mọi phiên online.
   *Sửa:* tách `regime_feature_frame()` trong `hmm.py` cho **cả hai tầng** dùng chung, và truyền
   duration mới vào. *Test:* `test_online_forest_input_row_matches_the_batch_regime_features` so
   toàn bộ cột regime của feature row thật (`record["forest_input"]`) với frame batch; mutation
   test xác nhận nó bắt đúng lỗi (270 vs 271).
   Bài học: phiên bản đầu của test tự gọi `_hmm_feature_row`, nên mutation vẫn pass — test phải
   assert trên giá trị mà production code *thực sự* dùng, không phải trên hàm gọi lại.

2. **Buffer ngắn hơn chuỗi batch đã fit làm lệch index.** `standardized_residuals` và
   `regime_probability_history` đều đánh chỉ số theo phiên và được nhân với nhau trong
   `simulate_paths`. Nếu `data.source` chứa ít phiên hơn dữ liệu `run-all` đã dùng thì hai mảng
   lệch nhau và chỉ vỡ ở bước Monte Carlo (`operands could not be broadcast (6306,) (6310,)`).
   *Sửa:* `build_online_state` kiểm tra độ dài buffer khớp với `handoff.volatility.features` và
   `handoff.hmm.probabilities`, không khớp thì từ chối kèm hướng dẫn chạy lại `run-all`.
   *Test:* `test_seeding_on_a_{shorter,longer}_history_than_the_batch_fit_is_refused` và
   `test_session_histories_stay_aligned_with_the_buffer_as_sessions_are_applied`.

Cả hai đều lọt qua bộ test đơn vị ban đầu — chúng chỉ xuất hiện khi chạy `run-all` thật rồi
`init-online-state` + `update-latest` trên artifact thật. Vì vậy quy trình xác minh của Phase 1
gồm cả một lần chạy end-to-end trong workspace cô lập, không chỉ `pytest -q`.

### Xác minh end-to-end trên dữ liệu thật (workspace cô lập, không đụng artifact của repo)

Batch chạy trên 6302 phiên đầu (`configs/quick.yaml`, `run_completed` 281.85 s, 70 hình, 50 bảng),
rồi trỏ `data.source` sang file đầy đủ để có 4 phiên mới thật:

```
init-online-state  → initialized, as_of=2026-07-07, buffer_rows=6302,
                     conformal_pool_size=2441, elapsed=5.0 s
update-latest  #1  → updated, sessions_applied=4, as_of=2026-07-13,
                     regime=Bull, center=+0.00917, sigma_h=0.03553, elapsed=17.1 s
update-latest  #2  → no_new_sessions, elapsed=0.17 s, mtime artifact không đổi
```

`latest_forecast.csv` giữ **đúng** header của tầng batch (đã khoá bằng
`BATCH_FORECAST_COLUMNS` trong `tests/test_online_cli.py`). Manifest ghim state vào
`last_data_date=2026-07-07` và `data_hash` của run batch.

Lưu ý hành vi đúng nhưng dễ hiểu nhầm: `conformal_pool_size` không tăng sau 4 phiên đầu, vì
`pending` khởi tạo rỗng — forecast do tầng online phát ra chỉ "chín" sau đúng `horizon` phiên.
Pool vẫn phủ đầy đủ validation+test tới ngày batch, nên không có khoảng trống calibration.

### Sửa thêm ngoài phạm vi hẹp (có lý do)

`cli.py` in kết quả JSON tiếng Việt bằng `print(..., ensure_ascii=False)`. Khi stdout được
redirect trên Windows (mặc định cp1252) lệnh **crash bằng `UnicodeEncodeError` sau khi đã chạy
xong** — cả `run-all` lẫn `update-latest`. Đây chính là cách triển khai mà prompt yêu cầu
(Task Scheduler/cron gọi CLI và ghi log), nên đã tách `emit_result()` ghi UTF-8 thẳng vào
`sys.stdout.buffer`, kèm `tests/test_cli_output.py`. Lỗi này có sẵn từ trước, không do Phase 1.
