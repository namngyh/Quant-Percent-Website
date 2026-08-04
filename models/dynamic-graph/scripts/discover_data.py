#!/usr/bin/env python
"""Scan the machine for candidate VN30 data sources (read-only).

Thin wrapper around the CLI so the pipeline can be driven either way:

    python scripts/discover_data.py --config config/local.yaml
    python -m dynamicgraph.cli discover-data --config config/local.yaml
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

from dynamicgraph.cli import main

if __name__ == "__main__":
    sys.exit(main(["discover-data", *sys.argv[1:]]))
