# Mô hình vị thế theo hợp đồng cho phái sinh — Thiết kế

Ngày: 2026-09-15

## Mục tiêu

Backtest và Paper hiện tính mọi mã theo một mô hình **tuyến tính**: khối lượng =
ký quỹ × đòn bẩy / giá, phí là % trên giá trị danh nghĩa, vốn là "đơn vị tài
khoản". Với hợp đồng tương lai chỉ số Việt Nam (VN30F, VN100F) mô hình này cho
ra số hợp đồng lẻ (ví dụ 5,157) và lãi/lỗ không phải tiền thật.

Bản thiết kế này thêm mô hình **hợp đồng**: vốn tính bằng đồng, khối lượng là số
hợp đồng nguyên, lãi/lỗ = điểm × hệ số nhân × số hợp đồng. Đây là phần 1 của yêu
cầu "bánh răng cài đặt"; phần 2 (bánh răng và bộ định dạng số dùng chung) có bản
thiết kế riêng và dựa trên phần này.

## Quyết định đã chốt

| Hạng mục | Quyết định |
|---|---|
| Chế độ hiển thị lợi nhuận (phần 2) | %, điểm giá, tiền |
| Phạm vi mô hình hợp đồng | Mã loại `futures_vn` (`^VN(30\|100)F[12][MQ]$`). Mọi mã khác giữ mô hình tuyến tính |
| Kiến trúc | Một module `position_model` dùng chung cho engine backtest và engine Paper |
| Số hợp đồng | Theo vốn và ký quỹ (mặc định) hoặc cố định N |
| Phí | Đồng/hợp đồng/chiều (mặc định) hoặc % giá trị danh nghĩa |
| Trượt giá | Tính bằng điểm, luôn theo chiều bất lợi |
| Buộc đóng vị thế | Theo ngưỡng tỷ lệ ký quỹ còn lại, kiểm trong nến |
| Giá trị mặc định | Chỉ hệ số nhân (100.000 đ/điểm). Tỷ lệ ký quỹ, ngưỡng buộc đóng, phí: **không có mặc định**, bắt buộc nhập lần đầu |
| Chuyển tiếp | Khi chưa có khối `contract`, mã phái sinh tạm tính tuyến tính và trả mã `contract_model_off` |
| Phiên Paper đang mở | Giữ mô hình lúc tạo; không tính lại giữa chừng |

## Thiết kế

### 1. Module `backend/strategy/position_model.py`

Một giao diện, hai hiện thực. Cả hai engine gọi cùng một đối tượng, nên quy tắc
khớp lệnh (§3.1 CLAUDE.md) chỉ có một nơi được viết.

```
PositionModel
  size(equity, price, size_pct) -> Sizing | None      # None: không đủ ký quỹ
  entry_fee(sizing, price) -> float
  fill(price, direction) -> float                      # trượt giá theo chiều bất lợi
  pnl(sizing, entry, exit, direction) -> (pnl, points)  # đã trừ phí ra
  unrealized(sizing, entry, mark, direction) -> float
  liquidation_price(entry, direction) -> float | None
```

`Sizing` mang: `quantity` (có dấu, đơn vị cơ sở), `contracts` (hoặc `None`),
`margin` (ký quỹ đã đặt), `notional`.

**LinearModel** — đúng công thức hiện tại, không đổi một phép tính:
ký quỹ = vốn × `size_pct`; danh nghĩa = ký quỹ × đòn bẩy; khối lượng = danh
nghĩa / giá; phí = danh nghĩa × `fee`; giá khớp = giá × (1 ± `slippage`); giá
thanh lý = giá vào × (1 − chiều / đòn bẩy), chỉ khi đòn bẩy > 1.

**ContractModel** — cho `futures_vn`:

| Đại lượng | Công thức |
|---|---|
| Giá trị một hợp đồng | giá × hệ số nhân |
| Ký quỹ ban đầu một hợp đồng (IM) | giá × hệ số nhân × `initial_margin_rate` |
| Số hợp đồng, chế độ theo vốn | ⌊ vốn × `size_pct` / IM ⌋ |
| Số hợp đồng, chế độ cố định | `contracts`; không vào lệnh nếu vốn < `contracts` × IM |
| Ký quỹ đã đặt | số hợp đồng × IM |
| Giá khớp | giá ± `slippage_points` theo chiều bất lợi |
| Phí một chiều, theo hợp đồng | số hợp đồng × `fee_per_contract` |
| Phí một chiều, theo danh nghĩa | số hợp đồng × giá × hệ số nhân × `fee_rate` |
| Điểm | (giá ra − giá vào) × chiều |
| Lãi/lỗ | số hợp đồng × điểm × hệ số nhân − phí ra |
| Lợi suất trên ký quỹ (`return_pct`) | lãi/lỗ / ký quỹ đã đặt × 100 |
| Giá buộc đóng | giá vào × (1 − chiều × (1 − `maintenance_threshold`) × `initial_margin_rate`) |

