# Tồn đọng 2026-09-16 — trạng thái và bước tiếp theo

> **ĐÃ XONG TOÀN BỘ (2026-09-16, cuối ngày).** Sáu việc trong danh sách đều đã
> làm và đã đẩy lên git; lỗi dấu trên vị thế bán cũng đã sửa. Báo cáo đầy đủ ở
> CLAUDE.md §4, hai mục "2026-09-16 (khuya)" và "2026-09-16 (tiếp)". Tài liệu
> này giữ lại để đối chiếu cách từng việc được đo.

Ghi lại để phiên sau tiếp tục ngay, không phải dò lại. Cập nhật: 2026-09-16.

## Đã xong và đã commit

| Việc | Commit | Kiểm chứng |
|---|---|---|
| Thẻ vị thế bám theo khi thu phóng trục giá | `c2b1f10` | lệch 131px → **0px**; `test_level_drag.html` 26/26 |
| Thẻ vị thế ghim sát trục giá (không che nến) | `a912c12` | left 796 + rộng 210 = 1006 trong plot 1014 |
| **Điều chỉnh chia tách/cổ tức cổ phiếu cho giá VN** | `25517a2` | xem bảng dưới; `tests/test_corporate_actions.py` 13/13 |
| `/api/live/status` trả trạng thái từng luồng | `e823eda` | `tests/test_stream.py` 11/11 |

Điều chỉnh chia tách, đo trên VIC 400 phiên, đòn bẩy 3, phí 0,15%:

| | Giá thô | Đã điều chỉnh |
|---|---|---|
| Phiên tệ nhất | −46,5% | **−7,0%** |
| Lợi nhuận | **−100%, cháy tài khoản** | −57,86% |
| Số lệnh | 2 | 7 |

VNM và HPG không có sự kiện → kết quả **giống hệt** trước/sau, nên bản sửa
không đụng vào mã sạch. Qua API: `adjust=1` → 1 sự kiện, phiên tệ nhất 7,00%,
giá đầu chuỗi 21,42; `adjust=0` → 46,52% và 40,05; giá mới nhất **241,40 ở cả
hai** (điều chỉnh lùi, hôm nay không đổi).

Tổng test Python sau các việc trên: **368**.

## Việc đang dở — `/api/live/status`, nửa frontend

Backend đã xong. Còn phần frontend **hỏi lại** trạng thái (§2.5), chưa viết:

1. `frontend/js/api.js` — thêm `liveStatus({symbol, timeframe})` gọi
   `/api/live/status` kèm query, đặt ngay sau `health`.
2. `frontend/js/live.js` — thêm `probeStatus()`; gọi nó trong handler `close`
   của socket, ngay sau `report({ state: 'offline' })`.
   - Không trả lời được → `report({state:'error'})` với câu "server không trả lời".
   - Trả lời và `body.stream.connected === true` → `report({state:'error'})` với
     câu "server vẫn nhận dữ liệu, trình duyệt không mở được kênh realtime".
   - Đây là chỗ phân biệt "server chết" với "socket hỏng", và là lý do endpoint
     này tồn tại.
3. Chuỗi mới phải đi qua `L(vi, en)`, nếu không ratchet i18n sẽ đỏ.

## Lỗi Nam vừa báo, chưa sửa — dấu lãi/lỗ đảo trên vị thế bán

Ảnh: `SHORT 5.130797 +4.54 VND (+0.05%)`, `SL +13.62 VND`, `TP −30.61 VND`.

**Nguyên nhân:** thẻ tính `quantity × (giá − giá vào)` và cần `quantity` **mang
dấu**, nhưng snapshot của engine paper trả `"quantity": abs(self.quantity)`
(`backend/paper/engine.py`), chiều nằm ở trường `position`. Vì vậy mọi con số
trên vị thế **bán** bị đảo dấu; vị thế mua tình cờ đúng nên không lộ.

Đối chiếu số trong ảnh: 5,1308 × (1949,90 − 1949,02) = +4,54 (phải là −4,54);
tại SL: × (1951,67 − 1949,02) = +13,62 (cắt lỗ mà báo lãi); tại TP: −30,61
(chốt lời mà báo lỗ).

**Cách sửa dự định:**

1. `frontend/js/charts.js` — `levelTitle` và `openProfit` lấy chiều từ
   `levels.side` thay vì giả định dấu của `levels.quantity`:
   `const signed = Math.abs(levels.quantity) * Math.sign(levels.side)`.
   Sửa cùng chỗ trong `frontend/js/paper.js` (`openProfit`).
2. Khối lượng in qua `Fmt` chứ không in thẳng 6 chữ số thập phân, và có đơn vị:
   "hợp đồng" khi mô hình hợp đồng bật, còn lại là khối lượng tài khoản.
3. **Test hiện tại không thể bắt lỗi này**: `tests/test_level_drag.html` chỉ
   dựng lệnh **mua**. Thêm một mục dựng `side: -1` và kiểm dấu ở cả ba chỗ
   (thẻ, SL, TP) trước khi sửa, để thấy nó đỏ.

## Còn lại trong danh sách Nam giao

1. **Chứng quyền (353) + trái phiếu (18) vào ô chọn mã.** `classify()` đã trả
   `"warrant"`/`"bond"`; cần nhóm riêng trong `symbol-picker.js`, sàn "Tự đặt",
   và một ghi chú nói rõ giả định giá cổ phiếu không áp dụng cho chúng.
2. **Bốn view chưa dùng**: `v_forecast_history`, `v_model_forecast_latest`,
   `v_network_latest`, `v_ingestion_gaps`. Dự định: một khối "Mô hình của team"
   trong cửa sổ Báo cáo, nạp sau khi cửa sổ mở và hỏng thì im lặng (như khối
   rủi ro thị trường đang làm).
3. **"Mất nến khi đổi mã/khung"** — chưa tái hiện được qua ba lần đo (mục
   2026-09-17). Cần Nam cho các bước chính xác; trong lúc chờ, dựng một bộ đếm
   trong app tự ghi lại khi một chuỗi về rỗng sau khi đổi mã.
4. **Nợ i18n**: `app.js` còn 70 chuỗi chưa dịch, có ratchet trong
   `tests/test_i18n.py` (`BUDGET`). Hạ về 0 rồi xoá dòng ratchet.

## Cách chạy lại nhanh

```bash
for %f in (tests\test_*.py) do .venv\Scripts\python.exe %f     # 368 check
NODE_PATH=./node_modules node tests/test_render.js             # render
.venv\Scripts\python.exe tests/test_i18n.py                    # 2/2
```

Trang Chrome cần server chạy; copy cạnh `index.html` rồi mở
`http://127.0.0.1:8000/static/<tên>.html` với `--headless --dump-dom`:
`test_level_drag.html` (26), `test_settings_ui.html` (17),
`_probe.html?only=<nhóm>`.
