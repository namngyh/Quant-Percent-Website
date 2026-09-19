"""Node-level and graph-level network metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.graphs.base import GraphSnapshot
from dynamicgraph.graphs.stability import edge_survival, edge_turnover
from dynamicgraph.network.communities import compare_partitions, detect_communities, modularity
from dynamicgraph.network.graph_metrics import compute_graph_metrics, herfindahl
from dynamicgraph.network.mst import correlation_distance, mst_summary
from dynamicgraph.network.node_metrics import compute_node_metrics
from dynamicgraph.network.spectral import (
    algebraic_connectivity,
    laplacian_entropy,
    spectral_radius,
)


def _snapshot(adjacency: np.ndarray, nodes: list[str] | None = None) -> GraphSnapshot:
    nodes = nodes or [f"N{i}" for i in range(adjacency.shape[0])]
    return GraphSnapshot(
        date=pd.Timestamp("2024-01-02"), nodes=nodes, adjacency=adjacency,
        layer="partial_correlation", window=60, return_type="residual",
    )


def test_graph_snapshot_keeps_raw_inference_and_display_separate(tmp_path):
    from dynamicgraph.graphs.base import SnapshotSeries

    nodes = ["A", "B", "C"]
    raw = np.array(
        [[0.0, 0.4, 0.2], [0.4, 0.0, 0.1], [0.2, 0.1, 0.0]]
    )
    inference = np.array(
        [[0.0, 0.4, 0.0], [0.4, 0.0, 0.0], [0.0, 0.0, 0.0]]
    )
    display = np.array(
        [[0.0, 0.0, 0.2], [0.0, 0.0, 0.0], [0.2, 0.0, 0.0]]
    )
    snapshot = GraphSnapshot(
        date=pd.Timestamp("2024-01-31"),
        nodes=nodes,
        adjacency=inference,
        adjacency_raw=raw,
        adjacency_inference=inference,
        adjacency_display=display,
        metadata={"nodes": nodes},
    )

    np.testing.assert_allclose(snapshot.adjacency, inference)
    np.testing.assert_allclose(snapshot.matrix("raw"), raw)
    assert snapshot.edge_list().iloc[0]["target"] == "C"

    series = SnapshotSeries([snapshot])
    series.save(tmp_path)
    loaded = SnapshotSeries.load(tmp_path, series.key)[0]
    np.testing.assert_allclose(loaded.adjacency_raw, raw)
    np.testing.assert_allclose(loaded.adjacency_inference, inference)
    np.testing.assert_allclose(loaded.adjacency_display, display)


def _two_blocks(block_size: int = 5, within: float = 0.6, across: float = 0.02) -> np.ndarray:
    n = 2 * block_size
    adjacency = np.full((n, n), across)
    adjacency[:block_size, :block_size] = within
    adjacency[block_size:, block_size:] = within
    np.fill_diagonal(adjacency, 0.0)
    return adjacency


def test_density_formula():
    adjacency = np.zeros((5, 5))
    adjacency[0, 1] = adjacency[1, 0] = 0.5
    adjacency[2, 3] = adjacency[3, 2] = 0.4
    snapshot = _snapshot(adjacency)
    assert snapshot.n_edges == 2
    assert snapshot.density == pytest.approx(2 * 2 / (5 * 4))


def test_complete_graph_has_density_one():
    adjacency = np.ones((6, 6))
    np.fill_diagonal(adjacency, 0.0)
    assert _snapshot(adjacency).density == pytest.approx(1.0)


def test_node_strength_and_degree():
    adjacency = np.array([
        [0.0, 0.5, -0.3, 0.0],
        [0.5, 0.0, 0.0, 0.2],
        [-0.3, 0.0, 0.0, 0.0],
        [0.0, 0.2, 0.0, 0.0],
    ])
    metrics = compute_node_metrics(_snapshot(adjacency)).set_index("ticker")
    assert metrics.loc["N0", "strength"] == pytest.approx(0.8)
    assert metrics.loc["N0", "degree"] == 2
    assert metrics.loc["N0", "positive_strength"] == pytest.approx(0.5)
    assert metrics.loc["N0", "negative_strength"] == pytest.approx(0.3)
    assert metrics.loc["N0", "edge_sign_ratio"] == pytest.approx(0.5 / 0.8)


def test_centrality_uses_absolute_weights():
    """A purely negative graph must still produce finite centralities."""
    adjacency = -np.abs(_two_blocks())
    metrics = compute_node_metrics(_snapshot(adjacency))
    assert (metrics["weights_used"] == "absolute").all()
    assert metrics["eigenvector_centrality"].notna().all()
    assert (metrics["pagerank"] > 0).all()


def test_pagerank_sums_to_one():
    metrics = compute_node_metrics(_snapshot(_two_blocks()))
    assert metrics["pagerank"].sum() == pytest.approx(1.0, abs=1e-6)


def test_hub_has_the_highest_centrality():
    n = 8
    adjacency = np.zeros((n, n))
    adjacency[0, 1:] = adjacency[1:, 0] = 0.8          # star centred on node 0
    metrics = compute_node_metrics(_snapshot(adjacency)).set_index("ticker")
    assert metrics["strength"].idxmax() == "N0"
    assert metrics["eigenvector_centrality"].idxmax() == "N0"
    assert metrics["betweenness_centrality"].idxmax() == "N0"


def test_spectral_radius_of_a_star_graph():
    """lambda_max of an unweighted star with n leaves is sqrt(n)."""
    n_leaves = 9
    adjacency = np.zeros((n_leaves + 1, n_leaves + 1))
    adjacency[0, 1:] = adjacency[1:, 0] = 1.0
    assert spectral_radius(adjacency) == pytest.approx(np.sqrt(n_leaves), rel=1e-6)


def test_algebraic_connectivity_is_zero_when_disconnected():
    adjacency = np.zeros((6, 6))
    adjacency[0, 1] = adjacency[1, 0] = 1.0
    adjacency[3, 4] = adjacency[4, 3] = 1.0
    assert algebraic_connectivity(adjacency) == pytest.approx(0.0, abs=1e-9)


def test_laplacian_entropy_higher_for_uniform_graph():
    uniform = np.ones((8, 8))
    np.fill_diagonal(uniform, 0.0)
    star = np.zeros((8, 8))
    star[0, 1:] = star[1:, 0] = 1.0
    assert laplacian_entropy(uniform) > laplacian_entropy(star)


def test_herfindahl_bounds():
    equal = np.ones(10)
    assert herfindahl(equal) == pytest.approx(0.1)
    concentrated = np.array([1.0] + [0.0] * 9)
    assert herfindahl(concentrated) == pytest.approx(1.0)


def test_community_detection_finds_two_blocks():
    result = detect_communities(_two_blocks(block_size=6, within=0.9, across=0.01),
                                [f"N{i}" for i in range(12)])
    assert result.n_communities >= 2
    labels = [result.labels[f"N{i}"] for i in range(12)]
    assert len(set(labels[:6])) == 1
    assert len(set(labels[6:])) == 1
    assert labels[0] != labels[6]
    assert result.modularity > 0.2


def test_modularity_is_higher_for_the_true_partition():
    adjacency = _two_blocks(block_size=6, within=0.9, across=0.01)
    true_labels = np.array([0] * 6 + [1] * 6)
    scrambled = np.array([0, 1] * 6)
    assert modularity(adjacency, true_labels) > modularity(adjacency, scrambled)


def test_compare_partitions_identical_gives_one():
    labels = {f"N{i}": i % 3 for i in range(9)}
    result = compare_partitions(labels, labels)
    assert result["ari"] == pytest.approx(1.0)
    assert result["nmi"] == pytest.approx(1.0)
    assert result["jaccard"] == pytest.approx(1.0)


def test_edge_turnover_and_survival():
    a = np.zeros((4, 4))
    a[0, 1] = a[1, 0] = 1.0
    a[2, 3] = a[3, 2] = 1.0
    b = np.zeros((4, 4))
    b[0, 1] = b[1, 0] = 1.0
    b[0, 2] = b[2, 0] = 1.0

    assert edge_survival(b, a) == pytest.approx(0.5)     # 1 of a's 2 edges survives
    assert edge_turnover(b, a) == pytest.approx(1 - 1 / 3)  # |∩|=1, |∪|=3


def test_graph_metrics_include_the_required_fields():
    snapshot = _snapshot(_two_blocks(block_size=6))
    correlation = np.clip(snapshot.adjacency + np.eye(12), -1, 1)
    metrics = compute_graph_metrics(snapshot, correlation=correlation)
    for key in (
        "number_of_nodes", "number_of_edges", "graph_density", "average_strength",
        "spectral_radius", "modularity", "number_of_communities", "largest_cc_share",
        "centrality_concentration", "market_mode_share", "mst_length",
        "positive_edge_ratio", "negative_edge_ratio", "average_clustering",
    ):
        assert key in metrics, f"missing graph metric `{key}`"
    assert metrics["number_of_nodes"] == 12
    assert 0 <= metrics["graph_density"] <= 1


def test_edge_turnover_is_nan_without_a_predecessor():
    metrics = compute_graph_metrics(_snapshot(_two_blocks()), previous=None)
    assert np.isnan(metrics["edge_turnover"])


def test_market_mode_share_rises_with_common_movement():
    from dynamicgraph.graphs.correlation import market_mode_share

    n = 10
    weak = np.eye(n) + 0.05 * (np.ones((n, n)) - np.eye(n))
    strong = np.eye(n) + 0.85 * (np.ones((n, n)) - np.eye(n))
    assert market_mode_share(strong) > market_mode_share(weak)
    assert 0 < market_mode_share(weak) < 1


def test_mst_length_shrinks_as_correlation_rises():
    n = 8
    weak = np.eye(n) + 0.1 * (np.ones((n, n)) - np.eye(n))
    strong = np.eye(n) + 0.9 * (np.ones((n, n)) - np.eye(n))
    nodes = [f"N{i}" for i in range(n)]
    assert mst_summary(strong, nodes)["mst_length"] < mst_summary(weak, nodes)["mst_length"]


def test_correlation_distance_is_a_metric_at_the_extremes():
    perfect = np.array([[1.0, 1.0], [1.0, 1.0]])
    opposite = np.array([[1.0, -1.0], [-1.0, 1.0]])
    assert correlation_distance(perfect)[0, 1] == pytest.approx(0.0)
    assert correlation_distance(opposite)[0, 1] == pytest.approx(2.0)


def test_snapshot_edge_list_round_trip():
    adjacency = np.zeros((4, 4))
    adjacency[0, 1] = adjacency[1, 0] = 0.5
    adjacency[2, 3] = adjacency[3, 2] = -0.4
    edges = _snapshot(adjacency).edge_list()
    assert len(edges) == 2
    assert set(edges["edge_sign"]) == {1, -1}
    assert (edges["absolute_weight"] >= 0).all()