Giá buộc đóng suy ra từ điều kiện (ký quỹ đã đặt + lãi/lỗ chưa thực hiện) ≤
`maintenance_threshold` × ký quỹ đã đặt. Với ngưỡng 0 điều kiện này trùng quy
tắc tuyến tính hiện tại (lỗ hết ký quỹ). Kiểm trong nến theo giá thấp nhất (mua)
hoặc cao nhất (bán), khớp ở đúng giá buộc đóng, lý do `liquidation`. Khác mô
hình tuyến tính (chỉ kiểm khi đòn bẩy > 1), mô hình hợp đồng **luôn** kiểm, vì
đòn bẩy thực tế 1 / `initial_margin_rate` luôn lớn hơn 1.

Với mô hình hợp đồng, `leverage` bị bỏ qua; đòn bẩy thực tế là
1 / `initial_margin_rate`.

### 2. Cấu hình

`BacktestConfig` thêm trường `contract: ContractConfig | None = None`.

```
ContractConfig
  sizing: "margin" | "fixed"            = "margin"
  contracts: int >= 1                   = 1
  multiplier: float > 0                 = 100_000     # đ / điểm
  initial_margin_rate: float (0, 1]     # bắt buộc
  maintenance_threshold: float [0, 1)   # bắt buộc
  fee_mode: "per_contract" | "notional" = "per_contract"
  fee_per_contract: float >= 0          # bắt buộc khi fee_mode = per_contract
  fee_rate: float [0, 0.01]             # bắt buộc khi fee_mode = notional
  slippage_points: float >= 0           = 0
```

`ExecutionSettings` (Pydantic) thêm khối `contract` tương ứng, tùy chọn.

### 3. Luồng dữ liệu

`ExecutionSettings.to_config()` đổi thành `to_config(symbol)`:

1. `market_vn.classify(symbol) == "futures_vn"` và có khối `contract` hợp lệ →
   cấu hình mang `contract`, engine dùng `ContractModel`.
2. `futures_vn` nhưng **không** có khối `contract` → cấu hình không mang
   `contract`, engine dùng `LinearModel`, kết quả trả `execution_model:
   "contract_model_off"`.
3. Mọi mã khác → `LinearModel`, `execution_model: "linear"`; khối `contract` nếu
   có thì bị bỏ qua.
4. Trường hợp 1 trả `execution_model: "contract"`.

Mười endpoint đang gọi `to_config()` đều chuyển sang `to_config(symbol)`.
`/api/strategies/backtest/markets` gọi trong vòng lặp từng mã, nên một lần quét
trộn BTCUSDT với VN30F1M dùng đúng mô hình cho từng dòng.

`execution_model` có mặt trong kết quả backtest, báo cáo và snapshot phiên
Paper. Giao diện rẽ nhánh theo mã này (§2.4), không theo văn bản.

### 4. Kiểm tra đầu vào và lỗi

- Miền giá trị như mục 2; sai miền → 422 của Pydantic.
- Mã phái sinh có khối `contract` nhưng thiếu `initial_margin_rate`,
  `maintenance_threshold` hoặc trường phí tương ứng `fee_mode` → 422 với
  `{code: "contract_settings_required", message: {vi, en}}`.
- Quét nhiều thị trường: lỗi trên gắn vào dòng của mã đó; các mã khác vẫn chạy.
- Không đủ ký quỹ cho một hợp đồng: backtest bỏ qua tín hiệu đó (không vào
  lệnh); lệnh tay trên Paper bị từ chối với `OrderRefused("insufficient_margin")`.
- Lệnh tay trên Paper ở chế độ cố định bỏ qua `% vốn` của bảng lệnh; ở chế độ
  theo vốn, `% vốn` thay cho `size_pct` như hiện nay.

### 5. Bản ghi lệnh

`Trade` và `PaperTrade` thêm:

- `points: float` — cả hai mô hình (tuyến tính: (giá ra − giá vào) × chiều).
- `contracts: int | None`, `multiplier: float | None` — chỉ mô hình hợp đồng.

`pnl`, `return_pct`, `equity_before`, `equity_after`, `mfe_pct`, `mae_pct` giữ
nguyên nghĩa; với mô hình hợp đồng chúng tính bằng đồng và trên ký quỹ đã đặt.
`quantity` với mô hình hợp đồng bằng số hợp đồng.

### 6. Lưu trữ phiên Paper

- `BacktestConfig.as_dict()` ghi thêm `contract` (object hoặc `null`).
- `_from_payload` chấp nhận payload thiếu khóa `contract` → `None` → tuyến tính.
- Phiên đang mở không được chuyển mô hình.

