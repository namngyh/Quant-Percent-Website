# Quant Percent — hướng dẫn làm việc

File này Claude Code tự đọc mỗi phiên. Nó có hai phần: **nguyên tắc** (Claude
phải tuân theo) và **báo cáo** (Claude ghi lại phát hiện của từng phiên, để Nam
đọc mà không cần lục lại hội thoại).

---

## 1. Dự án

Nền tảng nghiên cứu chỉ báo và chiến lược giao dịch, chạy local, một người dùng.

- **Backend:** Python 3.11, FastAPI, DuckDB (Bitcoin/Binance), TimescaleDB qua
  VPN Tailscale (cổ phiếu Việt Nam / HOSE, chỉ đọc, schema `api`).
- **Frontend:** JavaScript thuần, không build step, TradingView Lightweight
  Charts 4.2.3 (vendored).
- **Ngôn ngữ giao diện:** Việt/Anh, chuyển được không cần tải lại trang.

```bash
.venv\Scripts\python.exe run.py                 # chạy, mở http://127.0.0.1:8000
.venv\Scripts\python.exe tests/test_engine.py   # từng file test chạy độc lập
```

Không có test runner: mỗi file test là một script tự chạy, in `N passed, M failed`.
Chạy hết:

```bash
for %f in (tests\test_*.py) do .venv\Scripts\python.exe %f
```

---

## 2. Nguyên tắc làm việc

Những điều dưới đây rút ra từ các lỗi đã thực sự xảy ra trong dự án này, không
phải quy tắc chung chung.

### 2.1 Đo, đừng đoán

Mỗi khi sửa một lỗi, phải **tái hiện được nó bằng số liệu trước khi sửa** và đo
lại sau khi sửa. Đã có lần một bản sửa trông hợp lý mà **không thay đổi gì cả**
(`update({time})` với whitespace bị Lightweight Charts bỏ lặng lẽ) — chỉ phát
hiện ra vì có phép đo, không phải vì đọc lại code.

Khi báo cáo, đưa con số trước/sau. "Đã sửa" mà không có số đo là chưa đủ.

### 2.2 Giả thuyết sai thì nói ra

Trong một đợt kiểm tra, giả thuyết "Monte Carlo đánh giá thấp sụt giảm" hoá ra
**ngược lại** (56,65% so với 24,72% thật). Nếu phép đo bác bỏ giả thuyết của
Claude, hãy ghi điều đó vào báo cáo thay vì lặng lẽ đổi hướng.

### 2.3 Không sửa hàng loạt bằng regex mà không soát lại

Một lần thay em dash bằng regex có `\s+` đã **nối các dòng lại với nhau**, làm
nát comment và chuỗi nối ngầm trong Python. Quy tắc:

- Sao lưu trước khi chạy script sửa hàng loạt.
- Chỉ khớp khoảng trắng trong một dòng (` +`), không bao giờ `\s+`.
- **In toàn bộ before/after ra để soát**, rồi sửa tay những chỗ đọc chưa xuôi.

### 2.4 Frontend không được rẽ nhánh theo văn bản

Panel Thống kê từng chọn màu bằng cách so khớp chuỗi tiếng Việt của kết luận.
Khi chuỗi đó thành cặp `{vi, en}`, cả panel ném lỗi và **không hiện gì**, trong
khi request vẫn trả 200 và console không báo lỗi.

Backend phải trả một **mã ổn định** (`verdict.code`) và frontend rẽ nhánh theo
mã. Văn bản chỉ để hiển thị.

### 2.5 Trạng thái phải hỏi được, không chỉ được thông báo

Nhãn realtime từng kẹt ở "Đang nối" vì `stream_status` chỉ phát **một lần** lúc
luồng dựng xong; client nối vào sau không bao giờ nghe được. Bất cứ trạng thái
nào client cần biết đều phải có đường **hỏi lại**, không chỉ có đường phát.

### 2.6 Con số hiển thị hai chữ số thập phân phải đáng tin tới đó

Hệ số K từng chia cho sai số chuẩn cỡ `1e-17` (nhiễu dấu phẩy động trên đường
vốn phẳng) và in ra `-0.07` — một con số bịa, trông y hệt con số thật. Mọi mẫu
số suy ra từ phần dư, phương sai hay độ phân tán cần một **ngưỡng tương đối**
so với thang dữ liệu, không phải phép so với 0.

### 2.7 Nói ra giới hạn thay vì để người đọc tự phát hiện

Đây là nền tảng nghiên cứu định lượng: một con số không kèm giả định là một con
số không đọc được. Mỗi chỉ số/kiểm định phải kèm:

- đo cái gì,
- đọc thế nào,
- **hỏng ở đâu** (phần hay bị bỏ qua nhất và là phần tốn tiền nhất).

Chỗ nào không đo được thì nói "không đo được", không lấp bằng giá trị trông hợp lý.

### 2.8 Phạm vi

Làm đúng việc được yêu cầu. Nếu phát hiện việc khác đáng làm, **báo cáo** chứ
không tự mở rộng. Nếu một phần bị chặn, làm xong phần còn lại và nói rõ phần
nào bỏ lại và vì sao.

---

## 3. Quy ước kỹ thuật bắt buộc

### 3.1 Ngữ nghĩa khớp lệnh — không đổi nếu không có yêu cầu rõ ràng

Mọi kết quả backtest đứng trên các giả định này:

- Tín hiệu ở nến `i` khớp ở **giá mở nến `i+1`**. Không bao giờ khớp ở giá mà
  chiến lược đã nhìn thấy.
- Phí hai chiều trên giá trị danh nghĩa; trượt giá luôn theo hướng bất lợi.
- Mỗi vị thế đặt `size_pct` vốn hiện tại làm ký quỹ, điều khiển
  `ký quỹ × đòn bẩy` giá trị danh nghĩa.
- Thanh lý **trong nến** khi lỗ chạm ký quỹ, kiểm tra theo giá thấp nhất (mua)
  hoặc cao nhất (bán).
- Một vị thế tại một thời điểm; đảo chiều đóng và mở lại trong cùng nến.

### 3.2 Song ngữ

Văn bản backend sinh ra (kết luận thống kê, giả định, ghi chú) trả về cặp
`bi(vi, en)` → `{"vi": ..., "en": ...}`. Frontend mở bằng `tp()`.

Chuỗi frontend dùng một lần thì viết `L('tiếng Việt', 'English')` ngay tại chỗ.
Nhãn dùng nhiều nơi thì đặt key trong `frontend/js/i18n.js`.

Test `every narrative field carries both languages` chặn việc thêm chuỗi một
ngôn ngữ.

### 3.3 Bất biến căn chỉnh biểu đồ

Các pane chỉ báo là **biểu đồ riêng** đồng bộ theo **chỉ số**, nên mọi chuỗi
phải có đúng một điểm mỗi nến. Pane thiếu nến không cuộn sang phải xa được →
thư viện kẹp phạm vi → toàn bộ nội dung pane bị đẩy ngang (đo được 180px cho 30
nến thiếu).

Kiểm tra: `ChartManager.alignment()` trong console → `{aligned: true}`.

**Hai hành vi của Lightweight Charts 4.2.3, không có trong tài liệu:**

- Điểm whitespace **giữ chỗ** trên thang chỉ số, nhưng **không** xuất hiện
  trong `data()` hay `dataByIndex()`. Đếm điểm sẽ báo pane đúng là rỗng.
- Whitespace truyền vào `update()` bị **bỏ lặng lẽ**; cùng điểm đó trong mảng
  `setData()` thì giữ chỗ. Sửa bằng `update({time})` sẽ trông như chạy mà
  không làm gì.

### 3.4 Nút (i)

Một popover dùng chung (`frontend/js/explain.js`). Nút **luôn hiện**, không đợi
rê chuột — nút chỉ hiện khi hover thì trên màn hình cảm ứng là không tồn tại.
Thêm chỉ số nào thì thêm (i) cho chỉ số đó trong cùng lần sửa.

### 3.5 Bảo mật

- `.env` chứa `MARKET_DSN` và token Telegram, đã gitignore. **Không bao giờ**
  viết mật khẩu vào mã nguồn hay commit.
- Database VN **chỉ đọc**, chỉ schema `api`, chỉ qua VPN Tailscale. Gặp timeout
  thì hỏi Nam kiểm tra VPN, **không đi sửa thứ khác**. Gặp `permission denied`
  thì báo lại, không tìm đường vòng.
- Token Telegram trả về trình duyệt luôn ở dạng đã che.

### 3.6 Dữ liệu thị trường Việt Nam

- Không có dữ liệu tick; mức chi tiết nhất là nến 1 phút.
- `api.v_history_1m` **không có** cột `is_final` → dòng mới nhất có thể là nến
  chưa đóng. Luôn bỏ dòng cuối hoặc lọc `ts < đầu phút hiện tại`.
- Cột `ts` là **UTC**. Phiên VN 09:00–15:00 = 02:00–08:00 UTC.
- Giá niêm yết theo **nghìn đồng** (VIC 256.1 = 256 100 đ).

---

## 4. Báo cáo

Ghi theo thứ tự mới nhất trước. Mỗi mục: phát hiện gì, đo được gì, đã sửa chưa.

### 2026-09-11 — Chọn/xoá từng hình vẽ, và cắt lỗ / chốt lời cho lệnh tay

**258 test Python + toàn bộ render check.**

#### 1. Công cụ vẽ bị "dính", và không xoá được một hình

Hai lỗi trong một, và cái thứ nhất gây ra cái thứ hai.

