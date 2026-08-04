# QuantPercent — Data Pipeline VN30F1M

> **Vị trí local:** repository này nằm tại
> `D:\Quant Percent\Database-Onr-Percent`. Đây là mã nguồn database/pipeline.
> Dữ liệu PostgreSQL thật nằm trong Docker named volume `tsdb_data`, không
> mặc định nằm trong thư mục Git. Xem checklist và sơ đồ vận hành chung tại
> `D:\Quant Percent\README.md`.

## Trạng thái kiểm tra trên máy hiện tại

Tại ngày 04/08/2026 chưa thấy `.env`, `data/raw`, `backup`, `dockerdata` hoặc
Docker VHDX trên ổ D; PostgreSQL 5432 và Redis 6379 cũng không lắng nghe.
Do đó repository hiện nhìn thấy schema/code nhưng chưa xác nhận được dữ liệu
runtime. Không chạy `docker compose down -v`; hãy tìm volume và tạo `pg_dump`
trước khi thay đổi nơi lưu Docker.

Ingestion service là **kết nối duy nhất** tới DataPro. Model, website backend,
research chỉ đọc từ DB/Redis — không bao giờ chạm API.

```
DataPro.Client (app Windows = API server, cổng 6789, REST/CSV, ~2 req/s)
   │
   ├─ /api/symbols (bulk, MỌI mã)   poll 1s      ─► pseudo-tick cho cả watchlist
   └─ /api/data/minute/{symbol}     1 req/1.5s   ─► bar 1 phút chính thức
        xen kẽ ưu tiên: VN30F1M mỗi ~3s, mỗi cổ phiếu VN30 mỗi ~90s
   ▼
ingestion service
   ├──► TimescaleDB : ticks (hypertable) + bars_1m (hypertable) + ohlc_1m (cagg đối chiếu)
   ├──► Redis pub/sub: ticks:{symbol} + bars:{symbol}   ← model subscribe
   └──► Parquet     : data/raw/ticks/YYYY-MM-DD.parquet + data/raw/bars_1m/...
```

Watchlist cấu hình trong `.env`: `SYMBOLS` (ưu tiên — VN30F1M) và
`STOCK_SYMBOLS` (rổ VN30 + VN30INDEX). Nhờ quét bulk, thêm mã KHÔNG tốn thêm
request cho tick; chỉ bar phút quay vòng chậm dần theo số mã.
**Nhớ cập nhật `STOCK_SYMBOLS` khi HOSE đảo rổ VN30 (tháng 1 và 7 hằng năm)** —
lần gần nhất: từ 03/08/2026 bỏ TPB, PLX — thêm MCH, TCX.

Nguyên tắc cốt lõi: mỗi record được chuẩn hóa **một lần duy nhất**, rồi cùng
object đó publish Redis (trước, ưu tiên độ trễ) và ghi DB → dữ liệu model thấy
realtime **trùng 1:1** với DB, forward-test đối chiếu được với backtest.
Với bar: bản `final=true` trên Redis chính là dòng chốt trong `bars_1m`.

## Đặc thù DataPro (đã kiểm chứng thực tế 2026-07-23)

- DataPro.Client là app Windows **tự chạy API server** — app phải đang mở thì
  pipeline mới có dữ liệu. Ingestion trong container gọi qua
  `host.docker.internal:6789`.
- Gói hiện tại **không có tick thật** (`/api/data/tick` trả rỗng — cần DIAMOND).
  Pipeline dùng snapshot 1s làm pseudo-tick + bar phút chính thức.
- `TRADING_TIME` là **giờ VN encode dạng epoch** (bar "09:00" nghĩa là 9h sáng VN)
  — ingestion tự quy đổi, trong DB `ts` luôn là UTC thật.
- Response dạng CSV; auth `Authorization: Bearer {API_KEY}`; rate limit ~2 req/s
  (cấu hình poll mặc định dùng ~1.1 req/s).

## 1. Cài đặt

Yêu cầu: Docker + Docker Compose; DataPro.Client đang chạy trên máy host.

```bash
cp .env.example .env      # Windows: copy .env.example .env
# Mở .env, điền DATAPRO_API_KEY, đặt POSTGRES_PASSWORD mạnh,
# DATAPRO_MODE=datapro (hoặc mock để test không cần DataPro)
docker compose up -d --build
```

Lần đầu khởi động, TimescaleDB tự chạy `db/init/*.sql`. **Chỉ chạy khi volume
rỗng** — nếu sửa schema sau này phải migrate tay hoặc `docker compose down -v`
(mất dữ liệu!).

