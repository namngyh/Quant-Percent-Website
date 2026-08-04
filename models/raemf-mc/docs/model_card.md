# Model card RAEMF-MC

## Mục đích

RAEMF-MC là mô hình nghiên cứu xác suất trạng thái VN-Index ở 20, 40 và 60 phiên. Đầu ra gồm Bull, Sideway, Bear, Stress, confidence, Monte Carlo risk và backtest proxy.

## Người phát triển

Nguyễn Hoài Nam.

## Phạm vi sử dụng

Phù hợp cho nghiên cứu định lượng, kiểm tra calibration và phân tích chế độ thị trường. Không dùng như khuyến nghị đầu tư hoặc cam kết giá tương lai.

## Giới hạn

Dữ liệu đầu vào chỉ gồm OHLCV VN-Index; thiếu vĩ mô, breadth và dữ liệu thành phần. Nhãn và state phụ thuộc quy tắc; thị trường có thể drift. VN-Index không phải tài sản có thể giao dịch trực tiếp theo giả định backtest đơn giản.

## Đánh giá

Evaluation model dùng train, validation và final test tách thời gian có purge. Deployment model refit sau khi khóa kiến trúc và tham số. Kết luận ưu thế chỉ được phép khi metric, bootstrap và consistency giữa horizon cùng hỗ trợ.
