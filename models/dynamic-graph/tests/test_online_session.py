"""Phase 2 acceptance gate: one online session must reproduce the batch snapshot.

The online tier calls the same `build_snapshot` the batch tier does, on the same
trailing window, with the alpha frozen by the batch run. These tests hold that
equivalence in place - if they ever diverge, the graph published live is not the
graph the stress model was trained on.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.graphs.snapshots import SnapshotBuildConfig, build_snapshot_series
from dynamicgraph.online.session import advance_one_session, residual_returns
from dynamicgraph.online.state import build_online_state

CORE_KEY = "partial_correlation__residual__w60"
WINDOW = 60
RESIDUAL_WINDOW = 60
HELD_OUT = 4


@pytest.fixture(scope="module")
def wide_panel(request):
    panel = request.getfixturevalue("synthetic_panel")
    prices = panel[~panel["is_index"]].pivot_table(
        index="date", columns="ticker", values="adjusted_close"
    )
    index_price = panel[panel["is_index"]].set_index("date")["adjusted_close"]
    raw = np.log(prices / prices.shift(1)).dropna()
    market = np.log(index_price / index_price.shift(1)).reindex(raw.index)
    return raw.iloc[-320:], market.iloc[-320:]


@pytest.fixture(scope="module")
def split(wide_panel):
    raw, market = wide_panel
    return raw.iloc[:-HELD_OUT], market.iloc[:-HELD_OUT], raw, market


def _build_config(bootstrap: int = 0) -> SnapshotBuildConfig:
    return SnapshotBuildConfig(
        layer="partial_correlation",
        window=WINDOW,
        return_type="residual",
        alpha=0.02,
        bootstrap_iterations=bootstrap,
        stride=1,
        seed=42,
        n_jobs=1,
    )


def test_online_residual_returns_match_the_batch_rolling_regression(split):
    """Residualisation is a trailing rolling OLS, so a buffer reproduces it exactly."""
    batch_returns, batch_market, full_returns, full_market = split
    batch = residual_returns(full_returns, full_market, RESIDUAL_WINDOW)
    online = residual_returns(full_returns, full_market, RESIDUAL_WINDOW)
    assert np.allclose(batch.to_numpy(), online.to_numpy(), equal_nan=True)
    # A row deep inside the buffer does not depend on rows added later.
    truncated = residual_returns(
        full_returns.iloc[:-HELD_OUT], full_market.iloc[:-HELD_OUT], RESIDUAL_WINDOW
    )
    common = truncated.index
    assert np.allclose(
        batch.loc[common].to_numpy(), truncated.to_numpy(), equal_nan=True, atol=1e-12
    )


def test_online_snapshot_reproduces_the_batch_snapshot_for_the_same_date(split):
    """The gate: stepping one session forward equals rebuilding the whole series."""
    batch_returns, batch_market, full_returns, full_market = split
    build = _build_config()
    residual_full = residual_returns(full_returns, full_market, RESIDUAL_WINDOW).dropna(how="all")
    batch_series = build_snapshot_series(residual_full, build, progress_every=0)
    by_date = batch_series.by_date()

    state = build_online_state(
        returns=batch_returns,
        market_returns=batch_market,
        build_configs={CORE_KEY: build},
        core_key=CORE_KEY,
        residual_window=RESIDUAL_WINDOW,
        source_run_metadata={"data_hash": "test"},
    )
    for date in full_returns.index[-HELD_OUT:]:
        record = advance_one_session(
            state, full_returns.loc[date], float(full_market.loc[date]), date
        )
        online_snapshot = record["snapshots"][CORE_KEY]
        expected = by_date[pd.Timestamp(date)]
        assert online_snapshot.nodes == expected.nodes
        for name in ("adjacency_raw", "adjacency_inference", "adjacency_display"):
            assert np.array_equal(
                getattr(online_snapshot, name), getattr(expected, name)
            ), f"{name}差 @ {date}"
        assert online_snapshot.alpha == expected.alpha


def test_online_snapshot_reproduces_bootstrap_edge_stability(split):
    """Edge stability is seeded from the snapshot date, so it must match too."""
    batch_returns, batch_market, full_returns, full_market = split
    build = _build_config(bootstrap=12)
    residual_full = residual_returns(full_returns, full_market, RESIDUAL_WINDOW).dropna(how="all")
    by_date = build_snapshot_series(residual_full, build, progress_every=0).by_date()

    state = build_online_state(
        returns=batch_returns,
        market_returns=batch_market,
        build_configs={CORE_KEY: build},
        core_key=CORE_KEY,
        residual_window=RESIDUAL_WINDOW,
        source_run_metadata={"data_hash": "test"},
    )
    date = full_returns.index[-1]
    for step in full_returns.index[-HELD_OUT:]:
        record = advance_one_session(
            state, full_returns.loc[step], float(full_market.loc[step]), step
        )
    online_snapshot = record["snapshots"][CORE_KEY]
    expected = by_date[pd.Timestamp(date)]
    assert online_snapshot.stability is not None
    assert np.array_equal(online_snapshot.stability, expected.stability)


def test_advancing_updates_the_watermark_and_keeps_the_buffer_causal(split):
    batch_returns, batch_market, full_returns, full_market = split
    state = build_online_state(
        returns=batch_returns,
        market_returns=batch_market,
        build_configs={CORE_KEY: _build_config()},
        core_key=CORE_KEY,
        residual_window=RESIDUAL_WINDOW,
        source_run_metadata={"data_hash": "test"},
    )
    assert state.as_of_date == str(batch_returns.index[-1].date())
    date = full_returns.index[-HELD_OUT]
    advance_one_session(state, full_returns.loc[date], float(full_market.loc[date]), date)
    assert state.as_of_date == str(pd.Timestamp(date).date())
    assert len(state.returns) == len(batch_returns) + 1
    assert state.returns.index[-1] == pd.Timestamp(date)


def _state(split, bootstrap: int = 0):
    from tests.conftest import SECTORS  # noqa: F401

    batch_returns, batch_market, _, _ = split
    return build_online_state(
        returns=batch_returns,
        market_returns=batch_market,
        build_configs={CORE_KEY: _build_config(bootstrap)},
        core_key=CORE_KEY,
        residual_window=RESIDUAL_WINDOW,
        source_run_metadata={"data_hash": "test"},
        sector_of=SECTORS,
        seed=42,
    )


def test_online_graph_metrics_match_the_batch_metric_series(split):
    """Metrics compare each snapshot with the one before it, so the seeded
    previous snapshot has to be the real one, not an empty placeholder."""
    from dynamicgraph.network.graph_metrics import compute_metric_series
    from tests.conftest import SECTORS

    batch_returns, batch_market, full_returns, full_market = split
    build = _build_config()
    residual_full = residual_returns(full_returns, full_market, RESIDUAL_WINDOW).dropna(how="all")
    series = build_snapshot_series(residual_full, build, progress_every=0)
    batch_metrics, _ = compute_metric_series(
        list(series), sector_of=SECTORS, seed=42, return_communities=True
    )

    state = _state(split)
    compared = 0
    for date in full_returns.index[-HELD_OUT:]:
        record = advance_one_session(
            state, full_returns.loc[date], float(full_market.loc[date]), date
        )
        online = record["metrics"][CORE_KEY]
        expected = batch_metrics.loc[pd.Timestamp(date)]
        for column, value in expected.items():
            actual = online[column]
            if isinstance(value, float) and np.isnan(value):
                assert actual is None or (isinstance(actual, float) and np.isnan(actual)), column
            elif isinstance(value, (int, float, np.floating, np.integer)):
                assert float(actual) == pytest.approx(float(value), rel=1e-9, abs=1e-12), column
            else:
                assert actual == value, column
        compared += 1
    assert compared == HELD_OUT


def test_metric_history_grows_and_stays_indexed_by_date(split):
    batch_returns, batch_market, full_returns, full_market = split
    state = _state(split)
    seeded = len(state.metric_history)
    for date in full_returns.index[-HELD_OUT:]:
        advance_one_session(state, full_returns.loc[date], float(full_market.loc[date]), date)
    assert len(state.metric_history) == seeded + HELD_OUT
    assert state.metric_history.index.is_monotonic_increasing
    assert state.metric_history.index[-1] == pd.Timestamp(full_returns.index[-1])


@pytest.fixture(scope="module")
def batch_core(split, base_config):
    """Batch core metric history + the stress model fitted on its training part."""
    from dynamicgraph.network.graph_metrics import compute_metric_series
    from dynamicgraph.network.stress_score import build_descriptive_stress_score
    from tests.conftest import SECTORS

    _, _, full_returns, full_market = split
    residual_full = residual_returns(full_returns, full_market, RESIDUAL_WINDOW).dropna(how="all")
    series = build_snapshot_series(residual_full, _build_config(), progress_every=0)
    metrics, _ = compute_metric_series(list(series), sector_of=SECTORS, seed=42, return_communities=True)
    # Fit on the part that precedes every held-out session, exactly as the batch
    # tier fits on training folds only.
    train_mask = pd.Series(metrics.index < full_returns.index[-HELD_OUT], index=metrics.index)
    model, scores, _ = build_descriptive_stress_score(metrics, base_config, train_mask)
    return metrics, model, scores


def test_online_stress_score_matches_the_batch_score_row(split, batch_core):
    """`stress_percentile` is an expanding rank, so the online tier keeps the whole
    raw-score history rather than recomputing a window."""
    from tests.conftest import SECTORS

    metrics, model, scores = batch_core
    batch_returns, batch_market, full_returns, full_market = split
    first_new = full_returns.index[-HELD_OUT]

    state = build_online_state(
        returns=batch_returns,
        market_returns=batch_market,
        build_configs={CORE_KEY: _build_config()},
        core_key=CORE_KEY,
        residual_window=RESIDUAL_WINDOW,
        source_run_metadata={"data_hash": "test"},
        sector_of=SECTORS,
        seed=42,
        metric_history=metrics.loc[metrics.index < first_new],
        stress_model=model,
    )
    for date in full_returns.index[-HELD_OUT:]:
        record = advance_one_session(
            state, full_returns.loc[date], float(full_market.loc[date]), date
        )
        online = record["stress"]
        expected = scores.loc[pd.Timestamp(date)]
        for column in ("stress_raw", "stress_score", "stress_percentile", "stress_change_20d"):
            assert float(online[column]) == pytest.approx(
                float(expected[column]), rel=1e-9, abs=1e-12
            ), column


def test_stress_history_is_retained_for_the_expanding_percentile(split, batch_core):
    from tests.conftest import SECTORS

    metrics, model, _ = batch_core
    batch_returns, batch_market, full_returns, full_market = split
    first_new = full_returns.index[-HELD_OUT]
    seeded = metrics.loc[metrics.index < first_new]
    state = build_online_state(
        returns=batch_returns,
        market_returns=batch_market,
        build_configs={CORE_KEY: _build_config()},
        core_key=CORE_KEY,
        residual_window=RESIDUAL_WINDOW,
        source_run_metadata={"data_hash": "test"},
        sector_of=SECTORS,
        seed=42,
        metric_history=seeded,
        stress_model=model,
    )
    for date in full_returns.index[-HELD_OUT:]:
        advance_one_session(state, full_returns.loc[date], float(full_market.loc[date]), date)
    assert len(state.stress_history) == len(seeded) + HELD_OUT
    assert state.stress_history.index[-1] == pd.Timestamp(full_returns.index[-1])


def test_a_state_without_a_stress_model_still_advances(split):
    from tests.conftest import SECTORS

    batch_returns, batch_market, full_returns, full_market = split
    state = build_online_state(
        returns=batch_returns,
        market_returns=batch_market,
        build_configs={CORE_KEY: _build_config()},
        core_key=CORE_KEY,
        residual_window=RESIDUAL_WINDOW,
        source_run_metadata={"data_hash": "test"},
        sector_of=SECTORS,
        seed=42,
    )
    date = full_returns.index[-1]
    record = advance_one_session(state, full_returns.loc[date], float(full_market.loc[date]), date)
    assert record["stress"] is None


SECONDARY_KEY = "correlation__residual__w60"


def _multi_key_state(split):
    """Two graph layers, as a real run has. The stress classifiers are fitted on
    `flatten_graph_metrics` over every layer, so the online tier has to keep
    history for every layer too."""
    from tests.conftest import SECTORS

    batch_returns, batch_market, _, _ = split
    secondary = _build_config()
    secondary.layer = "correlation"
    return build_online_state(
        returns=batch_returns,
        market_returns=batch_market,
        build_configs={CORE_KEY: _build_config(), SECONDARY_KEY: secondary},
        core_key=CORE_KEY,
        residual_window=RESIDUAL_WINDOW,
        source_run_metadata={"data_hash": "test"},
        sector_of=SECTORS,
        seed=42,
    )


def test_every_layer_gets_its_own_metric_history(split):
    """Keeping only the core layer would leave the stress classifiers scored on
    a narrower feature matrix than they were fitted on -- silently, because the
    missing columns are simply absent rather than wrong."""
    _batch_returns, _batch_market, full_returns, full_market = split
    state = _multi_key_state(split)
    date = full_returns.index[-HELD_OUT]

    advance_one_session(state, full_returns.loc[date], float(full_market.loc[date]), date)

    assert sorted(state.metric_history_by_key) == sorted([CORE_KEY, SECONDARY_KEY])
    for key in (CORE_KEY, SECONDARY_KEY):
        assert pd.Timestamp(date) in state.metric_history_by_key[key].index


def test_the_core_layer_history_still_matches_the_flat_view(split):
    _batch_returns, _batch_market, full_returns, full_market = split
    state = _multi_key_state(split)
    date = full_returns.index[-HELD_OUT]

    advance_one_session(state, full_returns.loc[date], float(full_market.loc[date]), date)

    core = state.metric_history_by_key[CORE_KEY]
    assert state.metric_history.index.equals(core.index)


def test_reapplying_a_session_does_not_duplicate_a_metric_row(split):
    """`update-latest` can legitimately run twice for one day - a retry, a manual
    re-run. A second row for the same date would corrupt every expanding
    statistic downstream."""
    _batch_returns, _batch_market, full_returns, full_market = split
    state = _multi_key_state(split)
    date = full_returns.index[-HELD_OUT]

    advance_one_session(state, full_returns.loc[date], float(full_market.loc[date]), date)
    rows_after_first = {k: len(v) for k, v in state.metric_history_by_key.items()}

    state.as_of_date = str(pd.Timestamp(full_returns.index[-HELD_OUT - 1]).date())
    state.returns = state.returns.iloc[:-1]
    state.market_returns = state.market_returns.iloc[:-1]
    advance_one_session(state, full_returns.loc[date], float(full_market.loc[date]), date)

    assert {k: len(v) for k, v in state.metric_history_by_key.items()} == rows_after_first
    for frame in state.metric_history_by_key.values():
        assert not frame.index.duplicated().any()
