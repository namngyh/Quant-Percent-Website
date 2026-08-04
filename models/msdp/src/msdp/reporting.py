"""Sinh báo cáo nghiên cứu hoàn toàn bằng tiếng Việt."""
from pathlib import Path
import markdown

def generate_report(metrics,quality,latest,out_dir="reports",synthetic=False):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); hs=[5,20,60]
    rows=[]; comments=[]
    for h in hs:
        m=metrics[f"h{h}"]; delta=m["vs_zero_baseline"]
        rows.append(f"| {h} | {m['return_mae']:.4f} | {m['return_pinball']:.4f} | {m['brier']:.4f} | {m['coverage']:.1%} | {m['calibrated_interval']['coverage']:.1%} | {delta['return_pinball']:+.4f} |")
        comments.append(f"- Kỳ hạn {h}: Spearman {m['spearman']:.3f}, MAE {m['return_mae']:.3f}%, pinball {m['return_pinball']:.3f}. " + ("Pinball thấp hơn ZeroReturn." if delta["return_pinball"]<0 else "Pinball chưa thấp hơn ZeroReturn."))
        if m["calibrated_interval"]["width"]>m["width"]*1.25: comments.append(f"  Conformal nâng coverage từ {m['coverage']:.1%} lên {m['calibrated_interval']['coverage']:.1%}, đồng thời tăng độ rộng từ {m['width']:.2f}% lên {m['calibrated_interval']['width']:.2f}%.")
    verdict="Trong cấu hình và giai đoạn dữ liệu hiện tại, chưa có bằng chứng cho thấy MSDP vượt baseline."
    text=f"""# Báo cáo nghiên cứu đầy đủ MSDP

## Tóm tắt

MSDP dự báo phân phối lợi suất VN-Index ở 5, 20 và 60 phiên bằng bốn chuyên gia causal. {verdict}

## Dữ liệu

Dữ liệu có {quality['rows']} phiên, từ {quality['start']} đến {quality['end']}. Cảnh báo chất lượng: {quality['issues']}.

## Cơ sở toán học

Target lợi suất là `100 log(C[t+h]/C[t])`. MDD là drawdown nhỏ nhất của path tương lai và luôn không dương. Return head lấy median làm tâm; MDD head tạo severity dương rồi đổi dấu. CQR dùng `max(lower-y, y-upper, 0)` và order statistic riêng từng kỳ hạn.

## Kiến trúc

Input đi qua chuyên gia ngắn, trung, dài và range–volatility độc lập. Mỗi expert dùng projection, LayerNorm, GELU và causal residual Conv1d. Context kết hợp feature cuối với các latent; gate nhận context, latent và horizon embedding. Auxiliary head tạo dự báo riêng để đo bất đồng expert.

## Scaling, loss và chống leakage

Feature/target scaler chỉ fit train hoặc development thích hợp. Return, MDD severity và log-volatility có scaler riêng theo horizon. Loss gồm pinball, BCE-with-logits, Huber, batch load balancing và auxiliary MAE. Split theo thời gian có purge 60 phiên; conformal chỉ fit calibration prediction.

## Kết quả final test

| Kỳ hạn | MAE | Pinball | Brier | Coverage gốc | Coverage conformal | Pinball Δ so với ZeroReturn |
|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Nhận xét

{chr(10).join(comments)}

## Dự báo mới nhất

Ngày {latest['data_date']}, VN-Index {latest['current_vnindex']:.2f}. Đây là hồ sơ dự báo theo khoảng thời gian, không phải đường giá tương lai và không phải khuyến nghị mua bán.

## Hạn chế và kết luận

Artifact quick hiện chỉ dùng một seed và ba trial. Dữ liệu nguồn có vi phạm OHLC; interval dài hạn rộng; gate gần equal-weight. {verdict} Giá trị chính hiện nằm ở mô tả phân phối và hiệu chỉnh rủi ro, chưa phải dự báo điểm.

## Ánh xạ công thức–code–test

| Công thức | File | Thành phần | Test |
|---|---|---|---|
| CQR score không âm | `calibration.py` | `conformity_scores` | `test_calibration.py` |
| Return quantile có tâm median | `heads.py` | `MedianCenteredReturnQuantileHead` | `test_quantile_order.py` |
| MDD quantile âm | `heads.py` | `NegativeMonotonicMDDHead` | `test_quantile_order.py` |
| Convolution causal | `blocks.py` | `CausalConv1d` | `test_causal_conv.py` |
| Gate theo horizon | `gate.py` | `HorizonGate` | `test_horizon_gate.py` |
"""
    (out/"MSDP_BAO_CAO_DAY_DU_VI.md").write_text(text,encoding="utf-8"); (out/"MSDP_BAO_CAO_DAY_DU_VI.html").write_text(markdown.markdown(text,extensions=["tables","fenced_code"]),encoding="utf-8")
    (out/"MSDP_NHAN_XET_KET_QUA_VI.md").write_text("# Nhận xét kết quả\n\n"+"\n".join(comments)+"\n\n"+verdict+"\n",encoding="utf-8")
    (out/"MSDP_MODEL_CARD_VI.md").write_text("# Thẻ mô hình MSDP\n\nMô hình nghiên cứu dự báo phân phối VN-Index. Đầu vào Date/Close, OHLCV tùy chọn; đầu ra theo kỳ hạn 5/20/60. Không phải khuyến nghị đầu tư.\n",encoding="utf-8")
    (out/"MSDP_LIMITATIONS_VI.md").write_text("# Hạn chế\n\nKhông bảo đảm coverage iid; thị trường có thể đổi regime; quick run một seed không đủ kết luận mạnh; production cần tái huấn luyện và OOF calibration trước triển khai thực tế.\n",encoding="utf-8")
    (out/"figure_comments_VI.md").write_text("# Nhận xét biểu đồ\n\n"+"\n".join(comments)+"\n",encoding="utf-8")
