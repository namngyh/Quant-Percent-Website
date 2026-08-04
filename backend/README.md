# quantpercentBE — Public API cho quantpercent.com

Backend FastAPI phục vụ toàn bộ website: dữ liệu thị trường, đầu ra mô hình, báo cáo hiệu suất, tài khoản và biểu mẫu liên hệ. Thay thế lớp mock API đang chạy trong Next.js.

| Tài liệu | Dành cho |
|---|---|
| **[HUONG-DAN-CHAY.md](./HUONG-DAN-CHAY.md)** | Thành viên mới, không rành kỹ thuật — cài từ máy trắng đến khi mở được website |
| **[API.md](./API.md)** | Bản kê đầy đủ 28 endpoint: tham số, dữ liệu trả về, mã lỗi, rate limit |
| README này | Chạy dự án + tài liệu kiến trúc |

---

# Cách chạy dự án

## Đối chiếu với stack quen thuộc

Nếu bạn quen SQL Server + Visual Studio 2022 + VS Code, đây là bản đồ chuyển đổi:

| Bạn quen làm | Ở dự án này |
|---|---|
| SQL Server chạy nền như service Windows | PostgreSQL/TimescaleDB chạy trong Docker, thuộc repo `Database-Onr-Percent` |
| Connection string trong `appsettings.json` | `DATABASE_URL` trong file `.env` — **phải tự tạo** từ `.env.example` |
| Mở solution trong VS2022 rồi bấm chạy | Gõ lệnh `uvicorn app.main:app --reload` trong terminal (code vẫn mở bằng VS Code) |
| NuGet restore | `python -m venv .venv` + `pip install -r requirements-dev.txt` |
| EF Core `Update-Database` | `alembic upgrade head` |
| Sửa code xong phải build lại | Không cần — `--reload` tự nạp lại |
| FE `npm run dev` | Y hệt |

Ba khác biệt dễ vấp nhất:

1. **Backend không tự nối DB.** Không có IDE nào lo hộ. DB phải bật **trước**, và `DATABASE_URL` trong `.env` phải đúng. Nếu DB chưa bật, API vẫn khởi động bình thường nhưng `/readyz` báo lỗi và mọi endpoint dữ liệu trả 5xx.
2. **DB nằm ở repo khác** (`Database-Onr-Percent`), không nằm trong repo backend này.
3. **Có bước nạp danh mục (seed)** — danh sách model nằm trong config TypeScript của website, phải xuất ra JSON rồi nạp vào DB. Bên .NET không có bước tương đương.

Ba tầng, bật theo đúng thứ tự:

```
Website (3000)  ──►  Backend (8000)  ──►  PostgreSQL (5432) + Redis (6379)
quantpercent         quantpercentBE        Database-Onr-Percent
   npm                  uvicorn                docker compose
```

Chỉ muốn xem giao diện, không cần DB? Chạy `npm run dev` bên `quantpercent` với `.env.local` để trống là đủ — website tự dùng mock API. Không cần đọc tiếp phần dưới.

---

## A. Setup lần đầu (làm một lần, ~20 phút)

Cần sẵn: **Docker Desktop đang mở**, Node 20+, Python 3.12+. Nếu `docker` báo *"cannot find the file specified"* nghĩa là Docker Desktop chưa khởi động xong — mở app, đợi biểu tượng chuyển sang running.

### B1 — Bật database

```powershell
cd "D:\Quant Percent\Database-Onr-Percent"
copy .env.example .env
```

Mở `.env`, sửa 2 dòng:

```
POSTGRES_PASSWORD=<mật khẩu mạnh tự đặt>
DATAPRO_MODE=mock
```

`mock` để pipeline sinh dữ liệu giả lập, không cần app DataPro.Client.

```powershell
docker compose up -d
docker compose ps
```

Lần đầu Docker tải ảnh TimescaleDB (~300MB) nên mất vài phút. Xong bước này bạn có PostgreSQL ở `localhost:5432` và Redis ở `localhost:6379`.

### B2 — Tạo role riêng cho backend

Backend không dùng tài khoản superuser của ingestion — nó có role hạn chế quyền, chỉ đọc được qua các view đã kiểm duyệt.

```powershell
$env:QP_WEB_PASSWORD = python -c "import secrets; print(secrets.token_urlsafe(48))"
cd "D:\Quant Percent\Website QP\quantpercentBE"
Get-Content scripts\create_role.sql | docker exec -i qp-timescaledb psql -U quant -d market --set "api_password=$env:QP_WEB_PASSWORD"
```

Lệnh trên tự sinh mật khẩu URL-safe cho `qp_web`; ghi lại giá trị
`$env:QP_WEB_PASSWORD` để dùng ở B3. Kết quả đúng: `Role qp_web ready.`