## 2. Vận hành

```bash
docker compose ps                       # trạng thái + healthcheck
docker compose logs -f ingestion        # log ingestion realtime
docker compose restart ingestion        # sau khi đổi .env
docker compose up -d --build ingestion  # sau khi sửa code ingestion/
```

## 3. Kiểm tra pipeline

```bash
pip install "psycopg[binary]" redis
python scripts/check_pipeline.py        # tick 5', gap, bar chính thức, đối chiếu chéo
python examples/model_subscriber.py     # xem tick + bar realtime như model sẽ thấy
```

Nối model hiện tại vào pipeline: thay đoạn gọi API DataPro bằng subscribe Redis
như `examples/model_subscriber.py`:
- Kênh `ticks:VN30F1M` — pseudo-tick ~1s, dùng cho feature độ trễ thấp
- Kênh `bars:VN30F1M` — bar phút; **chỉ act khi `final=true`** để khớp backtest

Query lịch sử: bảng `ticks`, `bars_1m` (lọc `is_final`), view `ohlc_1m`.
Model ghi dự báo vào bảng `predictions`.

## 4. Backup

```bash
# DB — dump logic (chạy được khi container đang chạy)
docker exec qp-timescaledb pg_dump -U quant -d market -Fc > backup_$(date +%F).dump
# Khôi phục: docker exec -i qp-timescaledb pg_restore -U quant -d market < backup_xxx.dump

# Parquet thô — chỉ cần copy thư mục
tar czf parquet_backup_$(date +%F).tar.gz data/raw/     # Linux
# Windows: Compress-Archive data/raw parquet_backup.zip
```

Cron hằng ngày: chạy `pg_dump` sau 15:00 (hết phiên) và rsync `data/raw/`.

## 5. Cấu trúc repo

| Đường dẫn | Vai trò |
|---|---|
| `docker-compose.yml` | 3 service: timescaledb, redis, ingestion |
| `db/init/*.sql` | Schema: ticks, bars_1m, ohlc_1m, gap_log, predictions, nén |
| `ingestion/sources.py` | SnapshotSource + MinuteBarSource (DataPro thật) + 2 mock |
| `ingestion/writer.py` | Redis → DB (tick batch / bar upsert) → Parquet |
| `ingestion/main.py` | 2 runner song song, backoff + gap_log riêng từng nguồn |
| `examples/model_subscriber.py` | Mẫu subscribe 2 kênh cho model |
| `scripts/check_pipeline.py` | Health check + đối chiếu chéo tick vs bar |
| `data/raw/` | Parquet theo ngày VN — restart giữa ngày tạo file `.partN` |
| `dockerdata/` | Đĩa ảo Docker (database thật trong `wsl/disk/docker_data.vhdx`). KHÔNG sửa/xóa tay; `C:\Users\<user>\AppData\Local\Docker\wsl` là junction trỏ vào đây |
| `backup/` | `scripts\backup.ps1` ghi dump DB + zip parquet, tự giữ 8 bản gần nhất |
| `ingestion/backfill.py` | Nạp/vá lịch sử: `python backfill.py [all\|daily\|minute]` (dừng ingestion khi chạy) |

## 6. Ghi chú thiết kế

- `ts` lưu `timestamptz` UTC; mọi hiển thị/logic giờ giao dịch dùng `Asia/Ho_Chi_Minh`.
- Chống trùng: ticks PK `(symbol, ts, seq)` + `ON CONFLICT DO NOTHING`;
  bars_1m PK `(symbol, ts)` upsert, `is_final` chỉ tiến không lùi.
- Mất kết nối DataPro → `gap_log(disconnect_ts, reconnect_ts, note)` ghi rõ
  nguồn nào đứt; backoff 1s→60s; service không bao giờ tự thoát.
- Pseudo-tick `ts` = thời điểm quan sát; `volume` = delta VOL giữa 2 lần poll.
  Ngoài giờ giao dịch snapshot không đổi → không có tick (đúng thiết kế).
- `ohlc_1m` (tự tính từ tick) tồn tại để **đối chiếu chéo** với `bars_1m`
  chính thức — lệch lớn nghĩa là poll bị rớt dữ liệu.
- Nâng cấp sau này: nếu mua gói DIAMOND (tick thật), thêm source mới đọc
  `/api/data/tick` — kiến trúc giữ nguyên.
