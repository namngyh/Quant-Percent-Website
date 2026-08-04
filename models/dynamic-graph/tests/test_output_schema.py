"""Website output schema and terminology discipline."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.constants import INFLUENCE_LABEL, RECEIVER_LABEL, TRANSMITTER_LABEL
from dynamicgraph.graphs.base import DirectedSnapshot, GraphSnapshot
from dynamicgraph.network.communities import detect_communities
from dynamicgraph.network.node_metrics import compute_node_metrics
from dynamicgraph.network.transmitters import directed_roles, influence_nodes
from dynamicgraph.outputs.exporters import _sanitize, export_json
from dynamicgraph.outputs.schemas import REQUIRED_TOP_LEVEL_KEYS, empty_payload, validate_payload
from dynamicgraph.outputs.website_json import build_edges_json, build_nodes_json, build_website_payload


@pytest.fixture
def snapshot() -> GraphSnapshot:
    rng = np.random.default_rng(51)
    n = 8
    adjacency = rng.uniform(0.1, 0.8, (n, n))
    adjacency = (adjacency + adjacency.T) / 2
    np.fill_diagonal(adjacency, 0.0)
    adjacency[0, 1] = adjacency[1, 0] = -0.4
    return GraphSnapshot(
        date=pd.Timestamp("2026-07-24"),
        nodes=[f"TK{i}" for i in range(n)],
        adjacency=adjacency,
        layer="partial_correlation",
        window=60,
        return_type="residual",
    )


def test_empty_payload_has_every_required_key():
    payload = empty_payload()
    for key in REQUIRED_TOP_LEVEL_KEYS:
        assert key in payload


def test_validate_payload_catches_bad_probabilities():
    payload = empty_payload()
    payload["model"].update(
        {"name": "DynamicGraph", "version": "0.1.0", "generated_at": "x", "as_of_date": "2026-07-24"}
    )
    payload["stress_probabilities"] = {"5d": {"probability": 1.7}}
    problems = validate_payload(payload)
    assert any("outside [0, 1]" in p for p in problems)


def test_validate_payload_catches_out_of_range_stress_score():
    payload = empty_payload()
    payload["model"].update(
        {"name": "D", "version": "1", "generated_at": "x", "as_of_date": "2026-07-24"}
    )
    payload["network_state"]["stress_score"] = 150.0
    assert any("stress_score outside" in p for p in validate_payload(payload))


def test_validate_payload_rejects_transmitter_label_on_undirected_nodes():
    payload = empty_payload()
    payload["model"].update(
        {"name": "D", "version": "1", "generated_at": "x", "as_of_date": "2026-07-24"}
    )
    payload["leading_influence_nodes"] = [{"id": "AAA", "role": TRANSMITTER_LABEL}]
    problems = validate_payload(payload)
    assert any("may not be labelled as a transmitter" in p for p in problems)


def test_nodes_json_shape_matches_the_documented_contract(snapshot):
    metrics = compute_node_metrics(snapshot)
    features = pd.DataFrame(
        {
            "return_20d": np.linspace(-0.1, 0.1, snapshot.n_nodes),
            "volatility_20d": np.linspace(0.2, 0.5, snapshot.n_nodes),
            "current_drawdown": np.linspace(-0.3, 0.0, snapshot.n_nodes),
        },
        index=snapshot.nodes,
    )
    communities = detect_communities(np.abs(snapshot.adjacency), snapshot.nodes)
    sector_of = {t: "Banks" for t in snapshot.nodes}

    nodes = build_nodes_json(snapshot, metrics, features, sector_of, communities)
    assert len(nodes) == snapshot.n_nodes
    for record in nodes:
        for key in (
            "id", "label", "sector", "community", "strength",
            "eigenvector_centrality", "pagerank", "risk_score", "return_20d", "volatility_20d",
        ):
            assert key in record, f"nodes.json missing `{key}`"
        assert isinstance(record["id"], str)
        assert isinstance(record["community"], int)


def test_edges_json_shape_matches_the_documented_contract(snapshot):
    edges = build_edges_json(snapshot)
    assert edges
    for record in edges:
        for key in (
            "source", "target", "weight", "signed_weight", "absolute_weight",
            "edge_type", "window", "stability", "direction",
        ):
            assert key in record, f"edges.json missing `{key}`"
        assert record["absolute_weight"] >= 0
        assert record["direction"] is None


def test_directed_edges_are_marked(snapshot):
    directed = DirectedSnapshot(
        date=snapshot.date,
        nodes=snapshot.nodes,
        adjacency=np.triu(np.abs(snapshot.adjacency), 1),
        layer="lead_lag",
        window=120,
    )
    edges = build_edges_json(snapshot, directed)
    assert any(e["direction"] == "directed" for e in edges)
    assert any(e["edge_type"] == "lead_lag" for e in edges)


def test_influence_nodes_are_never_labelled_transmitters(snapshot):
    metrics = compute_node_metrics(snapshot)
    frame = influence_nodes(metrics, top_n=5)
    assert (frame["role"] == INFLUENCE_LABEL).all()
    assert not frame["causal_language_allowed"].any()


def test_no_directed_layer_means_no_transmitter_output():
    roles = directed_roles(None)
    assert not roles.available
    assert roles.transmitters().empty
    assert roles.receivers().empty


def test_directed_roles_split_by_net_spillover(snapshot):
    adjacency = np.zeros((snapshot.n_nodes, snapshot.n_nodes))
    adjacency[0, 1:] = 0.5           # node 0 sends to everyone
    directed = DirectedSnapshot(
        date=snapshot.date, nodes=snapshot.nodes, adjacency=adjacency, layer="lead_lag", window=120
    )
    roles = directed_roles(directed)
    assert roles.available
    assert roles.frame.iloc[0]["ticker"] == "TK0"
    assert roles.frame.iloc[0]["role"] == TRANSMITTER_LABEL
    assert (roles.receivers()["role"] == RECEIVER_LABEL).all()
    assert not roles.causal_language_allowed


def test_sanitize_removes_nan_and_numpy_types():
    payload = {
        "a": np.float64(1.5),
        "b": np.int64(3),
        "c": float("nan"),
        "d": float("inf"),
        "e": np.array([1.0, np.nan]),
        "f": pd.Timestamp("2026-01-01"),
        "g": np.bool_(True),
    }
    clean = _sanitize(payload)
    assert clean["a"] == 1.5 and isinstance(clean["a"], float)
    assert clean["b"] == 3 and isinstance(clean["b"], int)
    assert clean["c"] is None and clean["d"] is None
    assert clean["e"] == [1.0, None]
    assert clean["f"].startswith("2026-01-01")
    assert clean["g"] is True


def test_exported_json_is_parseable(tmp_path, snapshot):
    payload = empty_payload()
    payload["network_state"]["stress_score"] = np.float64("nan")
    path = export_json(payload, tmp_path / "out.json")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["network_state"]["stress_score"] is None


def test_website_payload_carries_disclaimers_and_survivorship_warning(snapshot):
    from types import SimpleNamespace

    from dynamicgraph.config import load_config

    config = load_config("config/default.yaml")
    metrics = compute_node_metrics(snapshot)
    features = pd.DataFrame(
        {"volatility_20d": np.linspace(0.2, 0.4, snapshot.n_nodes),
         "current_drawdown": np.linspace(-0.2, 0.0, snapshot.n_nodes),
         "return_20d": np.zeros(snapshot.n_nodes),
         "downside_volatility_20d": np.linspace(0.1, 0.3, snapshot.n_nodes),
         "sector": ["Banks"] * snapshot.n_nodes},
        index=snapshot.nodes,
    )
    stress = pd.DataFrame(
        {"stress_raw": [0.4], "stress_score": [62.0], "stress_percentile": [0.8],
         "stress_change_1d": [1.0], "stress_change_5d": [3.0], "stress_change_20d": [8.0]},
        index=[snapshot.date],
    )
    universe = SimpleNamespace(survivorship_bias=True, method="static_list")

    payload = build_website_payload(
        config=config,
        as_of_date=snapshot.date,
        snapshot=snapshot,
        node_metrics=metrics,
        node_features=features,
        graph_metrics_row=pd.Series({"graph_density": 0.3, "spectral_radius": 1.2}),
        stress_scores=stress,
        stress_state="elevated",
        stress_contributions=pd.DataFrame(),
        communities=detect_communities(np.abs(snapshot.adjacency), snapshot.nodes),
        universe=universe,
    )
    assert payload["disclaimers"]
    assert any("SURVIVORSHIP" in w.upper() for w in payload["warnings"])
    assert payload["risk_transmitters"] == []
    assert payload["directed_layer"]["available"] is False
    assert not validate_payload(payload)


def test_no_causal_language_in_generated_labels():
    """The vocabulary must never assert causation from an undirected graph."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "dynamicgraph"
    banned = ("causes ", "caused by", "is the cause")
    offenders = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for phrase in banned:
            if phrase in text and "not " + phrase not in text:
                offenders.append(f"{path.name}: '{phrase}'")
    assert not offenders, f"Causal language found: {offenders}"


