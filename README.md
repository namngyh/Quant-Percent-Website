# Quant Percent — vận hành và checklist trước khi thuê server

Tài liệu này là điểm bắt đầu chung cho ba phần của hệ thống:

Repository public chính:
`https://github.com/namngyh/Quant-Percent-Website`.

## Trạng thái dự án

**Giai đoạn hiện tại: full stack đã chạy được với database thật trên máy
local. Chưa sẵn sàng public production.**

Cập nhật 04/08/2026 — lần đầu website chạy end-to-end với dữ liệu thật.

| Hạng mục | Trạng thái |
|---|---|
| Frontend Next.js | Production build, lint, typecheck đạt; chạy `DATA_MODE=api` với dữ liệu thật |
| Backend FastAPI | 42 test đạt (trước đây 9 test âm thầm bị skip); auth, market, model, performance đã xác minh với DB thật |
| Database local | Đang chạy: TimescaleDB + Redis + ingestion, 535 MB, 2,37 triệu bar phút |
| Migration + seed | Đã chạy trên DB thật: schema `web`/`quant`/`api`, 12 view, 12 model, 3 báo cáo |
| 4 model mới | Trang nghiên cứu hoạt động; **chưa có inference runner** nên schema `quant` vẫn rỗng |
| Triển khai | Compose, Caddy HTTPS, migration, seed, backup và preflight đã chuẩn bị |
| Điểm chặn public | Không có ingestion trên server; chưa restore rehearsal; `/market/risk` và VN30 constituents chưa có dữ liệu |

### Đã xác minh chạy được (04/08/2026)

- `alembic upgrade head` trên database thật, tạo 3 schema và 12 view kiểm duyệt.
- `seed_catalogue` nạp 12 model và 3 báo cáo hiệu suất.
- Quote thật qua API: VN-Index 1777,23 (+0,82%), VN30 1927,35 (+0,50%),
  VN30F1M 1925,0 (+0,57%).
- Auth đủ vòng: đăng ký → đăng nhập → cookie httpOnly `qp_access`/`qp_refresh`/
  `qp_csrf` → `/auth/me`.
- 11 trang VI/EN render 200 với `DATA_MODE=api`, CORS cho `localhost:3000` đúng.

### Lỗi đã sửa trong lần chạy đầu tiên với DB thật

Bốn lỗi dưới đây khiến hệ thống không thể khởi động hoặc trả số sai; cả bốn
chỉ lộ ra khi chạy thật, không lộ ra trong test offline.

| Lỗi | Hậu quả | Sửa ở |
|---|---|---|
| `CORS_ORIGINS` bị pydantic-settings JSON-decode | Backend không khởi động được khi có `.env`, **và sẽ sập cả production** vì `compose.production.yml` truyền chuỗi thường | `app/core/config.py` |
| Alembic ghi bảng version vào schema `web` trước khi migration tạo schema đó | `alembic upgrade head` không bao giờ chạy được trên database trắng | `alembic/env.py` |
| Seeder đọc bắt buộc `updatedAt` (optional trong `ModelConfig`) | Seed chết ở model thứ 5 | `scripts/seed_catalogue.py` |
| `api.v_quote` lấy giá live từ `bars_1m` nhưng prev_close từ `bars_1d` | `bars_1d` chỉ được cập nhật bằng script chạy tay, nên % thay đổi sai trên mọi trang. VN-Index hiện +4,26% thay vì +0,82% | migration `0003` |

Ngoài ra `web.symbols` có thêm cột `feed_symbol` (migration `0004`): website
công bố chỉ số VN30 dưới tên `VN30`, còn DataPro trả về `VN30INDEX`, trước đó
không có gì dịch giữa hai tên nên `/market/VN30/quote` trả 404.

Không đưa `.env`, API key, mật khẩu, Docker volume, VHDX, raw market data,
dependency hoặc build cache lên repository public.

## Cấu trúc monorepo trên GitHub

```text
database/                 Database schema và ingestion pipeline
backend/                  FastAPI, migration, seed và production deploy
frontend/                 Next.js website
models/dynamic-graph/     Dynamic Graph research project
models/msdp/              Multi-Scale Distributional Predictor
models/raemf-mc/          RAEMF-MC research project
models/rarf-fhe/          RARF-FHE research project
README.md                 Trạng thái, vận hành và checklist chung
```

Các dependency, cache, secret và dữ liệu runtime bị loại khỏi monorepo; mã
nguồn và các artifact đã được từng repository model theo dõi bằng Git được
giữ lại.

## Vị trí workspace local

| Thành phần | Vị trí trên máy local |
|---|---|
| Database và ingestion đang chạy | `D:\Database - QuantPercent` |
| Monorepo (backend, frontend, models, bản sao database) | `C:\Users\Admin\Desktop\Web Quant Percent\Quant-Percent-Website` |

Compose project của database tên `database-quantpercent`, network
`database-quantpercent_default`. Ba container: `qp-timescaledb`, `qp-redis`,
`qp-ingestion`.

> Thư mục `database/` trong monorepo là **bản sao mã nguồn** để theo dõi bằng
> Git. Stack đang chạy thật là `D:\Database - QuantPercent`. Sửa schema hoặc
> ingestion phải đồng bộ cả hai nơi, nếu không lần rebuild sau sẽ mất thay đổi.

## Database ở ổ D nghĩa là gì?

`D:\Database - QuantPercent` chứa cả mã nguồn lẫn dữ liệu runtime:

