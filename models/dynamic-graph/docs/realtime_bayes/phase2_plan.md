# Phase 2 — kế hoạch thực thi (Dynamic Graph online layer)

Nguồn: `realtime-bayes-roadmap.md` (Phase 2) và kiến trúc 2 tầng đã chứng minh ở Phase 1 —
xem `RAFF/RARF-FHE-.../docs/realtime_bayes/phase1_plan.md`.

## Khảo sát: đo trước, thiết kế sau

Roadmap giả định nút thắt là "Graphical Lasso refit toàn bộ mỗi lần", nên đề xuất thay ước lượng
covariance bằng recursive/EWMA hoặc NIW conjugate. **Đo thực tế cho thấy giả định đó sai chỗ:**

| Thao tác (cửa sổ 60 phiên) | Thời gian |
| --- | --- |
| Ledoit-Wolf covariance, 30 nodes | **0.41 ms** |
| `build_snapshot`, `bootstrap_iterations=0`, 30 nodes | 17 ms |
| `build_snapshot`, `bootstrap_iterations=100`, 13 nodes | 1.2 s |
| `build_snapshot`, `bootstrap_iterations=100`, 30 nodes | **4.4 s** |
| như trên nhưng `n_jobs=-1` | 15.7 s (chậm hơn 3.5×) |

Ước lượng covariance chiếm ~0.01% chi phí một snapshot; ~99.8% nằm ở 100 vòng bootstrap
graphical-lasso của `edge_stability`. Viết incremental/EWMA covariance update sẽ tiết kiệm
0.4 ms trên tổng 4.4 s — vô nghĩa, mà lại đánh đổi bằng việc graph online khác graph batch.

Chi phí thật của tầng batch không nằm ở *một* snapshot mà ở *số lượng* snapshot: run thật có
**3526 snapshot core** (`partial_correlation__residual__w60`, 2012-06-05 → 2026-07-24, 13–30 nodes,
stride 1). Tầng online chỉ cần dựng **1** snapshot cho phiên mới.

### Quyết định

Tầng online gọi **chính `build_snapshot()` mà tầng batch dùng**, trên đúng cửa sổ trailing của
phiên mới, với `alpha` và toàn bộ `SnapshotBuildConfig` đã khóa từ run batch. Đây là hiện thực
đúng của lựa chọn "rolling chính xác": tương đương batch **theo cấu trúc** (cùng một hàm, cùng
input), không cần đại số incremental, không có train/serve skew cho model dự báo stress.

Hệ quả: không cần đổi tầng batch (quyền đó đã được cấp nhưng không dùng tới).

## Cái gì thực sự cần "state hóa"

Những đại lượng phụ thuộc lịch sử chứ không chỉ snapshot hiện tại:

| Đại lượng | Nguồn | Cách xử lý online |
| --- | --- | --- |
| `stress_percentile` | `raw.expanding(min_periods=60).rank(pct=True)` | giữ toàn bộ chuỗi `stress_raw` trong state (1 float/phiên) — chính xác tuyệt đối, rẻ |
| `stress_change_{1,5,20}d` | `diff` trên `stress_score` | giữ lịch sử `stress_score` |
| `add_dynamics` (rolling 5/20/60 trên graph metrics) | metric frame | giữ metric history có giới hạn |
| `compare_partitions` (ARI/NMI/Jaccard/turnover), `edge_turnover` | snapshot trước | giữ snapshot + partition trước |
| Residual returns | rolling OLS beta/alpha trên cửa sổ trailing | causal, dựng lại từ return buffer |

Center/scale/weights của `DescriptiveStressScore` và `raw_quantiles` đã fit-on-train và **đóng
băng** — đúng như roadmap dự đoán, chỉ cần mang nguyên qua handoff.

## Cái gì ở lại tầng batch

- Chọn `alpha` cho graphical lasso (`select_alpha`, CV/stability) — chỉ dùng training windows.
- `training/walk_forward.py`, `fit_final_model` — train model dự báo stress.
- Fit `DescriptiveStressScore` (median/MAD trên train), chọn metric, prune redundancy.
- Figures, reports, allocation backtest, graph validation.

**Quan trọng:** `latest.build_stress_probabilities()` hiện gọi `fit_final_model()` — tức là
*refit* mỗi lần sinh latest. Tầng online **không** được làm vậy: model đã fit tới ngày batch
được đóng băng trong handoff và chỉ inference.

## Kiến trúc (giống Phase 1)

```
run-all / build-graphs  ──► artifacts/online_state/batch_handoff.joblib
                                     │
                        init-online-state
                                     ▼
                        artifacts/online_state/online_state.joblib (+ manifest)
                                     │
                        update-latest  (mỗi phiên mới, đọc DB read-only)
                                     ▼
                        artifacts/latest/*  (giữ nguyên schema)
```

Một phiên online:

1. đọc phiên mới qua connector read-only đã có (`data/connectors.py` — tái dùng, không viết mới);
2. residual returns từ return buffer (rolling OLS, causal);
3. dựng snapshot core (bootstrap stability) + các key phụ (bootstrap=0, ~17 ms mỗi cái);
4. graph metrics / node metrics / communities + so với partition phiên trước;
5. descriptive stress score với center/scale đóng băng, percentile từ chuỗi `stress_raw` trong state;
6. xác suất stress từ model đóng băng (inference, **không** `fit_final_model`);
7. ghi lại `artifacts/latest/*` với đúng schema hiện tại.

Ngân sách thời gian mục tiêu: **< 10 s/phiên** (chi phối bởi 1 lần bootstrap stability).

## Ràng buộc kế thừa từ Phase 1

