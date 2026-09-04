# Quant Percent

Nền tảng chạy local để **theo dõi, thử nghiệm và tối ưu chỉ báo** trên dữ liệu
Bitcoin (Binance) và **chứng khoán Việt Nam** (HOSE, từ database của team).

- Dữ liệu OHLCV từ **Binance** (public API, không cần API key), lưu vào **DuckDB**
- Chart nến bằng **Lightweight Charts** (thư viện mã nguồn mở của TradingView)
- **189 chỉ báo** và **4 chiến lược** dùng ngay (gồm Bollinger Bands và vài mô hình ML đơn giản), tham số chỉnh trực tiếp bằng slider trên giao diện
- Thêm **chỉ báo riêng bằng file Python** — thả file vào `plugins/indicators/`
- **Backtest chiến lược** viết bằng Python, có phí và trượt giá, khớp lệnh không nhìn trước
- **Tối ưu tham số** bằng grid search hoặc random search, kèm cảnh báo overfit
- **Walk-forward validation**, **Monte Carlo** và **kiểm định thống kê** (phân phối,
  bước ngẫu nhiên, suy diễn) — kiểm tra xem kết quả có thật không
- **So sánh nhiều chiến lược** cạnh nhau, và **xuất CSV / PNG**
- **Nến realtime** qua WebSocket Binance, và **hot-reload** file `.py` khi bạn sửa
- **Paper trading** — chạy chiến lược tiến về phía trước trên dữ liệu thật, tiền ảo

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
.venv\Scripts\python.exe tests/test_optimizer.py         # 18 checks - grid search
.venv\Scripts\python.exe tests/test_stream.py            # 9  checks - luồng realtime
.venv\Scripts\python.exe tests/test_paper.py             # 10 checks - paper trading
.venv\Scripts\python.exe tests/test_market_vn.py         # 20 checks - dữ liệu thị trường VN
.venv\Scripts\python.exe tests/test_stats.py             # 38 checks - kiểm định thống kê
.venv\Scripts\python.exe tests/test_report.py            # 23 checks - báo cáo backtest
.venv\Scripts\python.exe tests/test_portfolio.py         # 31 checks - danh mục + Telegram
```

Tổng 179 checks. `test_market_vn.py` có 11 kiểm tra chạy offline và 9 kiểm tra
cần VPN — phần cần VPN sẽ **báo bỏ qua** chứ không báo lỗi khi VPN tắt.

Mọi con số kỳ vọng trong `test_engine.py` đều được tính tay và ghi trong
comment. Một engine tính sai phí hoặc khớp lệnh sớm một nến vẫn cho ra đường
equity trông rất thuyết phục — đây là thứ ngăn cách giữa điều đó và kết quả
đáng tin.

`test_stats.py` chạy trên chuỗi tổng hợp có tính chất **biết trước**: bước ngẫu
nhiên, AR(1) hồi quy trung bình, AR(1) xu hướng, GARCH. Điều quan trọng không
phải là các hàm trả về số, mà là chúng **không bác bỏ** trên dữ liệu không có
cấu trúc. Một bộ kiểm định chỉ chạy trên dữ liệu thị trường thật không phân
biệt được một kiểm định hoạt động đúng với một kiểm định luôn nói "có ý nghĩa".

`test_portfolio.py` không cần VPN: hàm phân tích nhận loader làm tham số, nên
nó chạy trên chuỗi giá tổng hợp có cấu trúc tương quan biết trước — đó là cách
duy nhất kiểm tra được đóng góp rủi ro, vì trên dữ liệu thật không có đáp án
độc lập để đối chiếu.

---

## Realtime & hot-reload

### Nến trực tiếp

Bấm nút **Realtime** ở góc trên bên phải. Chấm tròn chuyển xanh và nhấp nháy khi
luồng đang chạy; nến cuối trên chart tự cập nhật vài lần mỗi giây.

Cách hoạt động, và vì sao lại thế:

| Điểm | Cách xử lý |
|---|---|
| **Nến đang hình thành** | Đẩy thẳng lên chart, **không ghi database**. Binance cập nhật vài lần mỗi giây; ghi từng lần chỉ để lưu một con số sắp thay đổi là vô ích. |
| **Nến đóng** | Ghi vào DuckDB bằng cùng đường upsert với backfill, nên hai nguồn không thể lệch nhau. |
| **Chỉ báo** | Tính lại **khi nến đóng**, không phải mỗi tick. Giá trị chỉ báo chỉ có nghĩa khi nến chốt. |
| **Kết nối** | Một kết nối upstream cho mỗi khung đang xem; không còn ai xem thì đóng. Tự nối lại có backoff khi rớt mạng. |

Đổi khung thời gian thì luồng tự chuyển theo.

### Hot-reload

Khi realtime đang bật, sửa file trong `plugins/` là nền tảng **tự nạp lại**, không
cần F5. Thông báo nhỏ hiện ở dưới màn hình, chỉ báo trên chart vẽ lại với logic mới.

Đây là điểm khác biệt lớn nhất khi bạn đang loay hoay chỉnh một công thức: sửa
file, lưu, nhìn chart đổi.

---

## Paper trading

Chạy chiến lược **tiến về phía trước** trên dữ liệu thật với tiền ảo. Mục đích là
kiểm chứng xem backtest có nói thật hay không — nên nó dùng **đúng luật khớp lệnh
của backtest**: tín hiệu ở nến đóng, khớp ở giá mở nến kế tiếp, cùng phí và trượt
giá, cùng cách tính thanh lý.

Nếu hai bên khác luật thì chênh lệch kết quả chẳng nói lên điều gì về chiến lược.
Vì vậy có một kiểm thử tự động phát lại lịch sử qua cả hai và đối chiếu **từng
lệnh một** (`tests/test_paper.py`).

**Cách dùng:** tab *Chiến lược* → chọn chiến lược và tham số → **Chạy paper
trading**. Phiên xuất hiện ở tab *Paper*.

| Đặc điểm | Chi tiết |
|---|---|
| Chạy nền | Phiên **vẫn giao dịch khi bạn đóng trình duyệt** — nó tự giữ kết nối dữ liệu riêng |
| Sống sót restart | Trạng thái ghi vào DuckDB sau mỗi nến đóng; tắt server rồi bật lại, phiên tiếp tục nguyên vẹn |
| Khởi động ấm | Nạp 2 000 nến lịch sử để chỉ báo qua cửa sổ khởi động ngay từ đầu |
| Cập nhật | Vị thế và lãi/lỗ đẩy thẳng lên giao diện khi có nến mới, không cần bấm làm mới |
| Ký hiệu trên chart | Điểm vào/ra vẽ ngay trên nến, kể cả vị thế đang mở |

---

## Nhập file Python từ giao diện

Nút **Nhập .py** ở tab *Chỉ báo* và *Chiến lược*. Chọn file, hệ thống tự nhận biết
là chỉ báo hay chiến lược (qua `INDICATOR` hoặc `STRATEGY`), **kiểm tra trước khi
ghi**, rồi đặt vào đúng thư mục.

File lỗi bị từ chối kèm lý do và **không được ghi vào đĩa** — nếu không, thư mục
sẽ đầy file hỏng mà bạn phải tự dọn.

---

## Thị trường Việt Nam (HOSE)

Dữ liệu lấy **trực tiếp** từ TimescaleDB của team qua VPN, không sao chép về máy.
Cố ý như vậy: dữ liệu ghi liên tục trong phiên, DuckDB chỉ cho một tiến trình
ghi, và một bản sao cục bộ chỉ thêm việc phải đồng bộ mà không cho thấy gì hơn.

### Cài đặt

```bash
copy .env.example .env
```

Mở `.env`, điền mật khẩu vào `MARKET_DSN`. File này **đã được gitignore** — đừng
bao giờ viết mật khẩu vào mã nguồn.

Kiểm tra kết nối:

```bash
.venv\Scripts\python.exe scripts/check_market_db.py
```

> **Phải bật VPN của team (Tailscale).** Database không nghe trên Internet — đó
> là chủ ý. Báo timeout hoặc không tìm thấy máy chủ thì gần như chắc chắn là
> VPN chưa bật, không phải lỗi cấu hình.
>
> Nếu team dùng Tailscale, host là địa chỉ `100.x` của VPS (`tailscale status`
> để xem), không phải `10.10.0.1`.

### Cách dùng

Chọn mã ở ô Symbol trên thanh trên. Danh sách chia ba nhóm:

| Nhóm | Số mã | Khung thời gian |
|---|---|---|
| Crypto · Binance | 1 | `1m` → `1d`, có realtime |
| Việt Nam — có nến phút | 35 | `1m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `1d` |
| Việt Nam — chỉ nến ngày | 354 | `1d` |

