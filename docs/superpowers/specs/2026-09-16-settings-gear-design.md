# Bánh răng cài đặt và bộ định dạng số dùng chung — Thiết kế

Ngày: 2026-09-16. Phần 2 của yêu cầu cài đặt; phần 1 là
`2026-09-15-contract-position-model-design.md` (mô hình vị thế theo hợp đồng).

## Mục tiêu

Một nút bánh răng mở một hộp cài đặt duy nhất cho các lựa chọn hiển thị và mặc
định giao dịch, và **một** bộ định dạng số thay cho 8 bản `money`/`pct` chép
tay đang nằm rải trong `frontend/js`. Hộp này cũng là chỗ nhập thông số hợp
đồng mà phần 1 đòi hỏi: khi chưa nhập, mã phái sinh chạy tuyến tính và mọi kết
quả mang mã `contract_model_off`.

## Quyết định đã chốt (từ các câu hỏi trước)

| Hạng mục | Quyết định |
|---|---|
| Chế độ lợi nhuận | Tiền, phần trăm, hoặc điểm giá |
| Nhóm tùy chọn | Định dạng số, múi giờ, mặc định giao dịch, biểu đồ |
| Thông số hợp đồng | Bắt buộc nhập lần đầu, không có giá trị mặc định |
| Nơi lưu | `localStorage` của trình duyệt này, không gửi đi đâu |

## Thiết kế

### 1. `frontend/js/settings.js` — kho cài đặt và bộ định dạng

Một module, hai thứ công khai: `Settings` (kho) và `Fmt` (định dạng). Nạp ngay
sau `i18n.js` vì mọi module vẽ số đều dùng `Fmt`.

```
Settings.all()                -> bản sao của toàn bộ cài đặt
Settings.patch(part)          -> ghi một phần, lưu, báo cho người đăng ký
Settings.subscribe(fn)        -> gọi lại mỗi lần cài đặt đổi
Settings.contractPayload()    -> khối contract, hoặc null khi còn thiếu trường
Settings.contractMissing()    -> tên các trường còn thiếu
Settings.tzOffsetSeconds()    -> 25200 (GMT+7) hoặc 0 (UTC)
```

Cấu trúc lưu (`qp.settings.v1`):

```
display: { profit: 'money'|'percent'|'points', locale: 'en-US'|'vi-VN',
           decimals: 0..4, timezone: 'vn'|'utc' }
chart:   { grid: bool, bars: int }          # số nến khi vào chế độ làm việc
trading: { contract: { sizing, contracts, multiplier, initial_margin_rate,
                       maintenance_threshold, fee_mode, fee_per_contract,
                       fee_rate, slippage_points } }
```

Ba trường hợp đồng **không có mặc định** (`initial_margin_rate`,
`maintenance_threshold`, và trường phí theo `fee_mode`) — đúng quyết định của
phần 1: một tỷ lệ ký quỹ đoán bừa là một khoản chi phí bịa đặt trên tài khoản.

`Fmt`:

| Hàm | Trả về |
|---|---|
| `Fmt.number(v, d)` | số theo `locale` và `decimals` |
| `Fmt.money(v, {unit, digits})` | số kèm đơn vị tài khoản |
| `Fmt.pct(v)` | phần trăm có dấu |
| `Fmt.points(v)` | điểm giá có dấu |
| `Fmt.profit({money, pct, points, unit})` | **một** trong ba, theo `display.profit` |

`Fmt.profit` là chỗ chế độ lợi nhuận thật sự có hiệu lực. Nơi gọi truyền cả ba
đại lượng vì chỉ nơi gọi mới biết cách tính chúng; `Fmt` chỉ chọn và định dạng.
Đại lượng nào nơi gọi không có (điểm giá của một danh mục nhiều mã) thì truyền
`null`, và `Fmt.profit` rơi về tiền — thà hiện đúng một đại lượng khác còn hơn
một dấu gạch.

### 2. Hộp cài đặt

Nút bánh răng ở `topbar-right`, cạnh nút tìm kiếm, mở `#settings-dialog` theo
đúng khuôn `dialog-backdrop` đang dùng cho Paper và Thông báo. Năm nhóm:

1. **Lợi nhuận** — tiền / phần trăm / điểm.
2. **Định dạng số** — dấu phân cách theo `en-US` hoặc `vi-VN`, số chữ số thập phân.
3. **Múi giờ** — giờ Việt Nam (GMT+7) hoặc UTC. Áp cho trục thời gian biểu đồ,
   ngày trong báo cáo và mốc thời gian trong panel Thống kê.
4. **Mặc định giao dịch** — thông số hợp đồng phái sinh (phần 1). Khi còn thiếu
   trường bắt buộc, hộp nói rõ thiếu gì và kết quả phái sinh vẫn mang ghi chú
   "Mô hình hợp đồng chưa bật".
5. **Biểu đồ** — lưới nền bật/tắt, số nến hiện khi vào chế độ làm việc.

Lưu ngay khi đổi (không có nút Lưu): mỗi điều khiển là một lựa chọn độc lập, và
một hộp cài đặt có trạng thái chưa lưu là một cách mất thay đổi.

### 3. Luồng thông số hợp đồng

`Strategy.execution()` và bảng cài đặt Paper thêm `contract:
Settings.contractPayload()`. Backend đã sẵn sàng từ phần 1: khối này chỉ áp cho
mã `futures_vn`, mã khác bỏ qua; thiếu trường bắt buộc → 422
`contract_settings_required`. Vì giao diện chỉ gửi khi đủ trường, lỗi 422 đó là
lưới an toàn chứ không phải đường đi thường gặp.

### 4. Múi giờ và biểu đồ

`charts.js` đang cứng `TZ_OFFSET_SECONDS = 7 * 3600`; `report.js` và
`validation.js` mỗi nơi có một bản `+ 7 * 3600` chép tay. Cả ba đọc
`Settings.tzOffsetSeconds()`. Đổi múi giờ hoặc lưới sẽ vẽ lại chuỗi đang xem,
vì một trục thời gian đổi nghĩa mà nến không vẽ lại là hai hệ quy chiếu trên
cùng một màn hình.

### 5. Bộ định dạng dùng chung thay cho 8 bản chép

`strategy.js`, `paper.js`, `paper-dash.js`, `report.js`, `validation.js`,
`markets.js`, `portfolio.js` mỗi file giữ một `money`/`pct` riêng. Chúng trỏ
sang `Fmt`, giữ nguyên tên gọi tại chỗ để phần thân không phải sửa. Chỗ nào có
quy ước riêng đáng giữ (số chữ số thập phân cố định của một bảng) thì gọi `Fmt`
kèm tham số, không đổi hình thức con số.

## Giới hạn

- Cài đặt nằm trong `localStorage` của **một trình duyệt**; mở trên máy khác là
  bắt đầu lại từ mặc định. Không đồng bộ, không gửi lên server.
- Chế độ "điểm" chỉ có nghĩa với một mã; ở chỗ gộp nhiều mã, `Fmt.profit` rơi
  về tiền.
- Múi giờ chỉ đổi cách **hiển thị**. Mọi thứ lưu, so sánh và gửi đi vẫn là UTC.
- Thông số hợp đồng là giá trị người dùng nhập, không tự cập nhật theo quy định
  hiện hành (như phần 1 đã nói).

## Không thuộc bản thiết kế này

- Nhập số hợp đồng trực tiếp trên bảng lệnh Paper.
- Đơn vị tiền trong tin nhắn Telegram.
- Đồng bộ cài đặt giữa các máy.
