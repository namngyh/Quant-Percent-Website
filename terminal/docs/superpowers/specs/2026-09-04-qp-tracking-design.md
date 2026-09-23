# QP-TRACKING — Thiết kế

Ngày: 2026-09-04

## Mục tiêu

Nền tảng chạy local, một người dùng, để theo dõi / thử nghiệm / tối ưu chỉ báo
kỹ thuật trên dữ liệu Bitcoin. Người dùng thêm chỉ báo riêng bằng file Python và
thấy kết quả vẽ ngay trên chart, chỉnh tham số trực tiếp từ giao diện.

## Yêu cầu đã chốt

| Hạng mục | Quyết định |
|---|---|
| Triển khai | Web app chạy local, chỉ một người dùng |
| Nguồn dữ liệu | Binance public API (BTCUSDT). Bỏ vàng. |
| Khung thời gian | `1m, 5m, 15m, 1h, 4h, 1d` — full intraday |
| Lịch sử | Từ 2017 (nến BTCUSDT đầu tiên: 2017-08-17) |
| Realtime | Có — nhưng thuộc GĐ2 |
| Chỉ báo dựng sẵn | ~150+ từ thư viện, không viết tay từng cái |
| Chỉ báo tự viết | File `.py`, contract `calculate(df, params)` |
| Loại chỉ báo | Cả `overlay` (đè nến) lẫn `panel` (khung riêng) |
| Tham số | Chỉnh từ UI bằng slider, chart vẽ lại |
| Chiến lược | File Python `signals(df, indicators, params)` — GĐ3 |
| Backtest | Equity, tổng lợi nhuận, win-rate, profit factor, max drawdown, Sharpe, danh sách lệnh — GĐ3 |
| Tối ưu | Grid search theo dải tham số — GĐ3 |
| Chiều lệnh | Long + Short |

## Kiến trúc

```
Trình duyệt (Lightweight Charts v4 + JS thuần, không build step)
        │  REST JSON
FastAPI ─┼─ data/        Binance client, DuckDB store, backfill service
         ├─ indicators/  contract + catalog pandas-ta + plugin loader
         └─ api/         routes
        │
DuckDB (data_store/qp.duckdb)
```

### Phân kỳ

- **GĐ1 (bản này)** — dữ liệu, chart, chỉ báo dựng sẵn + plugin, chỉnh tham số live
- **GĐ2** — realtime WebSocket Binance
- **GĐ3** — strategy engine, backtest, optimizer

## Quyết định thiết kế & lý do

### Lưu trữ: DuckDB native table, không phải Parquet

Thiết kế ban đầu nói "DuckDB + Parquet". Khi triển khai đã đổi sang **bảng
DuckDB thuần**. Lý do: Parquet là immutable, không hợp với hai nhu cầu cốt lõi —
backfill tăng dần và (GĐ2) ghi đè liên tục cây nến đang hình thành. Bảng DuckDB
cho upsert, có ACID, vẫn quét hàng triệu dòng nhanh, và không cần tiến trình
server riêng.

Ghi bằng DELETE-then-INSERT thay vì UPSERT: lô nến mới thường chồng lấn nến đã
lưu (nến cuối luôn được tải lại vì có thể chưa đóng).

**Hệ quả phải chấp nhận:** DuckDB chỉ cho một tiến trình ghi. Vì vậy
`scripts/backfill.py` và `run.py` không chạy song song được; khi server bật thì
dùng endpoint `/api/backfill`.

### Thư viện chỉ báo: pandas-ta-classic

`pandas-ta` bản gốc đã bị gỡ khỏi PyPI cho Python < 3.12 (bản 0.4.x yêu cầu
≥3.12). Dùng **`pandas-ta-classic` 0.6.52** — fork được duy trì của nhánh 0.3.x,
chạy tốt với numpy 2.4 / pandas 3.0. Cho **193 chỉ báo**, catalog cuối còn
**185** sau khi loại:

- `beta`, `correl` — cần chuỗi giá thứ hai làm benchmark, ta chỉ có một symbol
- `vp` (volume profile) — chia bin theo *giá*, không phải theo thời gian, nên
  không có chuỗi một-giá-trị-mỗi-nến để vẽ lên trục thời gian
