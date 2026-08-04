"""Website payload assembly.

Produces `artifacts/latest/` :
    latest_dynamicgraph.json   full state document
    nodes.json / edges.json    D3.js / Cytoscape.js ready
    communities.json
    node_scores.csv, graph_metrics.csv, stress_forecasts.csv

Every probability is emitted with its provenance: model, calibration method,
OOS Brier score, sample size, retraining date and any confidence warning. A
number without that context should never reach an investor-facing page.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.constants import INFLUENCE_LABEL, VULNERABLE_LABEL
from dynamicgraph.logging_config import get_logger
from dynamicgraph.outputs.exporters import export_frame, export_json, output_formats
from dynamicgraph.outputs.schemas import empty_payload, validate_payload

logger = get_logger(__name__)

STANDING_DISCLAIMERS = [
    "DynamicGraph describes the dependence structure between VN30 stocks. It does not forecast "
    "the level of the VN30 index.",
    "Network edges are statistical associations (correlation / partial correlation). They are not "
    "causal links between companies.",
    "Centrality identifies stocks at the centre of the estimated dependence structure. It does not "
    "identify stocks that will rise or fall.",
    "Stress probabilities are out-of-sample calibrated estimates with material uncertainty. They "
    "are not predictions of certainty and must not be read as investment advice.",
]


def _safe(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        if isinstance(value, (float, np.floating)) and (np.isnan(value) or np.isinf(value)):
            return default
    except TypeError:
        pass
    return value


def build_website_payload(
    *,
    config: Any,
    as_of_date: pd.Timestamp,
    snapshot: Any,
    node_metrics: pd.DataFrame,
    node_features: pd.DataFrame,
    graph_metrics_row: pd.Series | None,
    stress_scores: pd.DataFrame,
    stress_state: str,
    stress_contributions: pd.DataFrame,
    communities: Any,
    universe: Any,
    directed_roles: Any = None,
    stress_probabilities: dict[str, dict[str, Any]] | None = None,
    model_quality: dict[str, Any] | None = None,
    reproducibility: Any = None,
    data_freshness_days: int = 0,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble `latest_dynamicgraph.json`."""
    payload = empty_payload()
    sector_of = dict(zip(node_features.index, node_features.get("sector", pd.Series(dtype=str))))

    payload["model"].update(
        {
            "name": "DynamicGraph",
            "version": str(config.project.version),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of_date": str(pd.Timestamp(as_of_date).date()),
            "data_source": "local_database",
            "data_freshness_days": int(data_freshness_days),
            "run_id": getattr(reproducibility, "run_id", "") or "",
            "git_commit": getattr(reproducibility, "git_commit", None),
            "config_fingerprint": getattr(reproducibility, "config_fingerprint", "") or "",
            "graph_layer": snapshot.layer,
            "graph_window": snapshot.window,
            "graph_return_type": snapshot.return_type,
        }
    )

    payload["universe"].update(
        {
            "index": str(config.data.index_symbol),
            "node_count": int(snapshot.n_nodes),
            "tickers": list(snapshot.nodes),
            "missing_tickers": list(getattr(snapshot, "excluded_nodes", []) or []),
            "survivorship_bias_warning": bool(getattr(universe, "survivorship_bias", True)),
            "universe_method": str(getattr(universe, "method", "static_list")),
        }
    )

    # ---- network state --------------------------------------------------
    if as_of_date in stress_scores.index:
        row = stress_scores.loc[as_of_date]
        payload["network_state"].update(
            {
                "label": str(stress_state),
                "stress_score": _safe(round(float(row.get("stress_score", np.nan)), 2)),
                "stress_raw": _safe(round(float(row.get("stress_raw", np.nan)), 4)),
                "historical_percentile": _safe(round(float(row.get("stress_percentile", np.nan)), 4)),
                "change_1d": _safe(round(float(row.get("stress_change_1d", np.nan)), 2)),
                "change_5d": _safe(round(float(row.get("stress_change_5d", np.nan)), 2)),
                "change_20d": _safe(round(float(row.get("stress_change_20d", np.nan)), 2)),
            }
        )
    if stress_contributions is not None and not stress_contributions.empty:
        payload["network_state"]["main_contributors"] = [
            {
                "metric": r["metric"],
                "contribution": _safe(round(float(r["contribution"]), 4)),
                "share": _safe(round(float(r["share"]), 4)),
                "direction": "raises_stress" if r["contribution"] > 0 else "lowers_stress",
            }
            for _, r in stress_contributions.head(6).iterrows()
        ]

    flags: list[str] = []
    percentile = payload["network_state"].get("historical_percentile")
    if percentile is not None and percentile > 0.95:
        flags.append("stress_score_above_95th_historical_percentile")
    change_20d = payload["network_state"].get("change_20d")
    if change_20d is not None and change_20d > 15:
        flags.append("stress_score_rose_sharply_over_20_sessions")
    payload["network_state"]["warning_flags"] = flags

    # ---- graph metrics ---------------------------------------------------
    if graph_metrics_row is not None:
        payload["graph_metrics"] = {
            key: _safe(float(value)) if isinstance(value, (int, float, np.number)) else str(value)
            for key, value in graph_metrics_row.items()
            if key not in {"date"} and not isinstance(value, (list, dict))
        }

    # ---- nodes ------------------------------------------------------------
    metrics = node_metrics.set_index("ticker") if "ticker" in node_metrics.columns else node_metrics
    joined = metrics.join(node_features, how="left", rsuffix="_feat")

    payload["leading_influence_nodes"] = _node_records(
        joined, sector_of, top_n=int(config.output.top_n_nodes),
        sort_by="influence_score" if "influence_score" in joined.columns else "strength",
        role=INFLUENCE_LABEL,
    )
    payload["vulnerable_nodes"] = _vulnerable_records(
        joined, sector_of, top_n=int(config.output.top_n_nodes)
    )

    # ---- directed roles ---------------------------------------------------
    if directed_roles is not None and getattr(directed_roles, "available", False):
        payload["risk_transmitters"] = _directed_records(
            directed_roles.transmitters(int(config.output.top_n_nodes)), sector_of
        )
        payload["risk_receivers"] = _directed_records(
            directed_roles.receivers(int(config.output.top_n_nodes)), sector_of
        )
        payload["directed_layer"] = {
            "available": True,
            "layer": directed_roles.layer,
            "disclaimer": directed_roles.disclaimer,
        }
    else:
        payload["risk_transmitters"] = []
        payload["risk_receivers"] = []
        payload["directed_layer"] = {
            "available": False,
            "note": (
                "No directed layer was produced, so no node can be labelled a risk transmitter or "
                "receiver. Undirected centrality only supports the label "
                f"`{INFLUENCE_LABEL}`."
            ),
        }

    # ---- communities --------------------------------------------------------
    payload["communities"] = _community_records(snapshot, communities, sector_of)

    # ---- edges ---------------------------------------------------------------
    edges = snapshot.edge_list()
    if not edges.empty:
        edges = edges.reindex(edges["absolute_weight"].sort_values(ascending=False).index)
        payload["top_edges"] = [
            {
                "source": r["source"],
                "target": r["target"],
                "weight": _safe(round(float(r["absolute_weight"]), 4)),
                "signed_weight": _safe(round(float(r["signed_weight"]), 4)),
                "edge_type": r["edge_type"],
                "window": int(r["window"]),
                "stability": _safe(round(float(r["stability"]), 3)) if pd.notna(r["stability"]) else None,
            }
            for _, r in edges.head(int(config.output.top_n_edges)).iterrows()
        ]

    # ---- probabilities and quality -------------------------------------------
    payload["stress_probabilities"] = stress_probabilities or {}
    if model_quality:
        payload["model_quality"].update(model_quality)

    # ---- warnings and disclaimers --------------------------------------------
    all_warnings = list(warnings or [])
    if payload["universe"]["survivorship_bias_warning"]:
        all_warnings.insert(
            0,
            "SURVIVORSHIP BIAS: the universe is a current-membership snapshot applied to history. "
            "Network statistics and model performance are optimistically biased.",
        )
    if not payload["stress_probabilities"]:
        all_warnings.append(
            "No calibrated stress probability is available for this run; only the descriptive "
            "network state is published."
        )
    payload["warnings"] = all_warnings
    payload["disclaimers"] = list(STANDING_DISCLAIMERS)

    problems = validate_payload(payload)
    if problems:
        logger.warning("Website payload schema problems: %s", problems)
        payload["warnings"].append(f"schema_validation: {'; '.join(problems)}")
    return payload


