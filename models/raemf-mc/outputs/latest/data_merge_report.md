# Báo cáo hợp nhất dữ liệu VN-Index

- File ưu tiên (primary): `VNINDEX_Daily.csv` — 6306 phiên
- File thứ cấp (secondary): `data.csv` — 6298 phiên
- Số ngày chồng lấn: 6298
- Số ô giá trị xung đột (> 0.1% tương đối): 2 trên 2 ngày
- Phiên chỉ có trong primary: 8
- Phiên chỉ có trong secondary: 0
- Chuỗi hợp nhất: 6306 phiên, 2000-07-28 → 2026-07-13

Quy tắc xử lý: với ngày xung đột, giá trị của file primary (bản DataPro cập nhật) được dùng; mọi xung đột được liệt kê trong `data_conflicts.csv`, không có ghi đè âm thầm. File gốc không bị sửa.
