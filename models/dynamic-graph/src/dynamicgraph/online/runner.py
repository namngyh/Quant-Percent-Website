"""CLI entry points for the online tier.

`init-online-state` seeds the state from a finished batch run; `update-latest`
applies every unseen trading session. Neither reselects the graphical-lasso
penalty, refits the stress model, or rebuilds the snapshot history.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from dynamicgraph.logging_config import get_logger
from dynamicgraph.online.handoff import load_batch_handoff
from dynamicgraph.online.persistence import (
    load_online_state,
    save_online_state,
)
from dynamicgraph.online.session import AbnormalSessionError, advance_one_session
from dynamicgraph.online.state import OnlineState, build_online_state

logger = get_logger(__name__)

Panel = tuple[pd.DataFrame, pd.Series, dict[str, str]]


@dataclass
class PanelContext:
    """Everything the data/feature stages produce that the online tier needs.

    Republishing the website payload needs more than returns: the stress
    classifiers are scored on `market_features`, and the node table needs
    `node_features`. Loading them here rather than in a second place keeps the
    online tier reading exactly the panel the batch tier reads, read-only
    guarantees included.
    """

    returns: pd.DataFrame
    market_returns: pd.Series
    sector_of: dict[str, str]
    market_features: pd.DataFrame | None = None
    node_features: Any = None
    panel_last_date: pd.Timestamp | None = None
    warnings: list[str] = field(default_factory=list)

    def as_panel(self) -> Panel:
        return self.returns, self.market_returns, self.sector_of


def load_panel_context(config: Any, force: bool = False) -> PanelContext:
    """Run the read-only data and feature stages and keep everything they made."""
    from dynamicgraph import pipeline as P

    state = P.PipelineState(config=config)
    state = P.stage_data(state, force=force)
    state = P.stage_features(state, force=force)
    features = state.node_features
    if features.returns_raw is None or features.market_returns is None:
        raise AbnormalSessionError(
            "Panel không có returns hoặc market returns; tầng online cần cả hai."
        )
    return PanelContext(
        returns=features.returns_raw,
        market_returns=features.market_returns,
        sector_of=dict(features.sector_of),
        market_features=state.market_features,
        node_features=features,
        panel_last_date=pd.Timestamp(state.bundle.panel["date"].max()),
        warnings=list(state.bundle.warnings),
    )


def load_panel_returns(config: Any, force: bool = False) -> Panel:
    """Raw returns, market returns and sectors, via the read-only data stages."""
    return load_panel_context(config, force=force).as_panel()


def initialize_online_state(config: Any, panel: Panel | None = None) -> dict[str, Any]:
    """Seed the online state from the most recent batch run.

    The panel is loaded with `force=True`, the same way `update_latest_online`
    loads it. That is not an optimisation choice: the cached feature artifacts
    and a fresh recompute are *not* byte-identical -- on the VN30 panel they
    disagree on 6 cells, where a cached NaN comes back as 0.0 at three 2020
    exchange-transfer dates. Seeding from the cache and updating from a
    recompute therefore trips `_assert_history_unchanged` on the very first
    session, and the documented `run-all` -> `init-online-state` ->
    `update-latest` sequence could never complete.
    """
    started = time.perf_counter()
    root = Path(config.artifacts_dir)
    handoff = load_batch_handoff(root)
    returns, market, sector_of = (
        panel if panel is not None else load_panel_returns(config, force=True)
    )

    last_batch = pd.Timestamp(handoff.run_metadata.get("last_data_date", returns.index[-1]))
    returns = returns.loc[returns.index <= last_batch]
    market = market.reindex(returns.index)

    state = build_online_state(
        returns=returns,
        market_returns=market,
        build_configs=handoff.build_configs,
        core_key=handoff.core_key,
        residual_window=handoff.residual_window,
        source_run_metadata=handoff.run_metadata,
        sector_of=handoff.sector_of or sector_of,
        seed=handoff.seed,
        metric_history=handoff.metric_history,
        stress_model=handoff.stress_model,
        metric_history_by_key=handoff.metric_history_by_key,
        stress_forecast_models=handoff.stress_forecast_models,
        publication=handoff.publication,
    )
    paths = save_online_state(root, state)
    logger.info("Online state seeded at %s (%d sessions).", state.as_of_date, len(returns))
    return {
        "status": "initialized",
        "as_of_date": state.as_of_date,
        "buffer_rows": int(len(returns)),
        "graph_keys": sorted(state.build_configs),
        "metric_history_rows": int(len(state.metric_history)),
        "state_path": str(paths["state"]),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def _assert_history_unchanged(state: OnlineState, returns: pd.DataFrame) -> None:
    overlap = returns.loc[returns.index <= pd.Timestamp(state.as_of_date)]
    rows = min(len(overlap), len(state.returns))
    if rows == 0:
        raise AbnormalSessionError("Nguồn dữ liệu không chứa phiên nào trùng với buffer hiện tại")
    left = overlap.tail(rows)
    right = state.returns.tail(rows)
    if not left.index.equals(right.index):
        raise AbnormalSessionError(
            "Lịch giao dịch trong nguồn đã khác buffer của online state; dừng để rà soát"
        )
    common = [c for c in right.columns if c in left.columns]
    if not left[common].round(10).equals(right[common].round(10)):
        raise AbnormalSessionError(
            "Return lịch sử trong nguồn đã bị sửa so với buffer; cần chạy lại "
            "`run-all` + `init-online-state` thay vì cập nhật tiếp"
        )


def update_latest_online(config: Any, panel: Panel | None = None) -> dict[str, Any]:
    """Apply every unseen trading session to the stored online state."""
    started = time.perf_counter()
    root = Path(config.artifacts_dir)
    state = load_online_state(root)
    context = None
    if panel is not None:
        returns, market, _ = panel
    else:
        context = load_panel_context(config, force=True)
        returns, market, _ = context.as_panel()

    fresh = returns.loc[returns.index > pd.Timestamp(state.as_of_date)]
    if fresh.empty:
        logger.info("No new session after %s; nothing written.", state.as_of_date)
        return {
            "status": "no_new_sessions",
            "as_of_date": state.as_of_date,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    _assert_history_unchanged(state, returns)

    records = []
    for date in fresh.index:
        records.append(
            advance_one_session(state, fresh.loc[date], float(market.loc[date]), date)
        )
    paths = save_online_state(root, state)
    if state.session_log:
        pd.DataFrame(state.session_log).to_csv(paths["sessions"], index=False)

    last = records[-1]
    core = last["metrics"].get(state.core_key, {})
    artifacts = [str(paths["state"]), str(paths["manifest"]), str(paths["sessions"])]
    published: dict[str, Any] = {"published": False}
    if context is not None:
        published = _republish(state, config, last, context)
        artifacts.extend(published.pop("artifacts", []))

    elapsed = time.perf_counter() - started
    logger.info(
        "Applied %d session(s) up to %s in %.2fs.", len(records), state.as_of_date, elapsed
    )
    return {
        "status": "updated",
        "sessions_applied": len(records),
        "as_of_date": state.as_of_date,
        "graph_density": core.get("graph_density"),
        "number_of_nodes": core.get("number_of_nodes"),
        "stress_score": (last["stress"] or {}).get("stress_score"),
        "stress_percentile": (last["stress"] or {}).get("stress_percentile"),
        **published,
        "artifacts": artifacts,
        "elapsed_seconds": round(elapsed, 3),
    }


def _republish(state: OnlineState, config: Any, record: dict[str, Any], context) -> dict[str, Any]:
    """Rewrite `artifacts/latest/`, or explain why it was left alone.

    A failure here must not roll back the session: the state has already been
    saved and is correct. What matters is that the caller is told the website
    payload is now older than the state, rather than being left to assume both
    moved together.
    """
    from dynamicgraph.online.publish import PublicationUnavailable, publish_latest

    try:
        written = publish_latest(
            state,
            config,
            record,
            market_features=context.market_features,
            node_features=context.node_features,
            panel_last_date=context.panel_last_date,
            bundle_warnings=context.warnings,
        )
        return {"published": True, "artifacts": list(written.values())}
    except PublicationUnavailable as exc:
        logger.warning("artifacts/latest/ giữ nguyên bản của tầng batch: %s", exc)
        return {"published": False, "publish_skipped_reason": str(exc), "artifacts": []}
    except Exception as exc:  # noqa: BLE001 - the state is already saved and valid
        logger.exception("Publish thất bại; artifacts/latest/ giữ nguyên bản batch.")
        return {"published": False, "publish_error": str(exc), "artifacts": []}