def _node_records(
    joined: pd.DataFrame, sector_of: dict[str, str], top_n: int, sort_by: str, role: str
) -> list[dict[str, Any]]:
    if joined.empty or sort_by not in joined.columns:
        return []
    ordered = joined.sort_values(sort_by, ascending=False).head(top_n)
    records = []
    for ticker, row in ordered.iterrows():
        records.append(
            {
                "id": str(ticker),
                "label": str(ticker),
                "sector": sector_of.get(ticker, "UNKNOWN"),
                "community": int(_safe(row.get("community"), 0) or 0),
                "strength": _safe(round(float(row.get("strength", np.nan)), 4)),
                "eigenvector_centrality": _safe(round(float(row.get("eigenvector_centrality", np.nan)), 4)),
                "pagerank": _safe(round(float(row.get("pagerank", np.nan)), 4)),
                "betweenness_centrality": _safe(round(float(row.get("betweenness_centrality", np.nan)), 4)),
                "centrality_change_20d": _safe(round(float(row.get("strength_change_20d", np.nan)), 4)),
                "volatility_20d": _safe(round(float(row.get("volatility_20d", np.nan)), 4)),
                "return_20d": _safe(round(float(row.get("return_20d", np.nan)), 4)),
                "current_drawdown": _safe(round(float(row.get("current_drawdown", np.nan)), 4)),
                "role": role,
                "interpretation": (
                    "Sits at the centre of the estimated dependence structure. This is not a view "
                    "on the stock's future return."
                ),
            }
        )
    return records