1. Không leakage: mọi thứ tại ngày `t` chỉ dùng dữ liệu tới hết `t`.
2. Không âm thầm nội suy/vá dữ liệu bất thường — dừng và báo.
3. State pin vào run batch gốc (`source_run_metadata`) và vào chính buffer (checksum);
   không khớp thì từ chối nạp thay vì ghi đè.
4. Toàn bộ 297 test hiện có phải tiếp tục pass, 0 warning.
5. DB read-only tuyệt đối.
6. Không viết scheduler Python — Task Scheduler/cron gọi CLI.

## Thứ tự thực thi (TDD)

1. `online/state.py`: dataclass state + save/load + manifest (mirror Phase 1).
2. `online/handoff.py`: `BatchHandoff` + `save/load`; `pipeline` ghi handoff ở cuối.
3. `online/session.py`: `advance_one_session` — snapshot + metrics + communities + stress.
   Gate quan trọng nhất: **snapshot online phải khớp bit-for-bit snapshot batch cùng ngày**.
4. Frozen stress model inference (thay `fit_final_model` ở đường online).
5. Republish `artifacts/latest/*` giữ nguyên schema (khóa bằng test).
6. CLI `init-online-state` / `update-latest` + config + docs.

---

## Tiến độ

Đã xong (**319 test pass**, ruff clean; baseline trước Phase 2 là 297):

| Bước | Trạng thái |
| --- | --- |
| 1. `online/state.py` | ✅ state + manifest + checksum |
| 2. `online/handoff.py` + `pipeline` ghi handoff | ✅ `_write_batch_handoff` cuối `stage_network_metrics` |
| 3. `online/session.py` | ✅ snapshot + graph metrics + communities + stress score |
| 4. Stress model đóng băng | ✅ `transform` từ model đã fit, không refit |
| 5. Republish `artifacts/latest/*` | ✅ **xong** (2026-08-26) — xem ghi chú dưới |
| 6. CLI + persistence | ✅ `init-online-state`, `update-latest`, save/load + guard |

### Ba gate tương đương, đều đã mutation-check

1. **Snapshot**: online khớp `build_snapshot` của batch cho cùng ngày, gồm cả `stability`
   bootstrap. Mutation lệch cửa sổ 1 dòng → fail.
2. **Graph metrics**: metric row online khớp `compute_metric_series`. Mutation bỏ seed snapshot
   trước → `edge_turnover` thành NaN, fail.
3. **Stress score**: khớp `DescriptiveStressScore.transform` của batch kể cả `stress_percentile`
   (expanding rank) và `stress_change_20d`. Mutation transform chỉ 1 dòng cuối → fail.

### Cách bước 5 được mở khoá (2026-08-26)

Vấn đề cũ: `latest.build_stress_probabilities()` gọi `fit_final_model()` — tức **refit** model dự
báo stress mỗi lần sinh latest. Tầng online không được làm vậy, nên trước đây `update-latest`
**không** ghi đè `artifacts/latest/`: ghi một payload thiếu lên trên payload tốt của batch còn tệ
hơn là không ghi.

Cách giải:

1. `latest.py` tách làm ba: `fit_stress_models()` (chỉ tầng batch), `stress_feature_builder()`
   (dùng chung — nếu hai tầng dựng ma trận đặc trưng khác nhau thì model bị chấm trên ma trận khác
   ma trận nó được fit, và không gì phía sau phát hiện được), và `predict_stress_probabilities()`
   (chỉ inference). **Cả hai tầng publish qua đúng một hàm**, nên schema payload không thể trôi.
2. `generate_latest()` fit một lần rồi giữ lại model; `_augment_batch_handoff()` ghi chúng vào
   batch handoff. Handoff được **mở lại và bổ sung** ở bước publish thay vì dời chỗ ghi ban đầu,
   để `build-graphs` chạy riêng vẫn sinh ra handoff dùng được.
3. `online/publish.py` chấm điểm model đã đóng băng rồi ghi `artifacts/latest/` bằng **chính**
   `build_website_payload` / `write_website_outputs` của tầng batch.

Hai chi tiết đáng lưu ý:

- **`metric_history_by_key`**: model stress được fit trên `flatten_graph_metrics` của **mọi** graph
  key, nhưng online state cũ chỉ giữ lịch sử của core key. Chấm điểm trên ma trận hẹp hơn sẽ im
  lặng — cột thiếu chỉ đơn giản là vắng mặt, không sai. Nên state và handoff nay giữ lịch sử theo
  từng key, và `SCHEMA_VERSION` lên **2**: state phiên bản 1 bị từ chối chứ không nâng cấp ngầm,
  vì phần lịch sử theo key không dựng lại được từ những gì bản 1 đã lưu.
- **Publish thất bại không rollback phiên**: state đã lưu và vẫn đúng. Lệnh trả về
  `published: false` kèm lý do, để người đọc biết payload website đang cũ hơn state — thay vì mặc
  định cho rằng hai thứ đi cùng nhau.

`directed_roles` vẫn lấy từ run batch: tầng online không dựng lại đồ thị có hướng/spillover, nên
file `edges.json` của phiên online không có lớp phủ directed. Payload ghi rõ
`model.produced_by = "online_tier"` và `model.source_run_metadata` để phân biệt.

### Giới hạn xác minh

Trước đây máy không có `config/local.yaml` nên toàn bộ verify chạy trên synthetic panel. Nay đã có
`config/local.yaml` trỏ vào TimescaleDB thật (`bars_1d`, 10.10.0.1) và `audit-data` chạy được trên
panel thật: **112 592 dòng, 31 mã, 2012-02-06 .. 2026-08-26**, 0 lỗi.