> **Lưu ý cú pháp.** Comment ở đầu `scripts/create_role.sql` ghi lệnh theo kiểu bash và **không chạy được trên PowerShell** — dùng đúng lệnh ở trên. Hai điểm khác biệt: PowerShell không có toán tử `<` nên phải dùng `Get-Content | docker exec -i`, và **không** bọc mật khẩu trong nháy đơn (`"'mat-khau'"`) vì file SQL đã tự thêm nháy, bọc thêm sẽ làm mật khẩu thật chứa luôn ký tự `'`.

### B3 — Tạo file cấu hình cho backend

```powershell
cd "D:\Quant Percent\Website QP\quantpercentBE"
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Mở `.env`, sửa 3 dòng (giữ nguyên phần còn lại):

```
DATABASE_URL=postgresql+asyncpg://qp_web:<QP_WEB_PASSWORD>@localhost:5432/market
JWT_SECRET=<dán chuỗi vừa sinh ở trên>
CORS_ORIGINS=http://localhost:3000
```

Mật khẩu trong `DATABASE_URL` phải khớp `$env:QP_WEB_PASSWORD` ở B2.

### B4 — Cài thư viện và tạo bảng

```powershell
cd "D:\Quant Percent\Website QP\quantpercentBE"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:DATABASE_URL = "postgresql+asyncpg://quant:<POSTGRES_PASSWORD_B1>@localhost:5432/market"
.venv\Scripts\python.exe -m alembic upgrade head
Remove-Item Env:DATABASE_URL
```

Migration phải chạy bằng database owner `quant` vì nó tạo schema và các view.
Thay `<POSTGRES_PASSWORD_B1>` bằng mật khẩu ở B1. API chạy thường xuyên vẫn
dùng role giới hạn `qp_web` trong file `.env`.

`alembic upgrade head` tạo schema `web`, `quant`, `api` và 12 view. Nó **không đụng** vào bảng của ingestion nên an toàn kể cả khi DB đã có dữ liệu.

### B5 — Nạp danh mục model và báo cáo hiệu suất

```powershell
cd "D:\Quant Percent\Website QP\quantpercentFE"
npx tsx scripts/export-catalogue.ts
```

```powershell
cd "D:\Quant Percent\Website QP\quantpercentBE"
.venv\Scripts\python.exe -m scripts.seed_catalogue --frontend ../quantpercentFE
```

Kết quả đúng: `seeded 12 models and 3 performance reports`.

### B6 — Trỏ website sang backend

Mở `D:\VuaBip123\quantpercent\.env.local`, thêm dòng:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Để trống biến này = website dùng mock API nội bộ. Sửa xong **phải khởi động lại** `npm run dev` — Next.js chỉ đọc biến môi trường lúc khởi động.

---

## B. Chạy hàng ngày

Sau khi setup xong, mỗi ngày chỉ còn 3 việc — mở 3 cửa sổ terminal:

**1. Database** — mở Docker Desktop là xong. Compose đặt `restart: unless-stopped` nên container tự bật lại, giống SQL Server chạy nền. Kiểm tra bằng `docker ps`, phải thấy `qp-timescaledb`, `qp-redis`, `qp-ingestion`. Nếu chưa có:

```powershell
cd D:\VuaBip123\Database-Onr-Percent
docker compose up -d
```

**2. Backend**

```powershell
cd D:\VuaBip123\quantpercentBE
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Lệnh này gọi thẳng Python trong venv nên không cần `activate` — tránh luôn lỗi ExecutionPolicy của PowerShell chặn `Activate.ps1`. (Nếu bạn thích cách truyền thống: `.venv\Scripts\activate` rồi `uvicorn app.main:app --reload`.)

**3. Website**

```powershell
cd D:\VuaBip123\quantpercent
npm run dev
```

**Kiểm tra:**

| Địa chỉ | Mong đợi |
|---|---|
| http://localhost:8000/healthz | `{"status":"ok"}` |
| http://localhost:8000/readyz | `database: ok` |
| http://localhost:8000/docs | Swagger, xem và thử toàn bộ API |
| http://localhost:3000 | Website, tự chuyển sang `/vi` |

Kiểm tra toàn tuyến bằng script của website: `npx tsx scripts/check-api.ts http://localhost:8000`.

**Tắt:** Ctrl+C ở terminal website và backend → `docker compose stop` bên repo DB (giữ nguyên dữ liệu).

> `docker compose down` xoá container nhưng **giữ** dữ liệu. Chỉ `docker compose down -v` mới xoá sạch — cẩn thận với lệnh này.

---

## Sửa cái gì thì chạy lại lệnh gì