Mã Việt Nam dùng tiền tố `VN:` (ví dụ `VN:VN30F1M`). Chỉ báo, backtest và tối ưu
chạy y hệt như với Bitcoin — engine không biết dữ liệu đến từ đâu.

### Ba điều đã mã hoá sẵn, để không tính sai

| Đặc điểm dữ liệu | Cách xử lý |
|---|---|
| **Không có dữ liệu tick** | Mức chi tiết nhất là nến 1 phút |
| **`v_history_1m` không có cột `is_final`** | Mọi truy vấn lọc `ts < date_trunc('minute', now())`, nên nến đang hình thành không bao giờ lọt vào tính toán |
| **`ts` lưu theo UTC** | Phiên VN 09:00–15:00 là 02:00–08:00 UTC; chỉ đổi múi giờ khi hiển thị |

Khung `5m`–`4h` được **gộp từ nến 1 phút ngay trên server** (chỉ `1m` và `1d` có
sẵn trong database), tránh kéo hàng trăm nghìn dòng qua VPN để gộp tại máy.

### Giới hạn

- Tài khoản **chỉ đọc**, chỉ thấy schema `api`. Nút "Cập nhật dữ liệu" và
  realtime tự khoá khi bạn chọn mã VN.
- Gặp `permission denied` thì **hỏi người quản trị**, đừng tìm đường vòng.
- Truy vấn giới hạn 30 giây (server cắt ở 60), luôn lọc theo mã và khoảng thời gian.

