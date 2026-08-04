r"""Node-level network metrics.

Signed-graph discipline: PageRank, eigenvector centrality, closeness, harmonic
centrality, clustering and coreness are undefined (or meaningless) with negative
weights, so they are computed on |A|. The transformation is recorded in the
returned frame's `weights_used` column so no downstream consumer can forget it.

Sign information is not thrown away -- it is exposed separately as
`positive_strength`, `negative_strength` and `edge_sign_ratio`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS
from dynamicgraph.graphs.base import GraphSnapshot
from dynamicgraph.logging_config import get_logger
from dynamicgraph.network.communities import (
    CommunityResult,
    detect_communities,
    participation_coefficient,
    within_community_degree_z,
)

logger = get_logger(__name__)


def compute_node_metrics(
    snapshot: GraphSnapshot,
    node_features: pd.DataFrame | None = None,
    community: CommunityResult | None = None,
    compute_betweenness: bool = True,
    compute_closeness: bool = True,
    pagerank_alpha: float = 0.85,
    risk_column: str = "volatility_20d",
    sector_of: dict[str, str] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Per-node metrics for one snapshot.

    `node_features` is an optional `ticker x feature` frame used for the
    neighbour-risk aggregations.
    """
    import networkx as nx

    nodes = snapshot.nodes
    signed = snapshot.adjacency
    absolute = np.abs(signed)
    n = len(nodes)

    frame = pd.DataFrame(index=pd.Index(nodes, name="ticker"))
    frame["date"] = snapshot.date
    frame["layer"] = snapshot.layer
    frame["window"] = snapshot.window
    frame["return_type"] = snapshot.return_type
    frame["weights_used"] = "absolute"

    # ---- degree / strength ------------------------------------------
    adjacency_binary = (absolute > 0).astype(float)
    frame["degree"] = adjacency_binary.sum(axis=1)
    frame["degree_centrality"] = frame["degree"] / max(n - 1, 1)
    frame["strength"] = absolute.sum(axis=1)
    frame["positive_strength"] = np.where(signed > 0, signed, 0.0).sum(axis=1)
    frame["negative_strength"] = np.abs(np.where(signed < 0, signed, 0.0)).sum(axis=1)
    frame["edge_sign_ratio"] = frame["positive_strength"] / (frame["strength"] + EPS)
    frame["mean_edge_weight"] = frame["strength"] / np.clip(frame["degree"], 1, None)

    graph = snapshot.to_networkx(use_absolute=True)

    # ---- spectral / walk centralities --------------------------------
    try:
        eigen = nx.eigenvector_centrality_numpy(graph, weight="weight")
    except Exception:
        try:
            eigen = nx.eigenvector_centrality(graph, weight="weight", max_iter=1000, tol=1e-6)
        except Exception:
            eigen = {node: np.nan for node in nodes}
    frame["eigenvector_centrality"] = pd.Series(eigen).reindex(nodes)

    try:
        pagerank = nx.pagerank(graph, alpha=pagerank_alpha, weight="weight")
    except Exception:
        pagerank = {node: np.nan for node in nodes}
    frame["pagerank"] = pd.Series(pagerank).reindex(nodes)

    # ---- distance-based centralities ---------------------------------
    # Shortest-path measures need a *cost*: strong edges must be cheap to cross.
    distance_graph = graph.copy()
    for u, v, data in distance_graph.edges(data=True):
        data["distance"] = 1.0 / max(float(data.get("weight", 0.0)), EPS)

    if compute_betweenness and n <= 300:
        try:
            betweenness = nx.betweenness_centrality(distance_graph, weight="distance", normalized=True)
        except Exception:
            betweenness = {node: np.nan for node in nodes}
    else:
        betweenness = {node: np.nan for node in nodes}
    frame["betweenness_centrality"] = pd.Series(betweenness).reindex(nodes)

    if compute_closeness:
        try:
            closeness = nx.closeness_centrality(distance_graph, distance="distance")
        except Exception:
            closeness = {node: np.nan for node in nodes}
        try:
            harmonic = nx.harmonic_centrality(distance_graph, distance="distance")
            max_harmonic = max(harmonic.values()) if harmonic else 1.0
            harmonic = {k: v / max(max_harmonic, EPS) for k, v in harmonic.items()}
        except Exception:
            harmonic = {node: np.nan for node in nodes}
    else:
        closeness = {node: np.nan for node in nodes}
        harmonic = {node: np.nan for node in nodes}
    frame["closeness_centrality"] = pd.Series(closeness).reindex(nodes)
    frame["harmonic_centrality"] = pd.Series(harmonic).reindex(nodes)

    # ---- local structure ----------------------------------------------
    try:
        clustering = nx.clustering(graph, weight="weight")
    except Exception:
        clustering = {node: np.nan for node in nodes}
    frame["clustering"] = pd.Series(clustering).reindex(nodes)

    try:
        simple = nx.Graph(graph)
        simple.remove_edges_from(nx.selfloop_edges(simple))
        coreness = nx.core_number(simple)
    except Exception:
        coreness = {node: np.nan for node in nodes}
    frame["coreness"] = pd.Series(coreness).reindex(nodes)

    # ---- communities ----------------------------------------------------
    community = community or detect_communities(
        absolute, nodes, method="auto", seed=seed, sector_of=sector_of
    )
    labels = np.array([community.labels.get(node, -1) for node in nodes])
    frame["community"] = labels
    frame["participation_coefficient"] = participation_coefficient(absolute, labels)
    frame["within_community_degree_z"] = within_community_degree_z(absolute, labels)

    # ---- neighbour aggregation ------------------------------------------
    weights = absolute.copy()
    row_sums = np.clip(weights.sum(axis=1), EPS, None)
    normalized = weights / row_sums[:, None]

    frame["avg_neighbor_strength"] = normalized @ frame["strength"].to_numpy()
    frame["avg_neighbor_degree"] = normalized @ frame["degree"].to_numpy()

    if node_features is not None and not node_features.empty:
        aligned = node_features.reindex(nodes)
        for feature, output in (
            (risk_column, "avg_neighbor_risk"),
            ("volatility_20d", "avg_neighbor_volatility"),
            ("downside_volatility_20d", "neighbor_downside_exposure"),
            ("current_drawdown", "avg_neighbor_drawdown"),
        ):
            if feature in aligned.columns:
                values = aligned[feature].to_numpy(dtype=float)
                filled = np.where(np.isnan(values), np.nanmean(values) if np.isfinite(values).any() else 0.0, values)
                frame[output] = normalized @ filled
            else:
                frame[output] = np.nan
    else:
        for output in (
            "avg_neighbor_risk", "avg_neighbor_volatility",
            "neighbor_downside_exposure", "avg_neighbor_drawdown",
        ):
            frame[output] = np.nan

    # ---- cross-sectional ranks -------------------------------------------
    for column in ("strength", "eigenvector_centrality", "pagerank", "betweenness_centrality"):
        frame[f"rank_{column}"] = frame[column].rank(ascending=False, method="min")

    return frame.reset_index()


