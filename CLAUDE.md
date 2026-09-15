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
- **Phiên KHÔNG liền mạch — có nghỉ trưa.** Đọc từ chính dữ liệu (VN30F1M,
  mật độ nến theo từng phút):

  | Khoảng | UTC | Giờ VN |
  |---|---|---|
  | Phiên sáng | 02:00–04:29 | 09:00–11:29 |
  | *Nghỉ trưa — không có nến* | 04:30–05:59 | 11:30–13:29 |
  | Phiên chiều | 06:00–07:29 | 13:00–14:29 |
  | ATC (một phút riêng lẻ) | 07:45 | 14:45 |

  Tính "số nến kỳ vọng" bằng cách lấy hiệu hai mốc thời gian sẽ **sai 90 phút
  mỗi phiên**. Đã suýt kết luận ba lần ngắt kết nối là mất dữ liệu trong khi cả
  ba rơi trọn vào giờ nghỉ trưa.

  Mỗi mã có hồ sơ phiên riêng: cổ phiếu bắt đầu 02:15 (ATO), phái sinh 02:00,
  nhóm `G-` chạy gần 24/5. Đừng áp hồ sơ của mã này lên mã khác.
- Giá niêm yết theo **nghìn đồng** (VIC 256.1 = 256 100 đ).
- **GIÁ KHÔNG ĐIỀU CHỈNH CHIA TÁCH / CỔ TỨC CỔ PHIẾU.** `api.v_history_1d` trả
  giá thô. Biên độ trần là 7% (HOSE), 10% (HNX), 15% (UPCOM), nên **mọi bước
  nhảy quá 20% trong một phiên là một sự kiện doanh nghiệp, không phải biến
  động thị trường**:

  | Mã | Phiên | Giá | Tỷ lệ |
  |---|---|---|---|
  | VNX | 2026-04-13 | 13,30 → 0,30 (−97,7%) | 44,33:1 |
  | CMN | 2026-06-11 | 82,10 → 28,70 (−65,0%) | 2,86:1 |
  | VIC | 2025-12-05 | 267,00 → 142,80 (−46,5%) | 1,87:1 |

  Đo được: **540 lần trên 320/1 533 mã (21%) chỉ trong 400 ngày gần nhất.**

  Hậu quả, theo thứ tự tốn tiền: một backtest đi qua ngày chia tách nhìn thấy
  một cú sập −46% **không có thật** và sẽ bán, dừng lỗ, hoặc bị thanh lý nếu có
  đòn bẩy; các chỉ số mô men bậc cao (skew, kurtosis) của danh mục mô tả chính
  cú nhảy giả đó chứ không mô tả rủi ro; và biến động cuộn vọt lên những mức
  không có nghĩa (đo được 104,5%/năm trên một danh mục bốn mã lớn).

  **Chưa có bản sửa.** Điều chỉnh lại đòi hỏi lịch sử sự kiện doanh nghiệp mà
  schema `api` không có. Trước khi tin bất kỳ kết quả nào trên cổ phiếu VN dài
  hơn vài tháng, phải kiểm mã đó có bước nhảy quá biên độ trần hay không.

---

## 4. Báo cáo

Ghi theo thứ tự mới nhất trước. Mỗi mục: phát hiện gì, đo được gì, đã sửa chưa.

### 2026-09-15 — Nâng cấp toàn diện giao diện workspace

Theo yêu cầu mới của Nam, giao diện chuyển sang nền sáng, menu navy, điểm nhấn
xanh dương. `workspace.css` được tải sau `styles.css`, giữ cấu trúc component
cũ và thống nhất header, thanh công cụ, panel, thẻ biểu đồ, form, bảng số liệu,
dialog, trình soạn thảo và trạng thái tương tác. Ưu tiên thiết kế mới này hơn
các ghi chú lịch sử về giao diện chỉ đen/trắng.

- Thêm tìm công cụ bằng Ctrl/Cmd+K, tìm tiếng Việt không dấu, phím mũi tên và
  Enter; lệnh dùng các control hiện có. Có nút đóng panel và toàn màn hình.
- Badge kết nối đọc trạng thái realtime thật; mã/khung thời gian ở tiêu đề
  theo ô đang làm việc. Các nhãn mới hỗ trợ Việt/Anh.
- Màn hình nhỏ dùng panel phủ bên cạnh menu; dưới 600px, 2/4 biểu đồ xếp dọc
  và cuộn. Đo ở 390px phát hiện `flex-wrap` cũ làm header tràn đến 918px;
  sau sửa, body rộng đúng 390px. Kiểm thêm 768, 1024 và 1536px đều không tràn.
- **Theo yêu cầu rõ ràng của Nam, bỏ ghi chú khi nguồn không có volume hoặc
  trả volume bằng 0.** Thay thế quyết định ghi chú ở báo cáo 2026-09-14 bên
  dưới. Không dựng cột giả; vẫn giữ bản sửa volume realtime và giới hạn pane.

Phát hiện thêm lỗi có sẵn ở nút **Lưu & nạp**: `Editor.save` gọi
`API.pluginImport` không tồn tại; API công khai là `API.importPlugin`.
Trước sửa, code hợp lệ nhưng đường dẫn lưu trống, đóng editor vẫn hỏi bỏ
thay đổi. Hai lỗi tiếp theo lộ ra sau đó: mẫu code dùng `params` dạng list
nhưng loader nhận dict (HTTP 422: `list has no attribute items`); callback
sau lưu gọi `Indicators.load` không tồn tại. Đã sửa mẫu Việt/Anh theo contract
(`type` cho chỉ báo, `params` dạng dict), cập nhật catalog qua `setCatalog`,
và await callback để lỗi được bắt. Thêm `tests/test_editor_templates.js`:
cả 4 mẫu thực tế đều được loader Python nạp và tính trên dữ liệu thử trong
thư mục tạm. Probe editor kiểm đường dẫn lưu, catalog cập nhật và đóng sạch.
Runner Chrome cũng ghi nhận và đóng hộp thoại confirm bất ngờ để test thất
bại rõ ràng thay vì treo ở `Runtime.evaluate`.

Đã kiểm tra bộ render Việt/Anh, 2 test i18n, cú pháp toàn bộ JS và 15 nhóm
Chrome: layout (14 kiểm tra), workspace (8), responsive (14), async, backtest,
panels, charttype, pickerflip, resize, persist, multichart, stay, tools,
editor, markets.
Đã xem ảnh chụp thật trên desktop và điện thoại. Backend và công thức tính
không đổi trong đợt nâng cấp này; không chạy lại toàn bộ 326 test Python.

### 2026-09-14 — Kiểm tra tính năng, volume trong lưới 4 ô và backtest

Đã kiểm tra 326 test Python (17 script), bộ render Việt/Anh, và 19 nhóm kiểm
tra trên Chrome: panels, charttype, pickerflip, types, guards, tools, persist,
resize, switching, autoscale, history, multichart, async, stay, layout,
backtest, picker, boot, markets. Các kiểm tra đều đạt sau sửa.

Các phát hiện và kết quả:

- **Volume ô vàng G-XAUUSD:** 200/200 nến 1h được kiểm tra có volume bằng 0;
  BTCUSDT, VNINDEX, VN30F1M đều có 200/200 giá trị dương. Biểu đồ giờ ghi
  rõ nguồn trả về 0, bằng Việt/Anh, thay vì để một vùng trắng không giải thích.
  Không dựng volume giả. Ghi chú tự ẩn nếu volume dương xuất hiện.
- **Volume realtime mất khi kéo lịch sử:** trên code trước sửa, cột live 777
  biến mất sau `prependCandles`, cột cuối quay về giá trị 20. Giờ mảng volume
  được cập nhật cùng series; cả cột mới 777 và lần sửa thành 888 được giữ lại.
- **Chỉ báo tràn sang ô dưới:** RSI/MACD/CCI ở ô đầu lưới 4 có đáy 685px,
  trong khi ô kết thúc tại 478,5px. Vùng chỉ báo giờ giới hạn 45% chiều cao,
  cuộn riêng; nến và volume vẫn nằm trong ô. Kiểm cả hàng cao và hàng thấp.
- **Backtest không dựng được biểu đồ vốn:** `EquityChart` tham chiếu `FONT`
  nằm trong scope của chart manager, gây `ReferenceError`. Dùng `CHART_FONT`
  chung; biểu đồ vốn đã vẽ được. Backtest trả về trễ giữ manager gốc: đo được
  38 dấu giao dịch ở ô gửi yêu cầu, 0 dấu ở ô khác, loading tắt đúng ô.
- **Kéo slider rồi chuyển ô ngay:** tham số RSI đã lưu thành 15 nhưng có
  0 yêu cầu tính mới. Giờ chạy lần debounce cuối trước khi đổi ô: đúng 1
  yêu cầu BTCUSDT/length=15 và kết quả vẫn về chart gốc.

Thêm `tests/test_chart_layout.html` (15 kiểm tra), probe `backtest`, mở rộng
probe `async` thành 8 kiểm tra. Runner `tests/run_browser_probes.js` tạo
browser context riêng cho mỗi nhóm để không sửa session trình duyệt đang dùng.
Ví dụ, với app ở :8000 và Chrome thử nghiệm có remote debugging ở :9223:

```text
node tests/run_browser_probes.js layout async backtest guards
```

Lỗi của phép kiểm đã phân biệt với lỗi sản phẩm: regex runner Python ban đầu
nhận nhầm thông báo thư viện “Failed to converge” là test fail dù script báo
40/40 và exit 0; browser runner ban đầu chưa nhận chuỗi kết thúc “chart guards
hold”, gây timeout giả. Đã sửa cách nhận kết thúc browser và chạy guards lại.

### 2026-09-14 — Phản hồi đến trễ khi chuyển ô biểu đồ

Tiếp tục trên các thay đổi chưa commit đang chuyển sang `ChartHub`/`DrawingHub`.
Đã tái hiện hai lỗi trên Chrome, bằng cách giữ phản hồi API rồi đổi ô:

| Thao tác | Trước | Sau |
|---|---|---|
| Tính RSI ở ô 0, chuyển ô 1 trước khi có kết quả | Số pane `[1, 0]` thành `[1, 1]`, dù ô 1 không bật chỉ báo | `[1, 0]`, kết quả chỉ vẽ vào ô gửi yêu cầu |
| Đổi BTC ô 0 từ 1h sang 4h rồi chuyển ô 1 | Nhãn 4h nhưng series vẫn `BTCUSDT\|1h`, loading không tắt | Ô gửi yêu cầu nhận đúng khung và tắt loading |

`loadCandles` giữ tham chiếu tới chart, drawing layer và loading của ô gửi yêu
cầu. Mỗi lần tải có token riêng, dùng chung với `loadCell`; phản hồi cũ không
được ghi đè lần tải mới, kể cả khi mã và khung giống nhau. Các cập nhật toolbar
chỉ chạy nếu ô đó còn được chọn. Tính chỉ báo cũng giữ ô, tham số và lần tải;
bỏ kết quả khi chỉ báo đã xóa, tham số đã đổi hoặc ô đã bị hủy.

Kiểm tra: probe `/static/_probe.html?only=async` có **7 pass, 0 fail** với nến
tổng hợp và phản hồi được chủ động giữ lại; probe `stay` trên dữ liệu thật có
**0 thay đổi khung nhìn/pane trong 6 lần bấm**. `tests/test_render.js` đạt toàn
bộ kiểm tra, `tests/test_i18n.py` đạt 2/2; kiểm tra cú pháp JS và `git diff
--check` không lỗi. Probe `async` thay API trong iframe và khôi phục sau kiểm
tra; nên chạy bằng hồ sơ trình duyệt thử riêng vì thao tác bố cục vẫn lưu session.

### 2026-09-18 (tối) — Các ô kết quả đè nhau, và "reload" khi đổi biểu đồ

**326 test Python** + **160 render check**, không lỗi. Probe mới `switchview`.

*Lưu ý khi đọc ảnh Nam gửi:* panel Kết quả trong ảnh vẫn còn tab "Tối ưu" và "Thống kê" — hai tab đã gỡ ở commit `d4e1f3c`. Trang trong ảnh chưa được tải lại sau commit đó.

#### 1. Ô đè nhau — một class không có CSS

Liệt kê mọi class mà JS/HTML sinh ra nhưng stylesheet không nhắc tới: 11 cái,
phần lớn là móc cho JS (`pf-cost`, `rp-close`…). Cái mang bố cục là
**`.stat-cards`** — khung chứa thẻ tóm tắt của tab Thị trường và cửa sổ Báo cáo.
Không có rule nào nên các thẻ rơi về block: một cột, thẻ này chạm thẻ kia.

