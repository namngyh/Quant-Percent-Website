#!/usr/bin/env sh
set -eu
python scripts/run_all.py --config "${1:-configs/quick.yaml}" --data "${2:-data/raw/VNINDEX_Daily.csv}"
