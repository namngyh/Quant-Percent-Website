# MSDP — Phase 3 (đang làm)

Lộ trình: [`realtime-bayes-roadmap.md`](realtime-bayes-roadmap.md).
Kiến trúc tham chiếu đã chứng minh ở Phase 1: `RAFF/RARF-FHE-.../docs/realtime_bayes/phase1_plan.md`.

## Baseline test — đọc trước khi hoảng

Trên máy laptop này, **2 test đã đỏ sẵn trước khi Phase 3 bắt đầu**, cả hai đều do môi trường
chứ không phải code:

| Test | Nguyên nhân |
| --- | --- |
| `test_saved_artifacts::test_saved_calibrator_load_and_bundle_distinction` | thiếu `artifacts/models/evaluation_model.pt` — file nằm trên PC |
| `test_production_ensemble::test_predict_latest_matches_run_all_latest` | `NotImplementedError` với `StringDtype` tại `inference.py:42`; scaler được pickle bằng pandas/sklearn khác, laptop này có pandas 2.3.3 |

Baseline: **31 passed, 2 failed**. Sau Phase 3 (phần đã làm): **55 passed, 2 failed** — vẫn đúng
hai lỗi đó, không hồi quy.

Việc đầu tiên trên PC: chạy `pytest -q` và xác nhận hai test này **xanh** (model có sẵn, môi
trường khớp). Nếu vẫn đỏ thì đó là vấn đề thật, cần xử lý trước khi tin bất cứ số nào.

## Khảo sát: thứ đã có sẵn nhiều hơn dự kiến

- `scripts/predict_latest.py` **đã là inference-only** — gọi `predict_latest_ensemble`, không train gì.
- `calibration.py` **đã có** `RollingCQRCalibrator` và `AdaptiveConformalCalibrator`, kèm đúng cơ chế
  pending/maturity (residual test chỉ vào lịch sử khi target đáo hạn). Tức phần ACI mà roadmap
  yêu cầu **gần như đã tồn tại**; production hiện vẫn dùng `StaticCQRCalibrator`.
- `MSDP.forward` trả `aux_return_median` shape `(batch, horizon, expert)` — **dự báo riêng của
  từng expert**. Đây chính là thứ Hedge cần để chấm điểm từng expert, và nó đã có sẵn.

## Đã làm

### 1. `online/hedge.py` — Bayesian model combination trên gate

Gate đã train là **prior** trên các expert. Bằng chứng thu được sau đó được nhân vào:

```
posterior_k  ∝  prior_k · exp(-eta · Σ_t loss_{k,t})
```

Đúng công thức Bayes với gate làm prior và exponentiated cumulative loss làm likelihood — cũng
chính là multiplicative-weights/Hedge. **Không đụng vào trọng số mạng.** Mỗi lần retrain batch
thay prior mới và reset bằng chứng.

Chi tiết đáng lưu ý: bảo đảm regret của Hedge giả định loss nằm trong [0,1], mà sai số return thì
không bị chặn và thang đo trôi theo biến động. Nên mỗi vòng, loss của các expert được **rescale
về [0,1] trong nội bộ vòng đó** (`normalized_losses`). Hệ quả có ích: vòng nào mọi expert sai như
nhau thì thành no-op, thay vì kéo tụt đều tất cả.

11 test, gồm một test kiểm tra chính điều Hedge hứa hẹn: khi prior đặt cược sai expert, tổ hợp
Hedge **đánh bại** prior tĩnh trên nửa sau chuỗi.

### 2. `gate_override` trong `MSDP.forward`

Posterior phải thực sự điều khiển mạng, không chỉ dán vào báo cáo. `forward` nhận thêm
`gate_override` (mặc định `None` → hành vi cũ y nguyên), và output trả về **cả hai**:
`gate_prior` (mạng nói gì) và `gate_weights` (thứ thực sự được fuse).

Gate quan trọng: override bằng chính gate weights của mạng phải cho kết quả **giống hệt** — chứng
minh override đi vào đúng chỗ mà gate đi vào. 5 test.

### 3. `online/state.py` + `online/session.py` — bookkeeping đáo hạn

Một forecast đã publish nằm trong `state.pending` cho tới khi horizon **thực sự trôi qua** trong
chuỗi giá; chỉ khi đó nó mới được chấm điểm và gate mới học từ nó. Đây là chỗ dễ leak nhất.