| | Trước | Sau |
|---|---|---|
| Tab Thị trường | 4 thẻ một cột, sát nhau | lưới 2×2, cách 8px |
| Thẻ ở Monte Carlo / Thống kê | **1 cột** | **2 cột** |
| Hộp ghi chú | vạch trái 3px đè lên góc bo | vạch vẽ bên trong hộp |
| Tab con của Kết quả | "Thị trường" gãy thành 2 dòng | không xuống dòng, cuộn ngang nếu thiếu chỗ |
| Bảng rộng trong panel 344px | cột cuối bị cắt | cuộn ngang |

*Thẻ một cột ở Monte Carlo không phải do thiếu CSS:* `.metrics` đòi mỗi thẻ tối
thiểu 150px; hai thẻ cộng khe 8px là 308px, còn nội dung panel chỉ ~300px — nên
lưới tự rơi về 1 cột. Hạ xuống 132px.

*Và một lỗi hiển thị lộ ra cùng lúc:* ghi chú backend dùng `**…**` để nhấn mạnh
(`risk.py`, `stats.py`, `multi.py`) và **35 chỗ** trong 6 file frontend in nguyên
dấu sao ("được \*\*đo\*\*"). Thêm `emph()` cạnh `tp()`/`L()`, chạy **sau** khi
escape nên chỉ biến văn bản đã an toàn thành `<strong>`, không mở lỗ cho markup từ
payload.

#### 2. "Mỗi lần bấm, biểu đồ còn lại reload"

Có **hai** nguyên nhân, và nguyên nhân chính không nằm ở chỗ tôi đã sửa lần trước:

1. **Lớp phủ đang tải phủ cả khu biểu đồ**, không phải riêng ô đang làm việc.
   Mỗi lần bấm ô khác, biểu đồ chính nạp mã mới → logo tải + nền trắng mờ trùm
   lên **mọi ô**, trông y như tất cả cùng tải lại. Đã chuyển lớp phủ vào trong
   biểu đồ chính. Probe dò điểm giữa ô kia mỗi 30ms suốt lúc chuyển: **0 lần** bị
   lớp phủ che.
2. **Khung nhìn nhảy.** Ảnh chụp của một ô được đóng khung lúc vẽ (160 nến cuối),
   còn biểu đồ chính thì người dùng đã zoom/cuộn — đổi qua lại là khung nhìn nhảy,
   và biểu đồ nhảy thì đọc như biểu đồ vừa tải lại. Giờ khoảng thời gian đang xem
   được mang theo cả hai chiều:

| | Đo được |
|---|---|
| Ô vừa rời, trước khi rời | 25/08 11:00 – 31/08 04:00 |
| Ảnh chụp ô đó sau khi rời | 25/08 11:00 – 31/08 04:00 — **giữ nguyên** |
| Ảnh chụp ô được chọn | 28/07 09:00 – 14/09 14:00 |
| Biểu đồ chính ở ô đó sau khi nạp | 28/07 09:00 – 14/09 14:00 — **giữ nguyên** |
| Request mỗi lần bấm | đúng **1** (nến của ô được chọn) |

*Theo §2.2, hai lần đọc sai của tôi:* lần đầu biểu đồ chính "sau khi vào" đọc ra
23/04–05/06 và tôi suýt đi tìm lỗi ánh xạ thời gian. Ghi vết mỗi 30ms thì thấy đó
là giá trị ở mili giây thứ 30 — **trước khi vẽ lại**; mili giây 120 đã đúng. Vì
khung hình trung gian đó có thật trong một khoảnh khắc, biểu đồ giờ chỉ hiện ra
sau một nhịp vẽ. Lần hai, headless không chạy `requestAnimationFrame` nên biểu đồ
đứng ở trạng thái "đang chờ" mãi — đúng thứ sẽ xảy ra ở tab chạy nền của trình duyệt
thật; thêm hẹn giờ 80ms làm dự phòng.

### 2026-09-18 (chiều) — Lịch sử không giới hạn, công cụ có nút riêng, đổi ô không tải lại

**326 test Python** + **160 render check**, không lỗi. Bốn nhóm probe mới: `history`, `switchload`, `pickerflip`, `tools`.

| Việc | Đo được |
|---|---|
| 1. Không giới hạn nến, kéo về sau là nạp | Biểu đồ chính, cuộn bằng bánh xe 4 lần: nến cũ nhất **23/06 → 12/05 → 31/03 → 18/02 → 07/01**, mỗi lần đúng 1 trang. Ô phụ cũng nạp trang cũ hơn khi cuộn (trước đây cố định 600 nến) |
| 2. Thống kê, Monte Carlo, Tối ưu có nút riêng | Ba nút mới dưới cùng rail. Bấm chạy → mở đúng panel đó, kết quả nằm trong chính panel (1 792 / 3 300 / 740 ký tự). Panel Kết quả còn 4 tab: tổng quan, lệnh, thị trường, kiểm định |
| 3. Đổi ô không tải lại ô khác, bỏ khung đen | Mỗi lần bấm chỉ **1 request nến** — của ô vừa chọn. Ô vừa rời hiện lại ảnh chụp sẵn, không tải lại (trừ khi đã đổi mã/khung/chỉ báo). Ô được chọn giữ ảnh chụp tới khi biểu đồ chính nạp xong, không nháy trắng. Không còn viền; ô đang làm việc có chấm navy ở chú thích |
| 4. Ô chọn thị trường bị che | Nút gần đáy panel giờ mở popup **lên trên**, nằm trọn trong cửa sổ, thấy 11 dòng |

#### Hai lỗi thật tìm thấy trong lúc làm việc 1

- **Trang lịch sử gửi giờ biểu đồ (+7h) thay vì UTC.** Mỗi trang xin một đoạn kết
  thúc muộn hơn nến cũ nhất 7 tiếng; phần trùng bị lọc nên trông vô hại, nhưng
  mọi trang đều tải lại những nến đã có.
- **Chỉ báo luôn tính trên `state.limit` (2 000 nến)** dù biểu đồ đã nạp thêm lịch
  sử, nên đoạn cũ hơn không có chỉ báo. Giờ tính trên số nến biểu đồ đang giữ.

#### Ba lần phép đo của tôi sai, ghi theo §2.2

1. Probe lịch sử đặt khoảng hiển thị trực tiếp bằng `setVisibleLogicalRange`; lần
   hai báo "KHÔNG nạp". Headless không vẽ lại giữa hai lệnh nên khoảng đó **chưa
   bao giờ có hiệu lực** — app chưa từng được hỏi. Đọc lại khoảng ngay sau khi đặt
   vẫn ra giá trị cũ, đó là manh mối. Chuyển sang cuộn bánh xe như người dùng: 4/4
   trang về. Trước khi tìm ra, đã loại trừ hai giả thuyết bằng số đo: không phải
   hết dữ liệu (kho BTC có nến 1h tới 2025-01-01), không phải đường lỗi (không có
   toast nào).
2. Probe công cụ báo Tối ưu "hết thời gian". Tối ưu **đúng là từ chối chạy** khi
   chưa tích tham số nào để quét; probe chờ một bảng không bao giờ đến. Tích một
   tham số dải 10–30 thì chạy.
3. Lần đo đổi ô đầu tiên còn 1 request thừa ở lần rời ô ban đầu — ảnh chụp của ô
   đang làm việc được dựng muộn. Giờ dựng sẵn cho mọi ô khi vẽ lưới; đo lại: đúng
   1 request mỗi lần bấm.

#### Giới hạn

- Kéo lịch sử dừng ở nơi dữ liệu dừng. Chỉ đo một mã: VIC 1h trước 01/06/2025
  trả **0 nến**, nên nến phút VN có điểm bắt đầu gần hơn nhiều so với nến ngày;
  điểm bắt đầu của từng mã chưa đo.
- Ảnh chụp của ô không làm việc không cập nhật live; chỉ ô đang làm việc là live.

### 2026-09-18 — Mọi ô trong bố cục 2/4 là một biểu đồ đầy đủ

**326 test Python** + **160 render check**, không lỗi. Probe `multichart`, `resize`, `persist` viết lại cho lưới mới; `switching`, `picker`, `markets`, `boot` chạy lại, không hồi quy.

#### Cách làm, và vì sao không nhân bốn `ChartManager`

`ChartManager` ôm một biểu đồ cùng mọi thứ treo trên nó: overlay và pane chỉ báo
đồng bộ theo chỉ số (§3.3), hình vẽ, dấu lệnh, đường SL/TP của Paper, bộ nạp lịch
sử, luồng live. Nhân bản nó là phải luồn một mã biểu đồ qua tất cả những thứ đó.

Thay vào đó mỗi ô giữ một **không gian làm việc** — mã, khung thời gian, danh sách
chỉ báo kèm tham số — và **biểu đồ đầy đủ nằm ở ô đang chọn** (viền đen), như bố
cục nhiều biểu đồ của các phần mềm charting. Bấm ô khác: DOM của biểu đồ được
**dời** (không dựng lại) sang ô đó và nạp không gian của ô đó; ô vừa rời vẽ lại
nến **và chỉ báo của chính nó** từ cùng endpoint compute. Chỉ báo, chiến lược, hình
vẽ, Paper không phải biết có nhiều biểu đồ.

**Giới hạn, nói trước (§2.7):** chỉ ô đang chọn là live. Các ô khác là ảnh chụp
600 nến gần nhất lúc vẽ, vẽ lại khi đổi mã/khung/chỉ báo. Backtest chạy trên ô
đang chọn.

#### Đo được

| Việc | Kết quả |
|---|---|
| Bố cục 4 | lưới 2×2 đều: **640×422** mỗi ô (trước: một hàng ba ô nhỏ trên một biểu đồ lớn) |
| Ô không chọn có nến | 4 123 / 6 485 / 4 099 điểm ảnh màu nến |
| Bấm ô 2 | biểu đồ chính sang ô 2, series `VN:G-XAUUSD|1h`, chỉ báo của ô đó (0) |
| Ô vừa rời | vẫn vẽ nến + RSI, chú thích "BTCUSDT · 1h · RSI 14" |
| Backtest | chạy trên ô đang chọn: 12 chỉ số, series G-XAUUSD |
| Bánh răng ô 1 → 1d | chỉ ô 1 đổi ("VNINDEX · 1d"), ô đang chọn vẫn 1h |
| Bật RSI 3 lần | **1** bản trên biểu đồ, **2** thông báo "RSI đã bật trên biểu đồ này…" |
| Tổng quan khi đang 4 ô | 1 ô hiện, biểu đồ rộng bằng cả lưới (1 384px) |
| Giao dịch lại | 4 ô, đúng 4 mã như trước |
| Kéo cột +200 / hàng −120 | 640→839/440 rộng; 422→302/541 cao; nhấp đúp về mặc định |
| Tải lại trang | VIC 15m + RSI, `fast=5`, layout 2, ô 1 "VNINDEX · 1d" — **giữ nguyên toàn bộ** |

Ô mới mở ra trên một thị trường **chưa có trên màn hình** (VNINDEX, VN30F1M, vàng,
BTC…), không để trống: một ô trống không bấm vào làm việc được, còn một bản sao mã
đang hiện thì không nói thêm gì.

*Một lỗi lộ ra từ DOM, không từ ảnh:* chính lưới mang thuộc tính `data-layout`, và
hàm đánh dấu nút layout chọn theo `[data-layout]` nên gắn nhầm `active` lên lưới.
Giờ chỉ chọn `button[data-layout]`.

*Chú thích:* bản đầu in "RSI 14,100" — 100 là hệ số `scalar` kiểu float. Chú thích
giờ chỉ lấy tham số nguyên (chu kỳ), đúng cách người ta gọi tên chỉ báo.

### 2026-09-17 (tối) — Thiết kế lại giao diện, và 12 mục Nam giao

**326 test Python** + **160 render check**, không lỗi. Chín nhóm probe trình duyệt mới trong `frontend/_probe.html` (`?only=<nhóm>`).

#### Thiết kế lại: "mực trên giấy"

Cái "nhựa" không nằm ở màu mà ở **cạnh**: mọi điều khiển là một hộp có viền,
mọi nhóm là hộp có viền trong một panel có viền, bo góc lệch nhau từng chút.
Giờ cấu trúc đến từ khoảng trống và nền xám nhạt; viền chỉ còn ở chỗ mang
thông tin (quanh biểu đồ, dưới tiêu đề bảng).

- **Một font: Be Vietnam Pro**, vẽ riêng cho tiếng Việt (dấu chồng ế/ộ/ữ nằm
  đúng chỗ). Để **local** ở `frontend/fonts/` (12 file, **185KB**), không gọi
  Google Fonts — link đó từng đo 319ms trên đường tải (mục 2026-09-15). Trục giá
  của biểu đồ cũng dùng font này thay cho font code.
