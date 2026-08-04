# Review repository ban đầu — trước khi nâng cấp

Ngày review: 20/07/2026. Trạng thái Git được review: `a07cd94`. Review này được hoàn tất trước khi sửa implementation.

## Bằng chứng thực thi ban đầu

- `pytest -q`: 9 test pass, 3,57 giây. Log: `before_changes_test_log.txt`.
- Quick pipeline: exit code 0, 14,97 giây. Log: `before_changes_quick_pipeline_log.txt`.
- Dữ liệu thật: 6.306 phiên từ 28/07/2000 đến 13/07/2026; parser phát hiện 46 vi phạm High và 5 vi phạm Low.

## Thành phần đã có

Repository đã có loader cho CSV lỗi delimiter, feature causal cơ bản, target return/direction/MDD/volatility, chronological split với purge, bốn encoder theo scale, gate theo horizon, multi-task trainer, static CQR, metric, inference, quick pipeline, báo cáo sơ bộ và test cơ bản. Pipeline tạo model, scaler, test prediction, latest forecast và bốn biểu đồ.

## Phát hiện theo mức độ nghiêm trọng

| Mức | File / function | Phát hiện |
|---|---|---|
| Critical | `calibration.py`, mọi conformity score | `max(lower-y, y-upper)` có thể âm khi observation nằm trong khoảng. qhat âm có thể làm khoảng calibrated hẹp hơn raw. Quantile chưa dùng order statistic tường minh. |
| Critical | `models/msdp.py`, `heads.py` | MDD dùng generic monotonic head và không bị chặn ở 0; output dương là hợp lệ theo code nhưng sai định nghĩa maximum drawdown. |
| Critical | `losses.py`, `pipeline.py` | Return, MDD và volatility được cộng trực tiếp trong đơn vị phần trăm thô; volatility có scale lớn, làm méo tối ưu multi-task. Không có target scaler. |
| High | `models/blocks.py` | `Conv1d(..., padding=1)` dùng padding đối xứng. Implementation không phải causal convolution như thiết kế temporal forecasting yêu cầu. |
| High | `models/experts.py` | Thiếu input Linear/LayerNorm; latent chỉ dùng global average, không nối last state; pooling không xử lý phần dư bằng cách giữ dữ liệu mới nhất. |
| High | `models/gate.py`, `models/msdp.py` | Gate dùng raw last feature trực tiếp; không có learned context kết hợp bốn expert. Horizon chỉ tác động gate, không cộng vào fused representation trước prediction heads. |
| High | `losses.py` | Regularizer `-entropy` thúc đẩy từng sample gần equal-weight; không phải batch load balancing. |
| High | `training/tuning.py`, `scripts/tune.py` | Placeholder: chỉ ghi model config hiện tại thành `best_params.yaml`; không tạo Optuna study, folds, trials hay pruning. README ngụ ý cấu hình nghiên cứu nhưng tuning thật chưa chạy. |
| High | `pipeline.py` | Chỉ train một seed dù `default.yaml` khai báo ba seed; không ensemble. `production_model.pt` là byte-equivalent về nội dung logic với evaluation model, không retrain production. |
| High | `pipeline.py`, `models/ablations.py` | Ablation chỉ là danh sách tên; không train/evaluate. Baseline chỉ có ZeroReturn được chạy; HistoricalMean/Ridge không được đánh giá. Bootstrap function tồn tại nhưng pipeline không gọi. |
| High | `features.py`, `pipeline.py` | Feature được chọn theo missingness toàn chuỗi, làm test ảnh hưởng selection. NaN warm-up bị điền bằng development median thay vì loại warm-up. Metadata thiếu `requires_ohlcv` và `expert_tags`. |
| High | `pipeline.py` | Test được đánh giá mỗi lần gọi pipeline; không có manifest/guard chống vô tình dùng lại test trong tuning. |
| Medium | `models/msdp.py` | Không có auxiliary expert forecast; “expert disagreement” trong confidence dùng độ lệch gate weights, sai khái niệm disagreement dự báo. |
| Medium | `calibration.py` | Rolling calibrator không quản lý maturity theo horizon (`i+h <= current_time`); API cho phép update residual ngay lập tức. |
| Medium | `trainer.py` | Không scheduler, không dừng rõ khi loss NaN, history chỉ có total loss. Direction head trả probability rồi BCE, kém ổn định hơn logits + BCEWithLogitsLoss. |
| Medium | `metrics.py` | Horizon bị hard-code `[5,20,60]`; thiếu ECE/reliability, gate metrics, market-condition, seed stability và CI comparison đầy đủ. |
| Medium | `inference.py` | Scaler nằm ngoài bundle; bundle thiếu target scalers, conformal qhat/source, metadata feature đầy đủ và version. |
| Medium | `reporting.py` | Báo cáo ngắn, bản Việt hóa bằng string replacement và đang mojibake; thiếu hầu hết mục học thuật yêu cầu. |
| Medium | `plotting.py` | Chỉ sinh bốn biểu đồ, chưa có manifest và nhận xét tự động. |
| Low | Toàn source | Nhiều statement một dòng, ít type hint/docstring và error message chưa đủ ngữ cảnh. |

## Sai khác giữa tài liệu và implementation

- README nói “production bundle is separate”, nhưng pipeline lưu cùng state/model args hai lần và không production retraining.
- README nói baseline superiority cần bootstrap, nhưng pipeline không tạo bootstrap result.
- `best_params.yaml` có tên như kết quả tuning dù chưa có Optuna study.
- Artifacts chỉ là quick one-seed run, không phải default research run.
- Báo cáo mô tả ordered MDD quantiles nhưng không nói output có thể dương.
- Các lệnh `evaluate.py`, `generate_report.py`, `tune.py` không nhận đủ CLI được README nâng cấp yêu cầu.

## Điểm trước khi sửa

| Hạng mục | Điểm / 10 | Lý do |
|---|---:|---|
| Code quality | 5.0 | Module hóa có nhưng code cô đặc, ít validation. |
| Mathematical correctness | 3.0 | Lỗi conformal, MDD head và loss scaling là lỗi nền tảng. |
| Leakage control | 5.0 | Split/purge đúng cơ bản; feature selection dùng toàn chuỗi và warm-up imputation chưa đúng. |
| Model architecture | 4.0 | Có bốn expert/gate nhưng convolution và context chưa khớp đặc tả. |
| Experimental design | 2.5 | Không tuning thật, ensemble, ablation hay bootstrap. |
| Calibration | 2.0 | Score có thể âm; rolling maturity chưa đúng. |
| Interpretability | 3.0 | Có gate output nhưng disagreement sai và biểu đồ thiếu. |
| Reproducibility | 5.0 | Có seed/metadata, nhưng chưa có multi-seed và artifact protocol đầy đủ. |
| Documentation | 4.0 | Có README nhưng bản Việt lỗi encoding và tuyên bố vượt implementation. |
| Deployment readiness | 3.5 | Latest chạy được trong pipeline, nhưng bundle chưa self-contained và production chưa retrain. |

## Kết luận review ban đầu

Prototype chạy được nhưng chưa đủ điều kiện gọi là implementation nghiên cứu có thể kiểm chứng. Ưu tiên sửa theo thứ tự: conformal → prediction heads → target scaling/loss → causal experts/context/gate/auxiliary output → leakage feature pipeline → test → tuning/ensemble/baseline/ablation/bootstrap → artifacts, biểu đồ và tài liệu.
