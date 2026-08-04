# Báo cáo Optuna

Run `20260720_161451_quick` dùng study `msdp_v3_quick_b9223de5_v1`, 2 expanding fold, purge 60 phiên và 8 trial. Có 8 trial hoàn tất, 0 bị cắt sớm, 0 lỗi. Tuning mất 1.092,70 giây; toàn pipeline mất 1.364,19 giây trên CPU.

Objective được tính sau inverse-transform và tương đối với baseline của chính fold. Best objective là `0.6862957481`. Tham số tốt nhất được lưu tại `artifacts/tuning/msdp_v3_quick_b9223de5_v1/best_trial.json`; metric từng fold nằm trong `fold_metrics.csv`.

Đây là kết quả kiểm tra pipeline, chưa phải kết quả nghiên cứu cuối cùng. Default 50 trial chưa được chạy vì chi phí quick đã khoảng 22,7 phút.
