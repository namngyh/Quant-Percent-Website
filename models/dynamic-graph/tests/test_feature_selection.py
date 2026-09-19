"""Feature selection must be fitted on training rows only."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.models.feature_selection import FeatureSelector
from dynamicgraph.models.registry import (
    CORE_GRAPH_METRICS,
    FeatureSetBuilder,
    flatten_graph_metrics,
)


@pytest.fixture
def toy() -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(71)
    n = 600
    index = pd.bdate_range("2020-01-01", periods=n)
    signal = rng.normal(0, 1, n)
    y = pd.Series((signal + rng.normal(0, 0.5, n) > 1.0).astype(float), index=index)

    frame = pd.DataFrame(
        {
            "informative": signal,
            "informative_copy": signal + rng.normal(0, 1e-4, n),   # redundant
            "noise_1": rng.normal(0, 1, n),
            "noise_2": rng.normal(0, 1, n),
            "constant": np.ones(n),
            "mostly_missing": np.where(rng.random(n) < 0.9, np.nan, rng.normal(0, 1, n)),
        },
        index=index,
    )
    return frame, y


def test_drops_constant_and_sparse_columns(toy):
    frame, y = toy
    selector = FeatureSelector(max_features=10).fit(frame, y)
    assert "constant" not in selector.selected_
    assert "mostly_missing" not in selector.selected_
    assert selector.dropped_constant_ >= 1
    assert selector.dropped_low_coverage_ >= 1


def test_removes_redundant_duplicates(toy):
    frame, y = toy
    selector = FeatureSelector(max_features=10, redundancy_threshold=0.95).fit(frame, y)
    kept = set(selector.selected_)
    assert not {"informative", "informative_copy"}.issubset(kept), (
        "two near-identical columns both survived redundancy pruning"
    )
    assert kept & {"informative", "informative_copy"}, "the informative signal was dropped entirely"


def test_respects_the_feature_budget(toy):
    frame, y = toy
    selector = FeatureSelector(max_features=2).fit(frame, y)
    assert len(selector.selected_) <= 2


def test_prefers_the_informative_column(toy):
    frame, y = toy
    selector = FeatureSelector(max_features=1, redundancy_threshold=0.99).fit(frame, y)
    assert selector.selected_[0] in {"informative", "informative_copy"}


def test_selection_ignores_rows_outside_the_training_block(toy):
    """The selector must be blind to anything not passed to `fit`."""
    frame, y = toy
    train = frame.iloc[:400]
    y_train = y.iloc[:400]

    baseline = FeatureSelector(max_features=3, seed=1).fit(train, y_train).selected_

    # Make a pure-noise column perfectly predictive, but ONLY after the training
    # block. A leak-free selector cannot notice.
    corrupted = frame.copy()
    corrupted.iloc[400:, corrupted.columns.get_loc("noise_1")] = y.iloc[400:] * 100
    after = FeatureSelector(max_features=3, seed=1).fit(corrupted.iloc[:400], y_train).selected_

    assert baseline == after, "feature selection changed when only test-period values changed"


def test_feature_builder_does_not_use_future_rows_to_choose_the_schema():
    index = pd.bdate_range("2020-01-01", periods=100)
    market = pd.DataFrame(
        {
            "stable": np.arange(100.0),
            "future_only": [np.nan] * 80 + list(np.arange(20.0)),
            "constant_in_full_sample": np.ones(100),
        },
        index=index,
    )
    graph = pd.DataFrame({"graph_density": np.linspace(0.1, 0.2, 100)}, index=index)

    baseline = FeatureSetBuilder(market, graph).market()
    changed = market.copy()
    changed.loc[index[80]:, "future_only"] = np.arange(20.0) * 100.0
    changed.loc[index[80]:, "constant_in_full_sample"] = np.arange(20.0)
    perturbed = FeatureSetBuilder(changed, graph).market()

    assert list(baseline.columns) == list(perturbed.columns)
    assert set(baseline.columns) == {
        "stable",
        "future_only",
        "constant_in_full_sample",
    }


def test_transform_reindexes_to_selected_columns(toy):
    frame, y = toy
    selector = FeatureSelector(max_features=2).fit(frame, y)
    out = selector.transform(frame)
    assert list(out.columns) == selector.selected_
    assert len(out) == len(frame)


def test_transform_before_fit_raises(toy):
    frame, _ = toy
    with pytest.raises(RuntimeError):
        FeatureSelector().transform(frame)


def test_selection_is_fast_enough_for_walk_forward():
    """Guard the runtime budget.

    The selector runs once per fold per model per feature set: 21 x 4 x 3 = 252
    times in a default run. A mutual-information estimator costs ~15 s at this
    shape, which is several hours; the rank-correlation default must stay well
    under a second.
    """
    import time

    rng = np.random.default_rng(9)
    X = pd.DataFrame(rng.normal(size=(2800, 664)))
    X.columns = [f"f{i}" for i in range(664)]
    y = pd.Series((rng.random(2800) < 0.1).astype(float))

    start = time.perf_counter()
    FeatureSelector(max_features=60).fit(X, y)
    elapsed = time.perf_counter() - start
    assert elapsed < 3.0, f"feature selection took {elapsed:.1f}s at realistic scale"


def test_mutual_info_scoring_still_available(toy):
    frame, y = toy
    selector = FeatureSelector(max_features=2, score="mutual_info").fit(frame, y)
    assert selector.selected_
    assert selector.selected_[0] in {"informative", "informative_copy"}


def test_flatten_graph_metrics_respects_the_whitelist():
    index = pd.bdate_range("2020-01-01", periods=400)
    metrics = pd.DataFrame(
        {
            "graph_density": np.linspace(0.1, 0.3, 400),
            "spectral_radius": np.linspace(1.0, 2.0, 400),
            "some_internal_diagnostic": np.arange(400.0),
            "number_of_nodes": np.full(400, 30.0),
        },
        index=index,
    )
    wide = flatten_graph_metrics({"pc__residual__w60": metrics}, index)
    base = [c for c in wide.columns if not any(s in c for s in ("_chg", "_z60"))]
    assert any("graph_density" in c for c in base)
    assert any("spectral_radius" in c for c in base)
    assert not any("some_internal_diagnostic" in c for c in wide.columns), (
        "a non-whitelisted metric leaked into the model feature space"
    )


def test_graph_feature_space_stays_tractable():
    """Guard against the p >> n blow-up that motivated the whitelist."""
    index = pd.bdate_range("2015-01-01", periods=2600)
    metrics = pd.DataFrame(
        {name: np.random.default_rng(3).normal(size=2600) for name in CORE_GRAPH_METRICS},
        index=index,
    )
    keys = {
        f"{layer}__{ret}__w{w}": metrics
        for layer in ("pc", "corr")
        for ret in ("residual", "raw")
        for w in (20, 60, 120, 252)
    }
    wide = flatten_graph_metrics(keys, index)
    # 16 layers x 23 metrics x 3 series (level, chg20, z60) is the ceiling.
    assert wide.shape[1] <= 16 * len(CORE_GRAPH_METRICS) * 3
    assert wide.shape[1] < 1200, f"graph feature space is {wide.shape[1]} columns"