| Vừa sửa | Cần làm |
|---|---|
| Code Python trong `app/` | Không cần gì — `--reload` tự nạp lại |
| `.env` của backend | Ctrl+C rồi chạy lại `uvicorn` |
| `.env.local` của website | Ctrl+C rồi chạy lại `npm run dev` |
| `config/models.ts` / `config/strategies.ts` bên website | Chạy lại 2 lệnh ở **B5** |
| Có file migration mới trong `alembic/versions/` | `.venv\Scripts\python.exe -m alembic upgrade head` |

## Lỗi hay gặp

| Triệu chứng | Xử lý |
|---|---|
| `docker: command not found` hoặc `cannot find the file specified` | Docker Desktop chưa chạy. Mở app, đợi running, mở terminal mới |
| `password authentication failed for user "qp_web"` | Mật khẩu trong `DATABASE_URL` không khớp B2. Chạy lại B2 với mật khẩu mới |
| Website vẫn hiện dữ liệu mock | Chưa khởi động lại `npm run dev` sau khi sửa `.env.local` |
| `permission denied for schema public` | **Đúng thiết kế** — backend chỉ được đọc view `api.*`. Code mới gặp lỗi này thì phải thêm view, không phải cấp quyền |
| Đăng nhập được nhưng F5 mất phiên | Cookie không được gửi. Kiểm tra `CORS_ORIGINS` của backend khớp đúng origin của website |
| `429 Too Many Requests` khi đăng nhập | Chống dò mật khẩu: 5 lần/15 phút. Đợi hoặc dùng email khác |