| Đường dẫn | Nội dung |
|---|---|
| `dockerdata\wsl\disk\docker_data.vhdx` | Đĩa ảo Docker, 6,87 GB — chứa volume PostgreSQL thật |
| `data\raw\ticks`, `data\raw\bars_1m` | Parquet dự phòng theo ngày |
| `backup\` | `pg_dump` và zip parquet |

Số liệu database tại 04/08/2026:

| Chỉ số | Giá trị |
|---|---|
| Dung lượng database `market` | 535 MB |
| `ticks` | 1.004.961 dòng, 24/07/2026 → 04/08/2026 |
| `bars_1m` | 2.367.349 dòng, 06/11/2017 → 04/08/2026, 35 mã |
| `bars_1d` | 110.374 dòng, 28/07/2000 → 04/08/2026 |

`bars_1d` **không** được service ingestion cập nhật — chỉ `backfill.py` chạy
tay mới ghi bảng này. Trước 04/08/2026 nó đứng ở 30/07. Cần đưa việc này vào
lịch chạy định kỳ, xem phần checklist.

Dữ liệu CSV trong `models\...\data` là dữ liệu nghiên cứu của từng model,
không phải database PostgreSQL phục vụ website.

Không xóa Docker volume, không chạy `docker compose down -v`, và không sửa
trực tiếp file VHDX. Luôn tạo `pg_dump` trước khi di chuyển database.

## Vận hành hiện tại

### Trạng thái thực tế trên máy lúc kiểm tra

- TimescaleDB, Redis và ingestion đang chạy, healthy, cổng 5432/6379 mở.
- Migration và seed đã chạy trên database thật.
- Backend đọc được dữ liệu thị trường thật; frontend chạy `DATA_MODE=api`.
- Schema `quant` rỗng hoàn toàn: `model_forecasts`, `market_state`,
  `risk_metrics`, `stock_rankings`, `model_runs` đều 0 dòng.

### Các mục phụ thuộc model pipeline đang được ẩn

Chưa có inference runner nào ghi vào schema `quant`, nên những phần đọc từ đó
được ẩn thay vì hiển thị rỗng hoặc hiển thị số mặc định.

| Mục | Trạng thái | Chờ bảng |
|---|---|---|
| Tab Rủi ro | Ẩn | `quant.risk_metrics` (+ `risk_mc_distribution`, `risk_scenarios`) |
| Tab Cổ phiếu VN30 | Ẩn | `quant.stock_rankings` |
| Regime, tín hiệu, xác suất, biến động, risk state | Ô tự ẩn | `quant.market_state` |
| Forecast của model | Không hiện | `quant.model_forecasts` |

Bật lại bằng `frontend/config/live-sections.ts` — đổi cờ tương ứng thành
`true` khi bảng đã có dữ liệu. Không cần sửa component, route hay bản dịch.
Xem tab nào đang hiện: `npx tsx scripts/check-live-sections.ts`.

Riêng nhóm market state **không có cờ**: API trả `null` cho từng trường khi
chưa có dữ liệu và component tự bỏ ô đó, nên chúng tự hiện lại khi có số thật.

**Lỗi đã sửa kèm theo:** `/api/v1/market/overview` trước đây trả
`regime="sideways"`, `risk_state="moderate"`, `risk_score=0`,
`probability_up=0.0`, `public_signal="low_conviction"` khi `market_state`
rỗng — website hiển thị nguyên vẹn như một nhận định thật của mô hình. Comment
ngay trên đoạn code đó ghi *"rather than inventing a market state"* trong khi
code làm đúng việc bịa. Nay các trường này nullable và trả `null`; hai test
trong `test_contract.py` và `test_market_service.py` khoá lại hành vi này.

### Luồng hoạt động khi stack được khởi động

```text
DataPro.Client trên Windows (:6789)
        |
        v
ingestion container
        |-- TimescaleDB: ticks, bars, forecasts và dữ liệu website
        |-- Redis: pub/sub realtime và cache
        `-- data/raw: Parquet dự phòng

TimescaleDB/Redis
        |
        v
FastAPI backend (:8000)
        |
        v
Next.js frontend (:3000)
```

1. DataPro.Client phải đang mở trên Windows. Ingestion gọi nó qua
   `host.docker.internal:6789`.
2. Ingestion chuẩn hóa mỗi bản ghi một lần, ghi TimescaleDB, publish Redis và
   lưu Parquet.
3. Backend chỉ đọc dữ liệu thị trường qua các view `api.*`, đọc catalogue,
   báo cáo và tài khoản từ schema `web`/`quant`.
4. Frontend local mặc định chạy mock. Production dùng `DATA_MODE=api` và lấy
   model, performance, market data, auth và contact qua FastAPI/database.
5. Bốn model `raemf-mc`, `rarf-fhe`, `dynamic-graph`, `msdp` hiện là trang
   nghiên cứu (`experimental`). Chưa có inference runner nên chưa phát sinh
   forecast live; `show_forecast=false` là trạng thái có chủ đích.

Nếu máy local tắt thì DataPro, ingestion và database local đều dừng, nên
không có dữ liệu mới. Nếu website cũng chạy trên máy này thì website dừng.
Trong kiến trúc production, website/database trên server vẫn hoạt động và
hiển thị dữ liệu cuối cùng, nhưng feed sẽ bị đánh dấu stale cho đến khi máy
Windows thu thập dữ liệu hoạt động lại.

## Cách chạy local

Bấm đúp `start.bat` ở thư mục gốc, hoặc gõ một lệnh:

```cmd
start.bat
```

Script tự làm: bật Docker Desktop và đợi sẵn sàng, bật DataPro.Client, bật 3
container database, mở hai cửa sổ backend (8000) và website (3000), rồi mở
trình duyệt. Chạy lại lần hai không tạo bản sao — cổng nào đã có người trả lời
thì bỏ qua.

Tắt: đóng hai cửa sổ `QP Backend` và `QP Website`. Database chạy nền, chỉ tắt
khi thật sự không dùng nữa.

<details>
<summary>Cách thủ công, nếu cần chạy từng phần</summary>

```powershell
# 1. Database (DataPro.Client phải đang mở trên Windows)
cd "D:\Database - QuantPercent"
docker compose up -d
docker compose ps

# 2. Backend
cd "C:\Users\Admin\Desktop\Web Quant Percent\Quant-Percent-Website\backend"
.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# 3. Frontend
cd "C:\Users\Admin\Desktop\Web Quant Percent\Quant-Percent-Website\frontend"
npm run dev
```

</details>

Chỉ muốn xem giao diện, không cần dữ liệu thật: đổi `DATA_MODE=mock` trong
`frontend\.env.local` rồi chỉ chạy `npm run dev` — không cần Docker lẫn backend.

