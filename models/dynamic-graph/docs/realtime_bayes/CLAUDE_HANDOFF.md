# Bàn giao cho phiên Claude chạy trên PC — Dynamic Graph

Viết cho **agent**, không phải cho người dùng. Người dùng không biết chi tiết hạ tầng và đã nói
rõ là để bạn tự dò. Đừng hỏi họ những gì bạn tự tìm được.

## 1. Đọc trước, đừng khảo sát lại

- `docs/realtime_bayes/phase2_plan.md` — thiết kế, số đo, và **lý do** tầng online không dùng
  EWMA/NIW. Đừng thiết kế lại từ đầu.
- `docs/realtime_bayes/deploy_on_pc.md` — cách chạy.
- `docs/realtime_bayes/realtime-bayes-roadmap.md` — lộ trình 3 model.

Trạng thái: 325 test pass, ruff clean, **chưa commit gì**. Cả `main` của repo này lẫn RAFF đều
đang bằng `origin/main`; hãy tạo branch, đừng commit thẳng lên `main`.

## 2. Việc dò, kèm lệnh cụ thể

### 2.1 Đường dẫn database → `config/local.yaml`

```bash
cp config/local.example.yaml config/local.yaml
python -m dynamicgraph.cli discover-data
```

Lệnh này dò các định dạng được hỗ trợ và in đường dẫn tìm được. Điền vào `data.database_path`.
Nếu nó không tìm ra, tìm tay các đuôi `.dat`, `.sqlite`, `.duckdb`, `.parquet` hoặc thư mục CSV
theo mã, rồi kiểm chứng bằng `python -m dynamicgraph.cli audit-data --config config/local.yaml`.

**Đừng đoán schema.** `data/schema_inference.py` đã có sẵn để suy ra cột; nếu nó suy sai thì
đọc bảng thật rồi map tay, và ghi lại vào `local.yaml`.

### 2.2 Website đọc dữ liệu bằng cách nào — ĐÃ TRẢ LỜI

Không cần hỏi. `src/dynamicgraph/api/` là một FastAPI app:

```
uvicorn dynamicgraph.api.app:app --host 0.0.0.0 --port 8000
```

`ArtifactStore` trong `api/routes.py` phục vụ **file tĩnh dưới `artifacts/latest/`**:
`latest_dynamicgraph.json`, `nodes.json`, `edges.json`, `communities.json`,
`network_history.{json,csv}`, `stress_forecasts.csv`. Read-only by construction: không có đường
ghi, không kết nối DB, không cách nào kích hoạt training qua HTTP.

Cache của nó **keyed theo mtime**, nên ghi đè file là request kế tiếp đọc bản mới — **không cần
restart service**. Vì vậy đích của tầng online chính là ghi vào `artifacts/latest/`, không cần
đụng gì tới API.

Việc còn cần xác nhận trên PC: frontend gọi FastAPI này, hay đọc thẳng file, hay có bước copy/
deploy trung gian. Kiểm tra bằng cách tìm base URL trong code frontend, hoặc xem service nào
đang chạy (`Get-Process`, task/service list). Kết quả ảnh hưởng tới việc có cần bước đồng bộ
sau `update-latest` hay không.

## 3. Việc còn lại của Phase 2 (theo đúng thứ tự)

Mục tiêu: `update-latest` ghi được `artifacts/latest/` để website cập nhật theo phiên.

### Bước 1 — đóng băng model dự báo stress

`latest.build_stress_probabilities()` hiện gọi `fit_final_model()`, tức **refit mỗi lần publish**.
Tầng online không được phép.

- Thêm vào `BatchHandoff` (`online/handoff.py`) một dict `stress_models: dict[int, Any]`, mỗi
  horizon một `CalibratedModel` (có `.feature_names` và `.predict_proba`), kèm `feature_set` và
  dict chất lượng OOS mà `latest._model_quality()` trả về.
- Ghi chúng trong `pipeline._write_batch_handoff` (đã tồn tại, cuối `stage_network_metrics`) —
  nhưng model chỉ có sau `stage_predictive`, nên có thể phải ghi bổ sung ở giai đoạn sau.
- Cho `build_stress_probabilities` nhận tham số `frozen_models=None`; khi có thì dùng thay
  `fit_final_model`. Batch giữ nguyên hành vi cũ khi tham số là `None`.

### Bước 2 — cache/nối tiếp metric history

`stage_network_metrics` gọi `compute_metric_series` trên **toàn bộ** series (3526 snapshot core),
mỗi snapshot một lần `detect_communities` + `compute_graph_metrics`. Quá chậm cho một phiên.

Primitive đã có và **đã có gate tương đương**:

- `online/incremental.py::extend_snapshot_series` — nối tiếp snapshot series từ cache
  (đã nối vào `stage_graphs(resume=True)`);
- `online/session.py::advance_one_session` — metric row + stress row cho một phiên, so với
  snapshot liền trước.

Làm tương tự cho `metrics_by_key`: lưu ra `artifacts/metrics/graph_metrics_<key>.csv` (đã lưu
sẵn rồi) và đọc lại, chỉ tính phần đuôi thiếu.

### Bước 3 — publish

Xong hai bước trên thì `update_latest_online` chỉ cần chạy các stage với `resume=True` rồi gọi
`generate_latest(state)` **sẵn có**. Không viết đường publish song song — toàn bộ payload
website do code đã được test sinh ra.

Khóa schema bằng test giống RAFF đã làm (`BATCH_FORECAST_COLUMNS` trong
`RAFF/.../tests/test_online_cli.py`).

## 4. Ràng buộc không được phá

1. **Không refit gì ở tầng online.** Không `fit_final_model`, không `select_alpha`, không fit lại
   `DescriptiveStressScore`.
2. **Ba gate tương đương phải luôn xanh** (`tests/test_online_session.py`): snapshot khớp
   `build_snapshot` kể cả `stability`; metric row khớp `compute_metric_series`; stress score khớp
   `transform` kể cả `stress_percentile` (expanding rank).
3. **Không âm thầm vá dữ liệu.** Phiên bất thường hoặc lịch sử bị sửa → dừng và báo.
4. **DB read-only tuyệt đối.**
5. `pytest -q` phải pass hết, ruff clean.
6. Khi sửa test, **mutation-check**: cố ý làm hỏng code và xác nhận test fail. Trong dự án này
   cách làm đó đã bắt được hai bug thật mà unit test ban đầu bỏ lọt.

## 5. Đo lại trên PC (số của laptop có thể không đúng)

```bash
python -m dynamicgraph.cli update-latest --config config/local.yaml
```

Ghi lại `elapsed_seconds` và `number_of_nodes`. Trên laptop, `build_snapshot` với
`bootstrap_iterations=100` mất 1.2 s (13 nodes) đến 4.4 s (30 nodes), và `n_jobs=-1` **chậm hơn
3.5×** so với `n_jobs=1`. `config/full.yaml` đang đặt `n_jobs: -1` — đo lại trước khi dùng.