Chi tiết mã lỗi của từng endpoint: xem **[API.md](./API.md#23-mã-lỗi)**.

## Bảng cổng

| Cổng | Dịch vụ |
|---|---|
| 3000 | Website (Next.js) |
| 8000 | Backend (FastAPI) |
| 5432 | PostgreSQL/TimescaleDB |
| 6379 | Redis |

## Trạng thái tích hợp website

- Production đặt `DATA_MODE=api` và `NEXT_PUBLIC_AUTH_MODE=api`.
- `API_BASE_URL` là địa chỉ FastAPI nội bộ cho Server Components.
- Browser gửi cookie bằng `credentials: "include"`; request thay đổi dữ liệu gửi
  kèm CSRF token.
- Mock gateway `app/api/v1/` được giữ cho phát triển offline. Caddy production
  route `/api/*` thẳng sang FastAPI nên mock không xuất hiện ngoài production.
- Bộ Compose/Caddy và checklist staging nằm trong `deploy/`.

---

# Tài liệu kỹ thuật

Ba repo phối hợp với nhau:

| Repo | Vai trò |
|---|---|
| `Database-Onr-Percent` | Pipeline dữ liệu (DataPro → TimescaleDB + Redis). **Sở hữu schema `public`** |
| `quantpercentBE` (repo này) | Public API. Sở hữu schema `web`, `quant`, `api` |
| `quantpercentFE` | Website Next.js |

## Kiến trúc

```
Browser ──► API (FastAPI) ──► Redis   : cache, rate limit
                          └─► Postgres/TimescaleDB (1 instance, 4 schema)
                                ├── public : ingestion sở hữu (ticks, bars, gap_log)
                                ├── quant  : model pipeline ghi (forecasts, market_state, risk)
                                ├── web    : repo này sở hữu (users, contacts, catalogue)
                                └── api    : view đã kiểm duyệt — role qp_web CHỈ đọc ở đây
```

Nguyên tắc: API **không có quyền** trên schema `public`. Mọi dữ liệu thị trường đi qua view `api.*` liệt kê cột tường minh, nên một cột mới trên bảng ingestion không thể vô tình bị công khai.

## Bề mặt API

Giữ nguyên hợp đồng website đang dùng, thêm auth:

| Nhóm | Endpoint |
|---|---|
| Market | `/api/v1/market/overview`, `/{symbol}/quote`, `/{symbol}/history`, `/vn30/constituents`, `/risk` |
| Models | `/api/v1/models`, `/{slug}`, `/{slug}/latest`, `/{slug}/history` |
| Performance | `/api/v1/strategies`, `/{slug}/performance`, `/{slug}/metrics`, `/{slug}/simulations` |
| System | `/api/v1/status`, `/data-freshness`, `/model-status`, `/healthz`, `/readyz` |
| Forms | `POST /api/v1/contact`, `/investor-interest` |
| Auth | `POST /api/v1/auth/{register,login,logout,refresh,forgot-password,reset-password,verify-email}`, `GET /auth/me` |

Hầu hết payload dữ liệu kèm khối freshness (`data_as_of`, `generated_at`, `source_status`, `is_stale`, `delay_minutes`) — trạng thái cũ được **suy ra từ mốc thời gian dữ liệu**, không phải khai báo tay. Ba ngoại lệ (`/models/{slug}`, vỏ ngoài của `/models/{slug}/latest`, và 3 endpoint system) được ghi rõ trong [API.md](./API.md#22-khối-freshness).

Chi tiết từng endpoint — tham số, trường trả về, mã lỗi, giới hạn tần suất: xem **[API.md](./API.md)**.

## Khoá model members-only

`web.models.access` là công tắc duy nhất:

- `public` — ai cũng xem được đầu ra.
- `members` — `/models` vẫn trả metadata kèm `locked: true`, còn `/{slug}/latest` và `/{slug}/history` trả **403** nếu chưa đăng nhập.

Đây mới là lớp khoá thật; hiệu ứng làm mờ trên website chỉ là trình bày.

## Auth

- Mật khẩu băm bằng **Argon2id**, không bao giờ ghi log.
- Phiên nằm trong cookie **httpOnly**: `qp_access` (15 phút) + `qp_refresh` (30 ngày, xoay vòng). Cookie CSRF đọc được để double-submit.
- Refresh token lưu **dạng hash**, theo family; dùng lại token đã xoay ⇒ thu hồi cả family.
- Đổi mật khẩu ⇒ thu hồi mọi phiên.
- Quên mật khẩu luôn trả cùng một phản hồi, dù email có tồn tại hay không.
- Rate limit: login 5/15 phút (theo IP **và** theo email), đăng ký 3/giờ, đặt lại mật khẩu 3/giờ, contact 5/10 phút. Redis chết thì rơi về bộ đếm trong tiến trình — **không** mở toang.

## Bảng mới thêm vào DB

Không sửa/xoá bảng nào của repo ingestion. Migration `0001` tạo:

- `web`: `users`, `refresh_tokens`, `one_time_tokens`, `audit_log`, `contacts`, `investor_interests`, `models`, `strategies` + cụm `report_*`, `symbols`, `index_constituents`, `trading_calendar`
- `quant`: `model_forecasts` (bản ghi §18 đầy đủ, hypertable), `market_state`, `risk_metrics`, `risk_mc_distribution`, `risk_scenarios`, `stock_rankings`, `model_runs`
- `api`: 12 view kiểm duyệt

**Vì sao thêm `quant.model_forecasts` thay vì dùng `predictions`:** bảng `predictions` hiện tại theo kiểu EAV (`label`/`value`) nên một dự báo phải tách thành ~12 dòng và không giữ được `interval_lower/upper`, `regime_probability`, `risk_score`, `model_version` một cách nhất quán. `predictions` được giữ nguyên cho model nội bộ.

## Việc phía model pipeline

Model ghi vào schema `quant` (API chỉ đọc):

| Bảng | Ai ghi | Dùng cho |
|---|---|---|
| `model_forecasts` | model | `/models/{slug}/latest`, `/history` |
| `market_state` | model | `/market/overview` |
| `risk_metrics`, `risk_mc_distribution`, `risk_scenarios` | model | `/market/risk` |
| `stock_rankings` | model | `/market/vn30/constituents` |
| `model_runs` | model | `/model-status` |

Khi giá trị thực tế đã biết, cập nhật `model_forecasts.actual_value` — API dùng nó để tính sai số và coverage của khoảng dự báo, và **chỉ** lấy các dòng đã có giá trị thực.

## Kiểm thử

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
```

`tests/test_contract.py` bảo vệ hợp đồng với website: đủ 26 endpoint, mọi payload có khối freshness, mọi metric đều nullable, và `ForecastRecord` **không** chứa trường cấm theo §18.

## Vận hành

- `/healthz` cho liveness, `/readyz` kiểm tra DB (bắt buộc) và Redis (chỉ suy giảm).
- Log JSON kèm `request_id` khi chạy production.
- Docker backend cài từ `requirements.lock`; cập nhật lock phải đi kèm chạy
  test và `pip-audit -r requirements.lock`.
- Worker (`app/workers/scheduler.py`) dọn token hết hạn, làm mới cache, cảnh báo feed đứng. Chạy bằng `python -m app.workers.scheduler` — luồng dev thường ngày không cần bật.
- Backup: dùng `scripts/backup.ps1` của repo DB, nhớ dump thêm schema `web`.

## Trạng thái hiện tại

Kiểm thử offline hiện có 42 test + lint. Kiểm thử tích hợp vẫn cần stack DB:
chạy `alembic upgrade head`, `seed_catalogue`, `deploy/preflight.sql`, rồi
`npm run check:api -- http://localhost:8000` để xác nhận migration, view và dữ
liệu seed thực tế.
