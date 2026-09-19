"""Extend a snapshot series instead of rebuilding it.

`stage_graphs` persists every series to `artifacts/graphs/` but has never read
them back, so each run rebuilds the whole history - 3526 core snapshots on the
current data, at roughly a second each because of the bootstrap edge stability.
A session update only needs the dates at the tail.

The cache is only trusted when it was produced by an identical build
configuration and its last snapshot still reproduces exactly; anything else is
a full rebuild. Reusing a stale cache would publish a graph that no rerun could
reproduce, which is worse than being slow.
"""

from __future__ import annotations

from dataclasses import fields

import pandas as pd

from dynamicgraph.graphs.base import GraphSnapshot, SnapshotSeries
from dynamicgraph.graphs.snapshots import (
    SnapshotBuildConfig,
    build_snapshot,
    build_snapshot_series,
)
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

# Fields that change the numbers in a snapshot. `n_jobs` and `stride` do not
# (stride only selects which dates are built, and is handled separately).
_IDENTITY_FIELDS = tuple(
    name
    for name in (field.name for field in fields(SnapshotBuildConfig))
    if name not in {"n_jobs", "stride"}
)


def _identity(build: SnapshotBuildConfig) -> tuple:
    return tuple(getattr(build, name) for name in _IDENTITY_FIELDS)


def _cache_identity(series: SnapshotSeries) -> tuple | None:
    """Recover the build identity a cached series was produced with."""
    snapshot = series.latest()
    if snapshot is None:
        return None
    metadata = snapshot.metadata or {}
    probe = SnapshotBuildConfig(
        layer=series.layer, window=series.window, return_type=series.return_type
    )
    for name, value in (
        ("alpha", snapshot.alpha),
        ("covariance_estimator", metadata.get("covariance_estimator")),
        ("edge_filter_method", metadata.get("edge_filter_method")),
        ("max_missing_ratio", metadata.get("max_missing_ratio")),
    ):
        if value is not None:
            setattr(probe, name, value)
    return _identity(probe)


def wanted_dates(returns: pd.DataFrame, build: SnapshotBuildConfig) -> pd.DatetimeIndex:
    index = returns.sort_index().index
    positions = range(build.window - 1, len(index), max(1, build.stride))
    return pd.DatetimeIndex([index[p] for p in positions])


def extend_snapshot_series(
    returns: pd.DataFrame,
    build: SnapshotBuildConfig,
    cached: SnapshotSeries | None,
    verify_tail: bool = True,
) -> tuple[SnapshotSeries, int]:
    """Return `(series, n_snapshots_built)` for `returns` under `build`.

    Snapshots present in `cached` are reused; only the dates after the cache's
    last snapshot are built. `verify_tail` rebuilds the cache's own last
    snapshot and compares it, which catches an upstream history rewrite before
    it gets stitched onto new sessions.
    """
    returns = returns.sort_index()
    targets = wanted_dates(returns, build)

    reusable: list[GraphSnapshot] = []
    if cached is not None and len(cached):
        reason = None
        if (cached.layer, cached.window, cached.return_type) != (
            build.layer,
            build.window,
            build.return_type,
        ):
            reason = "khác layer/window/return_type"
        elif _cache_identity(cached) != _identity(build):
            reason = "khác tham số build (alpha/estimator/filter)"
        else:
            wanted = set(targets)
            kept = [s for s in cached.snapshots if pd.Timestamp(s.date) in wanted]
            if not kept:
                reason = "không có ngày nào của cache còn nằm trong chuỗi cần dựng"
            elif pd.Timestamp(kept[-1].date) > pd.Timestamp(targets[-1]):
                reason = "cache đi trước dữ liệu hiện tại"
            elif verify_tail and not _tail_reproduces(returns, build, kept[-1]):
                reason = "snapshot cuối của cache không tái tạo được từ dữ liệu hiện tại"
            else:
                reusable = kept
        if reason:
            logger.info("Bỏ cache snapshot (%s); dựng lại toàn bộ %s.", reason, cached.key)

    if not reusable:
        series = build_snapshot_series(returns, build, progress_every=0)
        return series, len(series)

    last = pd.Timestamp(reusable[-1].date)
    missing = [date for date in targets if date > last]
    if not missing:
        return (
            SnapshotSeries(
                snapshots=list(reusable),
                layer=build.layer,
                window=build.window,
                return_type=build.return_type,
            ),
            0,
        )
    logger.info(
        "Nối tiếp %s: dùng lại %d snapshot, dựng thêm %d.",
        f"{build.layer}__{build.return_type}__w{build.window}",
        len(reusable),
        len(missing),
    )
    fresh = build_snapshot_series(returns, build, dates=missing, progress_every=0)
    return (
        SnapshotSeries(
            snapshots=[*reusable, *fresh.snapshots],
            layer=build.layer,
            window=build.window,
            return_type=build.return_type,
        ),
        len(fresh),
    )


def _tail_reproduces(
    returns: pd.DataFrame, build: SnapshotBuildConfig, snapshot: GraphSnapshot
) -> bool:
    date = pd.Timestamp(snapshot.date)
    if date not in returns.index:
        return False
    position = returns.index.get_loc(date)
    if position + 1 < build.window:
        return False
    window_returns = returns.iloc[position - build.window + 1 : position + 1]
    rebuilt = build_snapshot(window_returns, date, build)
    if rebuilt is None or rebuilt.nodes != snapshot.nodes:
        return False
    import numpy as np

    return bool(np.array_equal(rebuilt.adjacency_raw, snapshot.adjacency_raw))
