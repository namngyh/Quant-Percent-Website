# Bảng điều khiển ngoại tuyến

Một trang HTML duy nhất, tự chứa toàn bộ dữ liệu. Không cần máy chủ, không cần
mạng, không cần cài thêm gì.

## Dựng lại trang

```bash
python scripts/build_dashboard.py          # ghi dashboard/index.html
python scripts/build_dashboard.py --open    # dựng xong mở luôn trình duyệt
```

Script đọc thẳng từ `artifacts/` nên mỗi lần chạy lại pipeline chỉ cần dựng lại
trang là số liệu tự cập nhật.

## Mở trang

Nhấp đúp vào `dashboard/index.html`, hoặc:

```bash
start dashboard\index.html                  # Windows
```

Nếu muốn phục vụ qua HTTP (ví dụ để xem từ máy khác trong mạng nội bộ):

```bash
python -m http.server 8000 --directory dashboard
# rồi mở http://localhost:8000
```

## Vì sao mọi thứ được nhúng thẳng vào trang

Trình duyệt chặn `fetch()` tới tệp cục bộ khi trang mở bằng giao thức `file://`.
Nếu tách dữ liệu ra tệp JSON riêng thì trang sẽ trắng khi nhấp đúp mở, và bắt
buộc phải chạy máy chủ. Nhúng thẳng vào đổi lấy dung lượng tệp lớn hơn để có
được thứ quan trọng hơn: trang chạy được ở bất kỳ đâu, kể cả khi chép sang máy
không có Python.

Các chuỗi thời gian được lấy mẫu thưa trước khi nhúng — theo tuần cho lịch sử
chỉ số mạng lưới, theo cuối tháng cho đường vốn. Ở độ phân giải màn hình, một
đường 3.500 điểm hằng ngày không phân biệt được với bản lấy mẫu theo tuần của
chính nó, nên giữ đủ điểm chỉ làm tệp nặng gấp ba mà không thấy khác gì.

## Ghi chú về thiết kế

Trang hoàn toàn đen trắng. Mọi thông tin thường được mã hoá bằng màu đều chuyển
sang mã hoá bằng **hình thức**:

| Thông tin | Cách mã hoá |
|---|---|
| Dấu của tương quan riêng phần | nét liền = đồng biến · nét đứt = nghịch biến |
| Cụm | bậc xám của đỉnh |
| Quy tắc trọng số | hình dạng điểm đánh dấu (tròn, vuông, thoi, tam giác, chữ thập) |
| Bộ ước lượng graphical lasso | điểm đánh dấu tô đặc |
| Chiều tốt/xấu | tam giác ▲ ▼ |
| Phán quyết | ô đặc = có · ô viền nét đứt = không |
| Vị thế chạm trần 20% | cột được viền |

Nhờ vậy trang đọc được trên máy in đen trắng và với người mù màu — điều mà một
bảng màu không làm được.