Tôi cho công cụ **giữ nguyên** sau khi vẽ xong một hình, với lý do "vẽ năm mức
giá là năm cú nhấp thay vì năm lần đi lại thanh công cụ". Đó là đánh đổi sai:
nó có nghĩa là **mọi** cú nhấp sau đó lại vẽ thêm một hình — kể cả cú nhấp bạn
định dùng để chọn hình vừa vẽ. Vẽ mười hình rồi muốn xoá hình thứ năm thì thậm
chí không trỏ vào nó được. Vẽ là việc thỉnh thoảng, nhìn biểu đồ là việc liên
tục, nên trạng thái nghỉ phải là con trỏ.

Giờ: vẽ xong thì tự về con trỏ. Bấm vào một hình là **chọn** nó (đường dày lên,
hiện các điểm neo), rồi `Delete` hoặc nút xoá trên thanh công cụ. Nút chỉ bật
khi thật sự có hình đang chọn, và tooltip của nó khi chưa chọn nói luôn phải
làm gì.

Một chi tiết dễ hỏng: phím `Delete` bỏ qua khi con trỏ đang ở trong ô nhập —
nếu không, xoá lùi một ký tự trong ô tìm mã sẽ lặng lẽ xoá mất một hình vẽ ở
sau lưng.

#### 2. Zoom khi đổi mã — **đã chạy đúng**, và tôi sai ba lần khi đi tìm

Đo trên chính app đang chạy, ở chế độ giao dịch:

| | Phạm vi hiển thị |
|---|---|
| sau khi vào Giao dịch | 1820–2006 → **186 nến** |
| sau khi đổi BTCUSDT → VN:VNINDEX | 1217–1403 → **186 nến** |
| sau khi đổi khung thời gian | **186 nến** |

Nó giữ zoom. **Ba giả thuyết của tôi đều sai**, ghi lại cả ba theo §2.2:

1. *"Pane chỉ báo phát phạm vi của nó ngược lên biểu đồ chính"* — sai, pane đã
   nhận phạm vi của biểu đồ chính **trước khi** vào nhóm đồng bộ.
2. *"`fitAll` chạy trước khi biểu đồ được resize sang bề rộng mới"* — đảo thứ
   tự lại, đo lại: không đổi.
3. *"`fitAll` không có tác dụng"* — **chính phép đo của tôi mới là thứ hỏng**.
   Lần `setVisibleLogicalRange` đầu tiên sau đó trả về **2019 nến dù tôi chỉ
   xin 300**, nghĩa là fit đã tính đúng toàn bộ dải từ trước, chỉ là Chrome
   headless chưa vẽ lại nên tôi đọc phải giá trị cũ.

Giữ lại thay đổi thứ tự resize rồi mới fit vì nó đúng hơn về nguyên tắc (bề
rộng đo được: 775px ở chế độ làm việc so với 1161px ở tổng quan), nhưng
**không** nhận là nó sửa được gì.

Nếu Nam vẫn thấy chưa zoom: nhiều khả năng đang đổi mã trong **chế độ Tổng
quan**, nơi hiện toàn bộ lịch sử là cố ý. Bấm **Giao dịch** rồi đổi mã thì nó
zoom sẵn.

#### 3. Cắt lỗ / chốt lời cho lệnh đặt tay

Gắn được lúc đặt lệnh, hoặc gắn/sửa/gỡ sau khi vị thế đã mở
(`POST /api/paper/{id}/exits`).

**Khớp trong nến, ở đúng mức đã đặt**, cùng chỗ với kiểm tra thanh lý và cùng
lý do: lệnh chờ khớp khi giá **chạm** tới nó, không phải khi nến tình cờ đóng
qua nó. Đo: nến `O100 H101 L94 C99` với cắt lỗ 95 khớp ở **95.0000**, không
phải 99. Không cộng thêm trượt giá, vì mức đó đã là trường hợp xấu nhất người
dùng tự chọn.

**Một nến chạm cả hai mức thì cắt lỗ thắng.** Từ OHLC không có cách nào biết
cái nào đến trước — nến chỉ nói giá đã đi qua cả hai, không nói theo thứ tự
nào. Vậy nên lựa chọn là đoán có lợi hay đoán bất lợi, và một tài khoản giấy tự
giải quyết mập mờ của chính nó theo hướng có lợi thì dạy sai bài học. Cùng lý
do với việc trượt giá luôn bất lợi (§3.1).

**Mức đặt sai phía bị từ chối**, kèm mã ổn định: cắt lỗ **trên** giá vào của
lệnh mua không phải là cắt lỗ — nó khớp ngay ở nến sau và ghi vào nhật ký một
khoản lãi mang nhãn "stop loss". Kiểm theo **giá khớp** chứ không phải giá cuối
cùng, nếu không sẽ từ chối nhầm một lệnh vốn hợp lệ.

Mức được **xoá cùng vị thế**: một mức còn sót lại sẽ kích hoạt trên vị thế kế
tiếp, vốn không phải vị thế nó được đặt cho. Ô để trống nghĩa là *không đặt*,
không phải 0 — 0 là một mức giá không bao giờ chạm tới, khác hẳn với việc không
có mức nào.

### 2026-09-10 (khuya) — Mười hai kiểu biểu đồ, và bộ công cụ vẽ

**240 test Python + toàn bộ render check + 25 check kiểu biểu đồ.**

*Bối cảnh môi trường:* giữa phiên, Windows **Smart App Control** chuyển sang
trạng thái cưỡng chế và chặn các `.pyd` không ký của pandas, psycopg và
pydantic_core — nhật ký Code Integrity ghi đúng ba file đó, Event 3118. Không
phải lỗi code: file không đổi từ 4/9 và cùng bộ test đã chạy được một giờ trước
đó. Nam đã tắt Smart App Control (`VerifiedAndReputablePolicyState` 1 → 0) và
mọi thứ nạp lại bình thường. Lưu ý cho sau này: **tắt là một chiều**, Windows
không cho bật lại nếu không cài lại máy.

#### 1. Mười hai kiểu vẽ giá

Lightweight Charts 4.2.3 chỉ có **năm** loại series — candlestick, bar, line,
area, baseline, histogram — còn menu cần **mười hai**. Bảy kiểu còn lại là năm
loại đó được cấu hình hoặc **nạp dữ liệu khác đi**, và các phép suy đó không
hiển nhiên từ API nên đã ghi hẳn vào đầu `frontend/js/chart-types.js`:

| Kiểu | Dựng bằng |
|---|---|
| Nến rỗng | candlestick với thân **tăng** trong suốt; thân giảm vẫn đặc — đó mới là quy ước |
| Đường bậc | line với `lineType: 1` (WithSteps) |
| Đường có điểm | line với `pointMarkersVisible` |
| Vùng HLC | **ba** series: area cho close, hai đường mảnh cho high/low — thư viện không có primitive dạng dải |
| Các cột | histogram trên thang giá, tô màu theo close **hôm trước** (chiều cao đã là giá rồi, hướng phải đến từ chỗ khác) |
| Đỉnh–Đáy | bar với `openVisible: false` |
| Heikin Ashi | tính từ OHLC rồi nạp vào candlestick — làm mượt nằm ở **dữ liệu**, không phải ở kiểu vẽ |

Đổi kiểu là vẽ lại, không gọi lại API, và **giữ nguyên phạm vi đang xem**: đổi
cách vẽ không phải lý do để mất chỗ người dùng đang cuộn tới.

**Một cái bẫy đã xử lý:** `updateCandle` trước đây luôn gửi điểm OHLC. Series
đường **từ chối** điểm OHLC, nên nếu để nguyên thì biểu đồ sẽ **ngừng cập nhật
ngay khi ai đó chọn Đường** — im lặng, không lỗi nào ở console. Giờ mỗi kiểu tự
khai báo cách nhận một nến sống.

**Kiểm chứng chạy trong trình duyệt thật, không phải jsdom.** Lightweight Charts
vẽ lên canvas và đo layout thật nên jsdom không chạy được nó. `tests/test_chart_types.html`
dựng **cả mười hai** kiểu trên chính bản thư viện đang ship, nạp dữ liệu, rồi
đẩy thêm **một nến sống** — vì "lúc tôi viết thì chạy" chỉ chứng minh đúng cái
kiểu đang hiện trên màn hình.

*Hai lần assertion của tôi sai, ghi lại theo §2.2:*

- "HA ít đổi chiều hơn chuỗi gốc" — **fail**, nhưng vì fixture của tôi sai:
  chuỗi có drift 0.8 lớn gấp đôi nhiễu 0.4 nên **không nến nào** đóng ngược xu
  hướng, chẳng có gì để làm mượt. Tôi đang đo cái fixture chứ không đo công
  thức. Trên chuỗi răng cưa thật: **59 lần đổi chiều → HA còn 1**.
- "HA không bao giờ làm chuỗi choppy hơn" — cũng **fail**, và lần này *tôi sai
  chứ không phải fixture*: trên chuỗi có một cú đảo chiều gắt, gốc đổi chiều 1
  lần, HA đổi 2. Đó là HA chạy **đúng**: open của nó là trung điểm nến HA
  *trước*, nên nó trễ, và ở cú quay gắt độ trễ sinh ra đúng một nến chuyển
  tiếp. Làm mượt nhiễu và trễ ở điểm đảo chiều là **cùng một cơ chế nhìn từ hai
  phía** — một bộ làm mượt không bao giờ thêm lần đổi chiều nào thì không làm
  mượt gì cả. Đã đổi sang khẳng định đúng: độ trễ tốn **nhiều nhất một** lần.

#### 2. Bộ công cụ vẽ

Lightweight Charts không có công cụ vẽ, nên đây là một canvas phủ lên biểu đồ.
Điều duy nhất làm nó hoạt động được là **neo mọi hình theo toạ độ biểu đồ** —
một thời điểm và một mức giá — rồi mới đổi sang pixel lúc vẽ:

```
timeScale().timeToCoordinate(time)  ->  x
series.priceToCoordinate(price)     ->  y
```

