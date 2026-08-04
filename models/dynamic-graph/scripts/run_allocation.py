#!/usr/bin/env python
"""Run the capital-allocation experiment and print the comparison tables.

    python scripts/run_allocation.py --config config/local.yaml
    python -m dynamicgraph.cli allocate --config config/local.yaml
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

from dynamicgraph.cli import main

if __name__ == "__main__":
    sys.exit(main(["allocate", *sys.argv[1:]]))