> **Local dùng `npm run dev`, không dùng `npm start`.** `next.config.ts` đặt
> `output: "standalone"` cho ảnh Docker production, và Next cảnh báo rằng
> `next start` không hoạt động với cấu hình đó — nó gợi ý
> `node .next/standalone/server.js`. Trên production, Compose chạy đúng server
> standalone đó. `start.bat` đã dùng `npm run dev` nên không vướng.

Kiểm tra:

```powershell
curl.exe http://localhost:8000/readyz          # database: ok, redis: ok
cd "C:\Users\Admin\Desktop\Web Quant Percent\Quant-Percent-Website\frontend"
npx tsx scripts/check-api.ts http://localhost:8000
```

`check-api` phải in `All API checks passed.`. Dòng
`○ /api/v1/market/risk → 503` là bình thường — endpoint đó chờ model pipeline,
và script chỉ báo hỏng nếu nó trả mã khác 200/503.

### Thiết lập lại từ đầu (máy mới hoặc database trắng)

```powershell
# Role hạn chế quyền cho backend
$qpw = python -c "import secrets; print(secrets.token_urlsafe(48))"
Get-Content backend\scripts\create_role.sql | `
  docker exec -i qp-timescaledb psql -U quant -d market --set "api_password=$qpw"
# Ghi $qpw vào DATABASE_URL trong backend\.env

# Migration phải chạy bằng owner `quant`, không phải qp_web
$env:DATABASE_URL = "postgresql+asyncpg://quant:<POSTGRES_PASSWORD>@localhost:5432/market"
backend\.venv\Scripts\python.exe -m alembic upgrade head
Remove-Item Env:DATABASE_URL

