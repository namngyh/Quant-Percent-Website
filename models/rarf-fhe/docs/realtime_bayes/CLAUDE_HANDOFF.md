# Bàn giao cho phiên Claude chạy trên PC — RAFF

Viết cho **agent**, không phải cho người dùng. Người dùng không biết chi tiết hạ tầng và đã nói
rõ là để bạn tự dò. Đừng hỏi họ những gì bạn tự tìm được.

## 1. Trạng thái

Phase 1 **hoàn chỉnh**: 115 test pass, 0 warning, ruff clean. Đã verify end-to-end trên 6306
phiên thật, 4.15 s/phiên. **Chưa commit gì**; `main` đang bằng `origin/main` nên hãy tạo branch.

Đọc trước, đừng khảo sát lại:

- `docs/realtime_bayes/phase1_plan.md` — thiết kế, số đo, các sai lệch có chủ ý so với prompt gốc,
  và **hai bug chỉ lộ ra khi chạy end-to-end** (đã sửa, đã có test).
- `docs/realtime_bayes/deploy_on_pc.md` — cách chạy.
- `docs/realtime_bayes/phase1_raff_prompt.md` — yêu cầu gốc.

## 2. Việc duy nhất còn phải dò: nguồn dữ liệu thật

Đã có sẵn công cụ, không cần hỏi ai:

```bash
python -m vnindex_model.cli discover-source "C:/đường/dẫn/tới/store"
```

Nó mở nguồn **read-only**, liệt kê mọi bảng và cột, map tên cột về `date/open/high/low/close/
volume` bằng đúng bảng alias mà parser CSV đang dùng, đoán `date_unit` (phát hiện số nguyên
epoch-day), rồi in ra một khối `data.source` **dán thẳng được** vào `configs/default.yaml`.

Nếu chưa biết store nằm đâu, tìm các đuôi `.dat` (vendor SQLite hay dùng), `.sqlite`, `.duckdb`,
`.parquet`, `.csv`. `discover-source` sniff header nên nhận ra SQLite kể cả khi đuôi lạ.

Sau khi dán config, kiểm chứng **trước** khi chạy pipeline:

```bash
python -m vnindex_model.cli validate-data --config configs/default.yaml
```

### Nếu store là Postgres hoặc MySQL

Chưa có driver — cố tình không đoán schema. Thêm một class vào
`src/vnindex_model/data_source.py` theo đúng protocol `MarketDataSource`, chỉ cần hai method:

```python
def latest_date(self) -> pd.Timestamp: ...
def fetch_since(self, since, lookback_buffer_days) -> pd.DataFrame: ...
```

Dùng lại `_normalize()` và `_slice_since()` đã có, đăng ký backend mới trong
`build_market_data_source()`. Bắt buộc mở connection ở chế độ read-only (Postgres:
`default_transaction_read_only=on` hoặc user chỉ có quyền SELECT). Viết test theo mẫu
`tests/test_data_source.py::test_sqlite_source_refuses_to_write_to_the_source_database`.

## 3. Chạy

```bash
python -m vnindex_model.cli run-all           --config configs/default.yaml
python -m vnindex_model.cli init-online-state --config configs/default.yaml
python -m vnindex_model.cli update-latest     --config configs/default.yaml
```

Thứ tự bắt buộc: mỗi `run-all` reset tầng online.

## 4. Website

`update-latest` ghi `artifacts/forecasts/latest_forecast.csv`, `latest_forecast_summary.json`,
`latest_monte_carlo_samples.npz` với **đúng schema** của tầng batch (header đã khóa bằng test
`BATCH_FORECAST_COLUMNS` trong `tests/test_online_cli.py`), nên downstream không phải sửa.

Cần xác nhận trên PC: website đọc các file này trực tiếp, hay qua một service/bước copy. Nếu
Dynamic Graph là hình mẫu thì nó dùng FastAPI phục vụ file tĩnh với cache theo mtime — RAFF chưa
có API tương đương, nên nhiều khả năng website đọc file trực tiếp hoặc có bước đồng bộ riêng.
Tìm base URL trong code frontend hoặc xem service đang chạy để biết chắc.

`latest_drawdown_*` **không** bị tầng online đụng tới (tầng drawdown mặc định tắt); chúng vẫn là
của lần `run-all` gần nhất.

## 5. Ràng buộc không được phá

1. Không refit gì ở tầng online: không Baum-Welch, không MLE EGARCH, không train RF, không chọn
   lại conformal method.
2. Gate tương đương batch↔online phải luôn xanh: HMM `atol=1e-10`, EGARCH `1e-10`, feature row
   của forest khớp `regime_feature_frame` và `build_features`.
3. Không âm thầm vá dữ liệu. Phiên bất thường hoặc lịch sử bị sửa → dừng và báo.
4. DB read-only tuyệt đối.
5. `pytest -q` pass hết, **0 warning**, ruff clean.
6. Khi sửa test, **mutation-check**: cố ý làm hỏng code và xác nhận test fail. Cách này đã bắt
   được hai bug thật ở dự án này mà unit test ban đầu bỏ lọt (`hmm_state_duration` lệch 1 phiên;
   buffer lệch độ dài với chuỗi batch làm `simulate_paths` vỡ).

## 6. Nếu cần làm tiếp toàn hệ thống

Phase 2 (Dynamic Graph) chưa xong phần publish; Phase 3 (MSDP) chưa bắt đầu. Xem
`docs/realtime_bayes/realtime-bayes-roadmap.md` và handoff tương ứng trong hai repo kia.