def add_temporal_node_metrics(history: pd.DataFrame) -> pd.DataFrame:
    """Add change / acceleration / rank-change columns to a node-metric history.

    `history` is the long frame of `compute_node_metrics` outputs stacked over
    dates. All differences are backward-looking (`.diff()`), so no future data
    enters.
    """
    frame = history.sort_values(["ticker", "date"]).copy()
    grouped = frame.groupby("ticker", sort=False)

    for column in ("strength", "eigenvector_centrality", "pagerank", "degree", "betweenness_centrality"):
        if column not in frame.columns:
            continue
        frame[f"{column}_change_1d"] = grouped[column].diff(1)
        frame[f"{column}_change_5d"] = grouped[column].diff(5)
        frame[f"{column}_change_20d"] = grouped[column].diff(20)
        frame[f"{column}_acceleration"] = grouped[f"{column}_change_1d"].diff(1)
        frame[f"{column}_zscore_60"] = grouped[column].transform(
            lambda s: (s - s.rolling(60, min_periods=20).mean()) / (s.rolling(60, min_periods=20).std(ddof=1) + EPS)
        )

    for column in ("rank_strength", "rank_eigenvector_centrality", "rank_pagerank"):
        if column in frame.columns:
            frame[f"{column}_change_5d"] = -grouped[column].diff(5)  # positive = moved up

    if "community" in frame.columns:
        previous = grouped["community"].shift(1)
        frame["community_changed"] = (frame["community"] != previous) & previous.notna()
        frame["community_changes_20d"] = (
            frame.groupby("ticker", sort=False)["community_changed"]
            .transform(lambda s: s.rolling(20, min_periods=5).sum())
        )
    return frame