# Seed catalogue
cd frontend; npx tsx scripts/export-catalogue.ts; cd ..
cd backend; .venv\Scripts\python.exe -m scripts.seed_catalogue --frontend ../frontend
```

## Cập nhật tự động sau phiên

Bấm đúp `install-schedule.bat`, chạy một lần. **Không cần quyền Administrator** —
tác vụ chỉ gọi Docker (tài khoản đã thuộc nhóm `docker-users`), Python và ghi
file trong thư mục dự án.

```cmd
install-schedule.bat
```

Từ đó, **15:15 các ngày thứ 2–6**, máy tự chạy `daily-update.bat`:

| Bước | Việc | Thời gian |
|---|---|---|
| 1 | `backfill.py daily` → cập nhật `bars_1d` | ~45 giây |
| 2 | Xuất `VNINDEX_Daily.csv` từ database | ~1 giây |
| 3 | MSDP inference (không huấn luyện lại) | ~1 giây |
| 4 | Nạp dự báo vào `quant.model_forecasts` | ~1 giây |

Chọn 15:15 vì HOSE đóng phiên liên tục lúc 14:45 và hết ATC khoảng 15:00 —
15:15 để dư biên cho ingestion ghi nốt bar cuối.

**Script tự dừng khi không nên chạy:** cuối tuần, Docker chưa bật, hoặc
database không có bar nào của hôm nay. Điều kiện cuối quan trọng nhất — ngày
nghỉ lễ hoặc máy thu thập không chạy sẽ khiến model chạy trên dữ liệu cũ rồi
ghi đè dự báo đang đúng. Thà không cập nhật còn hơn cập nhật sai.

Nhật ký ghi vào `logs\daily-update-YYYY-MM-DD.log`.

```cmd
schtasks /Run    /TN "QuantPercent Daily Update"     :: chạy thử ngay
schtasks /Query  /TN "QuantPercent Daily Update" /V /FO LIST
schtasks /Delete /TN "QuantPercent Daily Update" /F  :: gỡ lịch
```

> Không dùng cờ `/RL HIGHEST` khi tạo tác vụ. Chính cờ đó mới đòi quyền
> Administrator, và tác vụ này không cần nó — đã kiểm chứng bằng cách chạy thật
> qua Task Scheduler: Docker, backfill và các script Python đều hoạt động.

Máy phải đang bật và Docker phải chạy vào thời điểm đó. RARF-FHE **không** nằm
trong lịch này: nó chạy full pipeline ~20 phút nên hợp với lịch tuần, chạy tay
khi cần.

### Cập nhật `bars_1d` thủ công

Service ingestion không ghi `bars_1d`. Chạy sau khi thị trường đóng cửa:

```powershell
cd "D:\Database - QuantPercent"
docker compose stop ingestion
docker compose run --rm --no-deps ingestion python backfill.py daily
docker compose start ingestion
```

Idempotent, khoảng 45 giây cho 35 mã. Từ migration `0003` trở đi, quote không
còn sai khi bảng này cũ, nhưng biểu đồ lịch sử 1D vẫn cần nó.

## Nhược điểm hiện tại và lộ trình khắc phục

Rà soát ngày 05/08/2026. Mỗi mục ghi rõ hậu quả thực tế, không phải mong muốn
chung chung. Thứ tự trong bảng là thứ tự nên làm.

### Chặn public — phải xong trước khi đổi DNS

| # | Vấn đề | Hậu quả nếu bỏ qua | Cách khắc phục |
|---|---|---|---|
| 1 | `compose.production.yml` **không có service ingestion** | Server dựng lên có database rỗng, không gì nạp dữ liệu mới. Website public ra một trang không có số | Chọn một trong ba: máy Windows local + VPN (rẻ nhất, không phải viết code — chỉ đổi `PG_DSN`/`REDIS_URL`), VPS Windows riêng cho DataPro, hoặc ingestion gateway có xác thực |
| 2 | 535 MB dữ liệu chỉ nằm trên ổ D | Mất ổ đĩa là mất toàn bộ lịch sử thu thập | `pg_dump` → `pg_restore` sang server, và giữ một bản ngoài máy |
| 3 | **Backup chưa từng khôi phục thử** | Không biết bản dump có dùng được không cho tới lúc cần nó nhất | Restore vào một database test, đếm số dòng, so với bản gốc |
| 4 | Không có giám sát | Backend chết lúc 2h sáng thì không ai biết tới khi có người mở web | Uptime monitor gọi `/readyz` mỗi 5 phút, gửi email khi hỏng |
| 5 | Legal chưa có luật sư VN rà soát | Rủi ro pháp lý khi công bố số liệu hiệu suất cho nhà đầu tư | Thuê luật sư đọc trang Legal và các caveat |

#### Độ trễ công bố — đã xử lý 05/08/2026

Website từng ghi "Trễ 15 phút" trên mọi khối dữ liệu trong khi phục vụ bar mới
nhất, tươi khoảng **60 giây** (đo được: bar 14:25 truy vấn được lúc 14:26:01).
`market.py` có hàm `delayed_cutoff()` để thực thi độ trễ, nhưng tìm toàn
backend chỉ thấy đúng dòng định nghĩa — **không truy vấn nào gọi nó**.

Tài liệu API của DataPro (`datapro.vn/docs/datapro.html`) chỉ mô tả kỹ thuật:
gói SILVER/GOLD/DIAMOND, và Remote API trễ vài giây so với luồng WebSocket
chính. **Không có điều khoản nào về phân phối lại, công bố ra công chúng, hay
yêu cầu độ trễ khi hiển thị.** Ràng buộc đó, nếu có, nằm trong hợp đồng dịch vụ
chứ không phải tài liệu kỹ thuật.

Đã đặt `MARKET_DELAY_MINUTES=0` ở mọi nơi cấu hình và xoá hàm chết.

Quan trọng: cấu hình này giờ **không thể nói dối được nữa**. Việc giữ lại dữ
liệu mới vẫn chưa được cài đặt, nên `Settings` từ chối khởi động với bất kỳ giá
trị nào khác 0:

```
MARKET_DELAY_MINUTES must be 0: withholding recent rows is not implemented,
so any other value would advertise a delay the API does not apply.
```

Nếu sau này hợp đồng dữ liệu yêu cầu độ trễ thật, phải cài `WHERE ts <= cutoff`
vào các truy vấn quote/history/freshness **trước**, rồi mới nâng giá trị này.
Test `test_declared_market_delay_is_actually_applied` khoá lại ràng buộc đó.

### Nên xong sớm sau khi public

| # | Vấn đề | Hậu quả | Cách khắc phục |
|---|---|---|---|
| 6 | Backup không tự động | Chỉ có bản tạo tay | Cron `pg_dump` hằng ngày sau 15:00, giữ 14 bản, đẩy một bản ra ngoài |
| 7 | Lịch chạy model chưa được đăng ký | Dự báo đứng yên vĩnh viễn | Chạy `install-schedule.bat` bằng quyền Administrator |
| 8 | Lịch chạy thất bại thì không ai biết | Model đứng một tuần mà website vẫn hiện số cũ | Cho `daily-update.bat` gửi email khi thất bại |
| 9 | **Không ai chấm điểm dự báo** | Không biết model đúng hay sai | Điền `quant.model_forecasts.actual_value` khi giá thực tế đã biết; API tự tính sai số và coverage |
| 10 | Artifact production của MSDP là bản `quick` | 8 trial, 2 fold, 1 seed — cấu hình kiểm thử, không phải để công bố | Chạy lại cấu hình đầy đủ trước khi bật `show_forecast` |
| 11 | Danh sách VN30 lệch nhau giữa ba nơi | BCM/BVH/POW có trong `web.symbols` mà không có dữ liệu giá | Chốt một nguồn sự thật, đồng bộ seed và ingestion |
| 12 | Nguồn dữ liệu có lỗi chất lượng | 13 phiên `Low > Close` trong CSV, 4 dòng OHLC sai trong `D.dat` | Thêm kiểm tra bất biến OHLC vào `check_pipeline.py`, cảnh báo khi phát hiện |

### Hạn chế đã biết, chấp nhận được trong giai đoạn này

| # | Vấn đề | Ghi chú |
|---|---|---|
| 13 | Toàn bộ chạy trên một máy cá nhân | Mất điện hoặc Windows Update là website chết. Chấp nhận được cho staging, không cho production |
| 14 | Ba model dùng ba môi trường Python | MSDP cần 3.12, còn lại 3.13. Dễ vỡ khi cài lại máy — ghi lại đường dẫn venv trong tài liệu |
| 15 | RARF-FHE không nằm trong lịch tự động | Full pipeline ~20 phút, hợp lịch tuần hơn lịch ngày |
| 16 | `market_state` và `stock_rankings` vẫn rỗng | Cần model xếp hạng theo mã; không model nào hiện có sinh regime/P(tăng) cho từng cổ phiếu |
| 17 | Cả hai model tự khai chưa vượt baseline | dynamic-graph AUROC 0,49; MSDP pinball kém ZeroReturn ở H5/H20. Đây là thực trạng nghiên cứu, không phải lỗi kỹ thuật |

### Kiểm thử

Từ 05/08/2026 có `npm run check:ui`: mở Chrome thật, chụp 11 trang × 2 khổ màn
hình, tự soi DOM tìm tràn ngang, lưới thưa, chữ bị cắt và chuỗi hỏng. Ba lỗi
giao diện lọt lưới trước đó đều trả HTTP 200 — `check:api` không thể bắt được
chúng. Chạy lệnh này trước mỗi lần deploy.

## Kiến trúc hosting đã chốt — Phương án B

Quyết định ngày 06/08/2026: **thuê thêm một Windows VPS cho DataPro**, đưa
toàn bộ hệ thống lên cloud.

### Vì sao phải có Windows VPS

DataPro là ứng dụng desktop chỉ chạy trên Windows. Nó phục vụ dữ liệu qua
`DATAPRO_REST_URL=http://host.docker.internal:6789` — tức localhost của máy
đang chạy nó. Không có bản Linux, không có API công khai thay thế.

Hệ quả: nếu chỉ thuê một VPS Linux cho backend, frontend và database thì
server đó **không có nguồn dữ liệu**. Đây là ràng buộc cứng, không phải vấn đề
cấu hình.

