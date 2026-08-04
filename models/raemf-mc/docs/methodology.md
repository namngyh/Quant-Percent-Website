# Phương pháp RAEMF-MC

## Dòng xử lý

RAEMF-MC tạo đặc trưng nhân quả từ OHLCV, lọc xác suất state hiện tại bằng Filtered HMM, ước lượng rủi ro bằng EGARCH Student-t và đưa toàn bộ đặc trưng vào EBM đa lớp riêng cho từng chân trời 20, 40 và 60 phiên.

## Validation và purge

Với quan sát tại thời điểm $t$ và chân trời $h$, train chỉ giữ hàng thỏa $\operatorname{target\_end\_date}_{t,h} < \operatorname{boundary}$. Tuning dùng expanding-window folds trước final test. Calibration chỉ học từ validation; final test không tham gia chọn feature, tham số hoặc temperature.

## Filtered HMM và căn chỉnh state

Xác suất $p(S_t=k\mid\mathcal{F}_t)$ được tính bằng forward recursion. State thô được căn chỉnh bằng mean return, volatility, downside, xác suất âm, tần suất và duration trên train. Tên kinh tế là tương đối và không đồng nhất trực tiếp với nhãn Bull, Sideway, Bear, Stress.

## EGARCH Student-t và Monte Carlo

Monte Carlo lấy state kế tiếp từ ma trận chuyển, dùng drift $\mu_k$, scale rủi ro theo state, cập nhật log variance EGARCH đệ quy và lấy innovation Student-t với $\nu$ đã fit. Xác suất EBM tái trọng số state cuối kỳ; ESS thấp kích hoạt clipping và tempering.

## Backtest

Signal sau đóng cửa ngày $t$ tạo position cho lợi suất ngày $t+1$. Chi phí giao dịch bằng turnover nhân cost rate. Bảng chính chỉ dùng final test và so sánh các chiến lược trên cùng ngày.
