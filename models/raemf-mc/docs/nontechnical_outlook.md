# Triển vọng thị trường theo RAEMF-VB-MC — bản đọc cho người không chuyên

Cập nhật theo phiên giao dịch **2026-07-13** (VN-Index đóng cửa **1.800,54**).
Đây là kết quả nghiên cứu, **không phải lời khuyên đầu tư**.

## 1. Mô hình đang thấy thị trường ở trạng thái nào?

Bộ nhận diện "thời tiết thị trường" (Filtered HMM) cho rằng thị trường đang ở
**trạng thái biến động trung bình** với xác suất 99,9% — không phải trạng
thái căng thẳng (biến động cao) và cũng không phải trạng thái yên ắng nhất.

Bộ dự báo trạng thái tương lai (EBM, cập nhật theo pipeline gần nhất) hiện
**không nghiêng rõ về hướng nào**: xác suất Bull / Sideway / Bear / Stress
cho 20–60 phiên tới đều nằm quanh 20–32%, entropy gần mức tối đa. Mức tự tin
của mô hình về *trạng thái* tương lai vì vậy được dán nhãn **"Uncertain"**.

## 2. Khoảng kết quả có thể xảy ra (fan chart RAEMF-VB-MC)

Dự báo phân phối lợi suất tích lũy từ 2026-07-13 (chế độ variational
posterior, 1.500 kịch bản Monte Carlo):

| Chân trời | Trung vị | Khoảng 80% | Khoảng 95% | P(lợi suất âm) | P(drawdown > 10%) |
|---|---|---|---|---|---|
| 20 phiên | +1,0% | −2,2% → +4,3% | −4,5% → +6,6% | 32,6% | 0,3% |
| 40 phiên | +2,3% | −2,5% → +6,9% | −6,0% → +10,2% | 25,4% | 1,6% |
| 60 phiên | +3,3% | −1,9% → +8,9% | −5,1% → +12,8% | 19,4% | 2,3% |

Cách đọc: fan chart **không phải cam kết** VN-Index sẽ đạt một mốc điểm.
Nó nói rằng, theo mô hình, khoảng 80% kịch bản 60 phiên rơi vào −1,9% đến
+8,9%, và vẫn có ~1/5 kịch bản kết thúc giảm điểm.

**Lưu ý quan trọng về độ tin cậy của khoảng dự báo**: kiểm định ngoài mẫu cho
thấy các khoảng của chế độ variational posterior ở chân trời 20 phiên đang
**hẹp hơn thực tế** (coverage thực ~79–86% cho khoảng danh nghĩa 90–95%).
Người đọc nên coi các khoảng ở bảng trên là **cận dưới** của độ bất định
thực; rủi ro thực tế có thể lớn hơn con số hiển thị.

## 3. Mức biến động và rủi ro giảm giá có lớn không?

- Xác suất drawdown vượt 10% trong 60 phiên: ~2,3% (thấp theo mô hình).
- VaR 95% cho 20 phiên (chế độ variational posterior): xem
  `outputs/latest/latest_drawdown_risk_vb.csv`.
- EGARCH cho thấy biến động điều kiện hiện tại ở mức trung bình so với lịch sử.

## 4. Mô hình tự tin ở mức nào, và sự không chắc chắn đến từ đâu?

Phân rã phương sai dự báo (xem `latest_uncertainty_decomposition.json`):

- **Sốc ngẫu nhiên hằng ngày + tích lũy theo path**: nguồn lớn nhất ở mọi
  chân trời.
- **Bất định về tham số mô hình** (đo bằng Variational Bayes): ~0% ở 20
  phiên, ~5% ở 40 phiên, ~14% ở 60 phiên — càng nhìn xa, phần "mô hình không
  chắc về chính nó" càng lớn.
- **Bất định về trạng thái hiện tại**: gần 0% (HMM đang rất chắc về trạng
  thái hôm nay).

## 5. Yếu tố nào làm dự báo thay đổi?

- Chuỗi phiên giảm mạnh (như 2026-07-13, −1,6%) đẩy xác suất trạng thái
  biến động cao và mở rộng fan chart.
- Biến động EGARCH tăng → mọi khoảng dự báo rộng ra gần như tỉ lệ thuận.
- Xác suất regime của EBM thay đổi → trọng số các kịch bản Monte Carlo đổi.

## 6. Mô hình KHÔNG biết điều gì?

- Sự kiện ngoài dữ liệu giá/khối lượng lịch sử (chính sách, dòng tiền ngoại,
  sự kiện quốc tế đột ngột).
- Khả năng nhận diện sớm Bear/Stress còn yếu: recall ngoài mẫu của lớp Bear
  chỉ ~7% (EBM) và mô hình Bayesian thay thế cũng không cải thiện được.
- Các tham số HMM/EGARCH vẫn là ước lượng điểm — bất định của chúng chưa
  được tính vào fan chart.

## 7. Dự báo này chưa thể kiểm chứng vào thời điểm nào?

Dự báo lập tại 2026-07-13 chỉ có thể chấm điểm khi đủ số phiên tương lai:
sau ~20 phiên (khoảng giữa tháng 8/2026), ~40 phiên (giữa tháng 9/2026) và
~60 phiên (giữa tháng 10/2026). Trước các mốc đó, mọi nhận định "dự báo đúng
hay sai" đều chưa có cơ sở.

## Giải thích nhanh các khối của mô hình

- **HMM** — nhận diện "thời tiết thị trường" hiện tại (4 trạng thái).
- **EBM** — ước lượng xác suất trạng thái 20/40/60 phiên tới, giải thích được.
- **EGARCH** — đo mức biến động hiện tại có tính bám sát chuỗi thời gian.
- **Variational Bayes** — đo mức KHÔNG chắc chắn về tham số phân phối lợi suất.
- **Monte Carlo** — tạo hàng nghìn kịch bản tương lai từ các khối trên.
- **Fan chart** — dải kết quả của các kịch bản, không phải một con số cam kết.