### Sơ đồ

```
┌─ Windows VPS ─────────────┐        ┌─ Linux VPS ──────────────────────┐
│  DataPro (desktop)        │        │  Caddy (HTTPS, tên miền)         │
│  :6789 chỉ nghe localhost │        │  Next.js frontend                │
│                           │        │  FastAPI backend                 │
│  ingestion container      │──────► │  TimescaleDB + Redis             │
│  (đọc DataPro, ghi DB)    │  VPN   │  (chỉ nghe trên private network) │
└───────────────────────────┘        └──────────────────────────────────┘
        model chạy theo lịch                    người dùng truy cập
```

Ingestion đặt cùng máy với DataPro để `host.docker.internal` vẫn dùng được,
rồi ghi thẳng vào database trên VPS Linux qua kênh riêng.

### Cấu hình đề xuất

| Thành phần | Cấu hình | Chi phí ước tính |
|---|---|---|
| Windows VPS (DataPro + ingestion + model) | 8 vCPU, 16 GB RAM, 200 GB SSD | 40–80 USD/tháng |
| Linux VPS (FE + BE + DB) | 4 vCPU, 8 GB RAM, 100 GB SSD | 20–40 USD/tháng |
| Sao lưu ngoài | object storage 100 GB | 2–5 USD/tháng |

Windows VPS cần nhiều nhân vì việc huấn luyện lại model chạy ở đó. Đo trên máy
16 nhân hiện tại: DynamicGraph 5 giờ 20 phút, RAEMF-MC 34 phút, RARF-FHE 20
phút. Máy 2 nhân sẽ mất khoảng một ngày cho DynamicGraph.

### Việc phải làm trước khi mở public

1. **Đóng database khỏi mạng công cộng.** Hiện `docker-compose.yml` bind
   `0.0.0.0:5432` và Redis không có mật khẩu. Trên VPS có IP công khai đây là
   lỗ hổng nghiêm trọng. Xem mục "Truy cập database từ xa" bên dưới.
2. **Đổi toàn bộ mật khẩu.** Mật khẩu database, Redis và tài khoản `qp_remote`
   hiện dùng cho môi trường phát triển. Chuỗi kết nối được đọc từ biến
   `PG_DSN` chứ không nằm trong mã nguồn (xem `database/scripts/_db.py`), nên
   việc đổi mật khẩu chỉ cần cập nhật biến môi trường và `.env`.
3. **Kiểm tra giấy phép DataPro** có cho phép chạy trên VPS không — đây là
   rủi ro duy nhất có thể làm phương án B không khả thi.
4. **Chính sách dữ liệu cho Quant Portfolio.** Tính năng nhận danh mục của
   người dùng. Hiện không lưu gì, nhưng cần nói rõ điều đó thành văn bản.
5. **Sao lưu tự động** `pg_dump` hằng ngày ra object storage, và diễn tập
   phục hồi ít nhất một lần.

### Nhược điểm đã biết của phương án này

- Chi phí gấp đôi so với chỉ thuê một VPS Linux.
- Hai máy phải quản lý thay vì một.
- Windows VPS đắt hơn Linux cùng cấu hình do phí bản quyền.
- Vẫn phụ thuộc vào một nhà cung cấp dữ liệu duy nhất.

Đổi lại, không còn phụ thuộc vào máy ở nhà và đường mạng dân dụng — đó là lý
do chọn B thay vì tách đôi giữa nhà và cloud.

## Checklist trước khi thuê server

### Đã hoàn thành trong mã nguồn

- [x] Catalogue 12 model và 3 báo cáo có snapshot seed database.
- [x] Model và performance production đọc FastAPI/database ở runtime.
- [x] Auth thật, cookie httpOnly, CSRF, contact và phân quyền backend.
- [x] Migration cho research profile của 4 model mới.
- [x] Docker production, Caddy HTTPS, private network, backup và preflight.
- [x] Role migration tách khỏi role `qp_web` giới hạn quyền.
- [x] Frontend production build, API smoke test và dependency audit đạt.
- [x] Backend có 42 test đạt, lint và dependency audit đạt.

### Bắt buộc làm với database thật

- [x] Xác định đường dẫn vật lý của Docker volume: `D:\Database - QuantPercent\dockerdata\wsl\disk\docker_data.vhdx`.
- [x] Khởi động Docker/PostgreSQL/Redis và xác nhận container healthy.
- [x] Tạo `pg_dump`: `backup\market_2026-08-04_premigration.dump` (97,3 MB).
- [x] Chạy migration `alembic upgrade head`, seed catalogue và kiểm tra 12
  model/3 report trên database thật.
- [x] Chạy frontend với `DATA_MODE=api` và kiểm tra toàn bộ API với FastAPI,
  không dùng mock.
- [ ] Chạy `scripts\check_pipeline.py`; xác nhận tick/bar mới và không có gap
  bất thường.
- [ ] **Khôi phục thử bản dump vào database test riêng.** Backup chưa restore
  thử thì chưa được xem là backup hợp lệ. Đây vẫn là điểm chặn public.
- [ ] Lưu một bản backup ra ngoài máy local.
- [ ] Chạy `backend\deploy\preflight.sql` để lấy dung lượng DB, row count và
  thời điểm dữ liệu mới nhất.

### Quyết định kiến trúc trước khi mua server

Bốn điểm dưới đây là thứ **thuê server không giải quyết được**. Chúng phải có
lời giải trước khi đổi DNS, nếu không website sẽ public ở trạng thái không có
dữ liệu mới.

- [ ] **`compose.production.yml` không có service ingestion.** Server dựng lên
  sẽ có database rỗng và không có gì nạp dữ liệu mới. Phải chọn: máy Windows
  local luôn bật + VPN, Windows VPS riêng cho DataPro, hoặc ingestion gateway
  có xác thực.
- [ ] **Chuyển 535 MB dữ liệu hiện có lên server.** Volume `database_data`
  trong compose production là volume mới, rỗng. Cần `pg_dump` → `pg_restore`,
  và phải restore thử trước.
