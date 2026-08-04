# Tóm tắt trước khi sửa các vấn đề còn lại

- Commit: `188752d`.
- Git sạch và đồng bộ `origin/main` trước khi bắt đầu.
- Pytest: 19 test pass.
- Quick pipeline hiện tại: pass trong 212,75 giây; study cũ có 3 trial, một fold, một seed.
- Best validation loss: 0,508896; best epoch: 1.
- Latest conformal trong `predict_latest.py` calibrate từng horizon bằng vector shape `(1,)` trong khi qhat có shape `(3,)`, tạo broadcasting sai và lấy phần tử đầu khi serialize.
- Production bundle chỉ chứa state của một seed, chưa tái tạo ensemble.
- Confidence trong pipeline truyền percentile hard-code `0.5`.
- Seed dispersion của pipeline dùng `seed_test` dòng cuối thay vì prediction mới nhất từng seed.
- Baseline metrics đang gộp point zero, empirical quantiles và historical frequency dưới một tên ZeroReturn.
- Optuna objective dùng validation total loss trong scaled space, chưa dùng metric inverse-transform ngoài mẫu.
- Chỉ Static CQR được báo cáo headline; chưa so sánh rolling/adaptive.
- OHLC lỗi được báo cáo nhưng feature range vẫn có thể sử dụng các dòng lỗi.

Số liệu quick trước sửa được giữ trong artifact hiện tại và lịch sử Git; run mới phải có `run_id` riêng, không được giả là default/full result.