Realized return tính bằng **phần trăm** log-return đúng `horizon` phiên — khớp đơn vị của mạng
(`inference.py` chiếu chỉ số bằng `exp(q/100)`).

8 test, gồm một test đi bộ qua 50 phiên và assert rằng ở mọi thời điểm, **không** pending nào đã
đáo hạn mà còn nằm lại. Mutation test (cho đáo hạn sớm 1 phiên) làm 2 test fail đúng như mong đợi.

## Đã làm tiếp (2026-08-26)

4. **Nguồn dữ liệu read-only** — `src/msdp/data_source.py` port từ RAFF, thêm backend
   **postgres** (RAFF cũng chưa có lúc đó). `src/msdp/data_sync.py` + `scripts/sync_source.py`
   xuất snapshot ra `data/raw/VNINDEX_Daily_db.csv`: mọi entry point của MSDP nhận `--data <path>`
   và run manifest ghi lại file nào đã dùng, nên giữ nguyên một file để hash là giữ nguyên hợp
   đồng provenance. Kèm `src/msdp/dotenv.py` vì Task Scheduler khởi động với môi trường trống.

5. **Nối vào `predict_latest_ensemble`** — `gate_override=posterior` đã chạy thật.
   `predict_latest_ensemble(data, model, hedge=state.hedge)`; mặc định `hedge=None` giữ nguyên
   hành vi batch. Mạng chạy **2 lần mỗi seed**: posterior cần prior của *chính seed đó*, mỗi seed
   học một gate khác nhau nên dùng chung một prior sẽ fuse sai trọng số. Hai forward pass trên
   một mẫu tốn vài micro giây.

6. **Persistence + CLI** — `online/persistence.py` (JSON, ghi atomic, có
   `assert_state_matches_run` từ chối state seed từ run khác), `online/runner.py`,
   `scripts/init_online_state.py`, `scripts/update_latest.py`. Ghi ra `artifacts/predictions/`
   **đúng schema** `predict_latest.py` đang ghi.

Chạy thật trên dữ liệu database: init tại 2026-05-06 → update tại 2026-07-01 → update tại
2026-08-26 cho `matured_forecasts: 2`, `pending_forecasts: 4`, `hedge_rounds: [1, 1, 0]`. Tức
kỳ hạn 5 và 20 phiên đã đáo hạn và gate posterior đã học từ kết quả thật; kỳ hạn 60 còn pending.
Một phiên mất ~1,5 giây.

## Còn lại

1. **ACI chưa nối.** Khoảng tin cậy vẫn từ `StaticCQRCalibrator` của bundle.
   `AdaptiveConformalCalibrator` cần một pool conformity score để tính quantile, mà
   `StaticCQRCalibrator.state_dict()` chỉ lưu `qhat` — không lưu pool. Muốn nối thật thì **tầng
   batch phải lưu lại residual của tập calibration**; đó là thay đổi ở tầng batch, không phải
   tầng online. Trong lúc chưa có, `update_latest` ghi `empirical_coverage` theo dõi độ phủ thực
   tế của các dự báo đã đáo hạn, để biết khi nào khoảng tin cậy tĩnh bắt đầu lệch.
2. **Chọn `eta`**: hiện mặc định 0.5, chưa tuning. Nên chọn trên validation bằng cách replay
   lịch sử, không phải đoán. Đây là tham số mới duy nhất Phase 3 thêm vào.
3. **Hai test đỏ vẫn đỏ** vì `artifacts/models/evaluation_model.pt` không có trên máy này — vấn
   đề thiếu file, không phải code. Suite hiện tại: **78 passed, 2 failed**.
4. **Website đang publish bản `quick`.** `D:\Quant-Percent-Website\models\msdp\` dùng
   `run_id: 20260720_161451_quick`, 1 seed, `configs/quick.yaml`; log hằng ngày tự in cảnh báo
   "Re-run MSDP with the full config before publishing these numbers". Repo này có sẵn bản GPU
   3 seed `20260722_154609_gpu`.

## Ràng buộc

Mạng neural **không** train online — quá rủi ro overfit với 1 điểm dữ liệu/ngày. Train lại toàn
mạng ở tầng batch, chu kỳ dài hơn RAFF/Graph (một run ~6000 giây, cân nhắc hàng tháng).
