# Vận hành hằng ngày RAEMF-MC

Tài liệu này mô tả quy trình chạy mô hình mỗi ngày với dữ liệu VN-Index (nến ngày) xuất từ DataPro.

## Quy trình chuẩn mỗi ngày

1. Sau khi thị trường đóng cửa, xuất **toàn bộ lịch sử VN-Index** từ DataPro thành một file CSV (cột `Date, Open, High, Low, Close, Volume`; định dạng ngày `d/m/yyyy`; dấu phẩy nghìn trong Volume được xử lý tự động).
2. Lưu file vào thư mục `incoming/` trong thư mục dự án. Tên file tùy ý — pipeline luôn lấy file mới nhất theo thời gian sửa đổi.
3. Chạy `run_daily.bat` (double-click) hoặc bấm **Cập nhật dữ liệu & chạy hôm nay** trong web UI.
4. Đọc kết quả trong `outputs/current_monitor/` hoặc ngay trên dashboard.

## Bước ingest làm gì

Lệnh `python -m raemf_mc.cli ingest-data` (được `daily` gọi tự động):

- Chọn file CSV/TXT mới nhất trong `incoming/`.
- Parse bằng loader chống lỗi tách cột do dấu phẩy nghìn.
- **Đối chiếu với `VNINDEX_Daily.csv` hiện tại và từ chối thay thế khi:**
  - ngày cuối của file mới cũ hơn lịch sử hiện tại;
  - file mới thiếu quá 5 phiên đã có trong lịch sử (dấu hiệu xuất thiếu);
  - hơn 5 phiên trùng nhau có giá close lệch quá 0.5% (dấu hiệu sai dữ liệu);
  - file parse được dưới 100 dòng hợp lệ.
- Backup file cũ vào `backups/VNINDEX_Daily_<timestamp>.csv` rồi mới thay thế.
- Chuyển file đã xử lý vào `incoming/processed/` để `incoming/` luôn sạch.

Nếu `incoming/` trống, `daily` vẫn chạy báo cáo với dữ liệu hiện có và ghi rõ điều đó.

## Web UI local

```
start_ui.bat        # hoặc: python -m uvicorn raemf_mc.webapp.app:app --port 8600
```

Dashboard tại `http://127.0.0.1:8600` (chỉ lắng nghe trên máy local):

- **Vận hành**: nút chạy chu trình hằng ngày, nút retrain toàn bộ pipeline (`run` với `configs/laptop.yaml`, sau đó tự chạy lại `current-report` trên baseline mới), nhật ký chạy trực tiếp, nút hủy tác vụ. Mỗi thời điểm chỉ một tác vụ được chạy; log lưu tại `outputs/webapp_jobs/`.
- **Biểu đồ**: diễn biến VN-Index (chọn 90 ngày → tất cả), dự phóng Monte Carlo theo horizon (trung vị, vùng 50%, vùng 95%), xác suất bốn trạng thái tại 20/40/60 phiên.
- **Báo cáo**: bản "cho người không chuyên" và toàn bộ hình do pipeline sinh ra.

Cài đặt phụ thuộc UI (đã có sẵn trong `.venv` của repo):

```bash
pip install -e .[ui]
```

## Retrain khi nào

Chu trình hằng ngày chỉ refit deployment với tham số đã khóa (nhanh). Retrain toàn bộ (tuning + walk-forward + backtest, chạy lâu) nên thực hiện định kỳ (ví dụ mỗi quý) hoặc khi báo cáo cảnh báo drift; kết quả mới được copy vào `outputs/latest` và trở thành baseline cho các ngày sau.

## Sự cố thường gặp

| Hiện tượng | Nguyên nhân / cách xử lý |
| --- | --- |
| `INGEST TỪ CHỐI: ... cũ hơn lịch sử hiện tại` | File xuất là bản cũ. Xuất lại file mới từ DataPro. |
| `INGEST TỪ CHỐI: ... thiếu N phiên` | File xuất không đủ toàn bộ lịch sử. Kiểm tra lại phạm vi ngày khi xuất. |
| `INGEST TỪ CHỐI: ... lệch quá 0.5%` | Dữ liệu nguồn khác thường (điều chỉnh chỉ số, lỗi file). Đối chiếu thủ công trước khi thay. |
| Muốn quay về dữ liệu cũ | Copy bản backup tương ứng từ `backups/` đè lên `VNINDEX_Daily.csv`. |
| Nút chạy bị khóa | Đang có tác vụ khác chạy — chờ xong hoặc bấm hủy. |