def node_edge_turnover(
    current: GraphSnapshot, previous: GraphSnapshot
) -> pd.Series:
    """Per-node Jaccard turnover of its incident edge set."""
    shared = [n for n in current.nodes if n in set(previous.nodes)]
    if not shared:
        return pd.Series(dtype=float)

    current_frame = pd.DataFrame(current.adjacency != 0, index=current.nodes, columns=current.nodes)
    previous_frame = pd.DataFrame(previous.adjacency != 0, index=previous.nodes, columns=previous.nodes)

    out = {}
    for node in shared:
        now = set(current_frame.columns[current_frame.loc[node]]) & set(shared)
        before = set(previous_frame.columns[previous_frame.loc[node]]) & set(shared)
        union = now | before
        out[node] = 1.0 - (len(now & before) / len(union)) if union else np.nan
    return pd.Series(out, name="edge_turnover")


def identify_influence_hubs(
    metrics: pd.DataFrame, top_n: int = 10
) -> pd.DataFrame:
    """Rank nodes by a composite *influence* score.

    Deliberately named "influence", not "transmitter": an undirected graph
    cannot establish direction of propagation. See `transmitters.py` for the
    directed case.
    """
    components = [
        "strength", "eigenvector_centrality", "pagerank",
        "betweenness_centrality", "avg_neighbor_risk",
    ]
    available = [c for c in components if c in metrics.columns and metrics[c].notna().any()]
    if not available:
        return metrics.head(0)

    scores = metrics[available].rank(pct=True)
    out = metrics.copy()
    out["influence_score"] = scores.mean(axis=1)
    out["influence_rank"] = out["influence_score"].rank(ascending=False, method="min")
    out["node_role"] = "high_influence_node"
    return out.sort_values("influence_score", ascending=False).head(top_n)


def identify_vulnerable_nodes(
    metrics: pd.DataFrame, node_features: pd.DataFrame, top_n: int = 10
) -> pd.DataFrame:
    r"""Nodes whose own risk is deteriorating while their network exposure rises.

    Composite of: deep drawdown, high downside volatility, stressed neighbours,
    and rising centrality.
    """
    merged = metrics.set_index("ticker").join(node_features, how="left")
    parts: list[pd.Series] = []

    if "current_drawdown" in merged.columns:
        parts.append((-merged["current_drawdown"]).rank(pct=True))
    if "downside_volatility_20d" in merged.columns:
        parts.append(merged["downside_volatility_20d"].rank(pct=True))
    if "avg_neighbor_risk" in merged.columns:
        parts.append(merged["avg_neighbor_risk"].rank(pct=True))
    if "strength_change_20d" in merged.columns:
        parts.append(merged["strength_change_20d"].rank(pct=True))
    elif "strength" in merged.columns:
        parts.append(merged["strength"].rank(pct=True))

    if not parts:
        return merged.head(0)

    merged["vulnerability_score"] = pd.concat(parts, axis=1).mean(axis=1)
    merged["node_role"] = "vulnerable_node"
    return merged.sort_values("vulnerability_score", ascending=False).head(top_n).reset_index()
