"""Minimal ``.env`` reader.

The online tier is driven by Windows Task Scheduler, which starts a process with
a bare environment: whatever the user exported in an interactive shell is gone.
The database password therefore has to come from a file, and it must be a file
that is already gitignored -- ``.env``.

This is deliberately not ``python-dotenv``: the package would be a new runtime
dependency for ~30 lines of parsing, and every extra dependency is another thing
that has to be installed on the machine that runs the scheduled task.

Precedence is real-environment-wins. A DSN exported for a one-off manual run
must not be silently overridden by a stale file.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILENAME = ".env"


def find_env_file(start: str | Path | None = None) -> Path | None:
    """Locate ``.env`` in ``start`` or any parent directory.

    Searching upward matters because the CLI is run from the repository root but
    the scheduled task may set a different working directory.
    """
    origin = Path(start) if start is not None else Path.cwd()
    origin = origin if origin.is_dir() else origin.parent
    for directory in [origin.resolve(), *origin.resolve().parents]:
        candidate = directory / ENV_FILENAME
        if candidate.is_file():
            return candidate
    return None


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines, ignoring blanks, comments and ``export``.

    Values keep everything after the first ``=`` verbatim apart from one layer of
    surrounding quotes, because a Postgres password may legitimately contain
    ``#``, spaces or ``=``.
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

    Returns an empty mapping when no file exists -- a missing ``.env`` is the
    normal case on a machine that exports its variables some other way.
    """
    path = find_env_file(start)
    if path is None:
        return {}
    values = parse_env_file(path)
    for key, value in values.items():
        if override or not os.environ.get(key):
            os.environ[key] = value
    return values