- **Chuyển động chỉ để trả lời thao tác**: thanh chọn khung thời gian có một
  "viên" đen trượt tới lựa chọn mới (`frontend/js/ui.js`), panel mở thì trượt
  vào, hộp thoại nổi lên. Không có gì tự chuyển động. `prefers-reduced-motion`
  tắt hết.
- Giá trên thanh trên luôn màu mực; hướng tick là một mũi tên nhỏ. Trước đây giá
  đỏ đứng cạnh phần trăm xanh trên cùng một màn hình.

*Ba lỗi chỉ ảnh chụp mới bắt được:* `text-transform: capitalize` biến "Của bạn"
thành "Của **B**ạn" (sai tiếng Việt → chỉ viết hoa chữ đầu); bảng đặt lệnh Paper
nằm trong lưới 2 cột nên chỉ chiếm **nửa thẻ**, ô cắt lỗ/chốt lời cắt mất chữ
gợi ý; tiêu đề panel xuống dòng làm tách đôi cụm nút.

#### Lỗi "1 biểu đồ mà không full màn hình"

`.multi-charts { display: grid }` **đè lên thuộc tính `hidden`** (thuộc tính đó
chỉ có độ ưu tiên của selector thẻ). Ở chế độ 1 khung, dải so sánh vẫn chiếm chỗ:

| | Trước | Sau |
|---|---|---|
| Dải so sánh ở chế độ 1 | **321px** | **0px** |
| Biểu đồ chính | 521px | **842px** |

Sáu thành phần đã tự thêm rule `[hidden]` riêng sau từng lần gặp lỗi; giờ có
**một** rule `[hidden] { display: none !important }` đóng cả lớp lỗi này.
*Probe cũ của tôi báo "đã ẩn"* vì nó đọc `el.hidden` chứ không đo chiều cao —
đo sai đại lượng (§2.1).

#### 12 mục

| # | Mục | Kết quả đo |
|---|---|---|
| 1 | "Chạy nhiều thị trường không ra gì" | API **luôn chạy đúng** (200, 3,1s, đủ mã). Bảng được ghi vào panel **Kết quả** trong khi nút nằm ở panel **Chiến lược** → màn hình không đổi. Giờ tự mở đúng tab: probe thấy `panel=results, tab=markets`, 4 dòng |
| 2 | Chỉ vào khi database đã tải | Splash chờ nến + danh sách mã VN (+ catalog nếu mở chế độ Giao dịch), **trần 20s** để VPN tắt không khoá cửa mãi. Probe: splash rời **sau** khi dữ liệu về |
| 3 | Tìm mã | `symbol-picker.js`: bỏ dấu, bỏ `VN:`, mã khớp chính xác xếp trước. "vic"→VIC đầu, "VN30F"→4 hợp đồng, Enter nạp VIC. Dùng cho cả ô chọn mã chính, ô so sánh và ô thêm thị trường |
| 4 | Bỏ "Đang bù n nến…" | Thay bằng logo Quant Percent đang tải; bỏ luôn toast "Đã tự bù n nến" |
| 5 | Mặc định không mở panel trái | Đã đóng; panel mở lần trước thì mở lại |
| 6 | Paper trading | Nhịp đều 10/8px, ô cao bằng nhau, số không xuống dòng, trạng thái chuyển xuống dưới tên; con trỏ **cố định** trong suốt lúc kéo panel; bề rộng tối thiểu 260→300px |
| 7 | Chỉ đen/trắng, xanh-đỏ cho nến, navy cho chú thích | `--warn` giờ trỏ về `--note` (navy `#1c2f5e`); bỏ vàng/cam; bảng màu chỉ báo (cả `backend/indicators/base.py`), huy hiệu mã, biểu đồ tròn danh mục đều thành sắc navy |
| 8 | Mất nến khi đổi mã/khung | **CHƯA tái hiện được** — xem dưới |
| 9 | Khung thứ 2 không full | Ô được tạo lấy bề rộng **một lần** lúc dựng → giờ `autoSize`. Probe: 3 ô 426px ở cửa sổ 1500px |
| 10 | Reload không mất việc | `session.js`. Probe dựng phiên VIC 15m + panel Chiến lược + `fast=5` + RSI + 2 khung VNINDEX, reload → **giữ nguyên toàn bộ** |
| 11 | Bỏ ô li sau nến | Tắt lưới ở biểu đồ chính, ô so sánh, đường vốn |
| 12 | Kéo giãn khung 2/4, tên mã mỗi khung | Kéo xuống 120px → dải +120 / biểu đồ −120; kéo cột 200px → 426/426/426 thành **626/226/426**; nhấp đúp về mặc định. Khung chính có nhãn tên mã + khung thời gian |

**Mục 10, lần đo đầu mất hai thứ** và cả hai đã sửa: khung 15m quay về 1d (trước
khi danh sách VN về, mọi mã VN trông như chỉ có nến ngày nên bị ép về 1d), và ô so
sánh mất tên (gán giá trị trước khi `<select>` có option, rồi giữ nguyên giá trị
rỗng đó khi dựng lại).

**Phạm vi thật của mục 10** (§2.7): giữ mã, khung, chế độ, panel đang mở, chỉ báo +
tham số, chiến lược + tham số, bố cục 1/2/4 + mã + kích thước (cộng các thứ vốn đã
nhớ: kiểu biểu đồ, hình vẽ, dấu sao, bề rộng panel, ngôn ngữ). **Chưa giữ**: các ô
nhập của Danh mục, khoảng ngày/chi phí backtest, code đang soạn dở trong trình
viết code, cửa sổ báo cáo đang mở.

#### Mục 8 — chưa tái hiện được, không nhận là đã sửa

Theo §2.2, cả ba lần đo đều **không** ra lỗi:

1. Đổi mã/khung nhanh và chậm, đếm điểm ảnh màu nến: có nến sau mọi lần đổi.
   *Lần đầu probe báo 0 ở cả 8 bước* — sai của probe: nó chọn "canvas lớn nhất",
   mà `#chart-main` có lớp vẽ hình (`.draw-layer`) trong suốt cùng kích thước.
   Hai cặp số trùng khít (13 533, 10 708) cũng cho thấy headless chưa chắc đã vẽ
   lại kịp, nên phép đo này không đủ để kết luận "không có lỗi".
2. Giả thuyết từ ảnh của Nam: trục giá đứng ở 75,5k–79,75k trong khi khung nhìn
   là tháng 6 (BTC ~60k) → **thang giá đã thôi tự co giãn** (kéo dọc biểu đồ làm
   Lightweight Charts tắt autoscale), nến vẫn còn nhưng nằm ngoài khung. Đo trực
   tiếp `priceScale().options().autoScale` qua `w.eval('ChartManager')`: sau khi
   kéo dọc rồi đổi mã, autoscale **vẫn bật**, nến **trong khung**. Có thể sự kiện
   chuột giả không kích hoạt được cơ chế đó — chưa loại trừ.

Đã thêm một chốt chặn đúng về nguyên tắc dù chưa chứng minh được là nguyên nhân:
**mỗi lần nạp chuỗi mới đều bật lại autoscale** — một thang giá chỉnh tay là lựa
chọn cho một chuỗi, không được mang sang mã khác. **Cần Nam cho các bước chính xác**
(kéo/cuộn biểu đồ trước khi đổi không, đang ở kiểu biểu đồ nào, đổi bằng ô chọn
hay sao).

#### Giới hạn dữ liệu lộ ra khi làm ô tìm mã

Gõ "vingroup" không ra VIC — **không phải lỗi ô tìm**: `v_quote` trả `name = "VIC"`
cho VIC, và chỉ **357/1 726** mã có tên công ty thật. Tìm theo tên công ty chỉ tốt
tới mức database có tên.

#### Còn tồn

- Dòng mô tả dưới tên phiên Paper vẫn cắt tên thị trường ("BTCUS…") khi có nhãn
  trạng thái và nút Dừng ở bên phải.
- Hai file probe `frontend/_probe.html` và `frontend/_shot.html` (điều khiển ảnh
  chụp) được giữ lại có chủ ý.

### 2026-09-17 — Bốn việc: đen trắng, Paper, đa khung, tab Học máy; và 16 chỉ số lên giao diện

**326 test Python** (trước 291) + **160 render check** (trước 109), không lỗi.

#### 1. Đen và trắng

Nam chọn "chỉ đen và trắng". Mọi thứ thuộc **khung giao diện** giờ là mực
`#131722` trên trắng: nút chính, tab đang chọn, viền focus, đường giá vào lệnh.

**Giữ lại màu ở đúng hai chỗ, và đây là giả định của tôi — Nam phủ quyết được:**
xanh/đỏ cho **hướng giá và lãi/lỗ** (nến, số dương/âm), và bảng màu **đường chỉ
báo**. Cả hai là dữ liệu chứ không phải trang trí: nến đen trắng thì không đọc
được hướng, còn ba đường EMA cùng màu đen thì không phân biệt được. Nếu Nam
muốn cả hai thứ này cũng thành đơn sắc thì đó là một thay đổi token trong
`:root` của `styles.css`.

#### 2. Panel Paper trading

Phần cài Telegram (bot token, chat id, ba nút) chiếm **phần lớn 397px** mà
panel phải cuộn, trong khi nó là cài đặt toàn cục chạm một lần, không liên
quan tới phiên nào. Chuyển ra hộp thoại sau nút **Thông báo** ở đầu panel.
Panel giờ chỉ còn: thanh hành động → nút giao dịch tay → danh sách phiên.

Panel Chiến lược: hai nhóm ít đổi (**Khoảng thời gian**, **Chi phí & vốn**) gập
thành `<details>`.

#### 3. Đa khung biểu đồ

Nút **1 / 2 / 4** trên thanh trên = số thị trường trên màn hình. Biểu đồ đang
làm việc (có chỉ báo, hình vẽ, đường SL/TP) luôn là một trong số đó và giữ chỗ
lớn phía dưới; các ô so sánh là nến + ô chọn mã, nằm thành **một hàng** phía
trên. Dải chỉ báo phụ nằm dưới cùng như trước.

*Bố cục đầu tiên sai và ảnh chụp cho thấy:* "4" dựng lưới 2×2 cho **ba** ô so
sánh, nên ô thứ tư trống trơn — trông như hỏng chứ không như một bố cục. Đổi
thành một hàng ba ô.

Đo bằng trình duyệt thật (`_probe.html?only=multichart`, chạy 3 lần liền, cả 3
giống hệt):

| | |
|---|---|
| VNINDEX / G-XAUUSD / VIC | **2 511 / 2 811 / 2 536** điểm ảnh màu nến mỗi ô |
| Dải chỉ báo phụ, trước → sau khi thêm RSI | 0px → **128px** |
| Biểu đồ chính khi dải mở | 520px → 392px, ba ô so sánh vẫn vẽ |
| Về lại "1" | 0 ô, band ẩn |

Đếm **điểm ảnh màu nến** chứ không đếm canvas: một biểu đồ đã mount và một
biểu đồ có nến trông y hệt nhau từ DOM.

*Ba lần phép đo của tôi sai trước khi ra được bảng trên, ghi theo §2.2:*

1. Probe gọi `w.MultiChart.setSymbolAt(...)` và **chết ngay dòng đó** — mọi
   module ở đây là `const` top-level, không tạo thuộc tính trên `window`. Đúng
   cái bẫy `window.Live.enabled` đã ghi ở mục 2026-09-16. Ảnh chụp ra một dải
   xám rỗng, trông như tính năng hỏng. Giờ probe chỉ điều khiển bằng control thật.
2. Chọn mã bằng `window.prompt()`: không chọn được từ 1 728 mã theo nhóm, và
   hộp thoại modal **chặn trang** nên headless Chrome treo. Thay bằng `<select>`
   lấy từ **cùng catalog** của ô chọn mã chính.
