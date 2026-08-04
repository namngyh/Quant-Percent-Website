# Báo cáo baseline

Các baseline được tách đúng mục tiêu: zero point cho MAE/RMSE; phân phối thực nghiệm cho pinball/MDD/biến động; tần suất lịch sử cho xác suất hướng; HistoricalMean và Ridge dùng residual từ validation tuần tự; Logistic chọn C theo validation tuần tự.

Trên final test quick, MSDP có pinball H5 `0.7731` so với empirical `0.7463`, H20 `1.7032` so với `1.5979`: baseline tốt hơn. Ở H60 cần đọc trực tiếp bảng metric current run trước khi kết luận. Không có bằng chứng MSDP vượt baseline nhất quán. Ridge có MAE `2.4065`, `5.5800`, `9.0625`; MSDP lần lượt `2.3688`, `5.0055` và metric H60 trong `final_metrics.json`.
