# RAFF — chạy tầng real-time trên PC

Trạng thái: **Phase 1 hoàn chỉnh.** 107 test pass, 0 warning, đã verify end-to-end trên
6306 phiên thật (2000-07-28 → 2026-07-13), **4.15 s/phiên**.

Thiết kế và số đo: [`phase1_plan.md`](phase1_plan.md). Yêu cầu gốc: [`phase1_raff_prompt.md`](phase1_raff_prompt.md).

---

## 0. Checklist trước khi chạy

- [ ] Python ≥ 3.10, cài được `arch` và `hmmlearn`
- [ ] `pytest -q` ra 107 passed
- [ ] Biết engine + tên bảng + tên cột OHLCV của DB trên PC
- [ ] Đã điền `data.source` trong `configs/default.yaml`
- [ ] Chạy `run-all` xong ít nhất một lần

---

## 1. Môi trường

```bash
cd RARF-FHE-Regime-Aware-Random-Forest-Forecasting-Hybrid-Engine
python -m pip install -e .
python -m pytest -q
```

Kỳ vọng: `107 passed`, không warning.

**Cạm bẫy đã gặp:** nếu trên PC có nhiều Python, `python` trên PATH có thể là venv của repo khác
và thiếu `arch`/`hmmlearn`. Kiểm tra bằng:

```bash
python -c "import arch, hmmlearn; print('ok')"
```

Nếu lỗi `ModuleNotFoundError`, gọi thẳng interpreter đúng thay vì dựa vào PATH.

Makefile giả định môi trường conda tên `eda` (`PYTHON := conda run -n eda python`). Nếu PC không
có env đó thì gọi trực tiếp `python -m vnindex_model.cli ...`, đừng dùng `make`.

---

## 2. Cấu hình nguồn dữ liệu

Sửa khối `data.source` trong `configs/default.yaml`:

```yaml
data:
  source:
    backend: csv          # csv | sqlite | duckdb
    path: data/raw/VNINDEX_Daily.csv
    table: null           # BẮT BUỘC khi backend là sqlite/duckdb
    column_map: {}        # map tên cột thật -> tên chuẩn
    date_unit: null       # "D" nếu ngày lưu dạng số nguyên epoch-day
```

### Nếu DB là SQLite / DuckDB

```yaml
data:
  source:
    backend: sqlite
    path: "C:/DataPro/D.dat"
    table: HIST
    column_map:
      date:   TRADINGDATE
      open:   OPENPRICE
      high:   HIGHPRICE
      low:    LOWPRICE
      close:  CLOSEPRICE
      volume: TOTALMATCHVOL
    date_unit: D
```

`column_map` chỉ cần liệt kê những cột có **tên khác** tên chuẩn. Cột nào trùng tên thì bỏ qua.

Kiểm tra nhanh trước khi chạy pipeline:

```bash
python -c "
import sys; sys.path.insert(0,'src')
from vnindex_model.data_source import build_market_data_source
s = build_market_data_source({'backend':'sqlite','path':'C:/DataPro/D.dat','table':'HIST',
                              'column_map':{'date':'TRADINGDATE','close':'CLOSEPRICE'},
                              'date_unit':'D'})
print('phiên gần nhất:', s.latest_date())
print(s.fetch_since(None, 5).tail())
s.close()"
```

### Nếu DB là Postgres / MySQL

**Chưa có driver** — cố tình không đoán schema. Interface `MarketDataSource` trong
`src/vnindex_model/data_source.py` chỉ cần hai method (`latest_date`, `fetch_since`), thêm một
driver là khoảng 40 dòng. Cần: engine, connection string, tên bảng, tên cột OHLCV.

### Đảm bảo read-only

Không có đường nào ghi vào DB nguồn:

- SQLite mở bằng URI `?mode=ro` **cộng** `set_authorizer` từ chối mọi opcode không phải
  SELECT/READ/FUNCTION/PRAGMA/TRANSACTION/RECURSIVE;
- DuckDB mở bằng `read_only=True`;
- CSV chỉ gọi API đọc.

Có test chứng minh (`tests/test_data_source.py`): thử `DELETE` phải ném `ReadOnlyViolation`, và
số dòng trong DB sau đó không đổi.

---

## 3. Chạy

```bash
# 1) tầng batch — chậm, chu kỳ dài (ví dụ hàng tuần)
python -m vnindex_model.cli run-all --config configs/default.yaml

# 2) seed tầng online — chạy NGAY SAU mỗi lần run-all
python -m vnindex_model.cli init-online-state --config configs/default.yaml

# 3) mỗi phiên mới
python -m vnindex_model.cli update-latest --config configs/default.yaml
```

**Thứ tự bắt buộc.** Mỗi lần `run-all` ghi handoff mới và **reset** tầng online, nên phải
`init-online-state` lại. Nếu quên, `update-latest` vẫn chạy trên state cũ và bạn sẽ dùng model cũ
mà không biết — manifest có `source_run_metadata` để đối chiếu.

