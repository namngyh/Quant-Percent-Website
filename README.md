# QP-TRACKING

Nền tảng chạy local để **theo dõi, thử nghiệm và tối ưu chỉ báo** trên dữ liệu Bitcoin.

- Dữ liệu OHLCV từ **Binance** (public API, không cần API key), lưu vào **DuckDB**
- Chart nến bằng **Lightweight Charts** (thư viện mã nguồn mở của TradingView)
- **187 chỉ báo** dùng ngay, tham số chỉnh trực tiếp bằng slider trên giao diện
- Thêm **chỉ báo riêng bằng file Python** — thả file vào `plugins/indicators/`

---

## Cài đặt

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Chạy

**Bước 1 — tải dữ liệu** (chạy khi server đang tắt):

```bash
.venv\Scripts\python.exe scripts/backfill.py -t 1h 4h 1d
```

**Bước 2 — mở nền tảng:**

```bash
.venv\Scripts\python.exe run.py
```

Trình duyệt tự mở ở http://127.0.0.1:8000

> **Lưu ý:** DuckDB chỉ cho phép **một tiến trình ghi** tại một thời điểm. Vì vậy
> `scripts/backfill.py` và `run.py` không chạy đồng thời được. Khi server đang chạy,
> hãy dùng nút **"Cập nhật dữ liệu"** trên giao diện thay cho script.

---

## Viết chỉ báo riêng

Tạo một file `.py` trong `plugins/indicators/`. Chỉ cần 2 thứ: một dict `INDICATOR`
mô tả chỉ báo, và một hàm `calculate`.

```python
INDICATOR = {
    "name": "RSI của tôi",
    "type": "panel",          # "overlay" = đè lên nến | "panel" = khung riêng bên dưới
    "params": {
        "period": {"type": "int", "default": 14, "min": 2, "max": 200},
    },
    "outputs": [
        {"key": "rsi", "label": "RSI", "color": "#aa00ff"},
    ],
}

def calculate(df, params):
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / params["period"]).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / params["period"]).mean()
    return {"rsi": 100 - 100 / (1 + gain / loss)}
```

Tải lại trang là chỉ báo xuất hiện trong mục **"của bạn (python)"**, kèm slider cho
mỗi tham số bạn khai báo.

**Quy tắc:**

| Thành phần | Ý nghĩa |
|---|---|
| `type` | `"overlay"` nếu cùng thang giá (EMA, Bollinger); `"panel"` nếu thang khác (RSI, MACD) |
| `params` | Mỗi tham số thành một slider. Kiểu: `int`, `float`, `bool` |
| `outputs` | Mỗi phần tử là một đường vẽ. `key` phải khớp key trả về từ `calculate` |
| `df` | DataFrame có cột `open, high, low, close, volume`, index là thời gian (UTC) |
| Trả về | dict `{key: Series}`, hoặc một Series/DataFrame |

Xem 2 file mẫu có sẵn: `example_ema_ribbon.py` (overlay) và `example_zscore.py` (panel).

Nếu file có lỗi, nền tảng **không sập** — lỗi hiện ở ô cảnh báo vàng trên sidebar,
các chỉ báo khác vẫn chạy bình thường.

---

## Cấu hình

Sửa `config.yaml`:

```yaml
data:
  symbols: [BTCUSDT]
  timeframes: ["1m", "5m", "15m", "1h", "4h", "1d"]
  start_date: "2017-01-01"
```

---

## Cấu trúc

```
backend/
  config.py            đọc config.yaml
  data/
    binance.py         client Binance (phân trang, retry, rate-limit)
    store.py           DuckDB: upsert / query nến
    service.py         điều phối backfill, tự resume
  indicators/
    base.py            contract chỉ báo (ParamSpec, OutputSpec, IndicatorSpec)
    builtin.py         bọc 185 chỉ báo pandas-ta-classic
    loader.py          nạp file .py của bạn
    registry.py        catalog hợp nhất + đường compute
  api/
    app.py             FastAPI + phục vụ frontend
    routes_data.py     /api/candles, /api/backfill, /api/coverage
    routes_indicators.py  /api/indicators, /api/indicators/compute
frontend/              giao diện (Lightweight Charts, không cần build)
plugins/indicators/    ← chỉ báo Python của bạn
data_store/qp.duckdb   database
```

---

## Trạng thái

**Giai đoạn 1 — xong.** Dữ liệu, chart, chỉ báo (dựng sẵn + plugin), chỉnh tham số live.

Giai đoạn tiếp theo:

- **GĐ 2** — realtime qua WebSocket Binance
- **GĐ 3** — chiến lược vào/ra lệnh bằng Python, backtest (equity, win-rate, max
  drawdown, Sharpe), tối ưu tham số bằng grid search