def test_nodes_json_is_ordered_by_centrality(snapshot):
    """An alphabetical dump forces every consumer to re-sort before it can show
    anything, and is unreadable by eye. Most-central must come first."""
    metrics = compute_node_metrics(snapshot)
    features = pd.DataFrame(
        {
            "return_20d": np.linspace(-0.1, 0.1, snapshot.n_nodes),
            "volatility_20d": np.linspace(0.2, 0.5, snapshot.n_nodes),
            "current_drawdown": np.linspace(-0.3, 0.0, snapshot.n_nodes),
        },
        index=snapshot.nodes,
    )
    communities = detect_communities(np.abs(snapshot.adjacency), snapshot.nodes)
    nodes = build_nodes_json(
        snapshot, metrics, features, {t: "Banks" for t in snapshot.nodes}, communities
    )

    strengths = [n["strength"] for n in nodes]
    assert strengths == sorted(strengths, reverse=True), "nodes.json is not ordered by strength"
    assert [n["rank"] for n in nodes] == list(range(1, len(nodes) + 1))
    assert len(nodes) == snapshot.n_nodes, "ordering must not drop nodes"


def test_edges_json_is_ordered_by_absolute_weight(snapshot):
    edges = build_edges_json(snapshot)
    weights = [e["absolute_weight"] for e in edges]
    assert weights == sorted(weights, reverse=True), "edges.json is not ordered by weight"
    assert [e["rank"] for e in edges] == list(range(1, len(edges) + 1))
    assert len(edges) == snapshot.n_edges, "ordering must not drop edges"
