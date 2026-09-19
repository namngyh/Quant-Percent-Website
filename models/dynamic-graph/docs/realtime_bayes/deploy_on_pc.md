# Dynamic Graph — chạy tầng real-time trên PC

Trạng thái: **Phase 2 chưa hoàn tất.** Tầng online cập nhật được state và trả về số liệu mạng,
nhưng **chưa ghi `artifacts/latest/`**, tức website vẫn phải lấy dữ liệu từ `generate-latest`
của tầng batch. Đọc mục 6 trước khi thử nối website.

325 test pass, ruff clean. Thiết kế, số đo và ba gate tương đương: [`phase2_plan.md`](phase2_plan.md).

---

## 0. Checklist trước khi chạy

- [ ] `.venv` hoặc env có đủ dependency (`networkx`, `pydantic`, `typer`, `duckdb`, `igraph`…)
- [ ] `pytest -q` ra 325 passed
- [ ] Đã tạo `config/local.yaml` và điền `data.database_path`
- [ ] `discover-data` nhìn thấy đúng DB
- [ ] Chạy `run-all` xong ít nhất một lần (nó ghi batch handoff)

---

## 1. Môi trường

```bash
cd "Dynamic Graph"
python -m pip install -e ".[db,community]"
python -m pytest -q
```

Kỳ vọng: `325 passed`.

Repo này có `.venv` riêng trên laptop. Trên PC nên tạo env riêng cho nó — dependency của nó
(`networkx`, `typer`, `pydantic`, `igraph`, `leidenalg`) gần như rời hẳn với RAFF (`arch`,
`hmmlearn`) và MSDP (`torch`, `optuna`). Dùng chung một env là cách nhanh nhất để gặp xung đột.

---

## 2. Cấu hình nguồn dữ liệu

`config/local.yaml` nằm trong `.gitignore` nên **không** đi theo git — phải tạo trên PC:

```bash
cp config/local.example.yaml config/local.yaml
python -m dynamicgraph.cli discover-data
```

`discover-data` dò các định dạng được hỗ trợ và in ra đường dẫn tìm được. Điền vào:

```yaml
extends: default.yaml

data:
  database_path: "C:/DataPro/D.dat"   # SQLite | DuckDB | parquet | thư mục CSV
  backend: auto                       # auto sniff; đặt tay nếu dò sai
  index_source_symbol: null           # ghim mã chỉ số nếu tên trong DB khác thường
  start_date: null
  end_date: null

output:
  artifacts_dir: artifacts
```

Connector đã read-only sẵn (`src/dynamicgraph/data/connectors.py`): SQLite mở `?mode=ro` cộng
authorizer chặn ghi, DuckDB mở `read_only=True`. Tầng online dùng lại đúng các connector này qua
`stage_data`, không mở thêm kết nối nào.

**Lưu ý về dữ liệu:** Dynamic Graph dựng đồ thị **giữa ~30 mã VN30**, nên nó cần panel giá từng
mã. `VNINDEX_Daily.csv` (một chuỗi chỉ số) **không dùng làm nguồn node được** — nó chỉ đóng vai
trò market factor cho residualization. `config/vn30_universe.csv` chỉ là danh sách mã, không phải
giá.

---

## 3. Chạy

```bash
python -m dynamicgraph.cli run-all            --config config/local.yaml
python -m dynamicgraph.cli init-online-state  --config config/local.yaml
python -m dynamicgraph.cli update-latest      --config config/local.yaml
```

Thứ tự bắt buộc như RAFF: mỗi `run-all` ghi handoff mới và reset tầng online.

`update-latest` trả về:

```json
{"status": "updated", "sessions_applied": 1, "as_of_date": "2026-07-24",
 "graph_density": 0.21, "number_of_nodes": 28,
 "stress_score": 43.2, "stress_percentile": 0.61,
 "artifacts": ["...online_state.joblib", "...manifest.json", "...online_sessions.csv"],
 "elapsed_seconds": 6.4}
```

Không có phiên mới → `{"status": "no_new_sessions"}`, không ghi gì (idempotent).

---

## 4. Tầng online làm gì và không làm gì

| Thành phần | Online | Vẫn ở batch |
| --- | --- | --- |
| Snapshot đồ thị | dựng **1** snapshot cho phiên mới, bằng chính `build_snapshot` của batch, `alpha` đã khóa | chọn `alpha` (CV/stability trên training windows) |
| Graph metrics, communities | tính cho phiên mới, so với snapshot liền trước | — |
| Descriptive stress score | `transform` từ model đã fit trên train | fit median/MAD, chọn metric, prune redundancy |
| Model dự báo stress | *(chưa nối — xem mục 6)* | `walk_forward`, `fit_final_model` |
| Figures, reports, allocation | — | toàn bộ |

**Ba gate tương đương batch↔online**, cả ba đều mutation-check:

1. snapshot online khớp `build_snapshot` cùng ngày, kể cả `stability` bootstrap;
2. metric row khớp `compute_metric_series`;
3. stress score khớp `DescriptiveStressScore.transform`, kể cả `stress_percentile`
   (expanding rank) và `stress_change_20d`.

