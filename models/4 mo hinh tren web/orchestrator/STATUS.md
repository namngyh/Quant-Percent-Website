# Trạng thái 4 mô hình — cập nhật 2026-08-26

Thay cho `docs/realtime_bayes/OVERVIEW-3-models.md` (viết cho 3 mô hình, trước khi có connector
database).

## Trả lời ngắn

Cả 4 mô hình **đã đọc được dữ liệu real-time từ database**. Trước đó không mô hình nào làm được:
database là PostgreSQL/TimescaleDB, còn cả bốn chỉ có connector cho file (CSV / SQLite / DuckDB /
Parquet).

| Mô hình | Nối DB | Tầng online | Publish | Còn thiếu |
|---|---|---|---|---|
| **RAFF** (VN-Index) | ✅ postgres + `sync-source` | ✅ có sẵn | ✅ `artifacts/forecasts/` | — |
| **Dynamic Graph** (VN30) | ✅ postgres, đọc thẳng | ✅ có sẵn | ✅ `artifacts/latest/` (mới) | universe file lệch rổ VN30 hiện tại |
| **MSDP** (VN-Index) | ✅ postgres + `sync_source.py` | ✅ Hedge + CLI (mới) | ✅ `artifacts/predictions/` | ACI chưa nối; thiếu `evaluation_model.pt` |
| **Tempus-VIN** | ✅ postgres, đọc thẳng | ✅ save/load + CLI (mới) | ✅ `artifacts/forecasts/` | fit đầy đủ chưa chạy lại |

## Nguồn dữ liệu

TimescaleDB tại `10.10.0.1:5432/market`, bảng `bars_1d`: 389 mã, 2000-07-28 → hiện tại,
gồm `VNINDEX` (6 338 phiên), `VN30INDEX` và rổ VN30. Read-only ép ở phía server bằng
`default_transaction_read_only=on`.

**Container `qp-timescaledb` trên ổ D không còn là DB sống** — dữ liệu dừng ở 2026-08-12.
`docker-compose.override.yml` đã trỏ ingestion sang `10.10.0.1`.

## Những gì đã làm

### Chung cả 4 repo

- Connector Postgres read-only, identifier đi qua `psycopg.sql.Identifier`, symbol là bound
  parameter.
- DSN nằm trong `.env` của từng repo (đã gitignore), có fallback đọc `.env` khi Task Scheduler
  chạy với môi trường trống.
- Test read-only chạy trên **server thật**, không mock: mock chỉ chứng minh mock biết từ chối.

### RAFF

`sync-source` xuất snapshot từ DB ra `data/raw/VNINDEX_Daily_db.csv` rồi tầng batch vẫn hash một
file như cũ — `run_metadata` giữ nguyên hợp đồng tái lập. Lệnh này báo riêng "thêm phiên mới" và
"lịch sử bị sửa"; cái sau làm hỏng online state nên phải nổi lên chứ không được nuốt.

### Dynamic Graph

Connector đọc thẳng, không qua file. Công thức điều chỉnh giá đã **kiểm chứng chứ không đoán**:
`bars_1d.adj_rate` là **số chia** tích lũy (giá trị mới nhất = 1), ngược hẳn với `ADJUST_RATE`
nhân 1e6 của DataPro SQLite. Trên 375 sự kiện quyền của 35 mã từ 2015, đẳng thức
`(ref_px/close_hôm_trước) × (adj_rate_trước/adj_rate_nay) = 1` có trung vị 1.000000 và 364/375
nằm trong 1%. Công thức nhân sai lệch ~9% trung vị.

**Phase 2 đã đóng**: `latest.build_stress_probabilities` trước đây gọi `fit_final_model` mỗi lần
sinh latest, nên tầng online không được phép ghi `artifacts/latest/`. Nay tách thành
`fit_stress_models` (batch) và `predict_stress_probabilities` (dùng chung), model đóng băng vào
batch handoff, tầng online chấm điểm và ghi lại `artifacts/latest/` bằng **đúng** hàm
`build_website_payload` / `write_website_outputs` của tầng batch.

### MSDP

`gate_override=posterior` đã nối vào `predict_latest_ensemble`; mạng chạy 2 lần mỗi seed vì
posterior cần prior của **chính seed đó**. Thêm `scripts/sync_source.py`,
`scripts/init_online_state.py`, `scripts/update_latest.py`.

Đã chạy thật: init tại 2026-05-06 → update tại 2026-07-01 → update tại 2026-08-26 cho
`matured_forecasts: 2`, `hedge_rounds: [1, 1, 0]` — gate posterior thực sự học từ kết quả đã đáo hạn.

### Tempus-VIN

Ba mảnh model card mục 4.8 nói là chưa tồn tại, nay đã có:

- `persistence.py` — lưu/tải posterior biến phân, kèm fingerprint dữ liệu; lịch sử bị sửa thì
  **từ chối** dự báo tiếp thay vì dự báo trên posterior đã lỗi thời.
- `cli.py` — `discover-source` / `fit` / `predict`.
- `data/source.py` — đọc thẳng DB, đi qua **đúng** tầng validate của đường CSV.

Đo thật: `predict` từ bundle đã lưu mất **6,8 giây** (model card ghi "tối thiểu ~9 phút" vì không
tách được fit khỏi predict).

## Bug thật đã tìm và sửa

