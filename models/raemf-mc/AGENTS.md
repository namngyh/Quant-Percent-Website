# Hướng dẫn cho tác nhân phát triển

- Không dùng dữ liệu tương lai khi tạo đặc trưng, chọn tham số, hiệu chỉnh xác suất hoặc backtest.
- Với mỗi horizon, train và validation phải được purge bằng `target_end_date_h < boundary`.
- Không dùng test để tuning, chọn feature, chọn calibration hoặc chọn ngưỡng.
- Không bịa số liệu. Thành phần không ước lượng được phải ghi rõ lý do.
- Báo cáo chính bằng tiếng Việt, trung lập, không đưa lời khuyên đầu tư.
- Lệnh kiểm thử chính: `conda run -n project python -m pytest -q`.
- Lệnh chạy laptop (point estimate): `bash scripts/run_laptop.sh`.
- Lệnh chạy RAEMF-VB-MC: `bash scripts/run_laptop_vb.sh` (hoặc
  `scripts/run_gpu_research.sh` khi có CUDA).
- Bayesian backend chính là `pytorch_cuda`; PyMC là backend tham chiếu và
  chỉ dùng cho NUTS validation trên bài toán nhỏ.
- Quy tắc chọn scenario mode mặc định và production classifier đã được đăng
  ký trước tại `scripts/summarize_vb_results.py`; không đổi quy tắc sau khi
  nhìn kết quả.
