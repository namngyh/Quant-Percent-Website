#!/usr/bin/env bash
set -euo pipefail

python -m raemf_mc.cli current-report \
  --data VNINDEX_Daily.csv \
  --baseline-run outputs/latest \
  --config configs/laptop.yaml \
  --output-dir outputs/current_monitor \
  --readme README.md
