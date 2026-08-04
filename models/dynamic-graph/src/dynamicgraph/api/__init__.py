"""Read-only FastAPI service.

The API only ever reads artifacts that the pipeline has already produced. No
endpoint triggers training, graph construction or database access; a web request
can never start a compute job.
"""

from __future__ import annotations

__all__ = ["create_app"]


def create_app(*args, **kwargs):  # pragma: no cover - thin re-export
    from dynamicgraph.api.app import create_app as _create_app

    return _create_app(*args, **kwargs)