---

## Giờ hiển thị

Mọi thời gian trên biểu đồ là **giờ Việt Nam (GMT+7)** — có nhãn `GMT+7` trên
thanh trên. Việt Nam không đổi giờ theo mùa nên đây là con số cố định, chính xác
quanh năm.

Bên trong, mọi thứ vẫn lưu và so sánh theo **UTC** (cả Binance lẫn HOSE). Chỉ
lúc vẽ lên chart mới cộng offset. Nhờ vậy dữ liệu hai thị trường so được với
nhau, còn trục thời gian thì đọc theo giờ bạn giao dịch.

---

## Dữ liệu tự cập nhật đến đâu

| Nguồn | Cách hoạt động |
|---|---|
| **Bitcoin (Binance)** | Kho DuckDB chỉ tiến khi app đang chạy. Mở app lên, nó **tự đo xem thiếu bao nhiêu nến và tự bù** — không cần bấm "Cập nhật dữ liệu". Bật Realtime thì nến mới về qua WebSocket. |
| **Việt Nam (HOSE)** | Đọc thẳng database của team nên **không bao giờ lạc hậu**. Bật Realtime thì nền tảng hỏi database mỗi vài giây trong phiên và vẽ nến mới ngay khi nó được ghi. |

Chỉ khi thiếu quá 5 000 nến (nghỉ rất lâu) nền tảng mới dừng lại và mời bạn bấm
nút, vì lúc đó là một lần tải lớn nên để bạn chủ động.

> **Giới hạn của "realtime" với dữ liệu VN:** database không có dữ liệu tick,
> nến 1 phút là mức chi tiết nhất. Nên chart khung 1m nhích một lần mỗi phút —
> đó đã là mức nhanh nhất dữ liệu cho phép, hỏi dày hơn cũng không hơn được.

### Tốn tài nguyên bao nhiêu

Đo thực tế trên máy bạn khi đang chạy BTC 1m realtime **và** một phiên paper
trading:

| | |
|---|---|
| RAM | ~208 MB, ổn định (không tăng dần) |
| CPU | **0,3%** toàn máy (3,4% của một lõi) |
| Mạng | Vài KB/giây |

