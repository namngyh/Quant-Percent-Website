# Quant Percent — vận hành và checklist trước khi thuê server

Tài liệu này là điểm bắt đầu chung cho ba phần của hệ thống:

Repository public chính:
`https://github.com/namngyh/Quant-Percent-Website`.

## Trạng thái dự án

**Giai đoạn hiện tại: code sẵn sàng dựng staging, chưa sẵn sàng public
production với dữ liệu thật.**

| Hạng mục | Trạng thái |
|---|---|
| Frontend Next.js | Production build, lint, typecheck và API smoke test đạt |
| Backend FastAPI | 42 test đạt; API, auth, model và performance contract đã đồng bộ |
| Database local | Schema/pipeline có sẵn; chưa kết nối được PostgreSQL/Redis runtime |
| 4 model mới | Trang nghiên cứu hoạt động; chưa có inference runner/forecast live |
| Triển khai | Compose, Caddy HTTPS, migration, seed, backup và preflight đã chuẩn bị |
| Điểm chặn public | Chưa backup/restore rehearsal và chưa test full stack với DB thật |

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
| Database và ingestion | `D:\Quant Percent\Database-Onr-Percent` |
| Backend FastAPI | `D:\Quant Percent\Website QP\quantpercentBE` |
| Frontend Next.js | `D:\Quant Percent\Website QP\quantpercentFE` |
| Mã nguồn và dữ liệu riêng của model | `D:\Quant Percent\models` |

## Database ở ổ D nghĩa là gì?

Thư mục `Database-Onr-Percent` ở ổ D chứa **mã nguồn schema và pipeline**.
PostgreSQL runtime được `docker-compose.yml` lưu trong named volume
`tsdb_data`; nó không tự động nằm bên trong repository. Nếu Docker Desktop
được chuyển data-root sang ổ D thì dữ liệu thật thường nằm trong một file
`docker_data.vhdx` hoặc thư mục Docker riêng trên ổ D.

Tại lần kiểm tra ngày 04/08/2026, trong repository chưa có `.env`,
`data/raw`, `backup` hoặc `dockerdata`; cổng PostgreSQL 5432 và Redis 6379
không mở, và lệnh Docker chưa khả dụng. Vì vậy chưa thể truy vấn số dòng,
dung lượng hoặc xác nhận volume PostgreSQL thật từ workspace này.

Dữ liệu CSV trong `D:\Quant Percent\models\...\data` là dữ liệu nghiên cứu
của từng model, không phải database PostgreSQL phục vụ website.

Không xóa Docker volume, không chạy `docker compose down -v`, và không sửa
trực tiếp file VHDX. Luôn tạo `pg_dump` trước khi di chuyển database.

## Vận hành hiện tại

### Trạng thái thực tế trên máy lúc kiểm tra

- PostgreSQL, Redis, ingestion, FastAPI và frontend chưa chạy thành một stack.
- Không có service lắng nghe ở cổng 5432/6379 và CLI Docker chưa khả dụng.
- Frontend vẫn chạy độc lập được ở mock mode, nhưng khi đó dữ liệu hiển thị
  không được đọc từ PostgreSQL local.
- Muốn kiểm tra chế độ database thật phải khởi động database, chạy migration
  và seed, sau đó chạy backend trước khi đặt frontend ở `DATA_MODE=api`.

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

## Cách chạy local sau khi Docker đã sẵn sàng

```powershell
cd "D:\Quant Percent\Database-Onr-Percent"
Copy-Item .env.example .env
# Điền DATAPRO_API_KEY và các mật khẩu trong .env
docker compose up -d --build
docker compose ps
docker compose logs -f ingestion
```

Sau đó chạy backend và frontend theo README của từng repository. Kiểm tra:

```powershell
python scripts\check_pipeline.py
curl.exe http://localhost:8000/readyz
cd "D:\Quant Percent\Website QP\quantpercentFE"
npm run check:api -- http://localhost:8000
```

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

- [ ] Xác định đường dẫn vật lý của Docker volume/database trên ổ D và ghi
  lại vào tài liệu này.
- [ ] Khởi động Docker/PostgreSQL/Redis và xác nhận container healthy.
- [ ] Chạy `scripts\check_pipeline.py`; xác nhận tick/bar mới và không có gap
  bất thường.
- [ ] Tạo `pg_dump` và bản sao `data/raw`; lưu thêm một bản ngoài máy local.
- [ ] Khôi phục thử bản dump vào database test riêng. Backup chưa restore thử
  thì chưa được xem là backup hợp lệ.
- [ ] Chạy migration `alembic upgrade head`, seed catalogue và kiểm tra 12
  model/3 report trên database thật.
- [ ] Chạy
  `Website QP\quantpercentBE\deploy\preflight.sql` để lấy dung lượng DB,
  row count và thời điểm dữ liệu mới nhất sau migration/seed.
- [ ] Chạy frontend với `DATA_MODE=api` và kiểm tra toàn bộ API với FastAPI,
  không dùng mock.

### Quyết định kiến trúc trước khi mua server

- [ ] Chọn cách đưa dữ liệu mới lên server: máy Windows local luôn bật và kết
  nối VPN, Windows VPS riêng cho DataPro, hoặc ingestion gateway có xác thực.
- [ ] Không public PostgreSQL 5432 hoặc Redis 6379 ra Internet.
- [ ] Chọn TimescaleDB image tag cố định sau khi restore thử thành công.
- [ ] Chỉ chọn dung lượng ổ đĩa server sau khi có kết quả `preflight.sql` và
  tốc độ tăng dữ liệu thực tế.
- [ ] Chuẩn bị domain, DNS, ba secret độc lập, email provider và nơi lưu backup
  ngoài server.
- [ ] Thiết lập backup tự động, cảnh báo feed stale, giám sát `/readyz` và
  diễn tập rollback trước khi đổi DNS production.

## Tài liệu liên quan

- Database/pipeline: `Database-Onr-Percent\README.md`
- Backend/API: `Website QP\quantpercentBE\README.md`
- API contract: `Website QP\quantpercentBE\API.md`
- Triển khai production: `Website QP\quantpercentBE\deploy\README.md`
- Frontend: `Website QP\quantpercentFE\README.md`
