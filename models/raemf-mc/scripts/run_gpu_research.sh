#!/usr/bin/env bash
# GPU research profile: identical stages to run_laptop_vb.sh but requires CUDA
# (fails loudly if unavailable), uses 7 ADVI seeds and heavier Monte Carlo.
set -euo pipefail

python -c "from raemf_mc.runtime.hardware import require_gpu; require_gpu()"
python -m raemf_mc.cli merge-data --output-dir outputs/latest
python -m raemf_mc.cli hardware-report --output-dir outputs/latest
python -m raemf_mc.cli benchmark-distribution \
  --data outputs/latest/canonical_vnindex.csv \
  --config configs/gpu_research.yaml \
  --output-dir outputs/distribution_oos_gpu
python -m raemf_mc.cli benchmark-plots --run-dir outputs/distribution_oos_gpu
python -m raemf_mc.cli benchmark-regime-head \
  --data outputs/latest/canonical_vnindex.csv \
  --config configs/gpu_research.yaml \
  --output-dir outputs/regime_head_benchmark_gpu
python scripts/validate_advi_with_nuts.py --output-dir outputs/latest/advi_nuts_validation
python scripts/forecast_latest_vb.py \
  --data outputs/latest/canonical_vnindex.csv \
  --config configs/gpu_research.yaml \
  --output-dir outputs/latest
