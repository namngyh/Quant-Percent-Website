r"""Minimum spanning tree of the correlation/partial-correlation graph.

The classical Mantegna distance turns a correlation into a metric:

    d_ij = sqrt(2 (1 - rho_ij))

so strongly co-moving stocks sit close together. The total MST length is a
long-standing market-integration measure: it *shrinks* when everything starts
moving together, which is why it enters the stress score with a negative sign.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS


def correlation_distance(correlation: np.ndarray) -> np.ndarray:
    r"""d_ij = sqrt(2 (1 - rho_ij)), with a zero diagonal."""
    rho = np.clip(correlation, -1.0, 1.0)
    distance = np.sqrt(np.clip(2.0 * (1.0 - rho), 0.0, None))
    np.fill_diagonal(distance, 0.0)
    return distance


def weight_distance(adjacency: np.ndarray) -> np.ndarray:
    """Distance for a general weighted graph: 1/|w| (infinite for absent edges)."""
    weights = np.abs(adjacency)
    with np.errstate(divide="ignore"):
        distance = np.where(weights > EPS, 1.0 / np.clip(weights, EPS, None), np.inf)
    np.fill_diagonal(distance, 0.0)
    return distance


def minimum_spanning_tree(distance: np.ndarray, nodes: list[str]):
    """MST as a NetworkX graph. Disconnected inputs give a spanning forest."""
    import networkx as nx

    n = len(nodes)
    graph = nx.Graph()
    graph.add_nodes_from(nodes)
    for i in range(n):
        for j in range(i + 1, n):
            d = distance[i, j]
            if np.isfinite(d) and d > 0:
                graph.add_edge(nodes[i], nodes[j], weight=float(d))
    if graph.number_of_edges() == 0:
        return graph
    return nx.minimum_spanning_tree(graph, weight="weight")


def mst_length(distance: np.ndarray, nodes: list[str]) -> float:
    """Total edge length of the MST (normalised by N-1)."""
    tree = minimum_spanning_tree(distance, nodes)
    if tree.number_of_edges() == 0:
        return float("nan")
    total = sum(w for _, _, w in tree.edges(data="weight"))
    return float(total / max(tree.number_of_edges(), 1))


def mst_summary(correlation: np.ndarray, nodes: list[str]) -> dict[str, float]:
    """MST length plus its degree profile (a hub-detection diagnostic)."""
    distance = correlation_distance(correlation)
    tree = minimum_spanning_tree(distance, nodes)
    if tree.number_of_edges() == 0:
        return {"mst_length": float("nan"), "mst_max_degree": float("nan"), "mst_diameter": float("nan")}

    import networkx as nx

    degrees = dict(tree.degree())
    lengths = [w for _, _, w in tree.edges(data="weight")]
    try:
        diameter = float(nx.diameter(tree)) if nx.is_connected(tree) else float("nan")
    except Exception:
        diameter = float("nan")
    return {
        "mst_length": float(np.sum(lengths) / max(len(lengths), 1)),
        "mst_total_length": float(np.sum(lengths)),
        "mst_max_degree": float(max(degrees.values())),
        "mst_mean_degree": float(np.mean(list(degrees.values()))),
        "mst_diameter": diameter,
    }


def mst_edge_frame(correlation: np.ndarray, nodes: list[str], date: pd.Timestamp) -> pd.DataFrame:
    tree = minimum_spanning_tree(correlation_distance(correlation), nodes)
    rows = [
        {"date": date, "source": u, "target": v, "distance": float(w), "edge_type": "mst"}
        for u, v, w in tree.edges(data="weight")
    ]
    return pd.DataFrame(rows)