### Kết quả trả về

`init-online-state`:

```json
{"status": "initialized", "as_of_date": "2026-07-07", "buffer_rows": 6302,
 "conformal_pool_size": 2441, "elapsed_seconds": 5.0}
```

`update-latest` khi có phiên mới:

```json
{"status": "updated", "sessions_applied": 4, "as_of_date": "2026-07-13",
 "center": 0.00917, "sigma_horizon": 0.03553, "regime_label": "Bull",
 "conformal_pool_size": 2441, "elapsed_seconds": 17.1}
```

`update-latest` khi không có phiên mới (**idempotent** — không ghi gì):

```json
{"status": "no_new_sessions", "as_of_date": "2026-07-13", "elapsed_seconds": 0.17}
```

---

## 4. Artifact cho website

`update-latest` ghi lại **đúng schema** của tầng batch, downstream không phải sửa:

| File | Ghi chú |
| --- | --- |
| `artifacts/forecasts/latest_forecast.csv` | Header giống hệt bản batch — đã khóa bằng test `BATCH_FORECAST_COLUMNS` |
| `artifacts/forecasts/latest_forecast_summary.json` | Thêm `update_mode: "online"` và `source_run_metadata` |
| `artifacts/forecasts/latest_monte_carlo_samples.npz` | price/return paths, terminal prices, max drawdowns |

`latest_drawdown_*` **không bị đụng tới**. Tầng drawdown mặc định tắt và là một tầng riêng nặng;
ghi bản một phần đè lên payload tốt của batch sẽ tệ hơn là để nguyên. Nếu website đang đọc các
file drawdown, chúng vẫn là của lần `run-all` gần nhất.

`latest_forecast_summary.json` của tầng online **không có** các khối chỉ batch mới tính được:
`importance_sampling`, `model_uncertainty` (seed stability), và khối drawdown. Đây là cố ý —
bịa số cho chúng còn tệ hơn thiếu. Trường `update_note` ghi rõ điều này.

---

## 5. Khi nào lệnh dừng và báo lỗi

Repo này không bao giờ tự vá dữ liệu. `update-latest` dừng khi:

| Tình huống | Thông báo |
| --- | --- |
| Phiên mới thiếu giá trị OHLCV | `thiếu giá trị: [...]` |
| Giá ≤ 0 | `có giá <= 0: [...]` |
| Vi phạm ràng buộc OHLC | `vi phạm ràng buộc OHLC` |
| Calendar gap > 10 ngày | `Calendar gap N ngày ... vượt ngưỡng` |
| Giá đóng cửa lịch sử trong DB đã bị sửa | `Giá đóng cửa lịch sử ... đã bị sửa so với buffer` |
| Online state bị sửa tay | `Buffer checksum ... không khớp manifest` |
| Chưa chạy `init-online-state` | `Chưa có online state tại ...` |

Ba trường hợp cuối yêu cầu chạy lại `run-all` + `init-online-state`, **không** tự động ghi đè.

Nếu máy tắt vài hôm, `update-latest` replay **tuần tự từng phiên** chứ không nhảy cóc — forward
filter của HMM và recursion của EGARCH chỉ đúng khi áp dụng đúng thứ tự.

---

## 6. Lập lịch (Windows Task Scheduler)

Không có scheduler trong Python — đúng triết lý sẵn có của repo. Tạo `update_raff.bat`:

```bat
@echo off
cd /d "C:\đường\dẫn\tới\RARF-FHE-Regime-Aware-Random-Forest-Forecasting-Hybrid-Engine"
if not exist logs mkdir logs
python -m vnindex_model.cli update-latest --config configs/default.yaml >> logs\update.log 2>&1
```

Task Scheduler → Create Task → Trigger: Daily, 16:00, chỉ ngày trong tuần → Action: chạy file
`.bat` trên. Không cần chạy với quyền admin.

Redirect stdout ra file đã an toàn: CLI ghi UTF-8 thẳng vào `sys.stdout.buffer`, nên chuỗi tiếng
Việt không còn làm lệnh crash bằng `UnicodeEncodeError` sau khi đã chạy xong.

---

## 7. Chu kỳ vận hành đề xuất

| Việc | Tần suất | Lệnh |
| --- | --- | --- |
| Cập nhật theo phiên | mỗi ngày giao dịch | `update-latest` |
| Refit toàn bộ | hàng tuần (cuối tuần) | `run-all` rồi `init-online-state` |

Sau mỗi `run-all`, đối chiếu `artifacts/online_state/online_state_manifest.json`:
`source_run_metadata.last_data_date` phải là ngày cuối của lần batch vừa chạy.

---

## 8. Thứ nên và không nên đưa vào git

`.gitignore` đã có `artifacts/online_state/*.joblib` — state được ghi lại mỗi phiên và nặng vài
MB, không thuộc về lịch sử git. Manifest JSON và `online_sessions.csv` vẫn được track vì chúng là
bản ghi kiểm toán và rất nhẹ.
