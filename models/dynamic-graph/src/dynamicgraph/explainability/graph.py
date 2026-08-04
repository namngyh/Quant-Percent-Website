"""Graph-side explanations: which nodes, edges and communities drive the score."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.graphs.base import GraphSnapshot
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def node_centrality_contributions(snapshot: GraphSnapshot, top_n: int = 10) -> pd.DataFrame:
    """Each node's share of total network strength and of the leading eigenvector."""
    absolute = np.abs(snapshot.adjacency)
    strength = absolute.sum(axis=1)
    total = strength.sum()

    values, vectors = np.linalg.eigh(0.5 * (absolute + absolute.T))
    leading = np.abs(vectors[:, -1])
    leading = leading / (leading.sum() + 1e-12)

    frame = pd.DataFrame(
        {
            "ticker": snapshot.nodes,
            "strength": strength,
            "strength_share": strength / total if total > 0 else np.nan,
            "eigenvector_share": leading,
            "degree": (absolute > 0).sum(axis=1),
        }
    )
    frame["claim_level"] = "association"
    return frame.sort_values("strength_share", ascending=False).head(top_n).reset_index(drop=True)


def edge_contributions(snapshot: GraphSnapshot, top_n: int = 20) -> pd.DataFrame:
    """Strongest edges, with the share of total edge weight each accounts for."""
    frame = snapshot.edge_list()
    if frame.empty:
        return frame
    total = frame["absolute_weight"].sum()
    frame["weight_share"] = frame["absolute_weight"] / total if total > 0 else np.nan
    frame["claim_level"] = "association"
    return frame.sort_values("absolute_weight", ascending=False).head(top_n).reset_index(drop=True)


def community_contributions(
    snapshot: GraphSnapshot, communities: dict[str, int], sector_of: dict[str, str] | None = None
) -> pd.DataFrame:
    """Internal / external weight per community, plus sector composition."""
    absolute = np.abs(snapshot.adjacency)
    labels = np.array([communities.get(n, -1) for n in snapshot.nodes])
    rows = []
    for community in sorted(set(labels)):
        mask = labels == community
        members = [n for n, m in zip(snapshot.nodes, mask) if m]
        internal = absolute[np.ix_(mask, mask)].sum() / 2.0
        external = absolute[np.ix_(mask, ~mask)].sum()
        composition: dict[str, int] = {}
        dominant_sector = None
        dominant_share = np.nan
        if sector_of and members:
            counts = pd.Series([sector_of.get(m, "UNKNOWN") for m in members]).value_counts()
            composition = counts.to_dict()
            dominant_sector = str(counts.index[0])
            dominant_share = float(counts.iloc[0] / len(members))
        rows.append(
            {
                "community": int(community),
                "size": len(members),
                "members": ", ".join(members),
                "internal_weight": float(internal),
                "external_weight": float(external),
                "cohesion": float(internal / (internal + external)) if (internal + external) > 0 else np.nan,
                "dominant_sector": dominant_sector,
                # Share of the community occupied by its modal sector. A modal
                # sector with a small share means the community is genuinely
                # mixed and should not be described as "mostly <sector>".
                "dominant_sector_share": dominant_share,
                "sector_composition": composition,
            }
        )
    return pd.DataFrame(rows).sort_values("size", ascending=False).reset_index(drop=True)


def stress_contribution_breakdown(
    stress_model: Any, scores: pd.DataFrame, date: pd.Timestamp, top_n: int = 8
) -> pd.DataFrame:
    """Which network metrics pushed the descriptive stress score up or down today."""
    try:
        frame = stress_model.contribution_table(scores, date)
    except Exception as exc:
        logger.warning("Stress contribution breakdown failed: %s", exc)
        return pd.DataFrame()
    frame["direction"] = np.where(frame["contribution"] > 0, "raises_stress", "lowers_stress")
    frame["claim_level"] = "association"
    return frame.head(top_n)


def multiscale_contributions(metrics_by_window: dict[int, pd.DataFrame], date: pd.Timestamp) -> pd.DataFrame:
    """Compare the same metric across scales on one date."""
    rows = []
    for window, frame in sorted(metrics_by_window.items()):
        if frame.empty or date not in frame.index:
            continue
        row = frame.loc[date]
        rows.append(
            {
                "window": window,
                "graph_density": row.get("graph_density"),
                "spectral_radius": row.get("spectral_radius"),
                "modularity": row.get("modularity"),
                "number_of_communities": row.get("number_of_communities"),
                "centrality_concentration": row.get("centrality_concentration"),
            }
        )
    return pd.DataFrame(rows)


def node_masking_analysis(
    snapshot: GraphSnapshot, metric_fn: Any = None, top_n: int = 10
) -> pd.DataFrame:
    """Leave-one-node-out: how much does removing each node change the spectrum?

    A large drop identifies a node the current structure depends on. It does NOT
    mean removing that stock would calm the market.
    """
    from dynamicgraph.network.spectral import spectral_radius

    metric_fn = metric_fn or spectral_radius
    baseline = float(metric_fn(snapshot.adjacency))
    rows = []
    for i, node in enumerate(snapshot.nodes):
        keep = [j for j in range(snapshot.n_nodes) if j != i]
        reduced = snapshot.adjacency[np.ix_(keep, keep)]
        try:
            value = float(metric_fn(reduced))
        except Exception:
            value = np.nan
        rows.append(
            {
                "removed_node": node,
                "metric_without_node": value,
                "baseline": baseline,
                "absolute_change": value - baseline,
                "relative_change": (value - baseline) / (abs(baseline) + 1e-12),
            }
        )
    frame = pd.DataFrame(rows)
    frame["claim_level"] = "association"
    frame["note"] = "Structural sensitivity of the estimated graph, not an intervention effect."
    return frame.reindex(frame["absolute_change"].abs().sort_values(ascending=False).index).head(top_n).reset_index(drop=True)


def edge_masking_analysis(snapshot: GraphSnapshot, top_n: int = 15) -> pd.DataFrame:
    """Leave-one-edge-out effect on the spectral radius."""
    from dynamicgraph.network.spectral import spectral_radius

    baseline = spectral_radius(snapshot.adjacency)
    i, j = np.triu_indices(snapshot.n_nodes, k=1)
    nonzero = np.where(snapshot.adjacency[i, j] != 0)[0]

    rows = []
    for k in nonzero:
        a, b = int(i[k]), int(j[k])
        masked = snapshot.adjacency.copy()
        masked[a, b] = masked[b, a] = 0.0
        rows.append(
            {
                "source": snapshot.nodes[a],
                "target": snapshot.nodes[b],
                "weight": float(snapshot.adjacency[a, b]),
                "spectral_radius_without_edge": float(spectral_radius(masked)),
                "change": float(spectral_radius(masked) - baseline),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.reindex(frame["change"].abs().sort_values(ascending=False).index).head(top_n).reset_index(drop=True)