- [ ] **Schema `quant` rỗng.** Chưa model nào ghi forecast, market state, risk
  hay stock ranking. Các mục đó hiện đã được ẩn (xem `live-sections.ts`), nên
  website public được mà không trưng chỗ trống — nhưng phần "model
  intelligence" vẫn chưa sống cho tới khi có inference runner.
- [ ] **Lịch chạy `backfill.py daily`.** Không có nó thì biểu đồ lịch sử 1D
  đứng yên từ ngày chạy tay gần nhất.

Còn lại:

- [ ] Không public PostgreSQL 5432 hoặc Redis 6379 ra Internet.
- [ ] Chọn TimescaleDB image tag cố định sau khi restore thử thành công.
  Local đang chạy tag nào thì ghim đúng tag đó.
- [ ] Chỉ chọn dung lượng ổ đĩa server sau khi có kết quả `preflight.sql`.
  Tham chiếu: 535 MB cho ~9 năm bar phút và ~2 tuần tick.
- [ ] Chuẩn bị DNS, ba secret độc lập, email provider và nơi lưu backup ngoài
  server.
- [ ] Thiết lập backup tự động, cảnh báo feed stale, giám sát `/readyz` và
  diễn tập rollback trước khi đổi DNS production.
- [ ] Rà soát nội dung Legal với luật sư VN.

## Lấp dữ liệu cho schema `quant` — kết quả thử nghiệm 04/08/2026

Ba phương án đã được thử thật, không phải ước lượng.

| | A. Nạp artifact cũ | B. Chạy lại model | C. Ẩn mục chưa có |
|---|---|---|---|
| Kết quả thử | Trường dữ liệu khớp bảng, kỹ thuật làm được | **Chạy được thật trên dữ liệu hôm nay** | Đã triển khai và xác minh |
| Ngày dữ liệu | 13/07 và 24/07 — cũ 3 tuần | 03–04/08 — hôm nay | — |
| Chất lượng | Kèm 13 phiên có `Low > Close` (bất khả thi) | Đã hết lỗi đó | — |
| Chi phí | ~1 ngày | Xem bảng thời gian bên dưới | Xong |

### Thời gian chạy đo được (04/08/2026)

Hai model có chi phí khác nhau một trời một vực, nên đừng gộp chung khi lập lịch.

| Model | Đường chạy | Huấn luyện lại | Thời gian |
|---|---|---|---|
| **msdp** | `predict_latest_ensemble` — chỉ suy luận | Không | **0,8 giây** |
| dynamic-graph | `build-features` | — | 12 giây |
| dynamic-graph | `build-graphs` | — | 100 giây |
| dynamic-graph | `generate-latest` | Có | **77 phút** (chế độ fast) |

msdp hợp với lịch chạy hằng ngày ngay sau `backfill.py daily`. dynamic-graph là
công việc theo lô chạy nền, không phải thứ cập nhật mỗi chiều.

Lưu ý môi trường: msdp yêu cầu Python `>=3.10,<3.13` còn máy mặc định là 3.13.
Dùng `D:\miniconda\envs\project\python.exe` (3.12.13). Venv phải đặt ở đường
dẫn ngắn — cài `torch` vào `Desktop\Web Quant Percent\...` thất bại với
`WinError 206` vì đường dẫn quá dài; `C:\qpvenv\msdp` chạy được.

> **Không chạy dynamic-graph ở chế độ `fast` trên thư mục artifacts thật.**
> `generate-latest` ghi đè cả 73 file trong `artifacts/`, kể cả hình và báo
> cáo. Artifact đang được commit là bản `config_mode: default` (chuẩn công bố);
> một lần chạy `fast` sẽ thay bằng bản mà chính config ghi rõ *"NOT publication
> grade"*, và mất mát đó không nhìn thấy được nếu chỉ xem giao diện. Kiểm tra
> bằng `config_mode` trong `artifacts/reports/run_summary.json`. Muốn thử
> nhanh thì trỏ `output.artifacts_dir` sang thư mục tạm.

**Phương án A bị loại** — không phải vì khó, mà vì đã trở thành vô nghĩa: chính
những model đó chạy lại được trên dữ liệu hôm nay, nên nạp bản 3 tuần trước chỉ
chuốc thêm rủi ro hiển thị số cũ mà không đổi lại được gì.

**Tối ưu: B, dựng trên nền C.** C là cơ chế an toàn — mục nào chưa có dữ liệu
thì ẩn. B lấp dần từng bảng, bật cờ tương ứng khi bảng có dòng.

### Những gì phát hiện khi thử

**Có một nguồn dữ liệu tốt hơn mà tài liệu chưa từng nhắc.** Lệnh
`discover-data` của dynamic-graph tìm ra `C:\DataPro\D.dat` — kho SQLite riêng
của app DataPro: **2.142 mã, 1970-01-02 → 04/08/2026, đã điều chỉnh giá**, cập
nhật hằng ngày. Rộng và dài hơn hẳn TimescaleDB của website (35 mã). Đường dẫn
này đã được ghi vào `models/dynamic-graph/config/local.yaml` (gitignored).

**Ba model đói dữ liệu vì file CSV tĩnh.** `rarf-fhe`, `msdp`, `raemf-mc` đọc
`VNINDEX_Daily.csv` nằm sẵn trong repo, và cả ba bản đều dừng ở 13/07/2026 —
đó chính là lý do artifact cũ 3 tuần. Database có cùng chuỗi số và dài hơn 14
phiên, nên script mới sinh lại file này:

```powershell
backend\.venv\Scripts\python.exe database\scripts\export_vnindex_daily.py --repo-root .
```

Đã kiểm chứng bằng chính parser của từng model: 6.322 dòng, 2000-07-28 →
04/08/2026, close cuối 1777,23 khớp website. So với bản cũ trên 6.306 phiên
chung, **open/high/close lệch đúng 0,0**.