Neo theo pixel thì đơn giản hơn nhiều và **sai hoàn toàn**: hình sẽ trượt khỏi
nến ngay khi ai đó cuộn, phóng to, đổi kích thước cửa sổ hay đổi khung thời
gian. Neo theo toạ độ biểu đồ thì nó dính chặt vào đúng những cây nến đã vẽ lên
— và đó chính là toàn bộ lý do người ta vẽ lên biểu đồ thay vì lên ảnh chụp.

Chín công cụ: con trỏ, đường xu hướng, đường ngang, tia, đường dọc, chữ nhật,
**Fibonacci thoái lui**, chữ, và **thước đo** (in ra cả % lẫn số nến — "cách bao
xa" trên biểu đồ là hai câu hỏi). Cộng nam châm (bám O/H/L/C của nến), khoá,
ẩn/hiện, hoàn tác, xoá hết.

**Ba chi tiết dễ hỏng, đều đã xử lý:**

- Lớp canvas **chỉ nhận con trỏ khi đang có công cụ vẽ** hoặc khi con trỏ đang
  ở trên một hình. Để nó nhận mãi thì nó nuốt mọi thao tác kéo và phóng to của
  biểu đồ bên dưới — công cụ chạy tốt còn biểu đồ thì như bị đơ.
- Kéo một hình dịch **mọi** điểm neo cùng một lượng, nên hình giữ nguyên hình
  dạng: kéo một bộ Fibonacci không được đồng thời co giãn nó.
- Điểm nào có thời gian đã trôi ra ngoài dải đã nạp thì `timeToCoordinate` trả
  `null`; vẽ với toạ độ null thì **không vẽ gì và cũng không báo gì**, nên hình
  đó bị bỏ qua tường minh.

Hình lưu trong `localStorage` theo **mã + khung thời gian**. Đó là ghi chú về
một chuỗi cụ thể; hiện đường xu hướng vẽ trên BTC 1h lên VIC ngày còn tệ hơn là
làm mất nó.

### 2026-09-10 (tối) — Đổi mã vẫn giữ zoom, và ô nhập của Quant Portfolio

#### 1. Khung nhìn đi theo chế độ, không theo lần nạp dữ liệu

`setCandles` luôn gọi `fitContent()` — đúng cho chế độ tổng quan, sai cho chế độ
làm việc. Đổi mã trong khi đang giao dịch là nạp dữ liệu mới, nên nó ném người
dùng về hai nghìn nến rộng vài pixel và phải zoom lại từ đầu **mỗi lần đổi mã**.

Chế độ đã biết nó muốn khung nhìn nào; việc nạp dữ liệu không được quyền ghi đè.
Giờ `setCandles` fit toàn bộ khi ở tổng quan và gọi `focusRecent()` khi ở chế độ
làm việc, nên đổi mã, đổi khung thời gian hay bù nến đều giữ nguyên cách đóng
khung.

#### 2. Ô nhập của Quant Portfolio

Hai ô số trên mỗi dòng vị thế đang là hộp 6px sắc cạnh nằm trong một thẻ 16px —
đọc như thứ sót lại từ một thiết kế khác. Giờ bo `10px`, bỏ viền, đặt trên nền
xám nhạt: ô đọc như một **khe** trong dòng chứ không phải một thẻ nổi trên thẻ.
Khi focus thì nền trắng lại và viền xanh hiện ra, nên vẫn rõ đang gõ ở đâu.

Ô mã là một tiêu đề tình cờ sửa được, nên focus vẽ một gạch dưới thay vì đóng
khung nó lại. Ô tiền mặt và hai ô chọn cùng nhận độ bo đó để cả panel đọc như
một bộ điều khiển chứ không phải hai.

### 2026-09-10 (chiều) — Zoom sẵn, sàn theo mã, Quant Portfolio, splash

**249 test Python + toàn bộ render check.**

#### 1. Vào "Giao dịch" là biểu đồ đã zoom sẵn

Chế độ tổng quan cố ý hiện **toàn bộ** lịch sử; mang nguyên phạm vi đó sang chế
độ làm việc nghĩa là mở ra với hai nghìn nến bị nén còn vài pixel mỗi cây, và
việc đầu tiên ai cũng phải làm là zoom vào — mỗi lần.

`focusRecent(180)` đưa đầu mới nhất lên màn hình ở bề rộng nến đọc được. Đếm
theo **số nến** chứ không theo hệ số zoom: lượng lịch sử hợp lý là một con số
nến, không phải một tỷ lệ — 180 cây là một màn hình đọc được dù chuỗi có 500
hay 20 000 cây. Quay lại tổng quan thì `fitAll()` trả về toàn bộ.

#### 2. Không hỏi sàn nữa khi sàn đã biết

Mở phiên tay trên VN30F1M mà vẫn bày ra "Binance Futures — taker" không phải là
thừa một lựa chọn vô hại: đó là giao diện hỏi một câu chỉ có một đáp án, và cho
phép người dùng trả lời sai. Danh sách sàn giờ **lọc theo mã**:

| Mã | Sàn được chào |
|---|---|
| `BTCUSDT` | Binance Futures taker / maker / Spot |
| `VN:VIC` | HOSE — cổ phiếu |
| `VN:VN30F1M` | Phái sinh VN (VN30F) |

Thêm preset **phái sinh VN** vì hợp đồng tương lai khác cổ phiếu ở hai điểm
thật: bán khống được, và chạy trên ký quỹ. Thị trường một sàn thì ô chọn bị vô
hiệu hoá — không giả vờ mời một quyết định không tồn tại. Phiên HOSE được nói
thẳng là **không bán khống được**, nên mọi lệnh BÁN chỉ là đóng vị thế mua.

*Một lỗi thiết kế của tôi lộ ra khi test:* quy tắc đầu của tôi là "giữ lựa chọn
cũ nếu còn áp dụng được, kể cả Tự đặt". Nhưng "Tự đặt" mang theo phí gõ tay, và
phí Binance gõ tay **không phải** mặc định hợp lý cho một phiên HOSE — một phiên
VN sẽ lặng lẽ mở bằng chi phí crypto mà không có ghi chú sàn nào. Giờ chỉ giữ
lựa chọn cũ khi **cùng thị trường**; đổi thị trường là bắt đầu lại từ sàn của
thị trường đó. Đã có test cho đúng tình huống này.

#### 3. Quant Portfolio

Các vị thế trước đây là tám thẻ rời, mỗi thẻ một viền, một shadow và một hiệu
ứng nhấc lên khi rê chuột. Tám hộp nổi trong một panel 344px là rất nhiều cạnh
cho rất ít nội dung — và đó là những shadow **duy nhất còn sót lại** trong giao
diện, mọi thứ khác đã chuyển sang phân tách bằng một đường kẻ mảnh.

Giờ là **một danh sách có viền, các dòng ngăn nhau bằng kẻ mảnh**, đúng hình
dáng phần còn lại của ứng dụng dùng cho một chuỗi thứ cùng loại. Mỗi dòng mở
đầu bằng **huy hiệu màu** giống hệt phiên paper — gọi `Paper.symbolBadge` chứ
không viết lại, vì toàn bộ giá trị của huy hiệu là *một mã một màu ở mọi nơi*;
hai bản sao của hàm băm và bảng màu sẽ lệch nhau ngay lần sửa đầu tiên.

*Bản đầu của tôi sai và ảnh chụp cho thấy:* tôi xếp ô số lượng nằm **cạnh** mã
và bọc biến thể xếp chồng trong `@media (max-width: 1080px)`. Đó là đo sai đại
lượng — panel rộng cố định 344px ở **mọi** bề rộng cửa sổ, nó không nở ra khi
cửa sổ nở. Không có màn hình nào mà mã, hai ô số có nhãn và nút xoá vừa trên
một dòng. Đã bỏ hẳn biến thể đó: badge + mã + nút xoá ở hàng trên, hai ô số ở
hàng dưới.

#### 5. Màn hình mở đầu

- **Logo TradingView không còn hỏng.** Cái SVG trước là tôi tự phỏng theo dấu
  hiệu của họ và nó render ra một hình méo. Phỏng theo thương hiệu người khác
  bằng tay là sai hai lần: nó trông như lỗi, và một logo sai còn tệ hơn không
  có logo. Giờ là **wordmark chữ có link tới tradingview.com** — đúng thứ giấy
  phép Lightweight Charts yêu cầu.
- **Logo QP to hơn**: 84px → 132px.
- **Chậm lại để chạy hết hiệu ứng**: dấu hiệu vẽ 0,78s, tên hiện ở 1,05s, thanh
  ở 1,35s, dòng ghi công ở 1,6s — trước đây màn hình bắt đầu rời đi ở 1 250ms,
  tức là phần tử cuối vẫn đang hiện dần thì cả màn hình đã tan. Giờ chờ 2 100ms.
  Khởi động chỉ tốn ~100ms trong số đó (các request chậm đã ra khỏi đường tới
  hạn), nên splash vốn đã phải đợi — đợi đúng độ dài là miễn phí.

### 2026-09-10 — Realtime mặc định, splash mới, thanh trên gọn lại, và một cái ratchet cho i18n

**249 test Python + toàn bộ render check.**

#### 1. Realtime bật sẵn cho mọi mã

Trước đây phải bấm nút mới chạy, nên nền tảng mở ra với một biểu đồ đã lặng lẽ
dừng ở lần chạy trước — và nó trông không khác gì một biểu đồ đang chạy. Giờ
`Live.setEnabled(true)` ngay lúc khởi động, cả hai thị trường (Binance đẩy,
database HOSE hỏi vòng).

#### 2. Lỗi kéo biểu đồ tổng quan lại nhảy vào chế độ giao dịch

Lỗi tôi tạo ra ở đợt trước. Trình duyệt bắn `click` sau **mọi** chuỗi
nhấn–kéo–thả trên cùng một phần tử, nên cử chỉ kéo về quá khứ để nạp lịch sử và
cử chỉ rời trang là **cùng một sự kiện**. Giờ so vị trí `pointerdown` với
`pointerup`: lệch quá 5px là kéo, không phải bấm.

#### 3. Thanh trên

- **Bỏ ô số nến khỏi thanh trên.** Từ khi vuốt trái tự nạp lịch sử, nó không
  còn quyết định thứ bạn nhìn thấy mà chỉ quyết định một lần *chạy* dùng bao
  nhiêu dữ liệu — cùng loại lựa chọn với khoảng ngày, nên nó chuyển xuống panel
  Chiến lược. Để nó ở trên còn khiến **cùng một con số hiện hai lần**, một ở ô
  chọn và một ở dòng trạng thái ngay cạnh giá.
- Thêm hai vạch ngăn: 12 điều khiển trong một hàng phẳng đọc như 12 thứ ngang
  nhau; ba nhóm thì đọc như ba.
- *Lỗi bố cục tìm được khi đo DOM thật:* `.topbar-controls { flex: 1 1 auto }`
  nuốt hết chỗ trống và bóp dòng trạng thái về **0 chiều rộng**, nên số nến
  biến mất hẳn. Đổi thành `flex: 0 1 auto` — nhóm bên phải vốn đã được
  `margin-left: auto` đẩy sang, không cần ai phình ra cả.
- Số nến đã nạp chuyển sang `title` của ô chọn mã. `onLiveCandle` xoá dòng
  trạng thái mỗi tick (chủ ý cũ: "dòng trạng thái dành cho thứ cần chữ"), nên
  từ khi realtime bật sẵn, một con số viết ở đó sẽ bị tick đầu tiên xoá và chỉ
  loé lên sau mỗi lần nạp lịch sử.

#### 4. Tiếng Anh còn dính tiếng Việt — tìm bằng máy

`tests/test_i18n.py` mới: đi qua từng file, bám theo việc con trỏ đang ở trong
comment, trong đối số **đầu** của `L(`, hay sau khoá `vi:` — ba chỗ tiếng Việt
được phép. Mọi chuỗi có dấu tiếng Việt ngoài đó là chuỗi không có bản tiếng Anh.

Bốn lần trình quét sai và đều đã sửa, ghi lại vì mỗi lần là một loại sai khác:

| Vấn đề | Hậu quả |
|---|---|
| Không vào trong `${…}` của template | `${L('a','b')}` bị báo nhầm, mà chuỗi trần trong cùng chỗ đó lại lọt |
| Recursion vào `${…}` mất ngữ cảnh `L(` | hai nhánh của `${x ? 'MUA' : 'BÁN'}` trong đối số tiếng Việt bị báo |
| Khoá object bị coi là văn bản | `'thấp':` — khoá tra cứu cố ý giữ nguyên theo API |
| Tên riêng có dấu | "Cramér", "López de Prado" trong **bản tiếng Anh** bị báo là tiếng Việt |

Kết quả: **254 → 97**. Đã dịch xong `validation.js` (toàn bộ panel Thống kê),
`strategy.js`, `portfolio.js`, `indicators.js`, `paper.js`, `favourites.js`.

**Còn lại 97 chuỗi trong `app.js`** — chủ yếu hai khối văn xuôi dài: hướng dẫn
định dạng file plugin và hướng dẫn cài Telegram. Không giấu đi: test dùng một
**ratchet** (`BUDGET = {'app.js': 97}`). Thêm bất kỳ chuỗi chưa dịch nào ở bất
kỳ file nào sẽ làm test đỏ, và nếu con số tụt xuống thì test cũng đỏ để bắt hạ
ngưỡng. Hạ về 0 rồi xoá dòng đó là xong.

#### 5. Màn hình mở đầu

Dấu hiệu vẽ ra, tên **QUANT PERCENT TERMINAL**, một thanh tiến trình, và dòng
"Charting powered by TradingView" ở chân. Thanh tiến trình **không xác định**
chứ không phải phần trăm: cả quá trình khởi động chỉ có hai request, không có
tỷ lệ nào đáng báo, và bịa ra một phần trăm còn tệ hơn một vệt quét thành thật.

### 2026-09-09 (khuya) — Sáu mục: co cửa sổ, luồng paper, lịch sử vô hạn, màu, khoảng ngày

**247 test Python + toàn bộ render check**, không lỗi.

#### 1. Lỗi khi thu nhỏ cửa sổ — đã sửa

Tái hiện được ở **1050px**: giá và dải nút khung thời gian vẽ đè lên nhau, cả
hai không đọc được.

Nguyên nhân: `.topbar-controls` được phép co, nhưng `.tf-group` bên trong nó
khai báo `flex-shrink: 0`. Một flex item từ chối co bên trong một cha đã co
**không bị cắt — nó tràn ra và vẽ đè** lên thứ bên cạnh. Đây là hành vi đúng
của flexbox và là loại lỗi chỉ hiện ra ở một khoảng bề rộng nhất định.

Sửa: dải khung thời gian tự cuộn ngang (`overflow-x: auto`) ở **mọi** bề rộng
— không phải chỉ dưới một breakpoint điện thoại, vì lỗi xuất hiện ở 1050px.
Thêm các mốc bỏ dần thứ ít quan trọng (1240 tên thương hiệu, 1140 ô số nến,
1080 nhãn Realtime và múi giờ), và dưới **1000px** thanh trên xuống hai dòng
thay vì giấu nút người dùng vẫn cần.

#### 2. Paper trading bắt đầu từ một thị trường cụ thể

Nút cũ chỉ ghi "Giao dịch tay", nên điều duy nhất cần biết trước khi bấm — *tôi
sắp giao dịch mã nào* — lại là điều nó không nói. Giờ nút ghi thẳng **"Giao
dịch tay trên BTCUSDT"**, đổi theo biểu đồ, và bị vô hiệu hoá khi chưa chọn mã.

#### 3. Vào chi tiết một thị trường thì hiện nến

Bấm vào **chính biểu đồ tổng quan** là mở chế độ nến. Nút trên thanh vẫn làm
được điều đó, nhưng cử chỉ người ta thật sự có là bấm vào thứ mình đang nhìn,
không phải đi tìm một nút.

*Nói rõ phần chưa làm:* tôi **chưa** dựng một bảng danh sách thị trường riêng
kiểu "Major indices" trong ảnh mẫu. Hiện ô chọn mã ở thanh trên đóng vai trò
đó. Nếu Nam muốn đúng dạng danh sách nhiều mã kèm giá và % thay đổi thì đó là
một mục riêng.

#### 4. Màu chỉ báo

Cái xấu thật không nằm ở bảng màu mà ở cách phát màu: `as_dict(i)` dùng chỉ số
output **bên trong một chỉ báo**, nên output đầu tiên của **mọi** chỉ báo đều
nhận cùng một màu. Vẽ EMA, VWAP và đường giữa Bollinger là ba đường xanh giống
hệt nhau.

- Mỗi **instance** được vẽ giờ lấy một offset khác nhau trong bảng màu, nên chỉ
  báo thứ hai bắt đầu từ chỗ chỉ báo thứ nhất dừng lại. Chỉ báo tự chọn màu thì
  không bị đụng vào (`color_auto` phân biệt hai loại).
- Bảng màu mới **8 màu thay vì 10**, chọn theo ba ràng buộc chứ không theo mắt:
  cùng dải độ sáng (bảng cũ trộn vàng mù tạt nhạt `#a16207` với xám gần đen
  `#475569` — cái nhạt biến mất, cái đậm trông như chuỗi quan trọng nhất); tránh
  hẳn dải xanh lá và đỏ vì hai màu đó mang nghĩa hướng giá; và không có cặp
  đỏ/xanh lá nào để bộ màu còn dùng được với người mù màu. Chỉ còn chỗ cho 8.
- Đường overlay mảnh lại **2px → 1.5px**: nó nằm đè lên giá và phải đọc được mà
  không che thứ nó vẽ lên trên.
- **Histogram cắt ngang 0** (MACD, momentum) giờ tô hai màu theo dấu. Dấu chính
  là thông điệp; một màu duy nhất bắt người đọc tự suy ra từ hình dạng.

#### 5. Vuốt trái là tự nạp lịch sử

Không cần đặt số nến nữa. Kéo qua nến cũ nhất thì trang trước đó tự về.

Kích hoạt theo **chỉ số logic** chứ không theo vị trí pixel, để cùng một cử chỉ
mang cùng một nghĩa ở mọi mức phóng to: "còn chưa tới một màn hình nến ở bên
trái bạn". Trang 1 000 nến — đủ nhỏ để về kịp trong một cú vuốt.

Hai chi tiết dễ bỏ sót, đều đã xử lý: phạm vi hiển thị được **chụp lại và khôi
phục** quanh `setData`, nếu không thì mỗi trang về là biểu đồ nhảy về đầu và cú
vuốt sẽ chống lại người dùng; và khi kho hết dữ liệu cũ hơn thì **ngừng hỏi** —
một biểu đồ bắn lại cùng một request rỗng theo từng cú vuốt là cách một cử chỉ
cuộn biến thành bão request.

#### 6. Backtest theo khoảng thời gian

`_load_candles` nhận `start`/`end` (ISO, bao gồm cả hai đầu), và **cả bảy**
request model nạp nến đều có thêm hai trường đó — backtest, report, optimize,
walk-forward, Monte Carlo, so sánh, và thống kê. Chạy walk-forward trên một
khoảng khác với backtest nó đang kiểm chứng là trả lời một câu hỏi khác.

Giao diện: hai ô ngày trong panel Chiến lược, bỏ trống thì dùng số nến gần nhất
như cũ. Ngày kết thúc gửi đi là **23:59:59** chứ không phải nửa đêm — chọn "đến
30/6" là có ý cả ngày 30/6, gửi nửa đêm sẽ lặng lẽ mất nến của ngày đó.

Từ chối có lý do: khoảng ngược (400), ngày không đọc được (400), và khoảng
không có nến nào (404 — chứ không phải một backtest rỗng báo 0 lệnh, vì con số
đó đọc như một kết luận).

*Một lỗi trong fixture test của tôi, đáng ghi lại:* tôi đổi `DatetimeIndex` sang
mili giây bằng `astype("int64") // 1_000_000`. pandas 3 lưu datetime bằng **micro
giây** chứ không phải nano giây, nên phép đó ra **giây** — sai một nghìn lần mà
vẫn trông như một timestamp hợp lệ. Dùng `astype("datetime64[ms]")` thay thế.

*Một lỗi tôi tự tạo khi sửa hàng loạt bằng regex, đúng §2.3:* chèn `period` vào
các endpoint trong `api.js` bằng regex làm `statsStrategy` có phần thân dùng
`period` nhưng **không có tham số** đó — lỗi runtime. Ba endpoint khác thì có
tham số mà không có thân. Đã sửa tay từng cái và thêm một phép kiểm quét lại
toàn file xem còn endpoint nào dùng `period` mà không khai báo không.

### 2026-09-09 (tối) — Khởi động, chế độ tổng quan, và chữ

**241 test Python + 109 check render**, không lỗi.

#### 1. Khởi động: 2 073 ms → 98 ms trước lượt vẽ đầu tiên

Đo từng endpoint trên đường khởi động (trung vị 3 lần, server đã ấm):

| Endpoint | Thời gian |
|---|---|
| `/api/config` | 16.9 ms |
| **`/api/markets/vn/symbols`** | **1 916.3 ms** |
| `/api/indicators` | 27.7 ms |
| `/api/strategies` | 14.9 ms |
| `/api/paper` | 16.4 ms |
| `/api/candles` (2 000 nến) | 80.9 ms |

Cả sáu cái này trước đây được `await` **lần lượt** trước khi vẽ nến đầu tiên.
Riêng danh sách mã Việt Nam chiếm **92%** thời gian chờ — cho một danh sách chỉ
được đọc khi người dùng mở ô chọn mã, và nó là một truy vấn database qua VPN
Tailscale nên khi VPN tắt thì còn phải chờ timeout.

Giờ chỉ `config` + `candles` nằm trên đường tới biểu đồ: **2 073 ms → 98 ms,
bớt 95%**. Danh sách mã VN, catalog chỉ báo, danh sách chiến lược và các phiên
paper đều gộp vào một màn hình đã dùng được rồi.

**Import server: 1 244 ms → 790 ms.** `backend.analysis.report` và
`backend.analysis.stats` kéo `scipy.stats` vào đúng đường khởi động, đo được
557 ms. Cả hai giờ import khi dùng lần đầu.

*Lần thử đầu không ăn thua và tôi ghi lại theo §2.2:* tôi hoãn import ở
`grid.py` và `routes_stats.py` trước, đo lại — **1243/1288/1262 ms, không đổi
gì**, vì `routes_strategy` vẫn kéo `analysis.report` vào. Chỉ khi hoãn nốt cái
đó thì con số mới xuống.

#### 2. Chế độ tổng quan

Ứng dụng giờ mở ra ở **Tổng quan**: một đường có gradient bên dưới, không nến,
không volume, không pane chỉ báo, không panel. Nó trả lời câu hỏi người ta có
*trước* mọi câu hỏi khác — thứ này dạo này thế nào — và chỉ tốn một request.

Bấm **Giao dịch** để sang chế độ làm việc. Catalog chỉ báo và danh sách chiến
lược nạp ở **lần đầu vào chế độ đó**, không phải lúc khởi động; nếu hỏng thì
lần sau thử lại chứ không để panel rỗng cả phiên.

Chuyển chế độ là đổi `visible`, không dựng lại gì: cùng một chart, cùng một
time scale, nên vị trí người dùng đang cuộn tới được giữ nguyên.

Đường tổng quan tô màu theo **cả cửa sổ** (kết thúc so với bắt đầu), khác với
màu nhấp nháy của ticker trên đầu (theo từng tick). Hai câu hỏi khác nhau và
thường ngược nhau.

Thêm `#trade` trong URL để mở thẳng chế độ làm việc — vừa đánh dấu được, vừa
làm cho việc chụp ảnh kiểm tra hai chế độ trở nên khả thi.

*Lỗi bắt được ngay trên ảnh chụp:* phần trăm hiện **+0.00%** trong khi đường
tổng quan đã xanh, vì mốc neo vào tick **đầu tiên nhận được** chứ không phải
nến đầu của cửa sổ. Neo lại vào `candles[0].close` thì nó thành **+21.35%**,
khớp với màu của đường.

#### 3. Chữ

**Trebuchet MS là lựa chọn sai cho tiếng Việt.** Nó là first choice của
TradingView nhưng phủ tiếng Việt kém: trên Windows, ế ộ ữ ậ rơi xuống font dự
phòng, nên một câu tiếng Việt được vẽ bằng **hai typeface cùng lúc** và dấu
chồng nằm sai độ cao. Đó chính là cái "cứng" — chữ không xấu, nó là hai font
giả vờ làm một. Đổi sang Segoe UI (có sẵn trên Windows, phủ đủ dấu chồng).

`line-height` 1.5 → **1.6**: tiếng Việt chồng dấu thanh lên trên dấu nguyên âm
(ế, ộ, ữ), cần nhiều chỗ phía trên x-height hơn chữ Latin.

**Tên chỉ báo bỏ font monospace.** Tên do người dùng đặt và thường là tiếng
Việt ("ML · Trạng thái thị trường"); font mono không phủ tiếng Việt nên chúng
cũng bị vẽ bằng hai typeface. Chỉ mã nguồn thật mới còn monospace; các con số
dùng `font-variant-numeric: tabular-nums` thay vì cả một font mono.

**Tiếng Anh chưa đồng nhất — tìm bằng máy, không bằng mắt.** Thêm phép kiểm
`English is clean` vào `tests/test_render.js`: render mọi panel ở chế độ tiếng
Anh rồi tìm ký tự có dấu tiếng Việt. Các panel đều sạch, nên vấn đề nằm ở HTML
tĩnh. Một script quét `index.html` tìm text và thuộc tính có dấu tiếng Việt mà
không có `data-i18n` đi kèm: **22 chỗ**, gồm 9 đoạn văn bản và 13 thuộc tính
`title`/`aria-label`. Đã dịch hết, quét lại còn **0**.

#### 4. Bố cục và kích thước

- Cỡ chữ nền 14px → **15px**.
- Nút cao 30px → **36px**, chữ 13px → 14px; thêm `.btn-lg` 40px cho nút đổi
  chế độ.
- Tên chỉ báo 11.5px → 13px, dòng trạng thái 11.5px → 12.5px.
- Ở chế độ tổng quan, giá hiển thị **26px** thay vì 19px, và biểu đồ nằm trong
  một khung bo 16px có lề — dáng của một trang báo giá.

### 2026-09-09 (chiều) — Giao dịch tay trong Paper Trading, và restyle theo TradingView

**241 test Python pass** (trước 231) và **98 check render pass** (trước 84).

#### Giao dịch tay

Paper trading trước đây chỉ chạy chiến lược. Giờ người dùng tự đặt lệnh
long/short/đóng trên bất kỳ mã nào, hoặc mở hẳn một phiên **Giao dịch tay**
không có chiến lược nào đứng sau.

**Lệnh tay khớp NGAY ở giá hiện tại — đây là ngoại lệ có chủ ý với §3.1.**
Quy tắc "tín hiệu ở nến `i` khớp ở giá mở nến `i+1`" tồn tại để chặn *chiến
lược* dùng thông tin nó chưa thể biết lúc ra quyết định. Người bấm nút Mua
không có vấn đề đó: họ đang hành động trên một con số đang hiện trên màn hình.
Bắt họ đợi tới nến sau là khớp ở một mức giá họ chưa từng nhìn thấy — một lời
nói dối tệ hơn cái mà quy tắc kia ngăn. Trượt giá vẫn bất lợi, phí vẫn hai
chiều.

Đo lại để chắc chi phí không bị bỏ sót ở đường đi mới này:

| Phép đo | Kết quả |
|---|---|
| Vòng khứ hồi ở giá đứng yên | −0.119976% (lý thuyết −0.120000%) |
| Phần chênh 0.000024 đ% | phí tính trên danh nghĩa **đã khớp** (100.02), đúng như sàn làm |
| Đảo chiều thẳng so với đóng-rồi-mở | equity **giống hệt** tới 1e-9 |
| Cỡ vị thế 25% / 50% / 100% | ký quỹ 2 500 / 5 000 / 10 000 |

Đảo chiều là **hai lần khớp**, mỗi lần trả phí riêng. Gộp thành một sẽ lặng lẽ
tặng người dùng một bộ phí.

**Hai thứ không được cùng lái một vị thế.** Đặt lệnh tay trên phiên có chiến
lược sẽ bật `manual_override`: chiến lược vẫn được tính và vẫn hiển thị nhưng
không còn giao dịch. Nếu không, nến kế tiếp sẽ lặng lẽ đảo ngược điều người
dùng vừa làm, và nhật ký lệnh hiện ra một lần đảo chiều không ai yêu cầu. Có
nút **Trả lại chiến lược** để giao quyền lại.

**Từ chối mang mã ổn định, không phải câu chữ.** `OrderRefused` trả về
`{code, message:{vi,en}}` — `already_flat`, `session_stopped`, `no_price`,
`bad_size`, `already_in_position`, `no_equity`, `no_strategy`. Đây là chỗ ý
định "có mùi tiền" của người dùng đi vào hệ thống, nên một lệnh bị nuốt im lặng
trông y hệt một lệnh đã khớp.

*Một lỗi thật lộ ra khi làm phần này:* `api.js` đang ép mọi `detail` không phải
chuỗi qua `JSON.stringify`, nên người dùng sẽ thấy nguyên dấu ngoặc nhọn thay
vì câu tiếng Việt. Giờ nó giữ nguyên object trên error và dùng `message` làm
văn bản.

**Bảng lệnh** đặt như một order pad thật: Mua bên trái màu xanh, Bán bên phải
màu đỏ, cả hai in giá sắp khớp, cộng ô % vốn. Nút bị **vô hiệu hoá chứ không
ẩn** khi không dùng được — nếu ẩn, bảng lệnh xô lệch dưới con trỏ giữa hai cú
nhấp. Mọi nút trên cùng một thẻ khoá lại trong lúc lệnh đang bay: nhấp đúp mà
không khoá là hai lần khớp và hai bộ phí.

#### Restyle theo TradingView

Toàn bộ đi qua token nên phần lớn nằm ở khối `:root`, cộng vài quy tắc thành
phần còn cứng ngôn ngữ Material.

| | Trước (Google) | Sau (TradingView) |
|---|---|---|
| Nền | `#f8f9fa` | `#ffffff` |
| Chữ | `#1f1f1f` | `#131722` |
| Nhấn | `#1f1f1f` đen | `#2962ff` |
| Tăng / giảm | `#16a34a` / `#dc2626` | `#089981` / `#f23645` |
| Bo góc nút | viên thuốc 999px | `8px` |
| Bo góc thẻ | 14px | `16px` |
| Phân tách | shadow | **viền 1px** |
| Font | Google Sans / Roboto | Trebuchet MS stack |

Ba lựa chọn đáng nói: **viền thay vì shadow** (elevation nghĩa là quan trọng
hơn; trên màn hình mười panel đều quan trọng ngang nhau thì shadow chỉ là
nhiễu); **nhãn nút màu mực chứ không xanh** (xanh còn phải mang nghĩa "hành
động chính", mười hai nhãn xanh làm nó thành vô nghĩa); và **chữ số dạng bảng ở
mọi nơi con số thay đổi** — một cái giá tự đổi độ rộng theo từng tick thì không
đọc được.

Thêm khối báo giá kiểu TradingView: giá lớn, cạnh nó là **% thay đổi so với giá
mở phiên**. Màu nhấp nháy theo tick trả lời "đang chạy hướng nào"; phần trăm
trả lời "so với lúc bắt đầu thì đang ở đâu" — hai câu này thường ngược nhau.

*Lỗi tôi tự tạo và bắt được bằng cách kiểm tra chính lời chú thích mình vừa
viết:* comment nói mốc phần trăm được neo lại khi đổi mã, nhưng handler đổi mã
**không** gọi `hidePrice()`, nên nó sẽ giữ mốc của mã cũ và báo mức tăng của
BTC theo phần trăm giá một cổ phiếu Việt Nam. Đã reset ở cả đổi mã lẫn đổi
khung thời gian.

*Lỗi thứ hai, phát hiện khi nhìn ảnh chụp màn hình:* bảng màu huy hiệu mã tôi
viết ra có chứa đúng `#089981` và `#f23645` — tức là dùng xanh/đỏ thị trường để
**trang trí**, vi phạm chính nguyên tắc số một của file style. Đã thay bằng
bảng màu không đụng vào hai màu đó.

Kiểm tra bằng Chrome headless trên một trang preview dựng riêng, vì server
cổng 8000 của Nam đang giữ khoá DuckDB nên không mở được server thứ hai.

### 2026-09-09 — Xong bốn mục còn lại: Optimize, AmiBroker, CVaR, Paper Trading

**231 test Python pass** (trước 209) và **84 check render pass** (trước 20).
Bốn mục còn lại trong danh sách đều đã xong; chỉ còn Cộng đồng QP mà Nam đã hoãn.

#### Mục 3 — Optimize: hai câu hỏi bảng xếp hạng không trả lời được

Bảng xếp hạng chỉ nói ô nào điểm cao nhất. Nó không phân biệt được **vùng tối
ưu thật** với **một ô may mắn**, và không nói được Sharpe của ô thắng có hơn
mức mà chính việc quét ngần ấy tổ hợp tự sinh ra hay không.

**(a) Độ bền theo lân cận tham số.** Với mỗi trục, lấy hai ô cách một bước, so
trung vị điểm của chúng vào phân phối điểm của cả lưới. Lợi thế thật suy giảm
từ từ; đỉnh nhọn thì xung quanh chỉ tầm thường.

Đo bằng **bách phân vị**, không phải tỷ số — điểm ở đây thường xuyên âm hoặc
gần 0, đúng cái bẫy đã gặp ở K-ratio (§2.6) và ở hiệu suất walk-forward.

*Bản đầu của tôi sai, và phép đo bắt được:*

| Lưới dựng tay | Trước (`side="right"`) | Sau (điểm giữa khối trùng) |
|---|---|---|
| đồi trơn `0.1 … 1.0 … 0.1` | plateau, bách phân vị **89** | plateau, **78** |
| đỉnh nhọn `0.1×8 + 1.0` | plateau, bách phân vị **89** | **spike, 44** |

`searchsorted(side="right")` đếm mọi ô **bằng** giá trị đang xét là "nằm dưới"
nó. Trên một lưới đầy ô đồng điểm, tám ô 0.10 quanh một đỉnh 1.0 bị đẩy lên
bách phân vị 89, nên **đỉnh nhọn nhất có thể có và một quả đồi trơn cho ra
cùng một kết luận, cùng một con số.** Lấy điểm giữa của khối trùng thì hai
trường hợp tách ra ngay.

**(b) Sharpe khử phồng, dùng độ phân tán ĐO ĐƯỢC.** `sharpe_tests` trong
`stats.py` phải **xấp xỉ** đại lượng quan trọng nhất của công thức DSR — độ
phân tán Sharpe giữa các phép thử — vì một backtest đơn lẻ không nhìn thấy các
phép thử khác. Comment cũ trong file nói đúng như vậy: *"một xấp xỉ bảo thủ"*.

Nhưng optimizer thì giữ Sharpe của **mọi** ô lưới, nên độ lệch chuẩn của cột đó
chính là đại lượng Bailey & López de Prado định nghĩa. `sharpe_tests` giờ nhận
`trial_dispersion`, và payload nói rõ con số này là **đo** hay **xấp xỉ**.

Đo trên một bước ngẫu nhiên (đúng ra phải không có lợi thế):

| Lưới | Sharpe tốt nhất | PSR | DSR | Kết luận |
|---|---|---|---|---|
| 4 tổ hợp | −0.616 | 35.9% | 27.5% | deflated_away |
| 36 tổ hợp | 0.779 | 67.6% | **30.9%** | deflated_away |
| 234 tổ hợp | 0.779 | 67.6% | **27.3%** | deflated_away |

Cùng một Sharpe 0.779, nhưng quét 234 tổ hợp thì nó đáng tin **kém hơn** quét
36 — đúng như phải thế. PSR 67.6% trông có vẻ khả quan; DSR 27–31% nói thẳng
rằng con số đó là sản phẩm của việc tìm kiếm.

Panel Tối ưu trước đây **chỉ có tiếng Việt cứng**, đã chuyển sang song ngữ luôn
trong lần sửa này.

#### Mục 5 — Quản trị rủi ro: từ một con số thành một công cụ

Trước: `cvar_95_pct`, một con số, không nói gì về độ tin cậy của chính nó và
không trả lời được câu hỏi người dùng thật sự hỏi — *"vậy tôi nên vào lệnh bao
nhiêu?"*. File mới `backend/analysis/risk.py`, tab mới **Quản trị rủi ro**.

**CVaR giờ nói ra nó dựa trên bao nhiêu quan sát.** CVaR 99% trên 2 000 nến là
trung bình của **20** quan sát, và in ra hai chữ số thập phân y hệt CVaR 90%
dựa trên 200 — vi phạm §2.6. Đo bằng bootstrap:

| Mức | CVaR | Bề rộng KTC 95% | Số quan sát đuôi |
|---|---|---|---|
| 90% | −1.73% | 0.161 đ% | 200 |
| 95% | −2.06% | 0.226 đ% | 100 |
| 99% | −2.71% | **0.426 đ%** | **20** |

Con số 99% bất định gấp **2.6 lần** con số 90%, dù hai cái trông giống hệt nhau.
Đuôi dưới 10 quan sát bị gắn cờ thẳng trên bảng.

**Cornish–Fisher, vì CVaR lịch sử không thể vượt quá cú lỗ tệ nhất đã xảy ra.**
Trên mẫu chưa gặp cú sập nào, nó báo rằng cú sập không tồn tại. Đo trên một mẫu
đuôi trái dày:

| Mẫu | VaR99 lịch sử | Cornish–Fisher | Chênh |
|---|---|---|---|
| chuẩn | −2.29% | −2.29% | 0.00 đ% |
| đuôi trái dày | −4.09% | **−7.69%** | **−3.59 đ%** |

Lịch sử báo thiếu gần một nửa. Trên mẫu bình thường hai cột trùng nhau, nên cột
này không phải lúc nào cũng doạ người đọc.

**Ngân sách rủi ro → cỡ vị thế.** Chiều ngược của bảng CVaR: người dùng phát
biểu điều họ chịu được, hệ thống trả về `size_pct`. Phép quay vòng **chính xác**
— xin ngân sách 1%, áp hệ số trả về, đo lại CVaR95 được đúng −1.000%.

Cộng Kelly và nửa Kelly (tính trên `equity_after/equity_before`, đúng đại lượng
engine cộng dồn), và trần đòn bẩy theo từng mức tin cậy. Mọi con số kèm giới
hạn: tỷ lệ tuyến tính **không** đúng với thanh lý, và trần đòn bẩy tính theo giá
đóng cửa trong khi engine thanh lý theo giá thấp/cao nhất **trong** nến, nên đó
là trần trên chứ không phải mức an toàn.

*Một test của tôi sai, không phải code:* Kelly lấy mẫu 400 lệnh ở p=0.6 có sai
số chuẩn 0.025 trên p, nên f dao động ±0.10 giữa các seed — test đo bộ sinh số
ngẫu nhiên nhiều hơn đo công thức. Đã thay bằng phép dựng tất định 60 thắng /
40 thua, kiểm f* = 0.20 tới 1e-9.

#### Mục 4 — Bảng AmiBroker

Bảng ba cột Tất cả / Mua / Bán vốn đã có. Rà từng ô của báo cáo AmiBroker thì
thấy phần lớn đã có (Recovery Factor, CAR/MDD, Ulcer, K-ratio, Expectancy,
Payoff, Standard Error…). Bổ sung phần còn thiếu: **RAR/MDD**, số nến giữ lâu
nhất, tổng số nến trong lệnh, độ phân tán lợi suất, sụt giảm **trong lệnh**
(tệ nhất và trung bình, đo bằng MAE), tỷ lệ lời lớn nhất / lỗ lớn nhất, và
thống kê **lý do đóng lệnh**.

*Bốn ô tôi thêm lúc đầu trùng tên với ô đã có* (`avg_bars_held_win` so với
`avg_bars_win`, `std_dev_pnl` so với `profit_std`…). Đã bỏ — hai tên cho cùng
một con số là thứ sẽ trôi lệch nhau ở lần sửa sau.

#### Mục 6 — Paper Trading tách khỏi backtest

Trước, phiên paper mượn luôn ô chi phí của backtest. Một ô phục vụ hai việc:
hạ phí xuống để xem backtest trông thế nào là **đặt luôn phí cho phiên live kế
tiếp**, và khi phiên đã chạy thì không có chỗ nào xem nó đang chạy với thông số
gì.

*Backend vốn đã đúng* — mỗi phiên dựng `BacktestConfig` riêng lúc bắt đầu nên
phiên đang chạy miễn nhiễm với mọi thay đổi sau đó. Vấn đề thuần tuý ở giao
diện. Hộp thoại mới:

- **Preset sàn** (ý tưởng lấy từ TradingView): Binance Futures taker/maker,
  Binance Spot, HOSE. Chọn nơi giao dịch, phí tự điền.
- **Chi phí khứ hồi**, không phải phí niêm yết. Phí 0.04% hiện ra là **0.120%**
  mỗi vòng — phí hai chiều cộng trượt giá hai chiều (§3.1) — kèm số tiền cụ
  thể. Đó là mức chiến lược phải vượt trước khi hoà vốn.
- **Cảnh báo theo ngữ cảnh**: đặt đòn bẩy trên spot, đòn bẩy ≥10x kèm biến động
  đủ thanh lý, maker chỉ đúng nếu lệnh thật sự nằm chờ trên sổ (chiến lược ở
  đây vào lệnh ở giá mở nến kế tiếp nên gần như luôn là taker), HOSE chưa gồm
  thuế bán 0.1%.
- **"Lấy từ backtest"** vẫn còn, nhưng giờ là một hành động có chủ ý.

#### Bộ test render mở rộng: 20 → 84 check

`tests/test_render.js` giờ phủ cả panel Tối ưu, **cả 7 tab báo cáo ở hai ngôn
ngữ**, và hộp cài đặt Paper Trading (mở hộp không được tự chạy phiên; preset
điền đúng phí; sửa tay chuyển sang "Tự đặt"; nút Bắt đầu gửi đúng giá trị trong
hộp chứ không phải giá trị của panel backtest).

Nó bắt được ngay một lỗi thật trong lần sửa này: đổi tên `kellyExplain` cho
hàm mới làm **hai call site trỏ nhầm về hàm cũ khác chữ ký**, syntax vẫn hợp lệ
và không có lỗi nào ở console.

### 2026-09-08 (tối) — Frontend của tính năng thu phí, và ba defect nữa

Frontend cho walk-forward và Monte Carlo đã xong. Trong lúc kiểm chứng bằng API
thật thì lộ ra ba vấn đề nữa, hai cái là lỗi thật, một cái là **giả thuyết của
tôi và nó sai** — ghi lại cả ba theo §2.2.

**Test: 25 pass** trong `tests/test_validation.py` (trước 22), cộng một bộ kiểm
tra render hoàn toàn mới, `tests/test_render.js`, **20 check pass**.

#### Defect 1 (nặng) — tên chỉ số sai thì walk-forward vẫn "chạy thành công"

`walk_forward` chấm điểm bằng `metrics.get(metric, 0.0)`. Tên nào không có
trong `RANKABLE_METRICS` thì **mọi tổ hợp tham số đều được 0.0**, sweep trả về
phần tử đầu tiên của lưới, và cả lượt chạy báo cáo folds, đường vốn, hiệu suất
walk-forward — mà chưa hề tối ưu gì.

Đo trên BTCUSDT 1h, lưới 6 tổ hợp, 15 fold:

| `metric` | Số bộ tham số thắng khác nhau |
|---|---|
| `sharpe_ratio` (tên nghe rất hợp lý, nhưng sai) | **1** |
| `not_a_metric` | **1** |
| `sharpe` | **5** |
| `total_return_pct` | **5** |

Hai dòng đầu giống hệt nhau: `sharpe_ratio` hỏng đúng như một tên bịa. Kiểu hỏng
này là tệ nhất — nó **trông như một kết quả**. `optimize` xưa nay vẫn từ chối tên
lạ (`grid.py:167`); nhánh này thì không. Đã sửa: từ chối luôn, và bỏ giá trị mặc
định `0.0` trong `.get()`.

Giao diện thật không gửi được tên sai (danh sách chọn được đổ từ
`RANKABLE_METRICS`), nên đường đi tới lỗi này là gọi API trực tiếp. Vẫn phải sửa:
đây là tính năng thu phí, và im lặng trả về kết quả sai còn tệ hơn báo lỗi.

#### Defect 2 — hiệu suất walk-forward in ra một tỷ số dưới cái nhãn không hợp

Thẻ ghi "phần lợi thế sống sót" rồi in thẳng `oos/is`. Tỷ số đó chỉ đọc được
như một *phần* khi cả hai vế cùng dương. Hai tình huống khác xảy ra thường xuyên:

- **ngoài mẫu lỗ trong khi trong mẫu lãi** — lợi thế không co lại mà *đảo chiều*;
  "−1.18 phần lợi thế còn lại" không phải một câu tiếng Việt hay tiếng Anh nào cả.
  Đo được trên chính dữ liệu thật: WFE = **−1.178**.
- **trong mẫu gần bằng 0** — mẫu số không đáng chia. 0.001% so với 0.9% sẽ in ra
  hiệu suất **900** cho một chiến lược không kiếm được gì lúc huấn luyện.

Backend giờ trả thêm `walk_forward_efficiency_code`: `ratio`, `inverted`, hoặc
`no_is_edge`. Thẻ hiện "Đảo chiều" / một dấu gạch ngang / con số, tuỳ trạng thái.
Ngưỡng "gần 0" là **tương đối**, không phải tuyệt đối — cùng lớp lỗi với K-ratio
đã ghi ở §2.6: một tỷ số 0.5 thật phải đọc được ở mọi thang đo, và test kiểm
đúng điều đó ở ba thang cách nhau 1000 lần.

#### Giả thuyết sai — "WFE đo trên lợi nhuận trong khi sweep tối ưu Sharpe"

Tôi thấy WFE = 8.45 và kết luận nguyên nhân là đo sai đại lượng: sweep tối ưu
Sharpe còn WFE tính trên lợi nhuận, hai thứ không so được với nhau. **Sai.**
Con số 8.45 hoàn toàn do Defect 1 sinh ra. Đo lại với tên chỉ số hợp lệ:

| `metric` | WFE trên lợi nhuận | WFE trên Sharpe |
|---|---|---|
| `sharpe` | −1.178 | −2.116 |
| `sortino` | −1.178 | −2.116 |
| `total_return_pct` | −1.178 | −2.116 |
| `profit_factor` | −0.793 | −1.784 |

Hai cách đo cùng dấu, cùng cỡ. Không có defect nào ở đây, và tôi **không** đổi
công thức. Nếu không đo lại thì đã đi viết một bản sửa cho một lỗi không tồn tại.

#### Defect 3 — không có gì kiểm tra rằng bảng biểu thật sự hiện ra

Mọi test trong `tests/` đều kiểm một con số. Không cái nào kiểm con số đó có tới
được màn hình không — mà đó đúng là chỗ con bug nặng nhất của dự án đã sống:
panel thống kê gọi `.startsWith()` lên một object `{vi, en}`, request trả 200,
console im lặng.

`tests/test_render.js` chạy chính module `Validation` dưới jsdom, chỉ giả lập
mạng, render từng panel **ở cả hai ngôn ngữ**, và fail khi:

- panel ném lỗi, hoặc render rỗng;
- văn bản chứa `[object Object]`, `undefined`, `NaN`, `null`, `Infinity`;
- thiếu nội dung mới (thanh so sánh, bảng độ ổn định, cột đã chuẩn hoá, biểu đồ
  quạt, phần hai bộ lấy mẫu, sai số mô phỏng trên mỗi xác suất, số dòng bảng
  đúng bằng số fold).

Chạy:

```
npm install --no-save jsdom
.venv/Scripts/python.exe tests/render_payloads.py
NODE_PATH=./node_modules node tests/test_render.js
```

Fixture sinh từ engine thật trên một bước ngẫu nhiên tổng hợp, nên **không cần
database và không cần server đang chạy**.

Bộ test này lập tức bắt được hai lỗi trong chính harness của tôi — `I18n.lang`
là getter chỉ đọc nên gán vào không có tác dụng gì (bằng chứng: vi và en render
ra **đúng cùng một số ký tự**), và regex nhận diện trạng thái của tôi chỉ viết
tiếng Anh. Không cái nào là lỗi sản phẩm, nhưng nếu chỉ nhìn "PASS" mà không
nhìn số ký tự thì tôi đã tin nhầm là đã kiểm tra cả hai ngôn ngữ.

#### Frontend đã nối xong

- `frontend/index.html` — thêm ô **Nến cách ly** và bộ chọn **Trượt / Neo gốc**,
  mỗi cái một nút (i).
- `frontend/js/api.js` — gửi `purge_bars` và `fold_mode`.
- `frontend/js/app.js` — đăng ký hai phần tử mới.
- `frontend/js/i18n.js` — 4 khoá mới.
- `frontend/js/explain.js` — một entry giờ có thể là **hàm**, giải ra lúc mở
  popover. Entry đăng ký lúc khởi động dưới dạng object sẽ **đóng băng** ngôn
  ngữ đang bật lúc đó, mà người dùng đổi ngôn ngữ sau đó rất lâu.
- `frontend/styles.css` — `.pf-bar-label`, `.pf-bar-value`, `.rp-svg.mc-fan`.

### 2026-09-08 (chiều) — Nâng cấp walk-forward và Monte Carlo

Sửa xong cả bốn khiếm khuyết đã ghi bên dưới, cộng một defect thứ năm lộ ra
trong lúc viết test. **206 test pass** (trước 184); walk-forward và Monte Carlo
từ chỗ **không có test nào** giờ có 22.

**Đã sửa, có số đo trước/sau:**

| | Trước | Sau |
|---|---|---|
| MC: 100 lệnh, mỗi lệnh +1% vốn ban đầu | +170.48% | **+100.09%** (đúng) |
| MC: xác suất cháy, chuỗi có lệnh −95% | 25.7% (chỉ xét giá trị cuối) | **41.7%** (xét dọc đường) |
| WF: degradation khi cửa sổ 250→2000 | 4.59 → **7.88** (tăng, artefact) | 4.59 → **0.71** (giảm, đúng) |

Chi tiết cách sửa:

1. **Engine giờ ghi `equity_before`/`equity_after` cho mỗi lệnh.** Đại lượng
   đúng để lấy mẫu lại chưa hề tồn tại: `pnl/initial` là lợi suất trên gốc cố
   định, còn `return_pct` bỏ qua phí vào lệnh (bị trừ ngay lúc mở). Đo thử ba
   cách đều lệch 4–7% so với engine. Với hai trường mới, cộng dồn tái tạo
   đường vốn **chính xác tới số dấu phẩy động** ở mọi cấu hình cỡ vị thế và
   đòn bẩy.

2. **Cháy tài khoản xét dọc đường.** Đường chạm 5% rồi hồi về 50% trước đây
   không bị tính là cháy, dù tài khoản đã bị đóng từ lúc chạm đáy.

3. **Chạy hai bộ lấy mẫu, báo cáo cả hai.** Khối (giữ chuỗi thắng/thua liền
   nhau) làm chuẩn, độc lập để đối chiếu. Khoảng cách giữa hai cái
   (`ordering_effect_pct`) chính là phần rủi ro đến từ **trật tự** các lệnh.
   Mọi xác suất kèm sai số mô phỏng và khoảng tin cậy.

4. **Degradation quy về cùng độ dài cửa sổ.** *Lần thử đầu tôi dùng CAGR và nó
   còn tệ hơn* — quy năm một cửa sổ 250 giờ là mũ 35, cho ra CAGR ngoài mẫu
   trên 7 000%. Cách đúng là compound lợi nhuận in-sample về đúng độ dài cửa sổ
   kiểm tra: cùng đơn vị, đọc được, không ngoại suy.

5. **Defect thứ năm, lộ ra khi viết test:** `walk_forward` gọi `spec.signals()`
   thẳng, **bỏ qua `resolve_params`**. Quét 1 tham số của chiến lược có 2 tham
   số → tham số kia thiếu hẳn → `KeyError` → bị `except Exception: continue`
   nuốt → báo "không vòng nào chạy được" mà không nói vì sao. Giờ đã resolve
   defaults, và lỗi của từng fold được giữ lại trong `failed_folds`.

**Nâng cấp thêm:**

- **Purge/embargo** (`purge_bars`): bỏ N nến giữa huấn luyện và kiểm tra. Chỉ
  báo có lookback L vẫn mang thông tin cửa sổ huấn luyện L nến vào cửa sổ kiểm
  tra; với chiến lược ML thì nhiều hơn.
- **Chế độ anchored**: cửa sổ huấn luyện bắt đầu từ nến 0 và nở ra, thay vì
  trượt. Đây là phép thử khó hơn — tham số phải sống qua nhiều chế độ thị
  trường chứ không chỉ bám theo cái mới nhất. *(Bản đầu của tôi có lỗi tràn
  dữ liệu, đã sửa và test bốn cấu hình.)*
- **Độ ổn định tham số**: hệ số biến thiên của tham số được chọn qua các vòng.
  Tham số nhảy loạn giữa các vòng nghĩa là chiến lược không có điểm tối ưu.
- **Walk-forward efficiency** (OOS/IS), `degradation_sharpe` (không thứ nguyên).

**Còn lại chưa làm** (theo thứ tự ưu tiên đã thống nhất): frontend cho các
trường mới; điểm bền vững của optimizer theo lân cận tham số; bảng AmiBroker
đầy đủ; biểu đồ Monte Carlo; công cụ CVaR; cài đặt Paper Trading; cộng đồng QP.

---

### 2026-09-08 — Soát lỗi trước đợt nâng cấp

**Tình trạng chung:** 184 test pass. Toàn bộ 33 endpoint trả đúng mã trạng
thái. Backtest và báo cáo khớp nhau (lợi nhuận 9.174108764914536 ở cả hai, 55
lệnh ở cả hai). 190 chỉ báo và 7 chiến lược nạp không lỗi. Không thiếu key
i18n. *(Không kiểm tra được bằng trình duyệt: MCP browser đã ngắt ở phiên này.)*

**Bốn khiếm khuyết trong đúng ba tính năng sắp nâng cấp** — đây là tính năng
thu phí nên ghi chi tiết:

**(1) `degradation_pct` của walk-forward đang đo độ dài cửa sổ, không phải overfit.**

Nó lấy `lợi nhuận in-sample − lợi nhuận out-of-sample`, nhưng in-sample đo trên
`train_bars` nến còn out-of-sample đo trên `test_bars` nến. Với cấu hình mặc
định 1000/250, in-sample bao phủ gấp **4 lần** thời gian.

Đo trên BTCUSDT 1h, 6000 nến, cửa sổ kiểm tra giữ nguyên 250:

| train/test | IS mean % | OOS mean % | degradation |
|---|---|---|---|
| 250/250 | 3.64 | −0.96 | 4.59 |
| 500/250 | 4.06 | −1.14 | 5.21 |
| 1000/250 | 5.05 | 0.11 | 4.94 |
| 2000/250 | 8.12 | 0.24 | **7.88** |

IS tăng đều theo cửa sổ, OOS gần như đứng yên. Degradation tăng 72% chỉ vì cửa
sổ dài ra. → Phải so bằng đại lượng đã chuẩn hoá theo thời gian (Sharpe, CAGR,
hoặc lợi suất mỗi nến). **Chưa sửa.**

**(2) Monte Carlo trộn lợi suất trên gốc cố định với phép cộng dồn.**

Nó lấy `pnl / initial_capital` rồi `cumprod(1 + r)`. Nhưng engine đặt cỡ vị thế
theo **vốn hiện tại**, nên `pnl/initial` chỉ đúng cho lệnh đầu tiên.

Đo: một chiến lược lãi đúng 1% vốn ban đầu mỗi lệnh, 100 lệnh → thực tế +100%,
Monte Carlo báo **+170.48%**. Sai 70 điểm phần trăm.

→ Phải lấy mẫu lại phần thay đổi vốn theo tỷ lệ (`return_pct × size_pct`), không
phải `pnl/initial`. **Chưa sửa.**

**(3) `probability_of_ruin` đo giá trị cuối, không đo đường đi.**

Nó đếm `finals <= initial * 0.1`. Một đường chạm 5% rồi hồi về 50% không được
tính là cháy, dù tài khoản đã bị đóng từ lúc chạm đáy.

Đo: chuỗi chứa một lệnh −95% báo ruin 25.7%; con số thật (chạm ngưỡng bất kỳ
lúc nào) cao hơn. → Phải kiểm tra dọc đường, không chỉ điểm cuối. **Chưa sửa.**

**(4) Monte Carlo lấy mẫu độc lập từng lệnh, phá vỡ tương quan chuỗi.**

*Giả thuyết ban đầu của tôi là nó đánh giá THẤP sụt giảm. Đo ra thì ngược lại.*
Trên chuỗi 10 thắng/10 thua lặp lại: MC báo sụt giảm p95 = **56.65%**, thực tế
**24.72%**. Lấy mẫu độc lập có thể rút ra nhiều lệnh thua liên tiếp hơn mẫu
hình thật.

Kết luận đúng: sai lệch **không có hướng cố định**, nên phân phối sụt giảm nó
đưa ra không có quan hệ xác định với hành vi thật khi các lệnh phụ thuộc chuỗi.
→ Cần bootstrap theo khối. **Chưa sửa.**

**Ghi chú thêm, chưa đo:** trong walk-forward, chỉ số in-sample được tính từ
một lần chạy tín hiệu **khác** với lần dùng để tối ưu (tối ưu chạy trên
`train_frame` riêng, báo cáo chạy trên cả `window` rồi cắt). Với chỉ báo nhân
quả thì hai cái trùng nhau, nhưng với chiến lược ML hoặc chỉ báo chuẩn hoá trên
toàn chuỗi thì không. Cần kiểm chứng.
