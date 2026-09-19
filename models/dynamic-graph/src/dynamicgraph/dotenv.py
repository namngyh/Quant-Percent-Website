"""Minimal ``.env`` reader for locally configured secrets.

``load_config`` already lets ``DYNAMICGRAPH_DATABASE_URL`` override
``data.database_path``, which keeps the connection string out of the tracked
YAML. That only helps if the variable is actually set, and the documented
deployment is Windows Task Scheduler -- which starts a process with none of the
user's interactive environment. The DSN therefore has to come from a file, and
``.env`` is already gitignored.

Deliberately not ``python-dotenv``: an extra runtime dependency for ~30 lines of
parsing is one more thing to install on the machine that runs the scheduled job.

Real environment variables always win over the file, so a one-off override
exported for a manual run is never silently replaced by a stale entry.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILENAME = ".env"


def find_env_file(start: str | Path | None = None) -> Path | None:
    """Locate ``.env`` in ``start`` or any parent directory."""
    origin = Path(start) if start is not None else Path.cwd()
    origin = origin if origin.is_dir() else origin.parent
    for directory in [origin.resolve(), *origin.resolve().parents]:
        candidate = directory / ENV_FILENAME
        if candidate.is_file():
            return candidate
    return None


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines, ignoring blanks, comments and ``export``.

    Everything after the first ``=`` is kept verbatim apart from one layer of
    surrounding quotes: a Postgres password may contain ``#``, spaces or ``=``.
    """
    values: dict[str, str] = {}
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def load_env_file(start: str | Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Load ``.env`` into ``os.environ`` and return what it contained.

    A missing file is the normal case on a machine that exports its variables
    some other way, so it returns an empty mapping rather than raising.
    """
    path = find_env_file(start)
    if path is None:
        return {}
    values = parse_env_file(path)
    for key, value in values.items():
        if override or not os.environ.get(key):
            os.environ[key] = value
    return values