**File cũ của nhà cung cấp có 13 phiên sai.** Trên 13 phiên, CSV vendor ghi
`Low` cao hơn `Close` — giá thấp nhất phiên không thể cao hơn giá đóng cửa.
Ví dụ 20/12/2005 ghi `L=313,7` trong khi `C=311,8`. Database có `Low = Close`,
hợp lệ. Vậy file sinh lại không chỉ mới hơn mà còn **đúng hơn**; các model
trước nay vẫn nạp 13 phiên dữ liệu không hợp lệ.

### Model tự khai báo phần nào của nó không dùng được

Đây là ràng buộc quan trọng nhất, và nó không phải vấn đề kỹ thuật. Sau khi
chạy lại trên dữ liệu 04/08, cả hai model đều tự ghi vào artifact rằng tầng dự
báo của chúng chưa có giá trị.

**dynamic-graph** — `model_quality` trong `latest_dynamicgraph.json`:

| Chỉ số | Giá trị | Nghĩa |
|---|---|---|
| `auroc` | 0,4906 | Tệ hơn tung đồng xu |
| `brier_skill_score` | −0,3245 | Kém hơn dự báo theo tỷ lệ nền |
| `mcc` | −0,0167 | Âm |
| `false_alarms_per_year` | 27,2 | Báo động giả liên tục |

Mỗi horizon trong `stress_forecasts.csv` còn kèm `confidence_warning`:
*"did not beat a constant base-rate forecast out of sample. Treat the
probability as uninformative."*

Ngược lại, tầng **mô tả** cho kết quả dùng được và đúng với luận điểm được
ủng hộ trong README của model: `network_state` = `high_stress`,
`stress_score` 86,6, phân vị lịch sử 0,9406.

**msdp** — README của nó: *"chưa có bằng chứng cho thấy MSDP vượt baseline"*;
H5 và H20 có pinball kém ZeroReturn, mọi CI95 của chênh lệch MAE đều chứa 0.
Model tự xác định giá trị nằm ở *"dự báo phân phối và hiệu chỉnh rủi ro, chưa
phải ở dự báo điểm"*.

Kết luận cho việc công bố: đưa lên website **trạng thái mạng lưới mô tả**,
**khoảng phân phối** và **thước đo rủi ro**. Không đưa `stress_probabilities`
của dynamic-graph, và không trình bày `probability_positive` của msdp như một
dự báo hướng đi. Điều này khớp với quy tắc nội dung sẵn có: tín hiệu công khai
chỉ dùng Bullish/Neutral/Defensive/High Risk/Low Conviction.

Ngoài ra artifact mới cảnh báo nguồn `D.dat` có `4 row(s) violate low <=
{open, close} <= high` — cùng loại lỗi với 13 phiên đã phát hiện trong CSV.

### Đường ống đã dựng xong (05/08/2026, viết lại 01/09/2026)

Bản đầu chỉ chạy **một** mô hình. Ba mô hình còn lại đọc `VNINDEX_Daily.csv`
tĩnh nằm sẵn trong repo nên không thể chạy hằng ngày; RARF-FHE có sẵn loader
nhưng chưa từng được gọi, còn DynamicGraph và RAEMF thì chưa có loader.

Nay cả bốn đều có connector Postgres read-only riêng và một **tầng online**:
tầng này áp các phiên mới lên trạng thái đã lưu và **không train lại gì**.
`daily-update.bat` chạy tuần tự sau khi đóng phiên:

```
[1/6] backfill.py daily        -> bars_1d (cả bốn mô hình đều đọc bảng này)
[2/6] RARF-FHE                 -> sync-source, update-latest
[3/6] MSDP                     -> sync_source.py, update_latest.py
[4/6] DynamicGraph             -> update-latest (đọc thẳng DB)
[5/6] Tempus / RAEMF-VB-MC     -> predict (nạp lại bundle đã fit)
[6/6] load_model_outputs.py    -> quant.*  +  npm run research:sync
```

Bốn mô hình độc lập nhau, nên mỗi bước tự bắt lỗi riêng: một mô hình hỏng
không chặn ba cái còn lại. Mô hình nào hỏng thì bước [6] gọi `--mark-failed`
cho nó, thay vì để dòng cũ nằm lại trong `quant.model_runs` trông như vừa chạy
xong — đúng kiểu hỏng âm thầm mà cổng `has_bars_today.py` sinh ra để chặn.

Không còn bước `export_vnindex_daily.py`: mỗi mô hình tự chụp snapshot của
chính nó và phân biệt được "thêm phiên mới" với "lịch sử bị sửa" — việc mà một
script ghi đè không làm được. `run_msdp_inference.py` cũng ra khỏi đường ống
vì nó chạy ensemble "nguội", bỏ qua posterior của cổng Hedge, tức **cùng
`model_id` nhưng khác số**; giữ lại chỉ để tái lập, không phải để dự phòng.

**Trước lần chạy đầu tiên phải bootstrap.** Tầng online cần một lần chạy tầng
batch làm gốc. Chưa có thì `update-latest` báo "Chưa có online state" và dừng:

```powershell
bootstrap-models.bat rarf-fhe        # vài phút
bootstrap-models.bat dynamic-graph   # nặng, hàng chục phút
bootstrap-models.bat msdp            # nhanh, chỉ seed state từ bundle có sẵn
bootstrap-models.bat raemf-mc        # fit hàng giờ, cần venv torch CUDA
```

Phải chạy lại cho mô hình nào vừa train lại tầng batch: tầng online bị reset
theo, và bỏ qua thì `update-latest` vẫn chạy trên state cũ **mà không báo lỗi**.

Môi trường: các mô hình cần `psycopg` + `torch` + `sklearn` + `hmmlearn`. Chỉ
Python hệ thống (3.13) có đủ; mọi venv cũ (`C:\qpvenv\*`, `.venv` trong từng
repo) đều **thiếu `psycopg`**. Đặt `QP_MODEL_PYTHON` để trỏ sang bản khác.

`load_model_outputs.py` có `--dry-run` để thử mà không ghi.

Trạng thái `quant` sau khi cả bốn chạy được:

