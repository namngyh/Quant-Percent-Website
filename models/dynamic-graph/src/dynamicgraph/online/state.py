"""State carried from one online session to the next."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.graphs.base import GraphSnapshot
from dynamicgraph.graphs.snapshots import SnapshotBuildConfig
from dynamicgraph.network.communities import CommunityResult

#: 2 adds `metric_history_by_key` and the frozen stress-forecast models, without
#: which the online tier cannot republish `artifacts/latest/`. A state written
#: under version 1 is refused rather than upgraded: the missing per-layer history
#: cannot be reconstructed from what version 1 stored.
SCHEMA_VERSION = 2


class OnlineStateError(RuntimeError):
    """Raised when a stored online state cannot be trusted as-is."""


@dataclass
class OnlineState:
    """Everything one session needs from the sessions before it.

    The return buffer is kept whole rather than trimmed to the longest graph
    window: residualisation, the graph windows and the metric dynamics each
    need a different amount of history, and a panel of a few thousand rows by
    thirty tickers is small enough that keeping all of it removes a whole class
    of off-by-one truncation bugs.
    """

    schema_version: int
    as_of_date: str
    returns: pd.DataFrame
    market_returns: pd.Series
    residual_window: int
    build_configs: dict[str, SnapshotBuildConfig]
    core_key: str
    source_run_metadata: dict[str, Any]
    sector_of: dict[str, str] = field(default_factory=dict)
    seed: int = 42
    snapshots: dict[str, GraphSnapshot] = field(default_factory=dict)
    communities: dict[str, CommunityResult] = field(default_factory=dict)
    metric_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Frozen by the batch run: robust location/scale and metric weights were
    # estimated on training folds only and must never be re-estimated online.
    stress_model: Any | None = None
    stress_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    session_log: list[dict[str, Any]] = field(default_factory=list)
    #: Metric history for every graph layer. `metric_history` above stays the
    #: core layer's view, because the descriptive stress score is defined on it;
    #: the stress *classifiers* were fitted on all layers flattened together and
    #: need the rest.
    metric_history_by_key: dict[str, pd.DataFrame] = field(default_factory=dict)
    #: Frozen per-horizon stress classifiers, carried from the batch handoff.
    stress_forecast_models: dict[int, Any] = field(default_factory=dict)
    #: Publication-time objects the payload needs and the online tier cannot
    #: cheaply recompute (OOS quality, directed roles, universe, run record).
    publication: dict[str, Any] = field(default_factory=dict)

    def buffer_checksum(self) -> str:
        """SHA-256 over the return buffer, so a hand-edited state cannot load."""
        digest = hashlib.sha256()
        digest.update(",".join(map(str, self.returns.columns)).encode("utf-8"))
        digest.update(pd.DatetimeIndex(self.returns.index).asi8.tobytes())
        digest.update(np.ascontiguousarray(self.returns.to_numpy(dtype=float)).tobytes())
        digest.update(np.ascontiguousarray(self.market_returns.to_numpy(dtype=float)).tobytes())
        return digest.hexdigest()

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "as_of_date": self.as_of_date,
            "buffer_rows": int(len(self.returns)),
            "buffer_start_date": str(pd.Timestamp(self.returns.index[0]).date()),
            "buffer_sha256": self.buffer_checksum(),
            "tickers": list(self.returns.columns),
            "core_key": self.core_key,
            "graph_keys": sorted(self.build_configs),
            "frozen_alpha": {key: build.alpha for key, build in self.build_configs.items()},
            "residual_window": self.residual_window,
            "metric_history_rows": int(len(self.metric_history)),
            "metric_history_keys": sorted(self.metric_history_by_key),
            "has_stress_model": self.stress_model is not None,
            "stress_forecast_horizons": sorted(self.stress_forecast_models),
            "sessions_applied": len(self.session_log),
            "source_run_metadata": self.source_run_metadata,
        }


def build_online_state(
    returns: pd.DataFrame,
    market_returns: pd.Series,
    build_configs: dict[str, SnapshotBuildConfig],
    core_key: str,
    residual_window: int,
    source_run_metadata: dict[str, Any],
    sector_of: dict[str, str] | None = None,
    seed: int = 42,
    metric_history: pd.DataFrame | None = None,
    stress_model: Any | None = None,
    metric_history_by_key: dict[str, pd.DataFrame] | None = None,
    stress_forecast_models: dict[int, Any] | None = None,
    publication: dict[str, Any] | None = None,
) -> OnlineState:
    """Seed the online state from the panel a finished batch run was built on.

    The seed builds the snapshot (and its community partition) for the last date
    in the buffer, because the metric row published for the *next* session is
    computed against the snapshot immediately before it. Starting from an empty
    previous snapshot would silently produce wrong turnover and community-churn
    metrics on the first live session.
    """
    from dynamicgraph.online.session import seed_snapshots

    returns = returns.sort_index()
    market_returns = market_returns.reindex(returns.index)
    if core_key not in build_configs:
        raise OnlineStateError(f"core_key {core_key!r} không có trong build_configs")
    if returns.empty:
        raise OnlineStateError("Return buffer rỗng; không seed được online state")

    state = OnlineState(
        schema_version=SCHEMA_VERSION,
        as_of_date=str(pd.Timestamp(returns.index[-1]).date()),
        returns=returns.copy(),
        market_returns=market_returns.copy(),
        residual_window=int(residual_window),
        build_configs=dict(build_configs),
        core_key=core_key,
        source_run_metadata=dict(source_run_metadata),
        sector_of=dict(sector_of or {}),
        seed=int(seed),
        metric_history=(
            pd.DataFrame() if metric_history is None else metric_history.sort_index().copy()
        ),
        stress_model=stress_model,
        metric_history_by_key={
            key: frame.sort_index().copy() for key, frame in (metric_history_by_key or {}).items()
        },
        stress_forecast_models=dict(stress_forecast_models or {}),
        publication=dict(publication or {}),
    )
    seed_snapshots(state)
    return state