def _vulnerable_records(joined: pd.DataFrame, sector_of: dict[str, str], top_n: int) -> list[dict[str, Any]]:
    if joined.empty:
        return []
    parts = []
    for column, ascending in (
        ("current_drawdown", True),
        ("downside_volatility_20d", False),
        ("avg_neighbor_risk", False),
    ):
        if column in joined.columns and joined[column].notna().any():
            parts.append(joined[column].rank(pct=True, ascending=ascending))
    if not parts:
        return []

    score = pd.concat(parts, axis=1).mean(axis=1)
    ordered = joined.assign(vulnerability_score=score).sort_values("vulnerability_score", ascending=False)
    records = []
    for ticker, row in ordered.head(top_n).iterrows():
        records.append(
            {
                "id": str(ticker),
                "label": str(ticker),
                "sector": sector_of.get(ticker, "UNKNOWN"),
                "vulnerability_score": _safe(round(float(row["vulnerability_score"]), 4)),
                "current_drawdown": _safe(round(float(row.get("current_drawdown", np.nan)), 4)),
                "downside_volatility_20d": _safe(round(float(row.get("downside_volatility_20d", np.nan)), 4)),
                "avg_neighbor_risk": _safe(round(float(row.get("avg_neighbor_risk", np.nan)), 4)),
                "strength": _safe(round(float(row.get("strength", np.nan)), 4)),
                "role": VULNERABLE_LABEL,
            }
        )
    return records


def _directed_records(frame: pd.DataFrame, sector_of: dict[str, str]) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [
        {
            "id": str(r["ticker"]),
            "label": str(r["ticker"]),
            "sector": sector_of.get(r["ticker"], "UNKNOWN"),
            "out_strength": _safe(round(float(r["out_strength"]), 4)),
            "in_strength": _safe(round(float(r["in_strength"]), 4)),
            "net_spillover": _safe(round(float(r["net_spillover"]), 4)),
            "role": str(r["role"]),
            "layer": str(r.get("layer", "")),
        }
        for _, r in frame.iterrows()
    ]