3. Sau khi sửa, ba lần chạy liên tiếp ra **3, rồi 2, rồi 1** ô có nến. Không
   phải tính năng chập chờn: ô trống luôn có canvas rộng **288px** (thang giá
   chưa có nhãn = chưa `setData`), còn ô có nến 280/286px. Probe ngủ 7 giây cố
   định trong khi mỗi ô tải qua VPN mất 1,1–1,8s và không xong cùng lúc — tôi
   đang đo **độ kiên nhẫn của probe**. Giờ probe chờ đúng điều kiện ("mọi ô có
   điểm ảnh nến"), không chờ đồng hồ.

Mỗi lần đổi mã chỉ dựng lại **đúng ô đó**, và kết quả tải về muộn của một ô đã
đổi mã bị bỏ — bản đầu dựng lại cả band mỗi lần chọn, nên lần tải của các ô cũ
đáp xuống node đã bị gỡ.

#### 4. Tab Học máy chỉ cho chiến lược ML

Backend không tính khối `ml` khi chiến lược không xuất `ml_probability`; tab
tự ẩn khi khối đó vắng. Trước đây EMA cross nhận nguyên một tab gạch ngang cộng
những con số Tổng quan đã có — **trông như một kết quả**.

Test mới kiểm cả hai nửa, và **đã xác nhận nó bắt được lỗi**: bỏ phần chặn ở
backend → 2 check đỏ; bỏ phần ẩn ở frontend → 1 check đỏ.

*Lần kiểm đầu của tôi cho kết quả sai, §2.3:* bỏ phần chặn backend mà test vẫn
xanh. Nguyên nhân: `render_payloads.py` in nguyên khối `ml` (có văn xuôi tiếng
Việt) ra console cp1252 → `UnicodeEncodeError` → script chết **trước khi ghi
fixture**, và tôi đã lọc output bằng `grep` nên không thấy traceback. Test chạy
trên fixture cũ. Đã sửa dòng in, và fixture ML giờ sinh từ chính `build_report`
với một mảng xác suất thật chứ không viết tay.

#### 16 chỉ số danh mục lên giao diện — tab **Hiệu suất**

Mục 2026-09-16 để chúng chỉ nằm trong payload. Giờ có tab riêng, bốn nhóm: Lợi
nhuận (CAGR, Sharpe, Sortino, Calmar), So với VN-Index (Information ratio,
Alpha, Beta, Upside/Downside capture), Hình dạng phân phối (Skew, Excess
kurtosis), Ổn định theo thời gian (Sharpe và biến động cuộn). VaR/CVaR, sụt
giảm tối đa và HHI đã có ở tab Tổng quan và Đa dạng hoá.

**Một tỷ số bị từ chối in ra lý do, không in dấu gạch** — "chưa có phiên lỗ nào
trong cửa sổ này" và "không đủ phiên trùng với VN-Index" là hai sự thật khác
nhau, còn một dấu gạch không nói cái nào. Test kiểm từng lý do; bỏ bảng lý do
đi thì 3 check đỏ.

Đo trên danh mục thật VIC/VNM/FPT/HPG, 252 phiên:

| | |
|---|---|
| CAGR / Sharpe / Sortino / Calmar | +34,85% / 0,58 / 0,67 / 0,83 |
| Information ratio / Alpha / Beta | 0,47 / +18,94% / 1,25 |
| Upside / Downside capture | 119,4% / 102,5% |
| Skew / Excess kurtosis | **−6,74 / 77,45** |
| Sharpe cuộn / biến động cuộn | −2,15 … 5,92 / 24,6% … 89,5% |

Kurtosis 77 là **cú chia tách chưa điều chỉnh của VIC ngày 2025-12-05** nằm
trong cửa sổ (§3.6), không phải rủi ro. Thẻ kurtosis tự ghi "rất cao — kiểm tra
xem có nến giá chưa điều chỉnh không" khi vượt 10. Sharpe, alpha và capture của
danh mục này cũng bị cú nhảy đó kéo lệch — **đừng tin bảng trên cho tới khi
dữ liệu được điều chỉnh**.

#### Cần Nam làm

**Khởi động lại `run.py`.** `/api/health` đang báo `stale: true`: phần chặn
tab Học máy nằm ở backend (`report.py`), nên server hiện tại vẫn trả khối `ml`
cho mọi chiến lược cho tới khi restart. Phần frontend không cần.

### 2026-09-16 (tiếp) — Chỉ số danh mục, và bốn việc Nam vừa giao

#### Đã xong trong vòng này

`backend/portfolio/metrics.py` — 11 chỉ số còn thiếu so với bảng Nam đưa, nối
vào `analyse()` dưới khoá `performance`. Đo trên danh mục thật (VIC/VNM/FPT/HPG,
500 phiên, benchmark VNINDEX):

| | |
|---|---|
| CAGR | 79,08% |
| Sharpe / Sortino / Calmar | 1,228 / 1,498 / 1,755 |
| Information Ratio | 0,978 (tracking error 41,44%) |
| Alpha | 36,97% |
| Upside / Downside capture | 133,2% / 96,8% (274 phiên tăng, 225 giảm) |
| Rolling Sharpe spread | 8,402 — biến động cuộn 9,5%–104,5% |
| Skew / Excess kurtosis | **−7,044 / 105,418** |

**Không chỉ số nào trả về một con số trần.** Mỗi tỷ số đi kèm một `code`, và từ
chối chia khi mẫu số là nhiễu thay vì in ra một con số lớn bịa từ 1e-17 — đúng
lớp lỗi K-ratio ở §2.6. Ví dụ: Calmar từ chối khi chưa có sụt giảm thật
(`no_drawdown_yet`); Information Ratio trả `tracks_the_benchmark` khi tracking
error gần 0; capture tách hai phía và mỗi phía cần tối thiểu 10 phiên riêng.

**Một dấu hiệu phải nói ra theo §2.7, chưa điều tra:** skew −7,04 và excess
kurtosis **105,4** là cực đoan đến mức gần như chắc chắn không phải rủi ro
thật — cộng với biến động cuộn chạm **104,5%/năm**, nhiều khả năng có một phiên
nhảy giá do **chia tách cổ phiếu chưa điều chỉnh** trong `v_history_1d`. Nếu
đúng thì mọi chỉ số dựa trên mô men bậc cao đang mô tả một lỗi dữ liệu. **Cần
kiểm trước khi tin bảng này.**

#### Còn lại — bốn việc Nam giao, chưa bắt đầu

1. **Giao diện toàn nền tảng**: tông trắng/đen/xanh lá/xanh dương/đỏ. Lưu ý
   ràng buộc đang có: xanh lá và đỏ hiện **chỉ dành cho hướng giá và lãi/lỗ**
   (quy tắc số một của `styles.css`); dùng chúng làm màu chủ đạo sẽ phá quy tắc
   đó, nên cần thống nhất lại với Nam ranh giới mới.
2. **Panel Paper trading**: dựng lại cấu trúc và trình bày theo tông trên.
3. **Đa khung biểu đồ**: chia 2 hoặc 4 ô nến cho 2–4 mã (tối đa 4), cộng một
   dải ngang nhỏ phía dưới cho chỉ báo phụ. Lưu ý §3.3: các pane đồng bộ theo
   **chỉ số**, nên mỗi chuỗi phải có đúng một điểm mỗi nến.
4. **Báo cáo → tab Học máy**: chỉ chạy cho chiến lược ML; chiến lược thường
   không cần tính lại phần đó.

#### Trạng thái kỹ thuật

~~`metrics.py` chưa có test riêng và chưa lên giao diện~~ — **đã xong ở mục
2026-09-17**: `tests/test_portfolio_metrics.py` (16 check) và tab **Hiệu suất**.
Nghi vấn chia tách ở trên **đã xác nhận**, ghi ở §3.6.

### 2026-09-16 — Nút bị cắt, bỏ điều khiển thừa, gập catalog, và giới hạn của dữ liệu VN

**291 test Python** + toàn bộ render check, không lỗi. Ratchet i18n siết hai nấc trong phiên này: `app.js` từ 95 xuống **70** chuỗi chưa dịch.

#### Nút kiểu biểu đồ "không ấn được" rồi "mất khung" — cùng một nguyên nhân

`.topbar-controls` có `overflow-x: auto` (thêm 2026-09-09 để dải khung thời
gian không đè lên giá ở cửa sổ hẹp). Một vùng cuộn **cắt mọi thứ tràn ra**, và
nút kiểu biểu đồ là con cuối cùng của nó:

| Đo được | |
|---|---|
| `.ct-picker` mép phải | **751px** |
| `.topbar-controls` mép phải | **710px** |

Nút bị cắt mất 41px — đúng phần viền phải và nửa mũi tên, nên nó *trông như*
một nút hỏng. Cùng vùng cuộn đó trước đấy đã cắt luôn cái menu 476px xuống còn
một mẩu, khiến bấm vào thì trúng canvas phía sau.

Sửa ở gốc thay vì vá từng thứ: **thứ cần cuộn là dải khung thời gian**, không
phải cả nhóm. `overflow-x: auto` chuyển xuống `.tf-group`; `.topbar-controls`
không cắt gì nữa. Đo lại: `ct phải = controls phải = 751` → không còn tràn.

#### Bỏ "Realtime" và "Cập nhật dữ liệu"

Cả hai là công tắc cho những việc **giờ đã tự xảy ra**: luồng realtime bật từ
lúc khởi động (2026-09-10), và nến thiếu được bù ngay khi nạp chuỗi. Một cái
đèn lúc nào cũng xanh thì không nói gì, còn một cái nút cho việc đã tự chạy chỉ
là thêm thứ để đọc nhầm.

*Một chi tiết phải xử lý cùng, nếu không sẽ hỏng lặng lẽ:* phần tự bù có ngưỡng
5 000 nến, trên ngưỡng thì nó dừng và bảo *"bấm Cập nhật dữ liệu"* — một cái nút
vừa bị xoá. Ngưỡng đó giờ đã bỏ: bù dài thì chậm chứ không nguy hiểm, và dòng
trạng thái vẫn nói trong lúc chạy.

Dọn theo: `runBackfill`, `applyMarketCapabilities`, ba tham chiếu phần tử, và
6 dòng CSS `.live-dot`/`.live-toggle`.

#### CSV và Báo cáo về đúng chỗ của chúng

Cả hai nằm trên `panel-head`, nên chúng đọc như hành động áp lên *tab đang mở*
— mà đó chính là thứ chúng không phải. Cả hai đều thao tác trên danh sách lệnh:
báo cáo dựng từ nó, còn CSV **chính là** nó. Giờ chúng nằm trong tab **Lệnh**.
**PNG đã bỏ hẳn** theo yêu cầu.

#### Panel Chỉ báo: 8 màn hình cuộn còn 0

Đo cả năm panel để biết cái nào thật sự rối, thay vì sửa theo cảm giác:

| Panel | Cao nội dung | Phải cuộn | Điều khiển |
|---|---|---|---|
| **Chỉ báo** | **6 280px** | **5 613px** | **193** |
| Chiến lược | 874px | 87px | 44 |
| Paper | 1 184px | 397px | 17 |
| Kết quả / Danh mục | vừa khung | 0 | 2 / 22 |

Chỉ báo rối gấp **14 lần** panel kế tiếp. Và nguyên nhân không phải thiếu cấu
trúc: catalog **đã** nhóm theo 11 danh mục từ trước, chỉ là **mở hết cùng lúc**.
Dữ liệu phân loại vốn đã có trong payload (`category`: momentum 53, overlap 45,
trend 22…) — frontend chỉ chưa dùng nó để gập.

Giờ mỗi danh mục là một `<details>`, và nó mở khi **có lý do để nhìn vào**:
đang tìm kiếm, đang chứa chỉ báo có trên biểu đồ, là nhóm ★, hoặc người dùng tự
mở. Nhóm người dùng mở được nhớ lại, nếu không thì mỗi lần đánh dấu sao hay
thêm chỉ báo sẽ gập sập nhóm họ đang làm việc.

Đo lại: **6 280px → 667px, cuộn 5 613px → 0px.** Vừa đúng một màn hình.

#### "Data chảy chưa mượt" — một thị trường ổn, một thị trường chạm trần dữ liệu

Đo bằng một client WebSocket nối thẳng vào `/ws/live`, không qua trình duyệt:

| | Số nến / 40s | Khoảng cách | Giá đổi |
|---|---|---|---|
| BTCUSDT | 21 | trung vị **2,0s** | 18/20 lần |
| VN30F1M | **0** | — | — |

BTC mượt. VN thì **không thể mượt hơn**, và lý do nằm ở nguồn chứ không ở code:

1. `_run_vn_poll` chỉ đẩy nến có `open_time` mới, nên khung 1m tối đa **một lần
   mỗi phút**.
2. Không có nến đang hình thành để đẩy. Đo ba lần cách nhau 12 giây, có và
   không có bộ lọc `ts < date_trunc('minute', now())`: **hai bên luôn cho cùng
   một dòng**. Pipeline chỉ ghi nến sau khi phút đã đóng.
3. `api.v_quote` cũng không cứu được: giá một mã mất **4–7 giây** mỗi truy vấn,
   và `data_as_of` của nó cũng chỉ có độ phân giải phút (07:09:00).

Nên với thị trường VN, **một lần mỗi phút là trần**, không phải lỗi. Nói ra
theo §2.7 thay vì để Nam tự đoán.

*Cải thiện thật làm được:* poll mỗi 5 giây nghĩa là **11 trong 12 lần hỏi một
view tốn vài giây để nhận đúng câu trả lời cũ**. Vòng lặp giờ ngủ tới ngay sau
mốc phút (`VN_BAR_SETTLE_SECONDS = 2`) — nơi nến tiếp theo mới có thể tồn tại.
Tải database giảm khoảng **12 lần**, và độ trễ từ "tối đa 5 giây sau khi nến
sẵn sàng" xuống còn khoảng 2 giây. Khi đang backoff vì lỗi thì vẫn dùng delay
cũ, vì lúc đó thứ đang chờ không phải mốc phút.

*Hai lần phép đo của tôi sai trước khi ra được bảng trên, ghi theo §2.2:*

1. Probe đọc `msg.candle.close`, nhưng message để `close` ở **cấp ngoài cùng**.
   Kết quả: "16 nến, 0 giá khác nhau" — trông y như luồng chết, trong khi giá
   đang chạy 77 684 → 77 688.
2. Probe đọc `window.Live.enabled` và nhận `undefined`, suýt kết luận luồng
   chưa bật. `const Live = (…)()` ở top-level **không** tạo thuộc tính trên
   `window` — đó là cách `const` hoạt động, không phải lỗi ứng dụng.

#### Dọn dẹp (theo yêu cầu "làm mọi thứ clean lại")

- **Khoá i18n chết được nối lại thay vì xoá.** 18 khoá không dùng, và mỗi khoá
  có một **bản sao tiếng Việt viết thẳng trong code** ở đúng chỗ đáng lẽ phải
  dùng nó. Nối lại là dọn cả hai đầu: nợ i18n của `app.js` **95 → 78** chuỗi.
- Bỏ `.splash-status` (không phần tử nào mang class đó), endpoint
  `/api/markets/vn/freshness` và hàm `market_vn.freshness()` (frontend không
  gọi, và `data_coverage` đã thay thế vai trò của nó).
- Ba file probe rời (`_probe`, `_perf`, `_ct`) gộp thành **một** `_probe.html`
  chạy tuần tự: coverage → panel → độ mượt → bố cục thanh trên → menu → timing.

#### Còn tồn, cần Nam quyết

- **`/api/live/status` không ai gọi.** Không xoá: nó tồn tại đúng theo §2.5
  ("trạng thái phải hỏi được, không chỉ được thông báo"). Frontend hiện chỉ
  *nghe* `stream_status` qua socket, nên client nối vào sau khi luồng đã chạy
  không có đường hỏi lại — đúng cái bẫy §2.5 mô tả. Đây là **lỗ hổng chưa nối**,
  không phải code chết.
- Panel **Paper** vẫn cuộn 397px và **Chiến lược** 87px. Nhỏ hơn Chỉ báo hai
  bậc nên chưa đụng tới; nếu Nam thấy vướng thì xử lý cùng cách (gập nhóm ít
  dùng).

### 2026-09-15 — Cảnh báo 27/07 là lỗi của tôi, và trang tải nhanh gấp 2,5 lần

**291 test Python** (trước 290) + toàn bộ render check, không lỗi. Test mới kiểm đúng lỗi cửa sổ trượt: bỏ bản sửa ra thì nó đỏ.

#### Nam hỏi "thiếu dữ liệu thật sao?" — một cảnh báo đúng, một cảnh báo sai

Hai toast trong ảnh chụp có **hai nguyên nhân hoàn toàn khác nhau**.

**Toast 27/07 là lỗi của tôi.** Cửa sổ 45 ngày cắt theo `now() - interval '45
days'`, tức **03:48 UTC ngày 27/07** — giữa phiên. Nên ngày cũ nhất chỉ được
đếm từ 03:48 trở đi:

| | Nến ngày 27/07 |
|---|---|
| Thật sự có trong database | **241** (đủ) |
| `data_coverage` nhìn thấy | **132** |

Ngày biên **luôn** bị báo thiếu, với **mọi mã**. Và đó chính là "bằng chứng"
tôi đã dùng ở mục 2026-09-14 để kết luận 27/07 là *sự cố toàn thị trường*:
bốn mã VN cùng thiếu một ngày trông rất thuyết phục, nhưng chúng thiếu vì
**dùng chung một mốc cắt**. Đã đính chính mục đó.

Sửa: cắt cửa sổ theo **ranh giới ngày** thay vì theo giờ — ngày biên phải
nguyên vẹn hoặc không có, không được nửa vời. Sau khi sửa:

| Mã | Trước | Sau |
|---|---|---|
| VN30F1M, VIC, SHS, VNINDEX, AAH | 1 "thủng" mỗi mã | **0 thủng** |
| G-XAUUSD, G-BTCUSD | 1 thủng | **1 thủng** (giữ nguyên) |

**Toast 9/9 là thật.** Nến mới nhất của `G-XAUUSD` là **2026-09-09 10:19 UTC**
— feed quốc tế dừng từ hôm qua và chưa chạy lại. Ngày 08/09 chạy gần đủ 24
giờ, ngày 09/09 chỉ tới 10 giờ rồi ngắt. Vàng, bạc, dầu, BTC, EUR/USD đều
dừng cùng lúc, nên đây là feed `G-` chứ không phải một mã.

Test mới `the window starts at midnight` kiểm đúng tham số truyền vào SQL. Đã
xác nhận nó bắt được lỗi: bỏ bản sửa ra thì test đỏ.

#### "Làm trang web nhanh hơn" — đo trong trình duyệt, không đo ở server

Mọi endpoint đều dưới 100ms, nên chỗ chậm không nằm ở server. Dựng
`frontend/_perf.html` đo bằng Navigation/Resource Timing API của chính trình
duyệt. Tài nguyên chậm nhất hiện ra ngay:

```
319ms   /css2?family=Roboto:wght@300;400;500;700&family=Roboto+Mono...
```

**Google Fonts — cho một font không được dùng ở đâu cả.** Kiểu chữ đã chuyển
sang Segoe UI từ 2026-09-09 (Roboto phủ tiếng Việt kém, dấu chồng rơi xuống
font dự phòng giữa chừng), nhưng cái `<link>` bị bỏ quên. Nó là tài nguyên tốn
thời gian nhất trên đường tải, và trên máy không có Internet thì còn phải chờ
timeout trước khi trang ổn định. Đã xoá.

| | Trước | Sau |
|---|---|---|
| `domContentLoaded` (trung vị 3 lần chạy nguội) | **465ms** | **184ms** |
| Request | 29 | 28 |

**Giảm 60%**, toàn bộ từ một dòng `<link>`.

*Còn gzip thì tôi thử và bỏ — §2.2.* Tổng tải là 1 804KB không nén, đúng hình
dạng gzip ăn tốt (JSON lặp lại nhiều: 1 728 mã, 2 000 nến, 190 chỉ báo). Bật
`GZipMiddleware` thì tải xuống còn **399KB, giảm 78%**. Nhưng đo thời gian
thật, ba lần chạy nguội mỗi cấu hình:

| | Lần 1 | Lần 2 | Lần 3 | Trung vị |
|---|---|---|---|---|
| Không gzip | 160 | 186 | 190 | **186ms** |
| Có gzip | 217 | 199 | 209 | **209ms** |

**Chậm hơn 12%.** Đây là công cụ chạy local: băng thông loopback là vô hạn,
nên 78% ít byte hơn không đổi lấy được gì, còn CPU nén thì tính vào thời gian
chờ thật. Đã bỏ. *(Nếu sau này Nam mở nền tảng qua Tailscale từ máy khác thì
bật lại là đúng — lúc đó băng thông mới là thứ có giá.)*

#### Chỗ chậm còn lại không phải kỹ thuật

Khởi động kỹ thuật giờ là **184ms**, còn màn hình mở đầu chờ **2 100ms** — cố
ý, theo yêu cầu "chậm lại một chút để chạy hết hiệu ứng" (2026-09-10). Nghĩa
là 92% thời gian từ lúc mở tới lúc dùng được là hiệu ứng, không phải tải.
Muốn nhanh hơn nữa thì rút splash, và đó là quyết định của Nam chứ không phải
một vấn đề kỹ thuật còn tồn.

Kiểm thêm: 1 728 option trong ô chọn mã **không tốn gì đo được** (nhân bản cả
`<select>` mất 0,0ms), nên danh sách dài không phải chỗ nghẽn.

### 2026-09-14 (tối) — Rủi ro thị trường của team, và một tối ưu tốc độ không ăn thua

**290 test Python** (trước 287) + toàn bộ render check, không lỗi. Ba check backend cho `market_risk`, bảy check render cho khối mới.

#### Mô hình rủi ro của team, đặt cạnh mô hình của người dùng

Tab **Quản trị rủi ro** tính rủi ro của *chiến lược người dùng vừa backtest*.
Team có một mô phỏng Monte Carlo riêng chạy trên *VNINDEX*. Hai thứ trả lời hai
câu hỏi khác nhau, nên đặt cạnh nhau thì đối chiếu được — nhưng chỉ khi nói rõ
chúng khác nhau ở đâu, nếu không hai con số rủi ro trên cùng màn hình sẽ được
đọc như thể so sánh được.

Đọc được từ `api.v_risk_metrics` + `api.v_risk_distribution` (phiên 09/09):

| | VNINDEX |
|---|---|
| VaR 95% | −9,35% |
| ES 95% | −11,80% |
| Biến động | 17,97% |
| Sụt giảm hiện tại | −5,23% (60 phiên: −11,15%) |
| Xác suất giảm | 51,39% **± 0,50** |

Cộng phân phối lỗ: ≥3% có xác suất 75,26%, ≥10% có 6,77%.

#### Ba giới hạn đi kèm, vì không cái nào nhìn thấy được trong con số

1. **`mc_paths` không cố định** giữa các lần chạy — cả 10 000 lẫn 40 000 đều
   xuất hiện. Hai dòng in cùng số chữ số thập phân **không mang cùng sai số**.
   Payload trả về sai số mô phỏng cho từng dòng, tính bằng `sqrt(p(1−p)/N)`:
   51,39% từ 10 000 đường là **±0,50 điểm phần trăm**, nên chữ số thập phân thứ
   hai là nhiễu. Có test kiểm đúng quan hệ này: gấp 4 lần số đường thì sai số
   phải giảm đúng một nửa.
2. **Chuỗi thưa và không đều** — 6 ảnh chụp, khoảng cách trung vị 2 ngày nhưng
   lớn nhất **29 ngày**. Giao diện gọi thẳng đó là "ảnh chụp rời rạc, đừng đọc
   như một đường diễn biến", và cảnh báo chỉ hiện khi lỗ lớn nhất gấp hơn 3 lần
   trung vị — tức là ngưỡng tương đối, không phải hằng số.
3. **Chỉ VNINDEX**, không phải mã người dùng đang xem. Tiêu đề khối ghi thẳng
   `(VNINDEX)` chứ không để người đọc tự suy.

Khối này nạp **sau khi cửa sổ báo cáo đã mở**, và hỏng thì im lặng: nó là ý
kiến thứ hai trên một tab, còn một báo cáo không mở được vì VPN tắt là một báo
cáo tệ hơn hẳn một báo cáo thiếu nó.

`test_render.js` thêm 7 check, gồm cả **"mô hình vắng mặt thì phần còn lại của
tab vẫn nguyên"** — vì đường hỏng mới là đường hay chạy nhất.

#### Câu hỏi của Nam: truy vấn nhanh hơn được không?

**Database đã nhanh hơn hẳn.** Đo lại cùng những truy vấn từng timeout:

| Truy vấn | Lần đo trước | Giờ |
|---|---|---|
| nến VN30F1M 1m, limit=600 | **timeout 30s** | 1,46s |
| nến VN30F1M 1m, limit=2000 | — | 1,35s |
| `data_coverage()` | — | 0,29s |
| `v_quote` (389 dòng) | ~20s → 5s | 5,02s |
| `list_symbols()` tổng | ~20s | 8,3s |

Nút thắt duy nhất còn lại là `v_quote` (5s) — chính CTE 45 ngày mà Nam đã nói
để nguyên.

*Tôi thử song song hoá và nó không ăn thua — ghi lại theo §2.2.* Ba truy vấn
(`v_quote`, CTE bù mã, tập mã có nến phút) độc lập nhau nên tôi cho chạy đồng
thời qua `ThreadPoolExecutor`, kỳ vọng 11s → 5s. Đo thật, ba lần xen kẽ:

| | Lần 1 | Lần 2 | Lần 3 | Tốt nhất |
|---|---|---|---|---|
| Tuần tự | 11,33 | 13,26 | 11,78 | **11,33s** |
| Song song | 24,55 | 11,84 | 10,60 | **10,60s** |

Nhanh hơn **7%**, và lần chạy nguội còn **chậm hơn gấp đôi** vì phải mở thêm
kết nối qua VPN. Database xử lý các truy vấn này tuần tự, nên gửi chúng cùng
lúc không rút ngắn được gì. **Đã hoàn nguyên** — không giữ lại một lớp phức tạp
đổi lấy 7% không chắc chắn.

*Một lần suýt kết luận sai trong lúc đo:* hai đường cho ra danh sách "khác
nhau", và tôi định đi tìm lỗi đồng bộ. Thật ra là **`volume` live đổi giữa hai
lần gọi** (4 mã: SSB, SSI, STB…) làm thứ tự sắp xếp đổi theo. So bằng tập hợp
thay vì danh sách có thứ tự thì hai đường trùng khớp hoàn toàn.

Đường này vốn đã nằm ngoài critical path (chỉ `config` + `candles` chặn lượt vẽ
đầu) và đã có cache 60 giây, nên 11s chạy nền một lần mỗi phút là chấp nhận
được. Muốn nhanh hơn nữa thì phải bỏ `v_quote` khỏi đường nóng — nhưng nó là
nguồn **duy nhất** cho tên công ty, và `price`/`change_percent` của nó thì
frontend không dùng đến (giá trên header lấy từ nến). Đó là một đánh đổi có
thật, để lại chờ Nam quyết.

### 2026-09-14 — Cảnh báo dữ liệu khuyết, và tiền đề sai của chính tôi

**287 test Python** (trước 281) + toàn bộ render check, không lỗi. Sáu check mới cho `data_coverage`, cộng một probe trình duyệt thật cho phần toast mà test jsdom không chạm tới.

#### Tôi đề xuất việc này dựa trên một con số đọc sai

Vòng trước tôi nói: *"58 lỗ chưa vá... anh backtest xuyên qua đoạn đó mà không
có dấu hiệu gì"*, và Nam bảo bắt đầu làm. Đo kỹ trước khi xây thì **tiền đề đó
sai ở cả ba mặt**, ghi lại theo §2.2:

| Điều tôi nói | Sự thật đo được |
|---|---|
| 58 lỗ "chưa vá" | `reconnect_ts IS NULL` = **không ghi nhận được lúc nối lại**, không phải đang chết — sau đó vẫn có 790 nến, tới tận phút hiện tại |
| 210 lần ngắt là vấn đề | **156/210 rơi ngoài giờ giao dịch**, không có nến nào để mất |
| Backtest chạy trên dữ liệu thủng | VN30F1M mất **3 nến thật** trong 33 phiên |

Ba lần ngắt trông tệ nhất (id=59, 94, 96 — "mất 75–99%") hoá ra **rơi trọn vào
giờ nghỉ trưa**. Tôi tính "số nến kỳ vọng" bằng hiệu hai mốc thời gian, mà phiên
VN có nghỉ trưa 90 phút. Đã bổ sung lịch phiên thật vào §3.6.

**`api.v_ingestion_gaps` là nguồn sai** cho câu hỏi này, dù tên của nó nghe đúng.
Xây cảnh báo trên đó là dựng 210 báo động để bắt 3 nến.

#### Nhưng có vấn đề thật, và nó lớn hơn

Đo trực tiếp **số nến thực có** thay vì số lần ngắt:

```
2026-07-27:  VN30F1M −34%  ·  VIC −31%  ·  SHS −35%  ·  VNINDEX −29%
```

> **ĐÍNH CHÍNH (xem mục 2026-09-15):** con số 27/07 này **là lỗi của tôi**, không
> phải sự cố thị trường. Cửa sổ 45 ngày cắt theo *giờ* nên ngày cũ nhất bị đếm
> nửa vời — và vì mọi mã dùng chung một mốc cắt, tất cả cùng "thiếu" một ngày,
> trông y hệt một sự cố toàn thị trường. Sau khi sửa: **mọi mã VN đều 0 thủng**.
> Sự cố `G-` ngày 2026-09-09 (vàng −55%, BTC −60%) thì có thật.

Và thứ quan trọng hơn cả lỗ thủng: **A32 có trung vị 1 nến/phiên**. Không phải
mất dữ liệu — mã đó gần như không giao dịch. Backtest intraday trên nó ra kết
quả rác mà biểu đồ trông vẫn bình thường.

#### `data_coverage()` — phân biệt ba thứ mà một con số "thiếu %" gộp làm một

Chấm mỗi phiên theo **trung vị của chính mã đó, cùng thứ trong tuần**:

| Nguyên nhân | Dấu hiệu | Ví dụ đo được |
|---|---|---|
| Sự cố hệ thống | phiên thấp hẳn so với thói quen của chính mã | `G-` ngày 09/09 (xem đính chính ở trên về 27/07) |
| Mã quá mỏng | trung vị < 30 nến/phiên → `thin`, không chấm | A32: 1 nến/phiên |
| Thị trường đóng cửa | so theo thứ trong tuần nên Chủ nhật so với Chủ nhật | vàng cuối tuần |

**Ngưỡng phải co giãn theo độ phân tán của chính mã (§2.6).** Bản đầu của tôi
dùng hằng số "thấp hơn 20% so với trung vị" — bắt đúng VN30F1M nhưng **buộc tội
AAH 7 phiên** trong khi mã đó vốn dao động 29–62 nến/phiên. Đo được: AAH có
IQR **0,423**, còn VN30F1M **0,000**. Cùng một quy tắc phần trăm không thể phục
vụ cả hai.

*Lần sửa thứ hai của tôi cũng chưa đúng:* tôi chuyển sang `3 × MAD`, và nó nhạy
đến mức fixture lệch 0,05 so với dữ liệu thật là đảo kết quả — tức là tôi đang
chỉnh hằng số cho vừa một test. Cuối cùng dùng **hàng rào Tukey** (`q1 − 1,5 ×
IQR`, kẹp bởi sàn 20%): không giả định phân phối, mà số nến/phiên thì không hề
chuẩn — nó dồn ở "phiên đầy đủ" rồi kéo đuôi sang trái.

Thêm một điều kiện nữa sau khi test bắt được: **một thứ trong tuần phải có ít
nhất 4 phiên** mới đủ để nói phiên nào bất thường. Chia theo thứ là thứ giúp
Chủ nhật của vàng không bị coi là mất dữ liệu, nhưng nó cũng chia mẫu ra 5–7
phần, nên mã mới niêm yết sẽ bị chấm dựa trên hai ba phiên của chính nó.

#### Cảnh báo chỉ hiện ở khung intraday

Nến ngày đến từ `v_history_1d`, một bảng khác mà các sự cố này không đụng tới.
Cảnh báo ở khung ngày là báo động cho một vấn đề không tồn tại.

**Kiểm bằng trình duyệt thật, không phải bằng mock**, vì phần người dùng thấy là
một cái toast:

```
[A32 @ 1m]      1 toast: "A32 chỉ khớp lệnh khoảng 1 phút mỗi phiên..."
[VN30F1M @ 1m]  1 toast: "...nặng nhất 27/07 (155/241 nến, thiếu 36%)..."
[A32 @ 1d]      0 toast   (đúng — nến ngày không bị ảnh hưởng)
```

*Hai lỗi chỉ probe mới bắt được:*

1. **Lần chạy đầu báo 0 toast** và trông y như tính năng hỏng. Thật ra toast tự
   xoá sau 5 giây còn probe đọc ở giây thứ 9. Đọc một lần ở cuối là cách biến
   một cảnh báo đang chạy thành "đã hỏng" — phải theo dõi bằng `MutationObserver`.
2. **A32 báo trùng 2 lần**, vì tôi khoá theo `mã|khung`. Nhưng đây là sự thật về
   **dữ liệu phút của mã**, mà 5m và 15m đều dựng từ chính những nến đó — nói
   lại ở mỗi khung là kể một sự thật như thể có nhiều. Khoá theo mã.

*Và một lỗi §2.3 nữa của tôi:* script sửa probe bằng `str.replace` không khớp và
**thất bại im lặng** (tôi không assert), nên bản probe chạy tiếp với hàm cũ đã bị
xoá. Đúng cái bẫy §2.3 nói: sửa hàng loạt phải soát lại, không tin vào "đã chạy
xong".

#### Chưa làm

`v_ingestion_gaps` **không** được đưa lên giao diện, có chủ ý — nó đo số lần
socket rớt, không đo dữ liệu thiếu, và hai thứ đó lệch nhau hoàn toàn trên số
liệu thật. Phần chẩn đoán hạ tầng đó thuộc về người vận hành pipeline.

### 2026-09-13 (tối) — Vàng, dầu, FX, crypto: 192 mã nữa vốn đã nằm sẵn trong database

**281 test Python** (trước 278) + toàn bộ render check, không lỗi. Ratchet i18n
siết thêm một nấc: `app.js` từ 97 xuống **95** chuỗi chưa dịch, vì hai nhãn nhóm
hardcode cũ giờ đã đi qua `L()`.

#### Nam hỏi đúng chỗ tôi làm sót

Vòng trước tôi thêm 1.140 cổ phiếu và báo là "đã lấy hết". **Sai.** Bộ lọc tôi
viết là `^[A-Z0-9]{3}$` — đúng cho cổ phiếu, và nó **cắt sạch mọi thứ không
phải cổ phiếu**. Nam nhớ có vàng và crypto trong database, và đúng là có.

Quét lại toàn bộ 2.100 mã trong `api.v_history_1d`, phân theo họ:

| Họ mã | Số mã | Còn cập nhật | Trước | Giờ |
|---|---|---|---|---|
| Cổ phiếu 3 ký tự | 1.533 | 1.523 | ✅ | ✅ |
| **`G-` quốc tế** | **66** | **66** | ❌ | ✅ |
| **Chỉ số ngành `I1-/I2-/I3-`** | **73** | **73** | ❌ | ✅ |
| **Chỉ số VN** | **25** | **25** | một phần | ✅ |
| **Phái sinh VN** (VN30F, VN100F) | **8** | **8** | một phần | ✅ |
| **ETF / chứng chỉ quỹ** | **25** | **24** | một phần | ✅ |
| Chứng quyền | 353 | 287 | ❌ | ❌ *(cố ý)* |
| Trái phiếu | 18 | 14 | ❌ | ❌ *(cố ý)* |

Họ `G-` là feed quốc tế của database, lịch sử dài hơn hẳn mọi thứ khác trong
kho: `G-XAGUSD` từ **1970**, `G-GOLD` từ **1975**, `G-BTCUSD` từ **2010**,
`G-USDVND` từ **1995**. Gồm vàng (2 chuỗi), bạc, bạch kim, nhôm, đồng, nickel,
kẽm, chì, dầu (3 loại), khí, đường, ca cao, cà phê, bông; 19 cặp ngoại hối; 16
đồng crypto; 14 chỉ số quốc tế (S&P, Dow, Nasdaq, Nikkei, FTSE, DAX, Hang
Seng, Thượng Hải, KOSPI...).

**Đường dẫn dữ liệu vốn đã sẵn sàng cho tất cả** — đo trước khi sửa: `sources.parse`
nhận `VN:G-XAUUSD`, `get_candles` trả nến đúng, và cả 6 mã kiểm thử đều có nến
1 phút. Thứ duy nhất chặn là **danh sách mã không liệt kê chúng ra**. Không
phải thiếu tính năng, chỉ là thiếu tên trong một cái danh sách.

#### Phân loại bằng bảng tra cứu, không bằng regex

`classify()` mới trả về lớp công cụ cho từng mã. Với họ `G-`, phân loại bằng
**bảng liệt kê tường minh** chứ không phải quy tắc suy diễn, vì suy diễn ở đây
sai một cách im lặng:

- `G-XAUUSD` (vàng, USD/ounce) và `G-EURUSD` (một tỷ giá) **cùng kết thúc bằng
  USD**. Một regex `USD$` sẽ xếp vàng vào ngoại hối.
- `G-USDTUSD` trông y hệt một cặp tiền tệ nhưng là **stablecoin**, thuộc crypto.

Mã `G-` nào chưa có trong bảng thì trả `None` và **không lên danh sách** — thà
nói "chưa biết" còn hơn gắn nhầm đơn vị cho một cái giá thật.

**Mỗi lớp khai báo đơn vị của nó** (`CLASS_CURRENCY`), vì đây đúng là chỗ §2.7
hay hỏng: cùng một con số `4.418,11` là USD/ounce với vàng, còn `1.827,12` là
**điểm chỉ số** chứ không phải tiền, và `246,00` là **nghìn đồng**. Bốn đơn vị:
`VND`, `USD`, `point`, `rate`.

Chứng quyền và trái phiếu vẫn bị loại, và giờ được loại **có tên gọi**:
`classify()` trả `"warrant"`/`"bond"` để phân biệt "cố ý bỏ" với "chưa từng
thấy hình dạng này". Lý do không đổi — chứng quyền có time decay theo giá thực
hiện, trái phiếu yết theo mệnh giá kèm lãi tích luỹ, cả hai không sống được với
giả định giá cổ phiếu mà phần còn lại của nền tảng dựng trên (§3.1, §3.6).

#### Ô chọn mã nhóm theo công cụ, không theo độ phân giải dữ liệu

Cách nhóm cũ ("có nến phút" / "chỉ nến ngày") là **nhóm theo thứ không ai dùng
để chọn mã**. Với 1.728 dòng, nó đặt vàng, một cổ phiếu ngân hàng và một chỉ số
ngành chung một danh sách chỉ vì chúng tình cờ cùng độ phân giải.

Giờ nhóm theo công cụ, và **các họ nhỏ đứng trước** — 1.530 cổ phiếu là đống cỏ
khô, để lên đầu thì chôn mất mọi thứ khác. Đo trên DOM thật của Chrome:

```
Hàng hoá & kim loại (17)   Tiền mã hoá (16)      Ngoại hối (19)
Chỉ số quốc tế (14)        Chỉ số Việt Nam (25)  Phái sinh Việt Nam (8)
Chỉ số ngành (73)          Quỹ ETF (25)          Cổ phiếu Việt Nam (1530)
```

Có thêm nhóm "Khác" bắt mọi lớp backend biết mà danh sách này chưa được dạy —
nếu không, dữ liệu mới sẽ **biến mất im lặng** đúng như lần vừa rồi.

#### Sàn giao dịch cho các họ mới

`venuesFor` trước đây coi mọi mã `VN:` không phải VN30F là "cổ phiếu HOSE". Với
vàng hay EUR/USD thì đó là gán một biểu phí HOSE cho một thứ không giao dịch
trên HOSE. Giờ: họ `G-` và các chỉ số → **"Tự đặt"**, vì không biết Nam sẽ giao
dịch qua broker nào và chọn bừa một cái là đặt phí của nó lên tài khoản mà
không có căn cứ. Phái sinh mở rộng từ `^VN30F` thành `^VN(30|100)F` — VN100F
vốn là hợp đồng tương lai mà trước đây bị tính phí như cổ phiếu.

#### Đo trước/sau

| | Trước | Sau |
|---|---|---|
| Mã trong ô chọn | 1.535 | **1.728** |
| Họ công cụ | 1 | **9** |
| Vàng / crypto / FX / chỉ số quốc tế | 0 | 17 / 16 / 19 / 14 |
| Chứng quyền + trái phiếu lọt vào | 0 | **0** |

*Ghi chú §2.2 — bộ phát hiện code cũ tự chứng minh nó có ích:* sau khi sửa, tôi
gọi `/api/health` trên server đang chạy và nhận `stale: true`. Đó chính là tình
huống nó được viết ra để bắt, và lần này nó bắt được trước khi tôi kịp nhầm
lẫn giữa "code sai" và "server cũ".

**Chưa làm, cần Nam quyết:** chứng quyền (353) và trái phiếu (18) — thêm được,
nhưng cần cách xử lý giá riêng cho từng loại chứ không dùng chung giả định cổ
phiếu. Và trong `api` còn **6 view chưa dùng đến**: `v_forecast_history` (57
dòng), `v_model_forecast_latest` (3), `v_network_latest` (1),
`v_risk_distribution` (24), `v_risk_metrics` (6), `v_ingestion_gaps` (210) —
trông như đầu ra mô hình dự báo và rủi ro của team, hiện không hiện ở đâu trên
nền tảng.

### 2026-09-13 — Database có thêm ~1.150 mã mới, và một view đã chậm hẳn đi

**278 test Python** (trước 272) + toàn bộ render check, không lỗi — DB đã nhanh trở lại nên phép kiểm live trước đó flaky cũng pass sạch.

#### Chẩn đoán: `api.v_quote` chỉ là một góc của database

Nam nói database có thêm nhiều dữ liệu, và đúng là vậy — nhưng không phải ở chỗ
app đang nhìn vào. Toàn bộ danh sách mã của app lấy từ `api.v_quote` (389 dòng,
đúng con số cũ). Đo trực tiếp `api.v_history_1d` thì nó có **2.100 mã**, và
**1.140 mã** trong số chênh lệch đó vẫn đang giao dịch tới đúng phiên gần nhất
(2026-09-09), có khối lượng thật, có khi 24 năm lịch sử (AGF từ 2002). Đây
không phải mã đã huỷ niêm yết bị bỏ sót — đây là mã **chưa bao giờ được thêm
vào nguồn báo giá trực tiếp** mà app dùng để dựng ô chọn mã.

Kiểm mẫu vài mã: `AAH`, `AAV`, `AAN`, `ITA`, `HBC`, `BVS`... đều có giá, khối
lượng thật ở phiên 2026-09-09 (`AAH`: 1,8 nghìn đồng, khối lượng 375.300).

*Một phát hiện phụ đáng nói ra theo §2.7:* trộn cả HOSE lẫn HNX trong cùng
chênh lệch đó (`BVS`, `SD9`, `AAV` là mã HNX quen thuộc) — nghĩa là database
này **không chỉ có HOSE** như mô tả cũ trong `market_vn.py` và CLAUDE.md, dù
schema không có cột nào ghi rõ sàn. Đã sửa docstring để không khẳng định một
sàn mà chính dữ liệu không xác nhận được, và bỏ chữ "HOSE" khỏi hai nhãn nhóm
trên ô chọn mã của frontend — nói "Việt Nam" thay vì đoán sàn.

#### Đã thêm: `_equities_without_quote`

`list_symbols()` giờ gộp `v_quote` với mọi mã có hình dạng cổ phiếu thường
(đúng 3 ký tự chữ/số — `^[A-Z0-9]{3}$`) xuất hiện trong `v_history_1d` mà
không có trong `v_quote`. Mã dạng khác — chứng quyền (`CVNM2609`, 353 mã),
trái phiếu (mã 9 ký tự bắt đầu bằng số, `41I1G8000`), chỉ số và chứng chỉ quỹ
— bị loại có chủ ý: chúng là loại công cụ khác, quy ước giá khác hẳn (không
theo nghìn đồng như cổ phiếu, §3.6), và trộn vào bộ chọn mã cổ phiếu là mang
chúng vào một bộ giả định backtest không dành cho chúng. **Chưa thêm nhóm này
— hỏi Nam nếu muốn có luôn, vì cần một cách xử lý giá riêng.**

Mã mới không có báo giá trực tiếp thì lấy giá từ **hai phiên đóng cửa gần nhất**
của chính nó trong `v_history_1d` — trễ tối đa một phiên so với báo giá thật,
đây là cái giá phải trả để không bỏ sót mã đó hoàn toàn. Chỉ một phiên thì
không có `change_percent` — trả `None` thay vì bịa ra 0% hay chia cho 0.

Đo trên dữ liệu thật:

| | Trước | Sau |
|---|---|---|
| Tổng số mã trong ô chọn | 389 | **1.529** |
| Trong đó có nến 1 phút | 35 (theo comment cũ) | 1.337 |

`tests/test_market_vn.py` thêm 6 check không cần VPN (regex, gộp danh sách,
khử trùng, sort theo khối lượng, `change_percent = None` khi thiếu điểm so
sánh), cộng siết lại phép kiểm live "danh sách mã" theo đúng con số đo được.

#### Phát hiện không sửa được từ phía app: `v_quote` và một vài truy vấn 1m đã chậm hẳn

Đo trực tiếp, không phải giả định:

| Truy vấn | Trước (báo cáo cũ) | Giờ |
|---|---|---|
| `SELECT ... FROM api.v_quote` (389 dòng) | 1.916 ms | **~20.000 ms** |
| `SELECT count(*) FROM api.v_quote` | — | **~13.000 ms** |
| `get_candles("VN30F1M", "1m", limit=20)` | nhanh | 3.0s |
| `get_candles("VN30F1M", "1m", limit=600)` | nhanh | **timeout, 30s server + ~70s round trip** |

Không phải lỗi VPN — mọi truy vấn khác (daily, coverage, symbol list mới) vẫn
trả lời được, chỉ chậm hơn hẳn trước. *Ban đầu tôi chỉ đoán* nguyên nhân là kế
hoạch truy vấn không còn hợp với khối lượng dữ liệu mới — **Nam cho biết cơ chế
thật**: `v_quote` tính bằng một CTE gộp **45 ngày** nến phút cho cả 389 mã, và
45 ngày là chủ ý để `prev_close` sống sót qua một kỳ nghỉ lễ dài (Tết). Đây là
việc của người quản trị database, không sửa được từ phía chỉ-đọc này, và theo
đúng yêu cầu của Nam — **để nguyên cửa sổ đó, không rút ngắn**.

**Việc duy nhất chặn được từ phía app:** ô chọn mã có cache 60 giây ở tầng
route (`routes_market.py`) — giữ nguyên. Đo lại sau khi Nam xác nhận: `v_quote`
đã về **~3.7–4.9s** (từ ~20s lúc đo lần đầu, có lẽ trạng thái tải của DB dao
động), vẫn chưa về được mốc gốc 1.9s nhưng đúng như Nam nói, không cần cố ép nó
về mốc đó vì cái giá là CTE 45 ngày đang bảo vệ đúng thứ cần bảo vệ.

**Đồng bộ luôn cửa sổ của `_equities_without_quote`:** hàm gộp mã mới của tôi
đang dùng cửa sổ 15 ngày để lấy hai phiên đóng cửa gần nhất — cùng một lớp rủi
ro Nam vừa nói (mã ít thanh khoản không giao dịch quanh một kỳ nghỉ dài sẽ mất
`prev_close`, hoặc bị loại khỏi danh sách một cách vô cớ). Đã nâng lên **45
ngày** để khớp đúng lý do đã được kiểm chứng cho `v_quote`, thay vì để hai cửa
sổ lệch nhau không có lý do. Đo lại: 4.171 dòng (từ 4.122 ở cửa sổ 15 ngày),
2.5s (từ 1.3s) — vẫn rẻ, và `list_symbols()` tổng còn **7.1s** thay vì hơn 20s
lúc đo lần đầu, vì `v_quote` bản thân nó cũng đã nhanh hơn. Thêm 6 mã ít thanh
khoản mà cửa sổ 15 ngày trước đó bỏ sót.

### 2026-09-12 (tối) — "unknown paper session: summary" không phải lỗi code

**272 test Python** (trước 269) + toàn bộ render check.

#### Chẩn đoán: server đang chạy code cũ

Ảnh chụp của Nam báo `'unknown paper session: summary'`. Trước khi sửa gì, đo
cùng một request ở hai chỗ:

| Gọi ở đâu | Kết quả |
|---|---|
| Trong tiến trình, `TestClient(app)` | **200** `{"sessions": 0, "note": {...}}` |
| Server đang chạy ở cổng 8000 | **404** `{"detail":"'unknown paper session: summary'"}` |

Cùng một mã nguồn, hai câu trả lời khác nhau → tiến trình đang chạy **có trước**
commit thêm endpoint đó. Thứ tự route cũng đã kiểm lại trên
`routes_paper.router.routes`: `/summary` ở vị trí 1, `/{session_id}` ở vị trí 2,
nên không có chuyện `/summary` bị nuốt thành một id. **Cách sửa là khởi động lại
`run.py`** — không có dòng code nào cần đổi.

#### Nhưng kiểu hỏng này đã ăn thời gian nhiều lần, nên giờ nó tự nói ra

File frontend được đọc lại từ đĩa mỗi request nên không bao giờ cũ. Python thì
import **một lần** lúc khởi động, nên sửa backend xong mà không restart thì
không có gì thay đổi — và cách nó lộ ra thì đánh lạc hướng hẳn: endpoint mới trả
404, router rơi xuống nhánh có tham số đường dẫn, nên `/api/paper/summary` quay
về dưới dạng *"unknown paper session: summary"*. **Câu báo lỗi đổ cho một phiên,
mà phiên không phải vấn đề.** Nó còn đúng ngữ pháp và trông như một lỗi thật.

`/api/health` giờ trả thêm `started_at`, `newest_source` và `stale`. Frontend hỏi
lúc khởi động; nếu cũ thì hiện thẳng "Server đang chạy code cũ — hãy khởi động
lại" thay vì để lần bấm tiếp theo báo một lỗi 404 vô nghĩa.

Đo để chắc nó không phải một cái đèn luôn tắt:

| Tình huống | `stale` |
|---|---|
| Tiến trình vừa khởi động | `False` |
| Đặt mtime một file backend muộn hơn `started_at` 10s | `True` (chênh 10.0s) |
| Trả mtime về như cũ | `False` |

`__pycache__` bị bỏ qua, nếu không thì mỗi lần import lại ghi `.pyc` và server
sẽ **vĩnh viễn** tự báo cũ. Ngưỡng có 1 giây trượt: một lần lưu file rơi đúng
giây khởi động chính là lần restart đó, không phải một thay đổi sau nó.

*Một phép kiểm của tôi vô nghĩa, bắt được khi đọc lại:* check đầu tôi viết
`newest <= now + 1.0 or newest > now` — hai vế phủ hết trục số, nó **đúng bất kể
câu trả lời là gì**. Nó "pass" vì không kiểm gì cả. Đã tách ngưỡng ra thành
`_is_stale(newest_source, started_at)` để kiểm được bằng số cụ thể thay vì bằng
trạng thái tình cờ của cây thư mục lúc chạy test.

### 2026-09-12 — Bảng tài khoản Paper, và danh mục chuyển thẳng sang paper

**269 test Python** (trước 258) + toàn bộ render check.

#### 1. Paper bám mã đang xem

Phiên của mã đang hiện trên biểu đồ được **đẩy lên đầu danh sách** và viền xanh.
Phiên thì cứ tích lại, mà cái cần dùng gần như luôn là cái của biểu đồ đang
nhìn — phải đi lục trong một danh sách xếp theo ngày tạo chính là "phải chọn
lại" mà Nam nói.

#### 2. Bảng tài khoản Paper Trading

Panel bên cạnh trả lời "phiên **này** đang thế nào" — một mã, một chiến lược,
một số dư. Nó không trả lời được "**tôi** đang thế nào", vì câu đó trải qua mọi
phiên cùng lúc và trong một cột rộng 344px không có chỗ đặt.

Cửa sổ mới `PaperDash` (nút **Tài khoản** ở đầu panel Paper), ba tab: Tài
khoản, Lịch sử lệnh, Theo mã. Backend gộp ở `backend/paper/summary.py`.

Hai điều bộ gộp này cẩn thận, và cả hai đều được nói lại trên giao diện chứ
không bắt người đọc đi tra:

- **Đường vốn chỉ có điểm tại thời điểm đóng lệnh.** Phiên paper ghi lệnh và số
  dư chạy, nó không giữ chuỗi vốn theo từng nến. Nội suy giữa các lần đóng lệnh
  sẽ vẽ ra một đường trơn mà tài khoản **chưa bao giờ đi qua**. Nên đường được
  vẽ **bậc thang**, chỉ nhảy ở đúng chỗ tiền thật sự chuyển.
- **Đã chốt và chưa chốt nằm ở hai thẻ riêng.** Một cái đã xong, một cái là ý
  kiến hiện tại về vị thế còn đang chạy. Cộng chúng vào một con số là cách một
  khoản sụt giảm đang mở bị giấu đi — test kiểm đúng chỗ này: lãi đã chốt +500
  cùng lỗ chưa chốt −800 phải hiện ra là hai số, không phải một số +300.

Vài chỗ nhỏ nhưng cố ý: không có phiên nào thì báo "chưa có phiên" chứ **không**
in ra một trang toàn số 0 (một trang số 0 đọc như "bạn chưa mất gì", đó là một
phát biểu về giao dịch); sụt giảm đo từ đỉnh xuống đáy dọc đường vốn chứ không
phải so với vốn ban đầu; profit factor trả `None` thay vì vô cực khi chưa có
lệnh lỗ nào, vì "∞" đọc như một kết luận còn `None` đọc đúng là "chưa trả lời
được".

Biểu đồ vẽ bằng SVG chứ không dùng thư viện chart: nó nằm trong một modal mở ra
đóng vào, mà thư viện thì cần một container để đo và tự quản vòng đời của nó.
Một SVG có `viewBox` co giãn theo bề rộng modal, không cần resize observer, và
không thể bị bỏ sót lại khi cửa sổ đóng.

#### 3. Danh mục chuyển thẳng sang Paper

Sau khi phân tích, nút **Paper trading cả danh mục** mở một phiên cho từng mã,
**chia vốn theo đúng tỷ trọng mà phân tích vừa đưa ra** — không chia đều. Cả ý
nghĩa của lần phân tích là *chính những tỷ lệ này* mang *chính những rủi ro
kia*; paper trading một tỷ lệ khác là trả lời một câu hỏi không ai hỏi.

Mã nào đã có phiên đang chạy thì **bỏ qua chứ không mở thêm**, vì hai phiên trên
một mã sẽ lặng lẽ nhân đôi mức phơi nhiễm của mã đó trong bảng tài khoản.

#### Một phép soi sai của tôi

Tôi kiểm thứ tự route bằng `app.routes` và nó báo **0 route paper**, suýt nữa
thì đi sửa `app.py`. Bản FastAPI này bọc router đã include vào `_IncludedRouter`
nên `app.routes` không trải phẳng — **phép soi sai, không phải code sai**. Kiểm
thẳng trên `routes_paper.router.routes` thì thấy đúng: `/summary` khai báo ở vị
trí 1, `/{session_id}` ở vị trí 2, nên `/summary` không bị nuốt thành một id.

### 2026-09-11 (tối) — Mốc phần trăm không còn tự nhớ, và đơn vị tiền

Ảnh thứ hai chỉ rõ hơn ảnh thứ nhất: trục giá **0 → 100.000**, header **+3993,11%**
trên BTCUSDT, nến bị nén dẹp xuống đáy.

`+3993%` giải được ra một con số: mốc so sánh ≈ **1.940**. Đó là một giá trị chỉ
số VN, trong khi giá đang là BTC.

#### Cái sai thật: một biến tự nhớ

`sessionOpen` là biến riêng của `app.js`, gán trong `loadCandles` và reset trong
`hidePrice`. Nó **có thể lệch khỏi thứ đang hiện trên biểu đồ**, và có ít nhất
ba đường để lệch:

- một lần nạp ném lỗi giữa chừng thì mốc của mã cũ nằm nguyên đó, trong khi tick
  của mã mới vẫn gọi `showPrice` — đúng ra +3993%;
- vuốt trái nạp thêm 1000 nến cũ hơn thì nến đầu cửa sổ đổi, mốc thì không;
- khi chưa có mốc, nó neo vào **tick đầu tiên** thay vì vào cửa sổ.

Bỏ hẳn biến đó. Mốc giờ **lấy từ chính dữ liệu biểu đồ đang giữ**
(`ChartManager.firstClose`), nên nó không thể mâu thuẫn với những cây nến nằm
ngay cạnh nó. Đo lại sau khi sửa: **+20,91%**, trục 75.600–84.000.

#### Ba lần tôi sai khi đi tìm, ghi lại theo §2.2

1. *"Cuộc đua ở phần nạp lịch sử trộn hai mã vào một chuỗi."* Tôi thêm guard
   theo `symbol|khung` cho cả `prependCandles` lẫn `loadOlderHistory`, rồi viết
   một probe để chứng minh. **Probe vô nghĩa**: nó gọi `loadOlderHistory` bằng
   `eval`, mà hàm đó nằm trong closure của module nên `eval` ném lỗi và probe
   im lặng không kiểm gì cả.
2. Sửa probe để kích hoạt đúng cách (kéo phạm vi về mép trái). Lần này nó chạy
   thật và cho `3000 nến` sau khi đổi mã — tôi gọi đó là dấu hiệu hỏng. **Sai
   nữa**: 3000 nến là phân trang **hợp lệ**, 2000 nến gốc cộng một trang 1000
   nến cũ hơn của cùng mã đó.
3. Chạy lại với guard đã khôi phục: vẫn 3000 nến. Nếu tin vào phép thử đó thì
   tôi đã kết luận guard không hoạt động.

Guard vẫn giữ — nó đúng về nguyên tắc và rẻ (một phép so chuỗi), nhưng **tôi
không nhận là nó sửa được thứ Nam gặp**, vì tôi chưa tái hiện được cuộc đua đó.
Thứ giải thích được toàn bộ các con số trên ảnh là mốc tự nhớ ở trên.

#### Xem nến quá khứ khi đang paper trading

Không có đoạn code nào chặn việc này — vuốt trái vẫn nạp lịch sử kể cả khi có
phiên paper đang chạy. Cái chặn là biểu đồ hỏng: khi trục giá bị kéo ra
0–100.000 thì nến dồn thành một vạch và không còn gì để xem. Sửa mốc là hết.

#### Đơn vị tiền trong cài đặt

"10.000" là hai tài khoản hoàn toàn khác nhau trên Binance và trên HOSE. Ô vốn
giờ ghi rõ đơn vị **theo sàn đã chọn** — `USDT` cho Binance, `VND` cho HOSE và
phái sinh VN — và bỏ trống khi chọn "Tự đặt", vì lúc đó không có sàn nào phía
sau để nói cho thành thật. Ô đòn bẩy ghi `×`.

### 2026-09-11 (chiều) — Rà soát biểu đồ: ba lỗ hổng cùng một chỗ

Ảnh Nam gửi: header ghi **1,966.00** cho BTCUSDT trong khi trục giá đúng
~79.000, và **không nến nào được vẽ** — chỉ còn volume.

Trong trình duyệt sạch mọi thứ đúng (2000 nến, giá 79.500), và tái hiện chuỗi
đổi mã qua lại cũng đúng. Nhưng một phép đo chỉ thẳng vào nguyên nhân: chuyển
sang `VN:VNINDEX` thì header hiện **1,827.12** — cùng cỡ với 1,966.00. Nghĩa là
biểu đồ đang giữ dữ liệu BTC còn header nhận tick của một mã VN.

Rà lại `loadCandles` thì thấy đúng chỗ đó, và nó là **lỗi cấu trúc chứ không
phải lỗi hiển thị**:

```js
await Indicators.recomputeAll();                  // ném lỗi thì…
drawPaperMarkers();
Live.subscribe(state.symbol, state.timeframe);    // …dòng này không bao giờ chạy
```

`recomputeAll` chạy code Python do người dùng nạp qua API. Một plugin ném lỗi
là chuyện bình thường, không phải chuyện bất thường. Khi nó ném, `catch` ở
ngoài chỉ ghi một dòng trạng thái, còn **đăng ký stream kẹt lại ở mã cũ** — nên
ô chọn ghi BTCUSDT mà tick của mã VN vẫn chảy vào biểu đồ.

Ba lỗ hổng, đều đã sửa:

**1. `Live.subscribe` nằm sau một `await` có thể ném.** Giờ nó chạy ngay sau
`setCandles`, lúc biểu đồ đã hiển thị chuỗi mới và **trước** mọi thứ có thể
hỏng. Không có gì giữa đó và cuối hàm là điều kiện cần để nhận dữ liệu live.

**2. `updateCandle` tin bất cứ thứ gì được đưa vào.** Socket có lọc theo mã,
nhưng bộ lọc đó chỉ mới bằng lần `Live.subscribe` gần nhất — mà lần đó có thể
đã không chạy. Giờ biểu đồ **tự biết mình đang giữ chuỗi nào** (`symbol|khung`)
và bỏ qua nến không thuộc về nó. Kiểm ở tầng sở hữu dữ liệu là tầng duy nhất
chắc chắn được, và tốn đúng một phép so chuỗi mỗi tick.

**3. Nến ngược thời gian làm chết luôn luồng live.** `series.update()` **ném**
khi nhận thời điểm sớm hơn điểm mới nhất nó đang giữ, và lỗi đó thoát ra khỏi
handler của socket, giết luôn feed cho cả phiên. Hai thị trường lệch đồng hồ
làm chuyện này thành bình thường chứ không hiếm: nến ngày mới nhất của VN đi
sau nến phút mới nhất của Bitcoin hàng giờ. Giờ nến cũ bị bỏ qua.

**Cộng thêm:** một chỉ báo hỏng không còn kéo theo mọi thứ sau nó. Trước đây
`recomputeAll` ném là mất luôn marker lệnh, đăng ký stream và phần bù nến, và
cả lần nạp bị báo là thất bại. Giờ nó được bắt riêng và báo bằng một toast.

**Kiểm chứng bằng cách bơm đúng hai thứ đã lọt vào trước đó**, trên chính app
đang chạy chứ không phải mock — vì lỗi nằm ở *cách các mảnh được nối với
nhau*, mà mock thì sẽ được nối theo đúng cách tôi tưởng tượng:

```
PASS  a candle from another instrument is dropped
PASS  an out-of-order candle is dropped, not thrown on
PASS  a genuine newer candle is still applied
PASS  and it was appended, not swallowed
```

Giữ lại thành `tests/test_chart_guards.html`.

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