Nhẹ hơn một tab trình duyệt thông thường. Phần nặng là backtest và tối ưu, và
chúng chỉ chạy khi bạn bấm nút.

---

## Kiểm định kết quả

Ba công cụ ở tab *Chiến lược → Kiểm định*. Chúng cùng trả lời một câu hỏi: **con
số backtest kia đáng tin đến đâu?**

### Walk-forward

Tối ưu tham số trên một cửa sổ, rồi áp **nguyên bộ tham số đó** lên cửa sổ kế
tiếp — dữ liệu mô hình chưa từng thấy. Trượt cửa sổ, lặp lại.

Cột "Ngoài mẫu" là ước lượng trung thực duy nhất. Khoảng cách giữa trong mẫu và
ngoài mẫu chính là **cái giá của việc chọn tham số bằng hậu nghiệm**.

Cần nhiều nến: đặt *Candles* từ 5 000 trở lên để có 3–5 vòng. Dưới 3 vòng nền
tảng sẽ **từ chối kết luận** thay vì đưa ra nhận định từ một hai con số.

### Monte Carlo

Lấy chính các lệnh của chiến lược, xáo lại thứ tự hàng nghìn lần. Cái thay đổi
là may rủi, cái giữ nguyên là lợi thế — nên dải kết quả cho biết con số thật
nằm ở đâu trong vùng hợp lý, thay vì một điểm duy nhất dễ gây tự tin nhầm.

Báo cả **xác suất lỗ** và **xác suất mất trên 90% vốn**.

### So sánh

Chạy nhiều chiến lược trên **cùng nến, cùng phí, cùng khoảng thời gian** rồi
xếp bảng, có cả dòng mua-và-giữ để đối chiếu.

---

## Xuất kết quả

Hai nút **CSV** và **PNG** ở góc panel *Kết quả*:

- **CSV** — danh sách lệnh (giờ Việt Nam, giá vào/ra, lãi lỗ, lý do thoát). Sau
  khi so sánh, file gộp mọi chiến lược kèm cột phân biệt. Có BOM UTF-8 nên Excel
  mở tiếng Việt không lỗi font.
- **PNG** — ảnh biểu đồ đúng như đang hiển thị.

---

## Kiểm định thống kê

Tab *Chiến lược → Kiểm định* có hai nút riêng cho phần này. Chúng phân biệt
**cấu trúc thật** với **ngẫu nhiên trông giống cấu trúc** — chuỗi giá ngẫu nhiên
vẫn tạo ra xu hướng, mẫu hình và chiến lược trông có lãi.

Mỗi kiểm định trả về cùng một cấu trúc và hiện đủ trong nút **(i)** cạnh nó:
tên, giả thuyết H₀ và H₁ viết bằng lời, thống kê, bậc tự do, p thô, p đã hiệu
chỉnh, kết luận, và **giả định** mà kiểm định đó đứng trên. Một p-value không
kèm giả định là một con số không đọc được.

### Bốn điều làm cho phần này chặt chẽ

1. **Đa kiểm định.** Chạy 9 kiểm định ở α = 0.05 thì xác suất có ít nhất một
   kết quả "có ý nghĩa" do may rủi là 37%. Toàn bộ họ được hiệu chỉnh
   **Benjamini–Hochberg**, và cả hai cột p đều hiện. Trên BTC 1h thực tế, cột
   này đã lật kết luận: Ljung–Box p thô 0.041 (có ý nghĩa) → p hiệu chỉnh
   0.075 (không).
2. **Nói rõ đang chạy phiên bản nào.** Tỷ số phương sai có hai thống kê z —
   một giả định phương sai đồng nhất, một bền với phương sai thay đổi. Trên
   BTC 1h ở kỳ hạn q = 4, z đồng nhất là −2.35 (bác bỏ bước ngẫu nhiên) còn z
   bền là −1.32 (không bác bỏ). **Cả hai đều được báo cáo**, và kết luận đọc
   theo z bền.
3. **Không bác bỏ ≠ chấp nhận H₀.** ADF luôn đi kèm **KPSS**, vốn đảo ngược
   giả thuyết; bốn tổ hợp kết quả cho bốn kết luận khác nhau, trong đó có
   "dữ liệu không đủ để nói gì".