def _community_records(snapshot: Any, communities: Any, sector_of: dict[str, str]) -> list[dict[str, Any]]:
    labels = getattr(communities, "labels", None)
    if not labels:
        return []
    from dynamicgraph.explainability.graph import community_contributions

    contributions = community_contributions(snapshot, labels, sector_of)
    records = []
    for _, row in contributions.iterrows():
        records.append(
            {
                "community_id": int(row["community"]),
                "size": int(row["size"]),
                "members": [m.strip() for m in str(row["members"]).split(",") if m.strip()],
                "dominant_sector": row.get("dominant_sector"),
                "dominant_sector_share": (
                    _safe(round(float(row["dominant_sector_share"]), 3))
                    if pd.notna(row.get("dominant_sector_share")) else None
                ),
                "sector_composition": row.get("sector_composition", {}),
                "cohesion": _safe(round(float(row["cohesion"]), 4)) if pd.notna(row.get("cohesion")) else None,
                "internal_weight": _safe(round(float(row["internal_weight"]), 4)),
                "external_weight": _safe(round(float(row["external_weight"]), 4)),
            }
        )
    result = sorted(records, key=lambda r: r["size"], reverse=True)
    if getattr(communities, "sector_purity", None) is not None:
        for record in result:
            record["overall_sector_purity"] = round(float(communities.sector_purity), 4)
    return result


def build_nodes_json(
    snapshot: Any,
    node_metrics: pd.DataFrame,
    node_features: pd.DataFrame,
    sector_of: dict[str, str],
    communities: Any = None,
) -> list[dict[str, Any]]:
    """`nodes.json` - one record per node, D3/Cytoscape friendly."""
    metrics = node_metrics.set_index("ticker") if "ticker" in node_metrics.columns else node_metrics
    joined = metrics.join(node_features, how="left", rsuffix="_feat")
    labels = getattr(communities, "labels", {}) or {}

    risk_parts = []
    for column, ascending in (("current_drawdown", True), ("volatility_20d", False)):
        if column in joined.columns and joined[column].notna().any():
            risk_parts.append(joined[column].rank(pct=True, ascending=ascending))
    risk_score = pd.concat(risk_parts, axis=1).mean(axis=1) if risk_parts else pd.Series(np.nan, index=joined.index)

    # Emit most-central first. An alphabetical dump forces every consumer to
    # re-sort before it can show anything useful, and makes the file unreadable
    # by eye. `rank` is carried explicitly so the ordering survives any
    # re-serialisation downstream.
    strength = joined["strength"] if "strength" in joined.columns else pd.Series(dtype=float)
    ordered_nodes = (
        strength.reindex(snapshot.nodes).sort_values(ascending=False).index.tolist()
        if not strength.empty
        else list(snapshot.nodes)
    )

    records = []
    for rank, ticker in enumerate(ordered_nodes, start=1):
        row = joined.loc[ticker] if ticker in joined.index else pd.Series(dtype=float)
        records.append(
            {
                "rank": rank,
                "id": str(ticker),
                "label": str(ticker),
                "sector": sector_of.get(ticker, "UNKNOWN"),
                "community": int(labels.get(ticker, _safe(row.get("community"), 0) or 0)),
                "strength": _safe(round(float(row.get("strength", np.nan)), 4), 0.0),
                "degree": _safe(round(float(row.get("degree", np.nan)), 2), 0.0),
                "eigenvector_centrality": _safe(round(float(row.get("eigenvector_centrality", np.nan)), 4), 0.0),
                "pagerank": _safe(round(float(row.get("pagerank", np.nan)), 4), 0.0),
                "betweenness_centrality": _safe(round(float(row.get("betweenness_centrality", np.nan)), 4), 0.0),
                "clustering": _safe(round(float(row.get("clustering", np.nan)), 4), 0.0),
                "risk_score": _safe(round(float(risk_score.get(ticker, np.nan)), 4), 0.0),
                "return_20d": _safe(round(float(row.get("return_20d", np.nan)), 4), 0.0),
                "volatility_20d": _safe(round(float(row.get("volatility_20d", np.nan)), 4), 0.0),
                "current_drawdown": _safe(round(float(row.get("current_drawdown", np.nan)), 4), 0.0),
                "avg_neighbor_risk": _safe(round(float(row.get("avg_neighbor_risk", np.nan)), 4), 0.0),
            }
        )
    return records


