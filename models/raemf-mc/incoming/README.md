# Thư mục nhận dữ liệu DataPro

Mỗi ngày, xuất **toàn bộ lịch sử VN-Index** (nến ngày, cột Date/Open/High/Low/Close/Volume) từ DataPro thành file CSV và lưu vào thư mục này. Tên file tùy ý — pipeline luôn lấy file mới nhất.

Sau đó chạy `run_daily.bat` (hoặc bấm nút trong web UI). Pipeline sẽ:

1. Đối chiếu file mới với lịch sử hiện tại (chặn file thiếu dữ liệu hoặc lệch giá bất thường).
2. Backup file `VNINDEX_Daily.csv` cũ vào `backups/` rồi thay bằng file mới.
3. Chuyển file đã xử lý vào `incoming/processed/`.
4. Chạy mô hình và cập nhật báo cáo trong `outputs/current_monitor/`.