- 5 hàm không nhận đầu vào giá (helper nội bộ)

### Sinh tham số tự động

pandas-ta khai báo mặc định trong signature là `None` và giải quyết giá trị thật
bên trong thân hàm, nên introspection chỉ lấy được *tên* tham số. Giải pháp:
bảng `PARAM_DEFAULTS` mô tả ~45 tên tham số phổ biến (phân bố rất lệch —
`length` xuất hiện ở 124/193 chỉ báo). Tham số ngoài bảng **không hiện lên UI**
và để thư viện dùng mặc định của nó — chỉ báo vẫn chạy đúng, chỉ ít núm vặn hơn.

Cách này tránh viết tay 185 file mô tả, và tự động đúng cho chỉ báo mới khi
nâng cấp thư viện.

### Phân loại overlay / panel

Mặc định theo category của pandas-ta: `overlap` → overlay, còn lại → panel. Kèm
danh sách ngoại lệ `OVERLAY_EXTRAS` cho các chỉ báo cùng thang giá nhưng nằm ở
category khác (`bbands`, `kc`, `donchian`, `psar`, `supertrend`...). Kết quả:
57 overlay / 128 panel.

### Căn chỉnh chuỗi kết quả

Đầu ra chỉ báo phải khớp 1-1 với nến. Ba trường hợp phải xử lý riêng:

1. **Index thời gian** — reindex theo DatetimeIndex của nến
2. **Index vị trí** (`td_seq`) — reindex sẽ ra NaN toàn bộ *âm thầm*; phải phát
   hiện và căn theo vị trí
3. **Trả về tuple** (`ichimoku`) — lấy phần lịch sử, bỏ phần chiếu về tương lai

NaN và vô cực được chuyển thành `null` để chart **ngắt đường** thay vì vẽ xuyên
qua khoảng trống.

### VWAP cần DatetimeIndex

Chỉ báo nhạy thời gian (VWAP neo theo phiên) cần DatetimeIndex, trong khi DuckDB
trả về index vị trí. `prepare_frame()` gán index thời gian cho mọi lần compute.

### Endpoint đồng bộ, không async

`/api/candles`, `/api/indicators`, `/api/indicators/compute` khai báo `def` chứ
không `async def`. Chúng làm việc chặn (DuckDB + pandas); FastAPI chạy handler
đồng bộ trong threadpool. Nếu để `async def`, một backfill dài đang stream trên
event loop sẽ làm đơ toàn bộ giao diện.

### Contract chỉ báo

```python
INDICATOR = {
    "name": str,
    "type": "overlay" | "panel",
    "params":  {tên: {"type": "int"|"float"|"bool", "default":…, "min":…, "max":…}},
    "outputs": [{"key":…, "label":…, "color":…}],
}

def calculate(df, params) -> dict[str, Series] | Series | DataFrame
```

Một file plugin lỗi **không được làm sập nền tảng**: loader bắt lỗi từng file,
báo lên sidebar, các chỉ báo còn lại vẫn chạy.

Cho phép bật **nhiều thực thể của cùng một chỉ báo** (EMA 20 song song EMA 50):
mỗi lần thêm sinh một `instanceId` riêng với bộ tham số riêng.

### Đa panel với Lightweight Charts v4

v4 chưa hỗ trợ nhiều pane trong một chart. Mỗi chỉ báo `panel` được cấp một
instance chart riêng, đồng bộ với chart chính qua `subscribeVisibleLogicalRangeChange`
(có cờ chống vòng lặp phản hồi).

## Đã kiểm chứng

- 185/185 chỉ báo compute sạch trên dữ liệu BTC thật
- EMA-20 khớp chính xác giá trị tính tay; RSI nằm đúng dải 0–100
- Backfill idempotent: chạy lại không nhân bản dòng
- Backfill resume: sau khi bị cắt giữa chừng, WAL phục hồi 592k nến 1m nguyên vẹn
- Slider đổi tham số gọi đúng 1 lần recompute (debounce)
- Chuyển sang khung chưa có dữ liệu: xóa cả nến lẫn đường chỉ báo cũ
- Khóa backfill trả 409 khi có tiến trình đang chạy
