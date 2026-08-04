#!/usr/bin/env python
"""Run the full out-of-sample walk-forward experiment.

Thin wrapper around the CLI so the pipeline can be driven either way:

    python scripts/run_walk_forward.py --config config/local.yaml
    python -m dynamicgraph.cli walk-forward --config config/local.yaml
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

from dynamicgraph.cli import main

if __name__ == "__main__":
    sys.exit(main(["walk-forward", *sys.argv[1:]]))
