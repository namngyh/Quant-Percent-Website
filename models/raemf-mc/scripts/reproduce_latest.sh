#!/usr/bin/env bash
set -euo pipefail
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-raemf}"
export PYTHONPATH="${PYTHONPATH:-src}"
python -m raemf_mc.cli reproduce --data data.csv --config configs/laptop.yaml