4. **Mỗi kiểm định tham số có một kiểm định phi tham số đi kèm.** Lợi suất
   hầu như không bao giờ theo phân phối chuẩn, nên kết luận không được phụ
   thuộc vào giả định đó.

### Phân tích chuỗi giá

| Nhóm | Kiểm định | Trả lời câu hỏi |
|---|---|---|
| Phân phối | Jarque–Bera, D'Agostino K² | Lợi suất có theo phân phối chuẩn không? |
| | Độ lệch, độ nhọn **kèm sai số chuẩn** | Lệch khỏi chuẩn có đáng kể, hay chỉ là nhiễu mẫu? |
| Rủi ro đuôi | VaR / CVaR 95% và 99%, kèm KTC bootstrap | Ngày tệ nhất mất bao nhiêu — và **có bao nhiêu quan sát** đỡ con số đó? |
| Tính dừng | ADF **và** KPSS | Chuỗi có dừng không, và hai kiểm định có đồng thuận không? |
| Cấu trúc | Ljung–Box | Lợi suất có tự tương quan — tức có hướng để khai thác? |
| | Hurst R/S **hiệu chỉnh Anis–Lloyd**, p-value hoán vị | Có bộ nhớ dài không? |
| | Tỷ số phương sai Lo–MacKinlay + **Chow–Denning** | Xu hướng, hồi quy trung bình, hay bước ngẫu nhiên? |
| Biến động | **Engle ARCH-LM** | Biến động có gom cụm không? |

Hai điểm kỹ thuật đáng nói, vì bản triển khai phổ biến hay làm sai:

- **Hurst.** Công thức `sqrt(std(diff))` lan truyền trên blog cho H ≈ 0.6 trên
  một chuỗi hoàn toàn ngẫu nhiên, và người đọc kết luận "có xu hướng" từ nhiễu.
  Ở đây dùng R/S trên đoạn không chồng lấn, trừ kỳ vọng Anis–Lloyd của chuỗi
  độc lập, và lấy p-value bằng **hoán vị chính chuỗi đó** — giữ nguyên phân
  phối biên, chỉ phá trật tự thời gian.
- **Biến động gom cụm.** Ljung–Box trên `|lợi suất|` là một xấp xỉ không có
  phân phối tới hạn chuẩn. Kiểm định đúng là **Engle ARCH-LM**, và đó là cái
  đang chạy.

### Kiểm định chiến lược

Ba cách hỏi cùng một câu, vì mỗi cách hỏng ở một chỗ khác nhau. Nếu chúng cho
kết luận khác nhau thì **bản thân điều đó là thông tin**: kết luận đang phụ
thuộc vào giả định chứ không phải vào dữ liệu.

| Kiểm định | Cần giả định gì | Khi nào tin |
|---|---|---|
| t một mẫu, một phía | Độc lập **và** xấp xỉ chuẩn | Mạnh nhất khi giả định đúng |
| Wilcoxon dấu-hạng | Đối xứng, không cần chuẩn | Khi phân phối lệch |
| **Hoán vị dấu** | Gần như không giả định gì | Đáng tin nhất — đọc cái này trước |
| Bootstrap BCa | Không giả định phân phối | Khoảng tin cậy cho lợi suất trung bình |

Kèm theo:

- **Lực kiểm định.** p = 0.30 trên 25 lệnh không nói "chiến lược vô dụng"; nó
  nói "25 lệnh không đủ để biết". Panel tính lực thật và số lệnh cần cho 80%.
- **PSR** (Bailey & López de Prado) — xác suất Sharpe thật > 0, có tính độ
  lệch và độ nhọn, nên **không** giả định phân phối chuẩn.
- **DSR — Sharpe khử phồng.** Đây là phần quan trọng nhất với một nền tảng có
  tính năng quét tham số. Chọn tổ hợp tốt nhất trong 2 000 tổ hợp là chọn cực
  đại của 2 000 biến ngẫu nhiên. Số tổ hợp của lần quét gần nhất được truyền
  thẳng vào, nên một Sharpe có PSR 94% có thể rơi xuống DSR 3% sau khi khử
  phồng — và con số thứ hai mới là con số đúng.
