r"""Graph-level metrics, one row per snapshot.

Key formulas:
    Density_t   = 2|E_t| / [N_t (N_t - 1)]
    SR_t        = lambda_max(|A_t|)
    MMS_t       = lambda_1(C_t) / trace(C_t)
    H_t         = sum_i (s_i / sum_j s_j)^2                (Herfindahl)
    Turnover_t  = 1 - |E_t ∩ E_{t-1}| / |E_t ∪ E_{t-1}|
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS
from dynamicgraph.graphs.base import GraphSnapshot
from dynamicgraph.graphs.correlation import (
    eigenvalue_concentration as correlation_eigenvalue_concentration,
    market_mode_share,
    negative_diversification_proxy,
)
from dynamicgraph.graphs.stability import edge_turnover
from dynamicgraph.logging_config import get_logger
from dynamicgraph.network.communities import CommunityResult, compare_partitions, detect_communities
from dynamicgraph.network.mst import mst_summary
from dynamicgraph.network.spectral import (
    algebraic_connectivity,
    eigenvalue_concentration,
    laplacian_entropy,
    spectral_gap,
    spectral_radius,
)

logger = get_logger(__name__)


def herfindahl(values: np.ndarray) -> float:
    total = np.nansum(values)
    if total <= EPS:
        return float("nan")
    shares = values / total
    return float(np.nansum(shares**2))


def compute_graph_metrics(
    snapshot: GraphSnapshot,
    previous: GraphSnapshot | None = None,
    community: CommunityResult | None = None,
    previous_community: CommunityResult | None = None,
    correlation: np.ndarray | None = None,
    sector_of: dict[str, str] | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """All graph-level metrics for a single snapshot."""
    import networkx as nx

    nodes = snapshot.nodes
    signed = snapshot.adjacency
    absolute = np.abs(signed)
    n = len(nodes)

    metrics: dict[str, Any] = {
        "date": snapshot.date,
        "layer": snapshot.layer,
        "window": snapshot.window,
        "return_type": snapshot.return_type,
        "number_of_nodes": n,
        "number_of_edges": snapshot.n_edges,
        "graph_density": snapshot.density,
        "alpha": snapshot.alpha,
        "n_excluded_nodes": snapshot.n_excluded_nodes,
    }
    if n < 3:
        return metrics

    i, j = np.triu_indices(n, k=1)
    weights = signed[i, j]
    nonzero = weights[weights != 0]

    strength = absolute.sum(axis=1)
    degree = (absolute > 0).sum(axis=1)

    metrics.update(
        {
            "average_degree": float(degree.mean()),
            "average_strength": float(strength.mean()),
            "median_strength": float(np.median(strength)),
            "maximum_strength": float(strength.max()),
            "edge_weight_mean": float(np.abs(nonzero).mean()) if nonzero.size else float("nan"),
            "edge_weight_std": float(np.abs(nonzero).std(ddof=1)) if nonzero.size > 1 else float("nan"),
            "average_absolute_weight": float(np.abs(weights).mean()),
            "average_signed_weight": float(weights.mean()),
            "positive_edge_ratio": float(np.mean(nonzero > 0)) if nonzero.size else float("nan"),
            "negative_edge_ratio": float(np.mean(nonzero < 0)) if nonzero.size else float("nan"),
            "centrality_concentration": herfindahl(strength),
        }
    )
    if snapshot.layer.startswith("partial"):
        metrics["avg_abs_partial_correlation"] = float(np.abs(weights).mean())
        metrics["average_partial_correlation"] = float(weights.mean())
    else:
        metrics["average_absolute_correlation"] = float(np.abs(weights).mean())

    graph = snapshot.to_networkx(use_absolute=True)
    try:
        metrics["average_clustering"] = float(nx.average_clustering(graph, weight="weight"))
    except Exception:
        metrics["average_clustering"] = float("nan")
    try:
        metrics["global_transitivity"] = float(nx.transitivity(nx.Graph(graph)))
    except Exception:
        metrics["global_transitivity"] = float("nan")
    try:
        metrics["assortativity"] = float(
            nx.degree_assortativity_coefficient(graph, weight="weight")
        )
    except Exception:
        metrics["assortativity"] = float("nan")

    try:
        components = list(nx.connected_components(graph))
        largest = max((len(c) for c in components), default=0)
        metrics["largest_cc_share"] = float(largest / n)
        metrics["n_connected_components"] = len(components)
    except Exception:
        metrics["largest_cc_share"] = float("nan")
        metrics["n_connected_components"] = np.nan

    metrics["spectral_radius"] = spectral_radius(signed)
    metrics["algebraic_connectivity"] = algebraic_connectivity(signed)
    metrics["laplacian_entropy"] = laplacian_entropy(signed)
    metrics["spectral_gap"] = spectral_gap(signed)
    metrics["eigenvalue_concentration"] = eigenvalue_concentration(signed)

    community = community or detect_communities(
        absolute, nodes, method="auto", seed=seed, sector_of=sector_of
    )
    sizes = np.array(list(community.sizes.values()), dtype=float) if community.sizes else np.array([n])
    metrics.update(
        {
            "modularity": community.modularity,
            "number_of_communities": community.n_communities,
            "largest_community_share": float(sizes.max() / n),
            "community_size_herfindahl": herfindahl(sizes),
            "community_method": community.method,
            "sector_purity": community.sector_purity,
            # Compression: 1 community = fully compressed market structure.
            "community_compression": float(1.0 - (community.n_communities - 1) / max(n - 1, 1)),
        }
    )

    if correlation is not None:
        metrics["market_mode_share"] = market_mode_share(correlation)
        metrics["correlation_eigenvalue_concentration"] = correlation_eigenvalue_concentration(correlation)
        metrics["negative_diversification"] = negative_diversification_proxy(correlation)
        metrics.update(mst_summary(correlation, nodes))
    else:
        metrics["market_mode_share"] = np.nan
        metrics["negative_diversification"] = np.nan
        metrics["mst_length"] = np.nan

    # Fragility proxy: dense + concentrated + tightly bound = fragile.
    fragility_parts = [
        metrics.get("graph_density"),
        metrics.get("centrality_concentration"),
        metrics.get("largest_cc_share"),
    ]
    valid = [p for p in fragility_parts if p is not None and np.isfinite(p)]
    metrics["network_fragility"] = float(np.mean(valid)) if valid else np.nan

    if previous is not None:
        shared = [node for node in nodes if node in set(previous.nodes)]
        if len(shared) >= 3:
            current_frame = pd.DataFrame(signed, index=nodes, columns=nodes).loc[shared, shared]
            previous_frame = pd.DataFrame(
                previous.adjacency, index=previous.nodes, columns=previous.nodes
            ).loc[shared, shared]
            metrics["edge_turnover"] = edge_turnover(
                current_frame.to_numpy(), previous_frame.to_numpy()
            )
        else:
            metrics["edge_turnover"] = np.nan
    else:
        metrics["edge_turnover"] = np.nan

    if previous_community is not None:
        comparison = compare_partitions(community.labels, previous_community.labels)
        metrics["community_ari"] = comparison["ari"]
        metrics["community_nmi"] = comparison["nmi"]
        metrics["community_jaccard"] = comparison["jaccard"]
        metrics["community_turnover"] = 1.0 - comparison["nmi"] if np.isfinite(comparison["nmi"]) else np.nan
    else:
        metrics["community_ari"] = np.nan
        metrics["community_nmi"] = np.nan
        metrics["community_jaccard"] = np.nan
        metrics["community_turnover"] = np.nan

    return metrics


def compute_metric_series(
    snapshots: list[GraphSnapshot],
    correlations: dict[pd.Timestamp, np.ndarray] | None = None,
    sector_of: dict[str, str] | None = None,
    seed: int = 42,
    return_communities: bool = False,
) -> tuple[pd.DataFrame, dict[pd.Timestamp, CommunityResult]]:
    """Metric history over a snapshot series, plus the community results."""
    rows: list[dict[str, Any]] = []
    communities: dict[pd.Timestamp, CommunityResult] = {}
    previous: GraphSnapshot | None = None
    previous_community: CommunityResult | None = None

    for snapshot in snapshots:
        community = detect_communities(
            np.abs(snapshot.adjacency), snapshot.nodes, method="auto", seed=seed, sector_of=sector_of
        )
        correlation = correlations.get(snapshot.date) if correlations else None
        rows.append(
            compute_graph_metrics(
                snapshot,
                previous=previous,
                community=community,
                previous_community=previous_community,
                correlation=correlation,
                sector_of=sector_of,
                seed=seed,
            )
        )
        communities[snapshot.date] = community
        previous, previous_community = snapshot, community

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.set_index("date").sort_index()
    logger.info("Computed graph metrics for %d snapshot(s).", len(frame))
    return frame, (communities if return_communities else {})


def add_dynamics(metrics: pd.DataFrame, windows: tuple[int, ...] = (5, 20, 60)) -> pd.DataFrame:
    """Add trailing changes and z-scores of every numeric graph metric."""
    frame = metrics.copy()
    numeric = [
        c for c in frame.columns
        if pd.api.types.is_numeric_dtype(frame[c]) and not c.startswith(("n_", "number_of_nodes"))
    ]
    for column in numeric:
        for window in windows:
            frame[f"{column}_chg_{window}d"] = frame[column].diff(window)
        frame[f"{column}_z60"] = (
            frame[column] - frame[column].rolling(60, min_periods=20).mean()
        ) / (frame[column].rolling(60, min_periods=20).std(ddof=1) + EPS)
        frame[f"{column}_pct252"] = frame[column].rolling(252, min_periods=60).rank(pct=True)
    return frame
