"""End-to-end behaviour of `init-online-state` and `update-latest`.

The panel is injected so these run without a configured database; the data path
itself is the batch tier's own read-only `stage_data`/`stage_features`.
"""

from __future__ import annotations

import types

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.graphs.snapshots import SnapshotBuildConfig
from dynamicgraph.online.handoff import BatchHandoff, save_batch_handoff
from dynamicgraph.online.persistence import online_state_paths
from dynamicgraph.online.runner import initialize_online_state, update_latest_online
from dynamicgraph.online.session import AbnormalSessionError
from dynamicgraph.online.state import OnlineStateError

CORE_KEY = "partial_correlation__residual__w60"
HELD_OUT = 3


@pytest.fixture(scope="module")
def panel(synthetic_panel):
    prices = synthetic_panel[~synthetic_panel["is_index"]].pivot_table(
        index="date", columns="ticker", values="adjusted_close"
    )
    index_price = synthetic_panel[synthetic_panel["is_index"]].set_index("date")["adjusted_close"]
    raw = np.log(prices / prices.shift(1)).dropna().iloc[-180:]
    market = np.log(index_price / index_price.shift(1)).reindex(raw.index)
    return raw, market


@pytest.fixture
def workspace(tmp_path, panel):
    from tests.conftest import SECTORS

    returns, _ = panel
    config = types.SimpleNamespace(artifacts_dir=tmp_path)
    save_batch_handoff(
        tmp_path,
        BatchHandoff(
            core_key=CORE_KEY,
            build_configs={
                CORE_KEY: SnapshotBuildConfig(
                    layer="partial_correlation",
                    window=60,
                    return_type="residual",
                    alpha=0.02,
                    bootstrap_iterations=0,
                    seed=42,
                    n_jobs=1,
                )
            },
            residual_window=60,
            sector_of=dict(SECTORS),
            seed=42,
            metric_history=pd.DataFrame(),
            stress_model=None,
            run_metadata={
                "data_hash": "test",
                "last_data_date": str(returns.index[-HELD_OUT - 1].date()),
            },
        ),
    )
    return config, tmp_path


def _panels(panel, upto: int | None = None):
    returns, market = panel
    if upto is None:
        return returns, market, {}
    return returns.iloc[:upto], market.iloc[:upto], {}


def test_init_seeds_the_state_at_the_batch_watermark(workspace, panel):
    config, root = workspace
    returns, _ = panel
    result = initialize_online_state(config, panel=_panels(panel))
    assert result["status"] == "initialized"
    assert result["as_of_date"] == str(returns.index[-HELD_OUT - 1].date())
    assert online_state_paths(root)["state"].exists()
    assert online_state_paths(root)["manifest"].exists()


def test_init_refuses_to_run_before_a_batch_run(tmp_path, panel):
    config = types.SimpleNamespace(artifacts_dir=tmp_path)
    with pytest.raises(OnlineStateError, match="run-all"):
        initialize_online_state(config, panel=_panels(panel))


def test_update_applies_every_unseen_session(workspace, panel):
    config, _ = workspace
    returns, _ = panel
    initialize_online_state(config, panel=_panels(panel))
    result = update_latest_online(config, panel=_panels(panel))
    assert result["status"] == "updated"
    assert result["sessions_applied"] == HELD_OUT
    assert result["as_of_date"] == str(returns.index[-1].date())
    assert result["number_of_nodes"] > 0
    assert 0.0 <= result["graph_density"] <= 1.0


def test_update_is_idempotent_when_nothing_is_new(workspace, panel):
    config, root = workspace
    initialize_online_state(config, panel=_panels(panel))
    update_latest_online(config, panel=_panels(panel))
    manifest = online_state_paths(root)["manifest"]
    stamp, payload = manifest.stat().st_mtime_ns, manifest.read_bytes()
    second = update_latest_online(config, panel=_panels(panel))
    assert second["status"] == "no_new_sessions"
    assert manifest.stat().st_mtime_ns == stamp
    assert manifest.read_bytes() == payload


def test_update_refuses_a_source_whose_history_was_rewritten(workspace, panel):
    config, _ = workspace
    initialize_online_state(config, panel=_panels(panel))
    returns, market = panel
    rewritten = returns.copy()
    rewritten.iloc[10, 0] = float(rewritten.iloc[10, 0]) + 0.5
    with pytest.raises(AbnormalSessionError, match="bị sửa"):
        update_latest_online(config, panel=(rewritten, market, {}))


def test_update_replays_sessions_one_at_a_time(workspace, panel):
    config, root = workspace
    initialize_online_state(config, panel=_panels(panel))
    update_latest_online(config, panel=_panels(panel))
    sessions = pd.read_csv(online_state_paths(root)["sessions"])
    assert len(sessions) == HELD_OUT
    assert sessions["as_of_date"].is_monotonic_increasing