- **MinTRL** — cần bao nhiêu nến để Sharpe hiện tại đạt mức tin cậy 95%.

> **Bayes đã được gỡ bỏ.** Hậu nghiệm Beta–Nhị thức trên tỷ lệ thắng không còn
> trong nền tảng.

---

## Báo cáo backtest đầy đủ

Nút **Báo cáo** ở panel *Kết quả* mở một cửa sổ ở giữa trang, sáu tab, theo bộ
chỉ số của AmiBroker.

| Tab | Có gì |
|---|---|
| Tổng quan | Lãi ròng, CAR, **RAR** (lợi suất đã chia cho phơi nhiễm), CAR/MDD, Sharpe, đường vốn so với mua-và-giữ |
| Lệnh | **Tách riêng mua và bán**, hệ số lợi nhuận, kỳ vọng, tỷ lệ lãi/lỗ, chuỗi thắng/thua dài nhất |
| Rủi ro | Sụt giảm tối đa, **chỉ số Ulcer**, UPI, hệ số phục hồi, **hệ số K**, thời gian dưới đỉnh |
| Theo kỳ | Bảng lợi suất **năm × tháng**, chia kỳ theo giờ Việt Nam |
| Phân phối | Histogram lợi suất từng lệnh, tán xạ **MAE–kết quả** |
| Học máy | Xem tín hiệu như bộ phân loại hướng nến kế tiếp |

Ba con số đáng chú ý, vì chúng nói ra những thứ bảng tóm tắt giấu đi:

- **Tách mua/bán.** Rất nhiều chiến lược "hai chiều" chỉ kiếm tiền ở một
  chiều. Trên BTC 1h, `example_ema_cross` lãi +915 ở chiều mua và lỗ −837 ở
  chiều bán — bảng gộp chỉ hiện +78.
- **Lệnh lớn nhất chiếm bao nhiêu tổng lãi.** Nếu một lệnh là 57% lợi nhuận
  thì hệ số lợi nhuận đang mô tả một lần may, không mô tả chiến lược. Panel
  cảnh báo khi con số này vượt 40%.
- **MAE của lệnh thắng.** Đây là ngưỡng dừng lỗ không được vượt qua: đặt chặt
  hơn mức đó nghĩa là cắt đúng những lệnh lẽ ra có lãi.

### Đánh giá học máy

Áp dụng cho **mọi** chiến lược, không riêng chiến lược ML, vì nó tách hai thứ
mà lợi nhuận trộn lẫn: mô hình đoán đúng hướng bao nhiêu lần, và mỗi lần đúng
ăn được bao nhiêu.

- Độ chính xác, và **đường cơ sở** (luôn đoán lớp phổ biến hơn). So với 50% là
  sai — thị trường hiếm khi cân bằng 50/50.
- Kiểm định nhị thức một phía cho chênh lệch so với đường cơ sở.
- Precision / recall / F1 cho từng chiều, MCC, ma trận nhầm lẫn.
- Nếu chiến lược gán `df["ml_probability"]` trong `signals()` thì có thêm
  ROC-AUC, điểm Brier, log-loss và bảng hiệu chuẩn.

Trên BTC 1h, `example_ema_cross` đạt độ chính xác 48.5% so với đường cơ sở
50.4% — tức là nó **không** dự đoán được hướng. Lợi nhuận (khi có) đến từ độ
lớn của những lần đúng, không từ tần suất đúng. Đó là một sự thật mà con số
lợi nhuận một mình không bao giờ nói ra.

---

## Quant Portfolio

Panel **Danh mục** đo rủi ro thật của một rổ cổ phiếu Việt Nam đã nhập. Chuyển
từ tính năng cùng tên trên quantpercent.com; phần toán giữ nguyên.

Nguyên tắc: **mọi con số đều đo được từ lịch sử giá mà database có, hoặc bị bỏ
đi.** Không có lợi suất giả định, không có tương quan giả định. Mã nào không đủ
lịch sử thì được báo trong danh sách "không phân tích được", chứ không được gán
một con số trông hợp lý. Không có gì được lưu lại.