---

## 5. Tăng tốc tầng batch: nối tiếp snapshot từ cache

`stage_graphs` vẫn lưu series ra `artifacts/graphs/` nhưng trước đây **không bao giờ đọc lại** —
mỗi lần chạy dựng lại toàn bộ (3526 snapshot core trên dữ liệu thật). Nay có
`stage_graphs(..., resume=True)`: dùng lại snapshot đã lưu, chỉ dựng phần đuôi còn thiếu.

Cache chỉ được tin khi **cả hai** điều kiện đúng:

- build config giống hệt (layer/window/return_type/alpha/estimator/filter), và
- snapshot cuối của cache **tái tạo lại được** từ dữ liệu hiện tại.

Sai một trong hai → vứt cache, dựng lại toàn bộ. Lịch sử bị sửa upstream sẽ bị bắt ở điều kiện
thứ hai thay vì được nối vào phiên mới.

### Số đo trên laptop này (cửa sổ 60 phiên)

| | thời gian |
| --- | --- |
| Ledoit-Wolf covariance, 30 nodes | 0.41 ms |
| `build_snapshot`, `bootstrap_iterations=0` | 17 ms |
| `build_snapshot`, `bootstrap_iterations=100`, 13 nodes | 1.2 s |
| `build_snapshot`, `bootstrap_iterations=100`, 30 nodes | **4.4 s** |
| như trên, `n_jobs=-1` | **15.7 s** (chậm hơn 3.5×) |

Hai điều rút ra:

1. Ước lượng covariance chỉ chiếm ~0.01% chi phí; ~99.8% nằm ở 100 vòng bootstrap
   graphical-lasso. Vì vậy tầng online **không** thay estimator bằng EWMA/NIW — làm vậy chỉ tiết
   kiệm 0.4 ms mà lại khiến graph online khác graph batch (train/serve skew).
2. `n_jobs=-1` **chậm hơn** `n_jobs=1` cho bài toán 30×30 vì joblib overhead áp đảo.
   `config/default.yaml` đã đặt `n_jobs: 1`; `config/full.yaml` đang đặt `-1` — nên đo lại trên
   PC trước khi dùng `full.yaml`.

---

## 6. ⚠️ Vì sao website chưa cập nhật theo phiên

`latest.build_stress_probabilities()` gọi `fit_final_model()` — tức **refit** model dự báo stress
mỗi lần sinh latest. Tầng online không được phép làm vậy, nên hiện `update-latest` **không** ghi
`artifacts/latest/`. Ghi một payload thiếu đè lên payload tốt của batch còn tệ hơn là không ghi.

**Website hiện vẫn phải đọc kết quả của `generate-latest` (tầng batch).**

Để website chạy theo phiên cần làm nốt hai việc:

1. **Đóng băng model dự báo stress** — lưu một `CalibratedModel` cho mỗi horizon (kèm
   `feature_names` và metadata chất lượng OOS) vào `BatchHandoff`, rồi cho
   `build_stress_probabilities` nhận model đóng băng thay vì `fit_final_model`.
2. **Cache/nối tiếp `metrics_by_key`** giống như đã làm với snapshot series, để `stage_network`
   không phải tính lại metric + community cho toàn bộ 3526 snapshot mỗi lần.

Primitive cho cả hai đã có và đã có gate tương đương:
`online/incremental.py::extend_snapshot_series` (graph) và
`online/session.py::advance_one_session` (metric row + stress row).

Xong hai việc đó thì `update-latest` chỉ cần gọi lại `generate_latest(state)` sẵn có — toàn bộ
payload website (`latest_dynamicgraph.json`, `nodes.json`, `edges.json`, `communities.json`,
`graph_metrics.csv`, `network_history.csv`, `stress_forecasts.csv`) do code đã được test sinh ra,
không cần viết đường publish song song.

---

## 7. Lập lịch

```bat
@echo off
cd /d "C:\đường\dẫn\tới\Dynamic Graph"
if not exist logs mkdir logs
python -m dynamicgraph.cli update-latest --config config/local.yaml >> logs\update.log 2>&1
```

CLI ghi stdout bằng UTF-8 trực tiếp nên redirect ra file trên Windows (cp1252) không gây
`UnicodeEncodeError`.

---

## 8. Giới hạn của phần đã verify

Laptop này không có `config/local.yaml` và không có panel giá VN30, nên **toàn bộ verify chạy
trên synthetic panel** của test suite (12 mã, cấu trúc nhân tố đã biết). Khác với RAFF — nơi đã
chạy được `run-all` thật trên 6306 phiên — Phase 2 **chưa có bước xác minh end-to-end trên dữ
liệu thật**. Việc đầu tiên nên làm trên PC là:

```bash
python -m dynamicgraph.cli run-all           --config config/local.yaml
python -m dynamicgraph.cli init-online-state --config config/local.yaml
python -m dynamicgraph.cli update-latest     --config config/local.yaml
```

và báo lại `elapsed_seconds` của `update-latest` cùng `number_of_nodes` — hai con số đó cho biết
ngân sách thời gian thật và kích thước đồ thị thật.
