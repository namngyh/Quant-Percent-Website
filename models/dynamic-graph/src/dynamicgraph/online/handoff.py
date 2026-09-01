"""What the batch tier hands to the online tier.

`run-all` ends by writing this bundle. It carries only things the online tier
must reuse *unchanged*: the graphical-lasso penalty and build parameters chosen
on training windows, the metric history the expanding stress statistics extend,
and the stress model fitted on training folds. Nothing here is re-estimated
between batch runs; every `run-all` replaces the bundle and resets the online
state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from dynamicgraph.graphs.snapshots import SnapshotBuildConfig
from dynamicgraph.online.state import SCHEMA_VERSION, OnlineStateError

HANDOFF_NAME = "batch_handoff.joblib"
STATE_DIRECTORY = "online_state"


@dataclass
class BatchHandoff:
    core_key: str
    build_configs: dict[str, SnapshotBuildConfig]
    residual_window: int
    sector_of: dict[str, str]
    seed: int
    metric_history: pd.DataFrame
    stress_model: Any | None
    run_metadata: dict[str, Any]
    schema_version: int = SCHEMA_VERSION
    notes: dict[str, Any] = field(default_factory=dict)
    #: Metric history per graph layer, not just the core one. The stress
    #: classifiers are fitted on `flatten_graph_metrics` over *every* key, so an
    #: online tier holding only the core layer would score them on a narrower
    #: matrix than they were fitted on -- silently, since the missing columns
    #: would simply be absent rather than wrong.
    metric_history_by_key: dict[str, pd.DataFrame] = field(default_factory=dict)
    #: Per-horizon stress classifiers frozen at publication time. Written by
    #: `latest._augment_batch_handoff`, which runs after the OOS experiment, so
    #: a handoff produced by `build-graphs` alone has this empty.
    stress_forecast_models: dict[int, Any] = field(default_factory=dict)
    #: Objects the website payload needs that the online tier cannot recompute
    #: cheaply (OOS quality, directed roles, universe metadata, run record).
    publication: dict[str, Any] = field(default_factory=dict)


def handoff_path(root: str | Path) -> Path:
    return Path(root) / STATE_DIRECTORY / HANDOFF_NAME


def save_batch_handoff(root: str | Path, handoff: BatchHandoff) -> Path:
    import joblib

    path = handoff_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(handoff, path, compress=3)
    return path


def load_batch_handoff(root: str | Path) -> BatchHandoff:
    import joblib

    path = handoff_path(root)
    if not path.exists():
        raise OnlineStateError(
            f"Chưa có batch handoff tại {path}; chạy `run-all` trước rồi mới `init-online-state`."
        )
    handoff: BatchHandoff = joblib.load(path)
    if handoff.schema_version != SCHEMA_VERSION:
        raise OnlineStateError(
            f"Batch handoff dùng schema {handoff.schema_version}, code hiện tại là "
            f"{SCHEMA_VERSION}; chạy lại `run-all`."
        )
    return handoff
