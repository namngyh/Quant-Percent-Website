#!/usr/bin/env python
"""Write every website-facing artifact.

Thin wrapper around the CLI so the pipeline can be driven either way:

    python scripts/export_website_outputs.py --config config/local.yaml
    python -m dynamicgraph.cli export-website --config config/local.yaml
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

from dynamicgraph.cli import main

if __name__ == "__main__":
    sys.exit(main(["export-website", *sys.argv[1:]]))
