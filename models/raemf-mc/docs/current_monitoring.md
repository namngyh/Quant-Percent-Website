# Theo dõi dự báo với dữ liệu hiện tại

## Mục tiêu

Lệnh `current-report` tách hai câu hỏi khác nhau:

1. Dự báo đã phát hành trước đây đang nằm ở đâu so với đường VN-Index thực tế?
2. Nếu refit deployment RAEMF-MC bằng dữ liệu mới nhất, outlook hiện tại là gì?

Phần này không thay thế final-test OOS trong báo cáo nghiên cứu và không tạo một benchmark mới.

## Baseline bất biến

`--baseline-run` cung cấp dự báo, calibration, hyperparameter và Monte Carlo đã lưu tại ngày phát hành. Đường thực tế mới được đặt lên đúng phân phối cũ. Nếu nhà cung cấp sửa dữ liệu tại ngày baseline, báo cáo vẫn giữ mức close đã ghi trong `latest_outlook.json` làm điểm neo và công khai độ lệch nguồn.

## Quy tắc chấm dự báo

Với horizon `h`, dự báo lớp chỉ được chấm khi đã có đủ `h` phiên giao dịch sau ngày phát hành. Trước mốc đó, báo cáo chỉ ghi:

- số phiên đã quan sát và còn thiếu;
- lợi suất tạm thời từ mức neo;
- vị trí của VN-Index trong dải Monte Carlo cũ;
- trạng thái `Đang theo dõi, chưa đủ phiên`.

Nằm trong dải 50%, 80% hoặc 95% không có nghĩa dự báo lớp đã đúng.

## Deployment hiện tại

Outlook mới chỉ dùng RAEMF-MC. HMM, EGARCH và EBM được refit trên dữ liệu hiện có; EBM chỉ học từ các hàng đã có nhãn hoàn chỉnh. Hyperparameter và temperature calibration được khóa từ baseline, nên dữ liệu mới không được dùng để tuning lại kiến trúc hoặc calibration.

## Artifact

Lệnh sau tạo lại toàn bộ phần theo dõi:

```bash
python -m raemf_mc.cli current-report \
  --data VNINDEX_Daily.csv \
  --baseline-run outputs/latest \
  --config configs/laptop.yaml
```

Artifact nằm trong `outputs/current_monitor/`, gồm đường theo dõi, outlook hiện tại, phân phối Monte Carlo, provenance, metadata fit, bốn hình RAEMF-MC với VN-Index và báo cáo cho người không chuyên.
