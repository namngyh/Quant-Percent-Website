#!/usr/bin/env python
"""Build node features, market features and forward targets.

Thin wrapper around the CLI so the pipeline can be driven either way:

    python scripts/build_features.py --config config/local.yaml
    python -m dynamicgraph.cli build-features --config config/local.yaml
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

from dynamicgraph.cli import main

if __name__ == "__main__":
    sys.exit(main(["build-features", *sys.argv[1:]]))
