# Phòng ngừa rò rỉ dữ liệu

## Feature construction

Đặc trưng tại hàng $t$ chỉ dùng OHLCV đến hết hàng $t$. Rolling window là trailing window; exponential window dùng `adjust=False`. Warm-up được giữ là missing, forward-fill từ quá khứ hoặc impute bằng median fit trên train. Không có `bfill()` xuyên toàn chuỗi và không có negative shift trong feature builder.

## Target overlap purge

Mỗi horizon lưu `target_end_date_h`. Với boundary validation hoặc test $b$, phần đứng trước boundary chỉ được giữ nếu:

```math
\operatorname{target\_end\_date}_{t,h} < b.
```

Điều kiện này loại quan sát có nhãn dùng giá nằm trong giai đoạn tiếp theo, kể cả khi row index của quan sát vẫn nằm trước boundary.

## Fit scope

- Evaluation HMM, scaler HMM và EGARCH chỉ fit trên train.
- Feature selection và median imputation chỉ fit trên train từng horizon.
- Random search dùng purged folds trước final test.
- Temperature scaling chỉ dùng validation.
- Final test chỉ dùng để báo cáo metric, reliability, bootstrap và backtest.
- Deployment model refit sau khi kiến trúc và tham số đã khóa; calibration deployment dùng temperature học từ validation evaluation.

## Backtest timing

Signal được xác định sau đóng cửa ngày $t$. Position thực thi cho lợi suất ngày $t+1$ bằng `signal.shift(1)`. Transaction cost được trừ tại ngày position thay đổi. Calendar backtest phải trùng chính xác calendar dự báo OOS đã lưu.

## Kiểm thử

Test suite perturb dữ liệu tương lai và xác minh feature cùng xác suất Filtered HMM trong quá khứ không đổi. Các test riêng kiểm tra target purge, calibration scope, OOS calendar và position lag một phiên.