Con số quan trọng nhất là **đóng góp rủi ro**:

```
phần rủi ro của vị thế i  =  wᵢ · (Σw)ᵢ / (wᵀΣw)
```

Bạn đã biết mỗi mã chiếm bao nhiêu phần trăm *tiền*. Điều bạn không thấy là
một mã chiếm 25% tiền có thể chiếm 45% rủi ro, vì nó vừa biến động mạnh hơn
vừa đi cùng chiều với phần còn lại. Trên một danh mục thật, VIC chiếm 28.8%
tiền nhưng **63.1% rủi ro**.

| Tab | Có gì |
|---|---|
| Tổng quan | Giá trị, lãi/lỗ, mức rủi ro, beta, VaR/CVaR, và biểu đồ **tiền so với rủi ro** |
| Từng mã | Bảng đầy đủ, **sắp xếp theo rủi ro chứ không theo tiền** |
| Đa dạng hoá | HHI, số mã hiệu dụng, **số cược độc lập**, tương quan trung bình, cặp giống nhau nhất |
| Dự phóng | Bootstrap khối cho kỳ 1–12 tháng, kèm đường cong xác suất sụt giảm |

Hiệp phương sai dùng **co rút Ledoit–Wolf** về mục tiêu tương quan hằng số, có
số hạng `rho`. Bỏ `rho` — cách rút gọn phổ biến — làm cường độ co rút bão hoà ở
1.0 trên lợi suất ngày Việt Nam: mọi tương quan sụp về trung bình và ma trận
mất đúng cái cấu trúc panel này tồn tại để tìm. Cường độ co rút được hiện ra để
bạn biết bao nhiêu phần kết quả đến từ dữ liệu.

**Hai khác biệt so với bản trên quantpercent.com**, cả hai do quyền truy cập:

- **Không có ngành.** Bản gốc lấy ngành từ `web.symbols`; tài khoản đọc ở đây
  chỉ thấy schema `api`. Phần tỷ trọng theo ngành bị **bỏ hẳn** thay vì đoán
  ngành từ mã cổ phiếu.
- **Dự phóng tự tính.** Bản gốc mượn một lần chạy Monte-Carlo VN-Index của mô
  hình RARF-FHE rồi ánh xạ qua beta và căn bậc hai thời gian. Nền tảng này
  không có lần chạy đó, và mượn số của một mô hình không kiểm chứng được thì
  tệ hơn là tự mô phỏng — nên ở đây là **bootstrap khối tĩnh** (Politis–Romano)
  trên chính chuỗi lợi suất của danh mục.

  Lấy theo khối chứ không lấy từng ngày độc lập là có chủ ý: kiểm định ARCH gần
  như luôn bác bỏ giả thuyết biến động cố định, và lấy mẫu độc lập sẽ phá vỡ
  hiện tượng gom cụm, **đánh giá thấp có hệ thống** xác suất của những đợt sụt
  sâu. Giới hạn thật của nó — mô phỏng không bao giờ sinh ra cú sốc lớn hơn cú
  sốc lớn nhất đã từng có trong cửa sổ — được ghi ngay trên tab đó.

---

## Thông báo Telegram

Tuỳ chọn, và **cấu hình được ngay trên web**: panel *Paper* → khung *Thông báo
Telegram*. Nhập token và chat id rồi bấm **Lưu**.

1. Nhắn cho **@BotFather**, gõ `/newbot` — nó trả về token dạng `123456789:AA…`
2. Nhắn một câu bất kỳ cho chính bot vừa tạo
3. Mở `https://api.telegram.org/bot<TOKEN>/getUpdates`, lấy `message.chat.id`
4. Dán cả hai vào form rồi bấm **Lưu**, sau đó bấm **Gửi tin thử**

Token được ghi vào `.env` trên máy bạn (file này đã nằm trong `.gitignore` nên
không bao giờ lên git) và có hiệu lực ngay, không cần khởi động lại. Trang web
chỉ hiện lại token đã che — phần bí mật sau dấu hai chấm không bao giờ được gửi
về trình duyệt.