### 7. Phần không phải sửa

Báo cáo (`analysis/report.py`), thống kê (`analysis/stats.py`), metrics
(`strategy/metrics.py`), walk-forward / Monte Carlo / tối ưu
(`optimizer/*`), tổng hợp Paper (`paper/summary.py`) và Telegram chỉ đọc `pnl`,
`return_pct` và vốn trước/sau lệnh; không module nào tính `quantity × giá`.

### 8. Giao diện trong phần này

Chỉ một thay đổi: khi `execution_model == "contract_model_off"`, panel Kết quả
và phiên Paper hiện một dòng ghi chú song ngữ:
"Mô hình hợp đồng chưa bật: lãi/lỗ đang tính tuyến tính, chưa áp dụng hệ số nhân."
Nhập thông số hợp đồng thuộc phần 2.

## Giới hạn

- Ngưỡng buộc đóng tính trên ký quỹ đã đặt cho **một vị thế**, không mô phỏng
  toàn bộ tài khoản ký quỹ của công ty chứng khoán (tiền dư, nhiều vị thế).
- Không mô phỏng thuế thu nhập cá nhân, lãi/phí qua đêm, hay đáo hạn và cuộn hợp
  đồng; chuỗi VN30F1M là chuỗi liên tục của dữ liệu nguồn.
- Tỷ lệ ký quỹ, ngưỡng và phí là thông số người dùng nhập, không tự cập nhật
  theo quy định hiện hành.

## Kiểm chứng

Số trong các ví dụ là số dùng cho test, không phải giá trị mặc định.

1. **Tuyến tính không đổi (đo trước/sau, §2.1).** Trước khi sửa engine, chạy
   engine hiện tại trên chuỗi giá sinh ngẫu nhiên có seed với 6 cấu hình (phí,
   trượt giá, đòn bẩy, % vốn, lệnh bán, có thanh lý), lưu lệnh và đường vốn vào
   `tests/fixtures/linear_golden.json`. Sau khi sửa, kết quả trùng tới 1e-12.
2. **Hợp đồng, số tính tay** (vốn 100.000.000 đ, `size_pct` 1, hệ số nhân
   100.000, tỷ lệ ký quỹ 0,2):

   | Trường hợp | Kết quả |
   |---|---|
   | Theo vốn, giá 1300 | IM 26.000.000 đ → 3 hợp đồng |
   | Cố định 5 hợp đồng | cần 130.000.000 đ → backtest 0 lệnh; Paper `insufficient_margin` |
   | Mua 3 HĐ 1300→1310, phí 20.000 đ/HĐ/chiều | điểm +10; lãi/lỗ 2.940.000 đ; vốn sau 102.880.000 đ; `return_pct` 3,769% |
   | Bán 3 HĐ 1300→1290, cùng phí | điểm +10; lãi/lỗ 2.940.000 đ |
   | Trượt giá 0,5 điểm, mua 1300→1310 | khớp 1300,5 và 1309,5; điểm +9 |
   | Phí danh nghĩa 0,03%, 3 HĐ giá 1300 | 117.000 đ mỗi chiều |
   | Ngưỡng 0,5, mua ở 1300 | giá buộc đóng 1170; đáy 1169 → đóng ở 1170 `liquidation`; đáy 1171 → không đóng |

3. **Paper khớp backtest.** Phát lại từng nến qua `PaperSession` với cấu hình
   hợp đồng ra đúng các lệnh của `run_backtest`.
4. **Lưu/nạp phiên.** Khối `contract` còn nguyên sau khi ghi và nạp; payload cũ
   không có khóa nạp thành tuyến tính.
5. **API** (dữ liệu tổng hợp, không cần VPN): phái sinh không có `contract` →
   `contract_model_off`; `contract` thiếu trường → 422
   `contract_settings_required`; quét trộn BTCUSDT + VN30F1M → mỗi dòng đúng
   `execution_model`.
6. **Phân tích phía sau.** Trên một backtest hợp đồng: lợi nhuận ròng của báo
   cáo bằng tổng `pnl`; Monte Carlo dựng lại đường vốn từ vốn trước/sau lệnh
   không sai lệch.
7. **Hồi quy.** Toàn bộ test Python, render check (thêm check song ngữ cho ghi
   chú `contract_model_off`), i18n.

## Không thuộc bản thiết kế này

- Bánh răng cài đặt, bộ định dạng số dùng chung, chế độ hiển thị %/điểm/tiền,
  múi giờ, mặc định giao dịch, tùy chọn biểu đồ → bản thiết kế phần 2.
- Nhập số hợp đồng trực tiếp trên bảng lệnh Paper.
- Hiển thị đơn vị tiền trong tin nhắn Telegram.
