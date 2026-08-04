#!/usr/bin/env bash
# RAEMF-VB-MC laptop pipeline: data merge -> hardware report -> OOS
# distribution benchmark (M0/M1/M2) -> regime head benchmark -> live forecast.
set -euo pipefail

python -m raemf_mc.cli merge-data --output-dir outputs/latest
python -m raemf_mc.cli hardware-report --output-dir outputs/latest
python -m raemf_mc.cli benchmark-distribution \
  --data outputs/latest/canonical_vnindex.csv \
  --config configs/laptop_vb.yaml \
  --output-dir outputs/distribution_oos_vb
python -m raemf_mc.cli benchmark-plots --run-dir outputs/distribution_oos_vb
python -m raemf_mc.cli benchmark-regime-head \
  --data outputs/latest/canonical_vnindex.csv \
  --config configs/laptop_vb.yaml \
  --output-dir outputs/regime_head_benchmark
python scripts/forecast_latest_vb.py \
  --data outputs/latest/canonical_vnindex.csv \
  --config configs/laptop_vb.yaml \
  --output-dir outputs/latest