**Volume của Tempus sai gấp 10–1000 lần trên 3879/6264 phiên.** Đối chiếu DB với CSV cho thấy giá
khớp tới số cuối cùng nhưng volume lệch theo bội số tròn. Nguyên nhân: file export tách số hàng
nghìn ra nhiều trường và **bỏ số 0 đầu** của mỗi nhóm — `538,080,668` thành `("538","80","640")`.
`_reconstruct_number_fields` pad zero cho 4 trường giá nhưng nối volume bằng `"".join(...)`, ra
`53_880_640`: đúng một phần mười, vẫn là con số hợp lý nên không kiểm tra nào phía sau bắt được.
Sau khi sửa, sai lệch tương đối lớn nhất còn `5,96e-08` — đúng epsilon float32 của file gốc.

**RAFF: `run-all` crash ở [`importance_sampling.py`](../RARF-FHE-Regime-Aware-Random-Forest-Forecasting-Hybrid-Engine/src/vnindex_model/importance_sampling.py).**
`np.asarray` **không copy** mảng đã là float64, nên `probability /= probability.sum()` ghi đè
regime posterior của chính caller — và raise `ValueError: output array is read-only` khi mảng đó
read-only (numpy 2.4). Sửa bằng `np.array` (luôn copy) + 3 test regression.

**Dynamic Graph: log tiếng Việt làm ngập log Task Scheduler.** Stdout đã redirect mặc định là
cp1252 trên Windows, nên mỗi dòng log có dấu tiếng Việt raise `UnicodeEncodeError` bên trong
handler. Logging nuốt lỗi nên chương trình vẫn chạy, nhưng in ra một traceback đầy đủ mỗi lần —
một lần chạy pipeline sinh **181+** traceback như vậy, đủ để chôn vùi log thật. Đã ép UTF-8 trong
`setup_logging`.

Hai lỗi nhỏ hơn: rò rỉ sqlite3 connection trong test RAFF (chỉ lộ dưới `-W error` khi có thêm
test chạy trước), và rò rỉ psycopg connection khi `PostgresConnector.__init__` validate thất bại.

## Đã chạy thật, không chỉ test

**RAFF — nguyên chu kỳ tuần trên database sống:**

```
run-all (dữ liệu cắt tới 2026-07-01)  →  init-online-state  as_of=2026-07-01, 16,6 s
sync-source                            →  rows_added: 40, history_rewritten: false
update-latest                          →  sessions_applied: 40, as_of=2026-08-26
```

40 phiên mất 492 s (**12,3 s/phiên**; tài liệu bàn giao ghi 4,15 s/phiên đo trên cấu hình khác).
Ghi ra `latest_forecast.csv` + `latest_forecast_summary.json` + `latest_monte_carlo_samples.npz`,
spot 1821,32 khớp database, regime `Bear`.

**MSDP — vòng online trên database sống:** init 2026-05-06 → update 2026-07-01 → update
2026-08-26 cho `matured_forecasts: 2`, `hedge_rounds: [1, 1, 0]`, ~1,5 s/phiên.

**Tempus — tách fit khỏi predict:** fit 32 s (400 phiên, cấu hình tối giản) → `predict` **6,8 s**
từ bundle đã lưu.

**Dynamic Graph — `audit-data`:** 112 592 dòng, 31 mã, 2012-02-06 .. 2026-08-26, 0 lỗi.

## Test

| Repo | Kết quả |
|---|---|
| RAFF | **154 passed**, 0 failed, `-W error`, ruff sạch (baseline 115) |
| Dynamic Graph | **369 passed**, 0 failed, 0 skipped, `-W error`, ruff sạch (baseline 325) |
| MSDP | **78 passed, 2 failed** — đúng 2 lỗi có sẵn, không hồi quy (baseline 31/2) |
| Tempus-VIN | **201 passed** (không tính 4 integration smoke chạy 15–90 phút), ruff sạch |

Artifact nghiên cứu của RAFF (run `configs/experimental.yaml` ngày 2026-07-15) đã được **khôi
phục** sau khi verify: các lần `run-all` ở trên dùng `configs/quick.yaml` nên không được để ghi
đè lên kết quả thật.

## Còn lại, theo thứ tự ưu tiên

1. **Website đang publish MSDP từ một bản `quick`.** `D:\Quant-Percent-Website\models\msdp\`
   dùng `run_id: 20260720_161451_quick`, **1 seed**, `configs/quick.yaml` — chính log hằng ngày
   in ra cảnh báo "Re-run MSDP with the full config before publishing these numbers". Repo dev có
   sẵn bản GPU 3 seed `20260722_154609_gpu`. Đây là thay đổi trên hệ thống đang chạy thật nên tôi
   không tự làm.
2. **`evaluation_model.pt` của MSDP không có trên máy này** — 2 test đỏ vì thiếu file, không phải
   vì code.
3. **`config/vn30_universe.csv` của Dynamic Graph lệch rổ hiện tại**: file có BCM, BVH (không có
   trong DB); rổ từ 03/08/2026 bỏ TPB, PLX, thêm MCH, TCX. Hiện chạy 31 mã.
4. **ACI của MSDP chưa nối**: khoảng tin cậy vẫn từ `StaticCQRCalibrator`. Cần tầng batch lưu lại
   pool conformity score của tập calibration thì mới seed được `AdaptiveConformalCalibrator`.
5. **Tempus chưa fit lại đầy đủ trên dữ liệu mới** — đường fit/predict đã chứng minh chạy được,
   nhưng bundle nghiên cứu quy mô đầy đủ (8 seed, ~9,5 giờ) chưa chạy lại.
6. **sklearn 1.9.0 vs 1.8.0**: scaler của MSDP được pickle bằng bản khác với môi trường hiện tại,
   sinh `InconsistentVersionWarning` mỗi lần inference.

## Vận hành

Xem [`README.md`](README.md) cùng thư mục: `run_session.ps1` cập nhật cả 4 mô hình, và ghi chú
quan hệ với task `QuantPercent Daily Update` đang chạy lúc 15:15 T2–T6.
