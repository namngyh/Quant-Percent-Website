"""Advance the published graph state by exactly one trading session."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.features.residualization import residualize_returns
from dynamicgraph.graphs.base import GraphSnapshot
from dynamicgraph.graphs.snapshots import build_snapshot
from dynamicgraph.logging_config import get_logger
from dynamicgraph.network.communities import CommunityResult, detect_communities
from dynamicgraph.network.graph_metrics import compute_graph_metrics
from dynamicgraph.online.state import OnlineState

logger = get_logger(__name__)

MAXIMUM_CALENDAR_GAP_DAYS = 10


class AbnormalSessionError(RuntimeError):
    """Raised when a new session cannot be trusted; nothing is silently patched."""


def residual_returns(
    returns: pd.DataFrame, market_returns: pd.Series, window: int
) -> pd.DataFrame:
    """Market-residualised returns, exactly as the batch feature builder makes them.

    `residualize_returns` fits a trailing rolling OLS per date, so the value at t
    depends only on [t-W+1, t]. Recomputing it on the buffer therefore reproduces
    the batch frame row for row rather than approximating it.
    """
    return residualize_returns(returns, market_returns, window=int(window)).residuals


def _snapshots_for_date(
    state: OnlineState, returns_by_type: dict[str, pd.DataFrame], date: pd.Timestamp
) -> dict[str, GraphSnapshot]:
    """Build every configured layer for one date, using the frozen build config."""
    snapshots: dict[str, GraphSnapshot] = {}
    for key, build in state.build_configs.items():
        source = returns_by_type.get(build.return_type)
        if source is None or pd.Timestamp(date) not in source.index:
            continue
        position = source.index.get_loc(pd.Timestamp(date))
        if position + 1 < build.window:
            continue
        window_returns = source.iloc[position - build.window + 1 : position + 1]
        snapshot = build_snapshot(window_returns, pd.Timestamp(date), build)
        if snapshot is None:
            logger.warning("%s: phiên %s không đủ node coverage, bỏ qua snapshot.", key, date.date())
            continue
        snapshots[key] = snapshot
    return snapshots


def _returns_by_type(state: OnlineState) -> dict[str, pd.DataFrame]:
    residual = residual_returns(state.returns, state.market_returns, state.residual_window)
    return {"residual": residual.dropna(how="all"), "raw": state.returns}


def _community_of(state: OnlineState, snapshot: GraphSnapshot) -> CommunityResult:
    return detect_communities(
        np.abs(snapshot.adjacency),
        snapshot.nodes,
        method="auto",
        seed=state.seed,
        sector_of=state.sector_of or None,
    )


def seed_snapshots(state: OnlineState) -> None:
    """Populate the snapshot/community the first live session will compare against."""
    date = pd.Timestamp(state.as_of_date)
    snapshots = _snapshots_for_date(state, _returns_by_type(state), date)
    state.snapshots = snapshots
    state.communities = {key: _community_of(state, snap) for key, snap in snapshots.items()}


def _metric_rows(
    state: OnlineState, snapshots: dict[str, GraphSnapshot]
) -> tuple[dict[str, dict[str, Any]], dict[str, CommunityResult]]:
    """One metric row per layer, compared against the previous session's snapshot.

    This mirrors `compute_metric_series`, which walks a series carrying
    `previous`/`previous_community` forward; online the predecessor comes from
    the state instead of the loop variable.
    """
    rows: dict[str, dict[str, Any]] = {}
    communities: dict[str, CommunityResult] = {}
    for key, snapshot in snapshots.items():
        community = _community_of(state, snapshot)
        rows[key] = compute_graph_metrics(
            snapshot,
            previous=state.snapshots.get(key),
            community=community,
            previous_community=state.communities.get(key),
            correlation=None,
            sector_of=state.sector_of or None,
            seed=state.seed,
        )
        communities[key] = community
    return rows, communities



def _append_metric_rows(history: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """Append and de-duplicate on date, keeping the newest row.

    Re-applying a session must be idempotent: `update-latest` can legitimately
    be run twice for the same day (a retry, a manual re-run) and the second run
    must not leave two rows for one date behind for the expanding statistics to
    trip over.
    """
    combined = pd.concat([history, rows]) if len(history) else rows
    return combined[~combined.index.duplicated(keep="last")].sort_index()


def _stress_row(state: OnlineState) -> dict[str, Any] | None:
    """Descriptive stress score for the newest session, from the frozen model.

    `transform` is applied to the whole metric history rather than to the new
    row alone because `stress_percentile` is an expanding rank and
    `stress_change_{1,5,20}d` are differences - both are functions of the past.
    Running the batch code over the retained history keeps the published number
    identical to what a full rebuild would produce, and costs milliseconds.
    """
    if state.stress_model is None or state.metric_history.empty:
        return None
    scores = state.stress_model.transform(state.metric_history)
    state.stress_history = scores
    return scores.iloc[-1].to_dict()


def validate_new_session(state: OnlineState, date: pd.Timestamp, row: pd.Series) -> pd.Timestamp:
    """Reject an anomalous session instead of interpolating or repairing it."""
    date = pd.Timestamp(date)
    as_of = pd.Timestamp(state.as_of_date)
    if pd.isna(date):
        raise AbnormalSessionError("Phiên mới thiếu ngày giao dịch")
    if date <= as_of:
        raise AbnormalSessionError(
            f"Phiên {date.date()} không mới hơn as_of_date {as_of.date()} của online state"
        )
    gap = int((date - as_of).days)
    if gap > MAXIMUM_CALENDAR_GAP_DAYS:
        raise AbnormalSessionError(
            f"Calendar gap {gap} ngày giữa {as_of.date()} và {date.date()} vượt ngưỡng "
            f"{MAXIMUM_CALENDAR_GAP_DAYS}; dừng để rà soát thay vì tự nội suy"
        )
    unknown = [name for name in row.index if name not in state.returns.columns]
    if unknown:
        raise AbnormalSessionError(
            f"Phiên {date.date()} có ticker chưa từng thấy trong buffer: {unknown[:10]}; "
            "universe đổi thì phải chạy lại `run-all`"
        )
    values = pd.to_numeric(row, errors="coerce")
    if np.isfinite(values.to_numpy(dtype=float)).sum() == 0:
        raise AbnormalSessionError(f"Phiên {date.date()} không có ticker nào có giá trị hữu hạn")
    extreme = values[values.abs() > 1.0]
    if len(extreme):
        raise AbnormalSessionError(
            f"Phiên {date.date()} có log-return |r| > 1.0 ({dict(extreme.head(5))}); "
            "gần như chắc chắn là lỗi dữ liệu, dừng để rà soát"
        )
    return date


def advance_one_session(
    state: OnlineState,
    returns_row: pd.Series,
    market_return: float,
    date: pd.Timestamp,
) -> dict[str, Any]:
    """Append one session and rebuild only what that session changes."""
    started = time.perf_counter()
    date = validate_new_session(state, date, returns_row)

    appended = state.returns.reindex(columns=state.returns.columns)
    appended.loc[pd.Timestamp(date)] = returns_row.reindex(state.returns.columns)
    appended = appended.sort_index()
    market = state.market_returns.copy()
    market.loc[pd.Timestamp(date)] = float(market_return)
    market = market.sort_index()

    previous_returns, previous_market = state.returns, state.market_returns
    state.returns, state.market_returns = appended, market
    try:
        snapshots = _snapshots_for_date(state, _returns_by_type(state), pd.Timestamp(date))
        metrics, communities = _metric_rows(state, snapshots)
    except Exception:
        state.returns, state.market_returns = previous_returns, previous_market
        raise

    if metrics:
        appended_metrics = pd.DataFrame(
            [metrics[state.core_key]] if state.core_key in metrics else list(metrics.values())
        )
        appended_metrics = appended_metrics.set_index("date").sort_index()
        state.metric_history = _append_metric_rows(state.metric_history, appended_metrics)
        # Every layer, not just the core one: the stress classifiers were fitted
        # on all of them flattened together.
        for key, row in metrics.items():
            appended = pd.DataFrame([row]).set_index("date").sort_index()
            state.metric_history_by_key[key] = _append_metric_rows(
                state.metric_history_by_key.get(key, pd.DataFrame()), appended
            )

    state.as_of_date = str(pd.Timestamp(date).date())
    state.snapshots.update(snapshots)
    state.communities.update(communities)
    stress = _stress_row(state)

    record = {
        "as_of_date": state.as_of_date,
        "snapshots": snapshots,
        "core_snapshot": snapshots.get(state.core_key),
        "metrics": metrics,
        "communities": communities,
        "stress": stress,
        "elapsed_seconds": max(time.perf_counter() - started, 1e-9),
    }
    state.session_log.append(
        {
            "as_of_date": state.as_of_date,
            "keys_built": sorted(snapshots),
            "elapsed_seconds": record["elapsed_seconds"],
        }
    )
    return record
