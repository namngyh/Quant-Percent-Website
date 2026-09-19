# Bộ điều phối 4 mô hình

Cập nhật cả bốn mô hình sau khi đóng phiên, đọc trực tiếp từ TimescaleDB.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File orchestrator\run_session.ps1
```

Bốn mô hình **độc lập** — khác stack, khác artifact, không dùng chung dòng code nào — nên mỗi
bước chạy trong `try/catch` riêng: một mô hình hỏng không chặn ba cái còn lại. Log ghi vào
`orchestrator/logs/session-YYYY-MM-DD.log`.

## Nguồn dữ liệu

| | |
|---|---|
| Database | TimescaleDB/PostgreSQL, bảng `bars_1d` |
| Host | `10.10.0.1:5432` (qua VPN), database `market` |
| Phủ | 389 mã, 2000-07-28 → hiện tại; `VNINDEX`, `VN30INDEX` và rổ VN30 |
| Quyền | read-only, ép ở phía **server** bằng `default_transaction_read_only=on` |

DSN nằm trong `.env` của từng repo (đã gitignore), **không** nằm trong YAML nào được version
control. Mỗi repo có tên biến riêng: `VNINDEX_MARKET_DSN` (RAFF), `DYNAMICGRAPH_DATABASE_URL`
(Dynamic Graph), `MSDP_MARKET_DSN` (MSDP), `RAEMF_MARKET_DSN` (Tempus).

> **Lưu ý:** container `qp-timescaledb` chạy local trên ổ D **không còn là DB sống** — dữ liệu
> của nó dừng ở 2026-08-12. `docker-compose.override.yml` đã trỏ ingestion sang `10.10.0.1`.
> Cấu hình ở đây trỏ đúng vào máy đó.

## Thứ tự trong từng repo

```
sync-source     ← chụp snapshot từ DB ra file (tầng batch vẫn hash một file để tái lập)
update-latest   ← áp phiên mới, KHÔNG refit gì
```

Dynamic Graph không có bước `sync-source`: connector Postgres đọc thẳng, không qua file trung gian.

Sau **mỗi** lần chạy lại tầng batch (`run-all` / train), phải chạy lại `init-online-state` —
tầng online bị reset theo. Bỏ qua bước này thì `update-latest` vẫn chạy trên state cũ mà không
báo lỗi; đối chiếu `source_run_metadata` trong manifest để phát hiện.

## Lần đầu: phải chạy tầng batch trước

`run_session.ps1` chỉ chạy tầng online. Tầng online cần một batch run làm gốc, nên trước khi đăng
ký task lần đầu (và sau mỗi lần retrain) phải chạy tay:

```powershell
# RAFF — vài phút với quick.yaml, lâu hơn với default.yaml
cd RARF-FHE-Regime-Aware-Random-Forest-Forecasting-Hybrid-Engine
python -m vnindex_model.cli sync-source        --config configs/default.yaml
python -m vnindex_model.cli run-all            --config configs/default.yaml
python -m vnindex_model.cli init-online-state  --config configs/default.yaml

# Dynamic Graph — nặng nhất; `fast.yaml` để thử, `local.yaml` cho kết quả thật
cd ..\Dynamic-Graph
python -m dynamicgraph.cli run-all            --config config/local.yaml
python -m dynamicgraph.cli init-online-state  --config config/local.yaml

# MSDP — không cần train lại, chỉ seed state từ bundle production có sẵn
cd ..\MSDP
python scripts\sync_source.py       --config configs\default.yaml
python scripts\init_online_state.py --data data\raw\VNINDEX_Daily_db.csv ^
                                    --model artifacts\models\production_ensemble_manifest.json

# Tempus-VIN — fit tốn hàng giờ ở quy mô nghiên cứu; chỉ chạy lại khi cần
cd ..\Tempus-VIN
.venv\Scripts\python -m raemf_mc.cli fit --config configs\gpu_research.yaml
```

Nếu thiếu bước này, `run_session.ps1` báo lỗi rõ ràng cho đúng mô hình đó (`Chưa có batch
handoff…` / `Chưa có online state…`) và vẫn chạy tiếp ba mô hình còn lại.

**Đừng sửa code trong lúc `run-all` của Dynamic Graph đang chạy**: `validate_publication_state`
so code fingerprint và sẽ từ chối publish ở cuối, làm mất toàn bộ thời gian chạy.

## Quan hệ với pipeline đang chạy của website

Máy này **đã có** một pipeline sản xuất riêng:

- Task Scheduler: `QuantPercent Daily Update`, 15:15 T2–T6
- Script: `D:\Quant-Percent-Website\daily-update.bat`
- Việc nó làm: `backfill.py daily` → xuất `VNINDEX_Daily.csv` → **chỉ chạy MSDP** → nạp vào
  schema `quant.*` cho website đọc

Hai đường **không ghi đè nhau**: đường kia ghi vào `quant.*`, đường này ghi vào `artifacts/` của
từng repo. `run_session.ps1` cũng không gọi tới `daily-update.bat`.

Nếu muốn gộp làm một, chèn `run_session.ps1` vào cuối `daily-update.bat` (sau bước `[1/4]`
backfill, để không phải backfill hai lần). Việc đó đổi hành vi của một job đang chạy thật nên
để người vận hành quyết định, script này không tự làm.

## Đăng ký chạy tự động

```powershell
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\Admin\Desktop\4 mo hinh tren web\orchestrator\run_session.ps1"'
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 15:25
Register-ScheduledTask -TaskName 'Bon mo hinh - cap nhat phien' -Action $action -Trigger $trigger
```

15:25 chứ không phải 15:15: `daily-update.bat` cần khoảng 2 phút để backfill `bars_1d`, và bốn
mô hình đều cần bar ngày của hôm nay đã có trong database.

## Cổng chặn

Script tự dừng (exit 0, không phải lỗi) khi:

- cuối tuần;
- `bars_1d` chưa có phiên của hôm nay — ngày nghỉ lễ, hoặc backfill chưa chạy.

Chạy model trên dữ liệu cũ rồi ghi đè lên dự báo đang đúng còn tệ hơn là không chạy. Muốn ép
chạy thì thêm `-SkipMarketCheck`.

## Yêu cầu môi trường

| Repo | Python |
|---|---|
| RAFF, Dynamic Graph, MSDP | Python hệ thống (3.13) — đã có `psycopg`, `pandas`, `torch`… |
| Tempus-VIN | `.venv` riêng trong repo (torch CUDA) |
