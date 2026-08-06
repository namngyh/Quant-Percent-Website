"""Shared database connection settings for the scripts in this directory.

The connection string used to be a default argument in each script, with the
live password written into it. That put a working credential in the repository
and made rotating it a six-file edit. It is read from the environment instead.

Set it once per shell, or in the environment the scheduled task runs under:

    set PG_DSN=postgresql://quant:<password>@localhost:5432/market
"""

from __future__ import annotations

import os

ENV_VAR = "PG_DSN"


def dsn_from_env(override: str | None = None) -> str:
    """The connection string, or a clear instruction if it is not configured.

    `override` is whatever `--dsn` supplied, so an explicit flag still wins.
    """
    if override:
        return override
    dsn = os.environ.get(ENV_VAR)
    if not dsn:
        raise SystemExit(
            f"{ENV_VAR} is not set. Export it before running this script:\n"
            f"    set {ENV_VAR}=postgresql://quant:<password>@localhost:5432/market"
        )
    return dsn
