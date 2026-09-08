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
