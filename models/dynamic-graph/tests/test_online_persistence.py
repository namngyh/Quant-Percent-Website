"""Handoff from the batch tier and on-disk persistence of the online state."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.graphs.snapshots import SnapshotBuildConfig
from dynamicgraph.online.handoff import BatchHandoff, load_batch_handoff, save_batch_handoff
from dynamicgraph.online.persistence import (
    load_online_state,
    online_state_paths,
    save_online_state,
)
from dynamicgraph.online.state import SCHEMA_VERSION, OnlineStateError, build_online_state

CORE_KEY = "partial_correlation__residual__w60"
HELD_OUT = 4


@pytest.fixture(scope="module")
def panel(synthetic_panel):
    prices = synthetic_panel[~synthetic_panel["is_index"]].pivot_table(
        index="date", columns="ticker", values="adjusted_close"
    )
    index_price = synthetic_panel[synthetic_panel["is_index"]].set_index("date")["adjusted_close"]
    raw = np.log(prices / prices.shift(1)).dropna().iloc[-200:]
    return raw, np.log(index_price / index_price.shift(1)).reindex(raw.index)


def _build() -> SnapshotBuildConfig:
    return SnapshotBuildConfig(
        layer="partial_correlation",
        window=60,
        return_type="residual",
        alpha=0.037,
        bootstrap_iterations=0,
        seed=42,
        n_jobs=1,
    )


@pytest.fixture
def state(panel):
    from tests.conftest import SECTORS

    returns, market = panel
    return build_online_state(
        returns=returns,
        market_returns=market,
        build_configs={CORE_KEY: _build()},
        core_key=CORE_KEY,
        residual_window=60,
        source_run_metadata={"data_hash": "test", "last_data_date": str(returns.index[-1].date())},
        sector_of=SECTORS,
        seed=42,
    )


def _handoff() -> BatchHandoff:
    return BatchHandoff(
        core_key=CORE_KEY,
        build_configs={CORE_KEY: _build()},
        residual_window=60,
        sector_of={"BNK1": "Banks"},
        seed=42,
        metric_history=pd.DataFrame({"graph_density": [0.2]}, index=pd.DatetimeIndex(["2024-01-02"])),
        stress_model=None,
        run_metadata={"data_hash": "test", "last_data_date": "2024-01-02"},
    )


def test_handoff_round_trips_with_the_frozen_alpha(tmp_path):
    save_batch_handoff(tmp_path, _handoff())
    restored = load_batch_handoff(tmp_path)
    assert restored.core_key == CORE_KEY
    assert restored.build_configs[CORE_KEY].alpha == pytest.approx(0.037)
    assert restored.residual_window == 60
    assert restored.run_metadata["last_data_date"] == "2024-01-02"


def test_loading_a_handoff_before_any_batch_run_is_refused(tmp_path):
    with pytest.raises(OnlineStateError, match="run-all"):
        load_batch_handoff(tmp_path)


def test_loading_a_handoff_from_another_schema_version_is_refused(tmp_path):
    handoff = _handoff()
    handoff.schema_version = SCHEMA_VERSION + 1
    save_batch_handoff(tmp_path, handoff)
    with pytest.raises(OnlineStateError, match="schema"):
        load_batch_handoff(tmp_path)


def test_state_round_trips_through_disk(tmp_path, state):
    save_online_state(tmp_path, state)
    restored = load_online_state(tmp_path)
    assert restored.as_of_date == state.as_of_date
    assert restored.core_key == state.core_key
    assert list(restored.returns.columns) == list(state.returns.columns)
    assert len(restored.returns) == len(state.returns)
    assert restored.build_configs[CORE_KEY].alpha == pytest.approx(0.037)
    assert set(restored.snapshots) == set(state.snapshots)


def test_manifest_pins_the_state_to_its_buffer_and_batch_run(tmp_path, state):
    save_online_state(tmp_path, state)
    manifest = json.loads(online_state_paths(tmp_path)["manifest"].read_text(encoding="utf-8"))
    assert manifest["as_of_date"] == state.as_of_date
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["buffer_sha256"] == state.buffer_checksum()
    assert manifest["frozen_alpha"][CORE_KEY] == pytest.approx(0.037)
    assert manifest["source_run_metadata"]["data_hash"] == "test"


def test_loading_a_state_with_a_tampered_buffer_is_refused(tmp_path, state):
    import joblib

    save_online_state(tmp_path, state)
    state.returns.iloc[0, 0] = 99.0
    joblib.dump(state, online_state_paths(tmp_path)["state"])
    with pytest.raises(OnlineStateError, match="checksum"):
        load_online_state(tmp_path)


def test_loading_a_state_before_initialisation_is_refused(tmp_path):
    with pytest.raises(OnlineStateError, match="init-online-state"):
        load_online_state(tmp_path)
