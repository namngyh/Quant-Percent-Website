"""Resuming a snapshot series instead of rebuilding 3526 of them.

`stage_graphs` already persists each series but never reads it back. Extending a
cached series is what makes a session update cheap, so the contract is: the
extended series must be indistinguishable from a full rebuild.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.graphs.snapshots import SnapshotBuildConfig, build_snapshot_series
from dynamicgraph.online.incremental import extend_snapshot_series

WINDOW = 60


@pytest.fixture(scope="module")
def returns(synthetic_panel):
    prices = synthetic_panel[~synthetic_panel["is_index"]].pivot_table(
        index="date", columns="ticker", values="adjusted_close"
    )
    return np.log(prices / prices.shift(1)).dropna().iloc[-160:]


def _build(**kwargs) -> SnapshotBuildConfig:
    return SnapshotBuildConfig(
        layer="partial_correlation",
        window=WINDOW,
        return_type="residual",
        alpha=0.02,
        bootstrap_iterations=0,
        stride=1,
        seed=42,
        n_jobs=1,
        **kwargs,
    )


def _assert_same(left, right):
    assert len(left) == len(right)
    for a, b in zip(left, right, strict=True):
        assert a.date == b.date
        assert a.nodes == b.nodes
        for name in ("adjacency_raw", "adjacency_inference", "adjacency_display"):
            assert np.array_equal(getattr(a, name), getattr(b, name)), f"{name} @ {a.date}"


def test_extending_a_cached_series_equals_a_full_rebuild(returns):
    build = _build()
    full = build_snapshot_series(returns, build, progress_every=0)
    cached = build_snapshot_series(returns.iloc[:-5], build, progress_every=0)

    extended, built = extend_snapshot_series(returns, build, cached)
    assert built == 5, "only the missing tail dates should be built"
    _assert_same(extended, full)


def test_extending_an_up_to_date_series_builds_nothing(returns):
    build = _build()
    cached = build_snapshot_series(returns, build, progress_every=0)
    extended, built = extend_snapshot_series(returns, build, cached)
    assert built == 0
    _assert_same(extended, cached)


def test_a_cache_built_with_a_different_alpha_is_discarded(returns):
    cached = build_snapshot_series(returns.iloc[:-5], _build(), progress_every=0)
    other = _build()
    other.alpha = 0.2
    extended, built = extend_snapshot_series(returns, other, cached)
    assert built == len(extended), "a mismatched cache must trigger a full rebuild"
    _assert_same(extended, build_snapshot_series(returns, other, progress_every=0))


def test_a_cache_whose_tail_no_longer_reproduces_is_discarded(returns):
    """History rewritten upstream must not be stitched onto new sessions."""
    build = _build()
    cached = build_snapshot_series(returns.iloc[:-5], build, progress_every=0)
    cached.snapshots[-1].adjacency_raw = cached.snapshots[-1].adjacency_raw + 1.0

    extended, built = extend_snapshot_series(returns, build, cached, verify_tail=True)
    assert built == len(extended)
    _assert_same(extended, build_snapshot_series(returns, build, progress_every=0))


def test_no_cache_at_all_is_a_plain_full_build(returns):
    build = _build()
    extended, built = extend_snapshot_series(returns, build, None)
    assert built == len(extended)
    _assert_same(extended, build_snapshot_series(returns, build, progress_every=0))


def test_a_cache_ahead_of_the_returns_is_trimmed_not_rebuilt(returns):
    """A shorter panel drops future snapshots but does not invalidate earlier ones.

    Every snapshot depends only on the trailing window ending at its own date,
    so removing sessions from the end cannot change any of them. What must not
    survive is a snapshot dated after the data now ends.
    """
    build = _build()
    cached = build_snapshot_series(returns, build, progress_every=0)
    shorter = returns.iloc[:-10]

    extended, built = extend_snapshot_series(shorter, build, cached)
    assert built == 0
    assert extended.dates.max() == pd.Timestamp(shorter.index[-1])
    _assert_same(extended, build_snapshot_series(shorter, build, progress_every=0))
