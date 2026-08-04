# Báo cáo hiệu chỉnh conformal

Run quick so sánh raw, static CQR, rolling CQR và adaptive conformal theo lịch sử causal. Phương pháp headline là **static CQR**, được chọn bằng sai lệch coverage so với 90% kết hợp interval score chuẩn hóa, không chọn theo coverage cao nhất.

Static đạt coverage H5/H20/H60 lần lượt `91,45%`, `86,14%`, `86,39%`, với độ rộng `10,16`, `20,73`, `39,23`. Khoảng dài hạn vẫn rất rộng và coverage H20/H60 còn dưới mục tiêu; không được diễn giải đây là bảo đảm iid.
