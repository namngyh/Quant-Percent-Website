# QP-TRACKING

Nền tảng chạy local để **theo dõi, thử nghiệm và tối ưu chỉ báo** trên dữ liệu Bitcoin.

- Dữ liệu OHLCV từ **Binance** (public API, không cần API key), lưu vào **DuckDB**
- Chart nến bằng **Lightweight Charts** (thư viện mã nguồn mở của TradingView)
- **187 chỉ báo** dùng ngay, tham số chỉnh trực tiếp bằng slider trên giao diện
- Thêm **chỉ báo riêng bằng file Python** — thả file vào `plugins/indicators/`
- **Backtest chiến lược** viết bằng Python, có phí và trượt giá, khớp lệnh không nhìn trước
- **Tối ưu tham số** bằng grid search, kèm cảnh báo overfit

---

## Chạy hằng ngày

**Lần đầu tiên (chỉ một lần):** nháy đúp **`setup.bat`** — tạo môi trường ảo và cài thư viện.

**Mỗi lần muốn dùng:** nháy đúp **`start.bat`**. Trình duyệt tự mở ở
http://127.0.0.1:8000. Đóng cửa sổ đen đó là tắt nền tảng.

Không cần gõ lệnh gì. Muốn tiện hơn: chuột phải `start.bat` → *Gửi tới* →
*Desktop (tạo lối tắt)*.

### Cập nhật dữ liệu

Dữ liệu **không tự cập nhật**. Khi muốn kéo nến mới nhất, bấm nút
**"Cập nhật dữ liệu"** ở góc trên bên phải — nó tải tiếp từ nến cuối cùng đã có,
cho đúng khung thời gian đang xem.

### Chạy bằng dòng lệnh (tuỳ chọn)

```bash
.venv\Scripts\python.exe run.py              # mở nền tảng
.venv\Scripts\python.exe run.py --reload     # tự khởi động lại khi sửa code backend
.venv\Scripts\python.exe scripts/backfill.py -t 1h 4h 1d   # tải hàng loạt
```

> **Lưu ý:** DuckDB chỉ cho phép **một tiến trình ghi** tại một thời điểm. Vì vậy
> `scripts/backfill.py` và `run.py` không chạy đồng thời được. Khi nền tảng đang bật,
> hãy dùng nút "Cập nhật dữ liệu" thay cho script.

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

## Viết chiến lược riêng

Tạo file `.py` trong `plugins/strategies/`. Chiến lược chỉ quyết định **nên
long, short hay đứng ngoài** ở mỗi nến — nó không đặt lệnh và không tính khối
lượng. Engine lo phần đó, nên mọi chiến lược đều được đo bằng cùng một thước.

```python
import pandas as pd

STRATEGY = {
    "name": "EMA Cross của tôi",
    "side": "both",                  # "long" | "short" | "both"
    "params": {
        "fast": {"type": "int", "default": 20, "min": 2, "max": 200},
        "slow": {"type": "int", "default": 50, "min": 3, "max": 400},
    },
}

def signals(df, params):
    fast = df["close"].ewm(span=params["fast"], adjust=False).mean()
    slow = df["close"].ewm(span=params["slow"], adjust=False).mean()

    out = pd.Series(0, index=df.index)
    out[fast > slow] = 1      # long
    out[fast < slow] = -1     # short
    out.iloc[: params["slow"]] = 0   # cửa sổ khởi động: đứng ngoài
    return out
```

Xem 2 file mẫu: `example_ema_cross.py` (thuận xu hướng) và
`example_rsi_reversal.py` (hồi quy trung bình, có lúc đứng ngoài thị trường).

### Backtest được thực hiện thế nào

Đây là các giả định mà **mọi con số kết quả đều dựa vào** — biết chúng thì mới
đọc kết quả cho đúng:

