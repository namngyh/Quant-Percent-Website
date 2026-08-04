# Báo cáo artifact production

Artifact production của run `20260720_161451_quick` nằm tại `artifacts/models/20260720_161451_quick/`. Quick chỉ có seed 42 theo config kiểm tra. Manifest chứa model seed, scaler feature, scaler target, metadata feature, calibrator và tham chiếu confidence.

Inference từ manifest đã được đối chiếu với output `run_all`; sai khác tuyệt đối lớn nhất bằng `0.0`. Đây là ensemble một phần tử do quick chỉ dùng một seed, vì vậy seed dispersion bằng 0 và không phải bằng chứng về ổn định đa seed.
