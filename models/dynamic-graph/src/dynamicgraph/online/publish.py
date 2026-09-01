"""Republish `artifacts/latest/` from the online state.

This is what Phase 2 was missing. The batch tier owned `artifacts/latest/`
because the payload needed `build_stress_probabilities`, which refitted the
stress classifiers on every call -- something the online tier is forbidden to
do. With those classifiers frozen into the batch handoff (`latest.py`), the
online tier can score them and write the same files.

Two rules shape this module:

* the payload is assembled by the *same* `build_website_payload` /
  `write_website_outputs` the batch tier uses, so the published schema cannot
  drift between the two tiers;
* anything the online tier cannot honestly recompute per session -- the
  out-of-sample quality table, the directed-role table, the reproducibility
  record -- is carried unchanged from the batch run rather than invented, and
  `latest_dynamicgraph.json` records which tier wrote it and which batch run it
  descends from.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from dynamicgraph.logging_config import get_logger
from dynamicgraph.online.state import OnlineState

logger = get_logger(__name__)


class PublicationUnavailable(RuntimeError):
    """Raised when the handoff lacks what a full payload needs.

    Deliberately loud. Overwriting a good batch payload with a partial one is
    worse than not writing at all, which is exactly the trade-off that kept this
    step unimplemented until the models could be frozen.
    """


def _classify_state(stress_scores, as_of, publication: dict[str, Any]) -> str:
    """Network-state label for one session, against the batch's frozen cutoffs.

    `DescriptiveStressScore.classify_state` recomputes its quantiles from
    whatever rows it is given, so calling it here would derive the thresholds
    from a series that already contains the session being published -- both a
    leak and a label that drifts every day. The batch stores the boundaries it
    estimated on training folds; this only has to place today's raw score
    between them.

    Falls back to whatever the score frame carries, then to `"unknown"`: a
    missing label is a visible gap on the website, which is the right outcome
    when the cutoffs were never handed over.
    """
    row = stress_scores.loc[as_of]
    cutoffs = [float(value) for value in publication.get("stress_state_cutoffs") or []]
    labels = [str(value) for value in publication.get("stress_state_labels") or []]
    raw = row.get("stress_raw")
    if cutoffs and len(labels) == len(cutoffs) + 1 and raw is not None and pd.notna(raw):
        position = int(sum(float(raw) > cutoff for cutoff in cutoffs))
        return labels[position]
    logger.warning(
        "Batch handoff không có ngưỡng network_state; nhãn trạng thái sẽ thiếu trong payload."
    )
    return str(row.get("network_state", "unknown"))


def _node_metrics_for(state: OnlineState, config: Any, snapshot: Any, community: Any, features):
    from dynamicgraph.network.node_metrics import compute_node_metrics

    return compute_node_metrics(
        snapshot,
        node_features=features,
        community=community,
        compute_betweenness=bool(config.network.compute_betweenness),
        compute_closeness=bool(config.network.compute_closeness),
        pagerank_alpha=float(config.network.pagerank_alpha),
        risk_column=str(config.network.neighbor_risk_feature),
        sector_of=state.sector_of or None,
        seed=int(state.seed),
    )


class _FeatureSource:
    """Adapter giving `latest.stress_feature_builder` what it expects.

    The builder reads `market_features`, `metrics_by_key` and `stress_scores`
    off a `PipelineState`. The online tier holds equivalent objects under
    different names; wrapping them is what lets both tiers call the identical
    feature-construction code instead of a re-implementation that could drift.
    """

    def __init__(self, market_features: pd.DataFrame, state: OnlineState) -> None:
        self.market_features = market_features
        self.metrics_by_key = state.metric_history_by_key or {state.core_key: state.metric_history}
        self.stress_scores = state.stress_history if len(state.stress_history) else None


def publish_latest(
    state: OnlineState,
    config: Any,
    record: dict[str, Any],
    market_features: pd.DataFrame,
    node_features: Any,
    panel_last_date: pd.Timestamp,
    bundle_warnings: list[str] | None = None,
) -> dict[str, str]:
    """Write every `artifacts/latest/` file for the session just applied."""
    from datetime import datetime

    from dynamicgraph.latest import predict_stress_probabilities
    from dynamicgraph.outputs.exporters import write_manifest
    from dynamicgraph.outputs.website_json import (
        build_edges_json,
        build_nodes_json,
        build_website_payload,
        write_website_outputs,
    )

    publication = dict(state.publication or {})
    if not state.stress_forecast_models:
        raise PublicationUnavailable(
            "Batch handoff chưa có model dự báo stress đã đóng băng; chạy `run-all` "
            "(hoặc `generate-latest`) rồi `init-online-state` trước khi publish theo phiên."
        )

    snapshot = record.get("core_snapshot") or state.snapshots.get(state.core_key)
    if snapshot is None:
        raise PublicationUnavailable("Phiên vừa rồi không dựng được snapshot cho core layer")
    as_of = pd.Timestamp(snapshot.date)
    community = record["communities"].get(state.core_key) or state.communities.get(state.core_key)

    features_at = node_features.matrix_at(as_of, snapshot.nodes)
    features_at["sector"] = [state.sector_of.get(t, "UNKNOWN") for t in features_at.index]
    node_metrics = _node_metrics_for(state, config, snapshot, community, features_at)

    stress_scores = state.stress_history
    if stress_scores is None or as_of not in stress_scores.index:
        raise PublicationUnavailable(
            "Chưa có stress score cho phiên mới; không publish payload thiếu chỉ số trạng thái"
        )
    stress_state = _classify_state(stress_scores, as_of, publication)

    contributions = pd.DataFrame()
    if state.stress_model is not None:
        from dynamicgraph.explainability.graph import stress_contribution_breakdown

        contributions = stress_contribution_breakdown(state.stress_model, stress_scores, as_of)

    builder_source = _FeatureSource(market_features, state)
    from dynamicgraph.latest import stress_feature_builder

    probabilities = predict_stress_probabilities(
        state.stress_forecast_models, stress_feature_builder(builder_source), as_of
    )

    core_metrics = state.metric_history
    metrics_row = core_metrics.loc[as_of] if as_of in core_metrics.index else core_metrics.iloc[-1]
    freshness = int((pd.Timestamp(datetime.now().date()) - pd.Timestamp(panel_last_date)).days)

    payload = build_website_payload(
        config=config,
        as_of_date=as_of,
        snapshot=snapshot,
        node_metrics=node_metrics,
        node_features=features_at,
        graph_metrics_row=metrics_row,
        stress_scores=stress_scores,
        stress_state=stress_state,
        stress_contributions=contributions,
        communities=community,
        universe=publication.get("universe"),
        directed_roles=publication.get("directed_roles"),
        stress_probabilities=probabilities,
        model_quality=publication.get("model_quality"),
        reproducibility=publication.get("record"),
        data_freshness_days=freshness,
        warnings=list(bundle_warnings or publication.get("warnings") or []),
    )
    # Provenance, so a reader can tell a session update from a full research run
    # and see which batch run the frozen models came from.
    payload["model"]["produced_by"] = "online_tier"
    payload["model"]["source_run_metadata"] = dict(state.source_run_metadata)
    payload["model"]["sessions_since_batch"] = len(state.session_log)

    # `directed_roles` needs the directed/spillover graphs, which the online tier
    # does not rebuild; the batch run's table is carried forward, so the edge
    # file has no directed overlay for this session.
    nodes = build_nodes_json(snapshot, node_metrics, features_at, state.sector_of, community)
    edges = build_edges_json(snapshot, None)

    node_scores = node_metrics.merge(
        features_at.reset_index().rename(columns={"index": "ticker"}),
        on="ticker", how="left", suffixes=("", "_feature"),
    )
    headline = [
        "ticker", "sector", "community", "strength", "degree", "eigenvector_centrality",
        "pagerank", "betweenness_centrality", "positive_strength", "negative_strength",
        "edge_sign_ratio", "avg_neighbor_risk", "return_20d", "volatility_20d",
        "current_drawdown", "downside_volatility_20d",
    ]
    present = [c for c in headline if c in node_scores.columns]
    node_scores = node_scores[present + [c for c in node_scores.columns if c not in present]]
    if "strength" in node_scores.columns:
        node_scores = node_scores.sort_values("strength", ascending=False).reset_index(drop=True)

    stress_forecasts = pd.DataFrame(
        [
            {"horizon": horizon, "as_of_date": str(as_of.date()), **entry}
            for horizon, entry in probabilities.items()
        ]
    )
    network_history = stress_scores.join(
        core_metrics[[c for c in core_metrics.columns if c not in stress_scores.columns]],
        how="left",
    )

    written = write_website_outputs(
        config=config,
        payload=payload,
        nodes=nodes,
        edges=edges,
        node_scores=node_scores,
        graph_metrics=core_metrics,
        stress_forecasts=stress_forecasts,
        network_history=network_history,
    )
    write_manifest(config.artifacts_dir / "latest", written)
    logger.info("artifacts/latest/ republished by the online tier for %s.", as_of.date())
    return written