| Điểm | Cách xử lý |
|---|---|
| **Khớp lệnh** | Tín hiệu tính xong lúc nến `i` đóng → vào lệnh ở **giá mở nến `i+1`**. Không thể giao dịch bằng giá chưa nhìn thấy (không có look-ahead bias). |
| **Phí** | Tính cả hai chiều, trên notional. Mặc định 0.04% (taker Binance futures). |
| **Trượt giá** | Giá khớp bị làm xấu đi theo chiều bất lợi. Mặc định 0.02%. |
| **Vốn** | Mỗi lệnh ký quỹ `% vốn` hiện có, điều khiển `ký quỹ × đòn bẩy` notional. |
| **Thanh lý** | Vị thế đòn bẩy bị thanh lý **trong nến** khi lỗ chạm mức ký quỹ — kiểm tra bằng giá thấp nhất (long) / cao nhất (short), nên râu nến quét qua không bị bỏ sót. |
| **Vị thế** | Mỗi lúc chỉ một vị thế. Đảo chiều = đóng và mở lại trong cùng nến. |

Kết quả luôn hiển thị **mua-và-giữ** bên cạnh lợi nhuận chiến lược. Lãi 40%
trong giai đoạn mà chỉ cần giữ đã lãi 120% thực chất là thua lỗ.

### Tối ưu tham số

Tích ô bên trái tham số cần quét, đặt dải **Từ / Đến / Bước**, chọn chỉ số xếp
hạng rồi bấm **Chạy tối ưu**. Nhấn một hàng trong bảng để nạp bộ tham số đó và
chạy backtest đầy đủ.

Kết quả không chỉ đưa ô tốt nhất mà còn cho biết **bao nhiêu phần trăm tổ hợp
có lãi** và **trung vị**. Nếu chỉ vài phần trăm tổ hợp có lãi mà ô đứng đầu lại
vượt xa trung vị, nền tảng sẽ cảnh báo **overfit** — dáng đó thường là may mắn
chứ không phải lợi thế thật.

---

## Kiểm thử

```bash
.venv\Scripts\python.exe tests/test_engine.py            # 12 checks - engine backtest
.venv\Scripts\python.exe tests/test_metrics.py           # 9  checks - chỉ số hiệu năng
.venv\Scripts\python.exe tests/test_strategy_pipeline.py # 9  checks - toàn tuyến chiến lược
.venv\Scripts\python.exe tests/test_optimizer.py         # 12 checks - grid search
```

Mọi con số kỳ vọng trong `test_engine.py` đều được tính tay và ghi trong
comment. Một engine tính sai phí hoặc khớp lệnh sớm một nến vẫn cho ra đường
equity trông rất thuyết phục — đây là thứ ngăn cách giữa điều đó và kết quả
đáng tin.

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

### Đang làm dở (cập nhật 2026-09-04)

**Dữ liệu `1m` chưa tải hết.** Năm khung `5m, 15m, 1h, 4h, 1d` đã đủ tới hôm nay
(~3,12 triệu nến tổng cộng). Riêng khung `1m` mới tới **2020-12-21**, còn khoảng
3 triệu nến nữa.

Tiếp tục bằng một trong hai cách — an toàn, tự động chạy tiếp từ nến cuối:

```bash
.venv\Scripts\python.exe scripts/backfill.py -t 1m
```

hoặc mở nền tảng, chọn khung `1m`, bấm **"Cập nhật dữ liệu"**. Mất khoảng 20–25 phút.

### Giai đoạn tiếp theo — chưa bắt đầu

- **GĐ 2** — realtime qua WebSocket Binance; hot-reload file `.py` (hiện phải F5 trang)
- **GĐ 3** — chiến lược vào/ra lệnh bằng Python `signals(df, indicators, params)`,
  backtest (equity curve, win-rate, profit factor, max drawdown, Sharpe, danh sách
  lệnh), tối ưu tham số bằng grid search, long + short

**Chưa quyết:** làm GĐ2 hay GĐ3 trước. Khuyến nghị **GĐ3** — backtest và tối ưu là
giá trị cốt lõi; realtime chỉ có ý nghĩa khi đã có chiến lược để chạy.
