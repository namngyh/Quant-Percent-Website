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
  bước ngẫu nhiên, suy diễn, Bayes) — kiểm tra xem kết quả có thật không
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
.venv\Scripts\python.exe tests/test_optimizer.py         # 12 checks - grid search
.venv\Scripts\python.exe tests/test_stream.py            # 9  checks - luồng realtime
.venv\Scripts\python.exe tests/test_paper.py             # 10 checks - paper trading
.venv\Scripts\python.exe tests/test_market_vn.py         # 20 checks - dữ liệu thị trường VN
```

Tổng 87 checks. `test_market_vn.py` có 11 kiểm tra chạy offline và 9 kiểm tra
cần VPN — phần cần VPN sẽ **báo bỏ qua** chứ không báo lỗi khi VPN tắt.

Mọi con số kỳ vọng trong `test_engine.py` đều được tính tay và ghi trong
comment. Một engine tính sai phí hoặc khớp lệnh sớm một nến vẫn cho ra đường
equity trông rất thuyết phục — đây là thứ ngăn cách giữa điều đó và kết quả
đáng tin.

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

### Phân tích chuỗi giá

| Nhóm | Kiểm định | Trả lời câu hỏi |
|---|---|---|
| Phân phối | Jarque–Bera, độ lệch, độ nhọn | Lợi suất có theo phân phối chuẩn không? |
| Rủi ro đuôi | VaR / CVaR 95% và 99% | Ngày tệ nhất trong 20 và trong 100 mất bao nhiêu? |
| Quá trình | ADF | Chuỗi có dừng không? |
| | Ljung–Box | Lợi suất có tự tương quan — tức có gì để khai thác? |
| | Hurst, tỷ số phương sai | Xu hướng, hồi quy trung bình, hay bước ngẫu nhiên? |
| | Ljung–Box trên \|lợi suất\| | Biến động có gom cụm không? |

### Kiểm định chiến lược

- **Suy diễn:** t-test một phía trên lợi suất từng lệnh — lợi thế quan sát được
  có khác 0 một cách có ý nghĩa, hay chỉ là may?
- **Bayes:** hậu nghiệm Beta–Nhị thức trên tỷ lệ thắng, kèm khoảng tin cậy 95%
  và xác suất tỷ lệ thắng thật vượt 50%. Bề rộng khoảng tin cậy là thứ mà một
  con số tỷ lệ thắng đơn lẻ che mất.

---

## Thông báo Telegram

Tuỳ chọn. Thêm vào `.env`:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Lấy token từ **@BotFather**; lấy chat id bằng cách nhắn cho bot rồi mở
`https://api.telegram.org/bot<TOKEN>/getUpdates`.

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
- **Nút i:** mọi chỉ báo và chiến lược đều có nút giải thích — đo cái gì, đọc
  thế nào, và điều dễ hiểu sai.

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
