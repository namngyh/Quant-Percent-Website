#!/usr/bin/env python
"""Train the tabular baselines under purged walk-forward evaluation.

Thin wrapper around the CLI so the pipeline can be driven either way:

    python scripts/train_baselines.py --config config/local.yaml
    python -m dynamicgraph.cli train-baselines --config config/local.yaml
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

from dynamicgraph.cli import main

if __name__ == "__main__":
    sys.exit(main(["train-baselines", *sys.argv[1:]]))
