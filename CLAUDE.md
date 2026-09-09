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
