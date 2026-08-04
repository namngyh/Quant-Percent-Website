#!/usr/bin/env python
"""Produce artifacts/latest/, figures and markdown reports.

Thin wrapper around the CLI so the pipeline can be driven either way:

    python scripts/generate_latest.py --config config/local.yaml
    python -m dynamicgraph.cli generate-latest --config config/local.yaml
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

from dynamicgraph.cli import main

if __name__ == "__main__":
    sys.exit(main(["generate-latest", *sys.argv[1:]]))