| Bảng | Nguồn |
|---|---|
| `model_forecasts` | MSDP, horizon 5/20/60, khoảng 90% |
| `risk_metrics` | RARF-FHE (VaR/ES) + drawdown và biến động tính từ database |
| `risk_mc_distribution` | RARF-FHE `drawdown_probabilities` |
| `model_runs` | cả 4 mô hình, kèm `as_of` trong `note` |
| `market_state` | chưa map |
| `stock_rankings` | **không map được** — xem bên dưới |

DynamicGraph và RAEMF chỉ ghi `model_runs`, không ghi `model_forecasts`. Lý do
khác nhau: mạng lưới của DynamicGraph là tầng **mô tả**, đi tới website bằng
file chứ không qua schema này; còn payload `predict` của RAEMF không có xác
suất hướng đi lẫn khoảng hai phía, mà `model_forecasts` bắt buộc cả hai — suy
ngược `probability_up` từ một cái đuôi VaR một phía là bịa số.

`/api/v1/market/risk` đã trả 200 với dữ liệu thật thay vì 503.


### Bảng xếp hạng cổ phiếu của DynamicGraph

Trang `/models/dynamic-graph` có bảng xếp hạng 30 mã VN30 kèm hai biểu đồ, đọc
từ `frontend/public/research/dynamic-graph-nodes.json` — chính là
`artifacts/latest/nodes.json` mà model xuất ra.

Bảng xếp theo **vị trí trong mạng lưới liên kết**, không phải theo dự báo giá.
Cột gồm: mức ảnh hưởng (kèm thanh trực quan), điểm rủi ro, lợi suất 20 phiên,
biến động, mức giảm từ đỉnh — bấm nút để đổi tiêu chí sắp xếp. Kèm biểu đồ phân
tán *ảnh hưởng so với rủi ro* và bảng các cụm cổ phiếu mô hình tự tìm ra.

Đây là lựa chọn có chủ đích: model **không** sinh regime hay xác suất tăng theo
từng mã, nên bảng không giả vờ có. Xếp hạng dựa trên tầng mô tả — thứ mà chính
kiểm định của model ủng hộ (tỷ lệ cạnh tồn tại giữa hai phiên ≈ 0,90).

Làm mới sau khi chạy lại model:

```powershell
# trong models/dynamic-graph
python -m dynamicgraph.cli export-website --config config/local.yaml
# trong frontend
npm run research:sync
```

`export-website` chỉ ghi vào `artifacts/latest/` của model; bước `research:sync`
đưa file sang website và in ra `as_of` để phát hiện ngay nếu bản chép bị cũ.

### Vì sao `stock_rankings` vẫn rỗng

Bảng này cần `regime`, `probability_up`, `volatility`, `risk_state` cho **từng
mã** VN30. Không model nào sinh regime hay xác suất tăng theo mã.
DynamicGraph có `volatility_20d`, `current_drawdown` và các chỉ số trung tâm
mạng lưới theo mã, nhưng centrality không phải xác suất tăng giá. Ánh xạ chúng
sang nhau là bịa dữ liệu, nên bảng để trống và tab Cổ phiếu VN30 vẫn ẩn.

### Hai điều kiện chưa đạt để bật tab Rủi ro

Dữ liệu đã nằm trong database nhưng cờ `risk` trong `live-sections.ts` vẫn để
`false`, vì:

1. **Artifact tự chặn công bố.** `latest_forecast_summary.json` có
   `promotion_eligible: false` và `drawdown_calibration_status: experimental`.
   Giá trị này được ghi vào `quant.model_runs.note` để nhìn thấy được.
2. **Nội dung sai horizon.** `messages/*.json` mô tả biểu đồ là *"250 phiên
   tiếp theo"*, nhưng mô phỏng chạy ở **20 phiên** (`simulation.horizon` trong
   mọi config đều là 20). Phải sửa câu chữ hoặc lấy horizon từ dữ liệu trước
   khi hiển thị.

Tương tự, `show_forecast` của msdp vẫn `false`: artifact production hiện tại là
bản `quick` (8 trial, 2 fold, 1 seed) và README của MSDP ghi rõ model chưa vượt
baseline. Đường ống đã kiểm chứng chạy đúng — bật hay không là quyết định công bố.

### Ba lỗi đã sửa trong repo model

| Lỗi | Hậu quả | Sửa ở |
|---|---|---|
| `probability /= probability.sum()` trên mảng read-only | RARF-FHE crash giữa pipeline; đồng thời sửa tại chỗ mảng dùng chung của caller | `rarf-fhe/src/vnindex_model/importance_sampling.py` |
| `output_root` bị phớt lờ, root hardcode `Path(".")` | Mọi lần chạy thử ghi đè artifact chuẩn công bố trong repo | `rarf-fhe/src/vnindex_model/pipeline.py` |
| Pipeline không tạo thư mục output | `output_root` mới luôn lỗi `non-existent directory` | cùng file |

### Còn thiếu gì để B hoàn tất

- [ ] Chạy MSDP ở cấu hình đầy đủ để thay artifact `quick`.
- [ ] Chạy RARF-FHE tới khi `promotion_eligible: true`.
- [ ] Sửa câu chữ horizon của biểu đồ drawdown.
- [ ] Map `market_state` (regime từ RARF-FHE) — chưa làm.
- [ ] Đặt lịch chạy sau phiên, cùng chỗ với `backfill.py daily`.
- [ ] Bật cờ trong `frontend/config/live-sections.ts` sau khi bốn mục trên xong.

### Sai lệch rổ VN30 cần quyết định

`seed_catalogue.py` khai báo VN30 gồm BCM, BVH, POW; nhưng ingestion đang thu
thập DGC, LPB, VPL và không thu thập ba mã kia. Hệ quả: BCM, BVH, POW xuất
hiện trong `web.symbols` mà không có bất kỳ dữ liệu giá nào. Cần xác định danh
sách nào đúng với rổ VN30 hiện hành rồi đồng bộ hai bên.

## Tài liệu liên quan

- Database/pipeline: `database\README.md`
- Backend/API: `backend\README.md`
- API contract: `backend\API.md`
- Triển khai production: `backend\deploy\README.md`
- Frontend: `frontend\README.md`