Vẫn có thể đặt thẳng trong `.env` như trước:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Nút **Lưu** kiểm tra token qua `getMe` **trước khi** ghi xuống — lưu một token
hỏng rồi báo lỗi sau sẽ để lại file chứa thứ không dùng được, và sự kiện paper
trading kế tiếp lặng lẽ thất bại. Token hợp lệ vẫn chưa chứng minh chat id
đúng; chỉ **Gửi tin thử** làm được việc đó.

Sau đó mỗi lần phiên paper trading vào hoặc đóng lệnh sẽ có tin nhắn. Bỏ trống
thì nền tảng **không gửi gì cả**, và Telegram hỏng cũng không làm phiên dừng.

> Không hỗ trợ WhatsApp: nó đòi tài khoản Business, xét duyệt mẫu tin nhắn và
> một nhà cung cấp trung gian — quá nặng cho một công cụ chạy trên máy cá nhân.

---

## Tuỳ chỉnh giao diện

- **Kéo giãn:** kéo đường phân cách giữa panel và biểu đồ, hoặc giữa biểu đồ
  giá và khung chỉ báo. Nhấn đúp để về mặc định. Kích thước được nhớ lại.
- **Đánh dấu sao:** bấm ☆ cạnh mã, chỉ báo hoặc chiến lược. Mục đã đánh dấu
  nổi lên nhóm riêng ở đầu danh sách.
- **Nút (i):** một popover dùng chung cho toàn bộ nền tảng. Nó gắn được vào
  bất cứ thứ gì — chỉ báo, chiến lược, từng ô cài đặt chi phí, từng chỉ số
  backtest, từng dòng trong bảng kiểm định thống kê. Với một chỉ số, nó nói đo
  cái gì, đọc thế nào, và **hỏng ở đâu**; với một kiểm định, nó nói H₀, H₁,
  thống kê, cả hai cột p, và giả định. Nút luôn hiện chứ không đợi rê chuột,
  vì một nút chỉ xuất hiện khi rê chuột thì trên màn hình cảm ứng là không tồn
  tại.

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
  strategy/
    engine.py          khớp lệnh, phí, đòn bẩy, thanh lý, MFE/MAE
    metrics.py         chỉ số tóm tắt
  analysis/
    stats.py           kiểm định thống kê (không Bayes)
    report.py          báo cáo kiểu AmiBroker + đánh giá ML
  portfolio/
    analytics.py       Quant Portfolio: Ledoit-Wolf, đóng góp rủi ro, bootstrap
  notify/telegram.py   thông báo + ghi cấu hình vào .env
  api/
    app.py             FastAPI + phục vụ frontend
    routes_data.py     /api/candles, /api/backfill, /api/coverage
    routes_indicators.py  /api/indicators, /api/indicators/compute
    routes_stats.py    /api/stats/series, /api/stats/strategy
    routes_portfolio.py   /api/portfolio/analyze
    routes_notify.py   /api/notify/status, /settings, /test
frontend/              giao diện (Lightweight Charts, không cần build)
  js/explain.js        popover (i) dùng chung + từ điển thuật ngữ
  js/report.js         cửa sổ báo cáo backtest
  js/portfolio.js      panel Quant Portfolio
plugins/indicators/    ← chỉ báo Python của bạn
data_store/qp.duckdb   database
```

---

## Trạng thái

Cả ba giai đoạn đã xong.

- **Giai đoạn 1.** Dữ liệu, chart, 187 chỉ báo (dựng sẵn + plugin), chỉnh tham số live.
- **Giai đoạn 2.** Nến realtime qua WebSocket Binance, hot-reload file `.py`.
- **Giai đoạn 3.** Chiến lược bằng Python, backtest có phí/trượt giá/thanh lý, tối ưu grid search.

### Dữ liệu hiện có

Toàn bộ 6 khung đã đủ từ 2017 tới nay — **6,12 triệu nến**, không có dòng trùng.

| Khung | Nến |
|---|---|
| `1m` | 4 751 106 |
| `5m` | 950 199 |
| `15m` | 316 740 |
| `1h` | 79 198 |
| `4h` | 19 816 |
| `1d` | 3 306 |

Bấm **"Cập nhật dữ liệu"** để kéo nến mới nhất cho khung đang xem.