def build_edges_json(snapshot: Any, directed_snapshot: Any = None) -> list[dict[str, Any]]:
    """`edges.json` - undirected core edges plus any directed lead-lag edges."""
    records: list[dict[str, Any]] = []
    edges = snapshot.edge_list()
    # Strongest first: a frontend that renders only the top N edges then needs
    # no sorting, and the file is readable without tooling.
    if not edges.empty:
        edges = edges.reindex(edges["absolute_weight"].sort_values(ascending=False).index)
    for rank, (_, row) in enumerate(edges.iterrows(), start=1):
        records.append(
            {
                "rank": rank,
                "source": str(row["source"]),
                "target": str(row["target"]),
                "weight": _safe(round(float(row["absolute_weight"]), 4), 0.0),
                "signed_weight": _safe(round(float(row["signed_weight"]), 4), 0.0),
                "absolute_weight": _safe(round(float(row["absolute_weight"]), 4), 0.0),
                "edge_type": str(row["edge_type"]),
                "window": int(row["window"]),
                "stability": _safe(round(float(row["stability"]), 3)) if pd.notna(row["stability"]) else None,
                "direction": None,
            }
        )

    if directed_snapshot is not None:
        directed = directed_snapshot.edge_list()
        if not directed.empty:
            directed = directed.reindex(
                directed["weight"].abs().sort_values(ascending=False).index
            )
        for rank, (_, row) in enumerate(directed.iterrows(), start=len(records) + 1):
            records.append(
                {
                    "rank": rank,
                    "source": str(row["source"]),
                    "target": str(row["target"]),
                    "weight": _safe(round(abs(float(row["weight"])), 4), 0.0),
                    "signed_weight": _safe(round(float(row["weight"]), 4), 0.0),
                    "absolute_weight": _safe(round(abs(float(row["weight"])), 4), 0.0),
                    "edge_type": str(row["edge_type"]),
                    "window": int(row["window"]),
                    "stability": None,
                    "direction": "directed",
                }
            )
    return records


def write_website_outputs(
    config: Any,
    payload: dict[str, Any],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    node_scores: pd.DataFrame,
    graph_metrics: pd.DataFrame,
    stress_forecasts: pd.DataFrame,
    network_history: pd.DataFrame | None = None,
) -> dict[str, str]:
    """Write every file under `artifacts/latest/`. Returns a path manifest."""
    latest = config.artifacts_dir / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    formats = output_formats(config)
    written: dict[str, str] = {}

    written["latest_dynamicgraph"] = str(export_json(payload, latest / "latest_dynamicgraph.json"))
    written["nodes"] = str(export_json(nodes, latest / "nodes.json"))
    written["edges"] = str(export_json(edges, latest / "edges.json"))
    written["communities"] = str(
        export_json(payload.get("communities", []), latest / "communities.json")
    )

    for name, frame in (
        ("node_scores", node_scores),
        ("graph_metrics", graph_metrics),
        ("stress_forecasts", stress_forecasts),
    ):
        paths = export_frame(frame, latest / name, formats=formats, index=name == "graph_metrics")
        if paths:
            written[name] = str(paths[0])

    if network_history is not None and not network_history.empty:
        history = network_history.tail(int(config.output.history_export_days))
        paths = export_frame(history, latest / "network_history", formats=formats, index=True)
        if paths:
            written["network_history"] = str(paths[0])
        written["network_history_json"] = str(
            export_json(
                [
                    {"date": str(pd.Timestamp(idx).date()), **{k: _safe(v) for k, v in row.items()}}
                    for idx, row in history.iterrows()
                ],
                latest / "network_history.json",
            )
        )

    logger.info("Website artifacts written to %s (%d file(s)).", latest, len(written))
    return written
