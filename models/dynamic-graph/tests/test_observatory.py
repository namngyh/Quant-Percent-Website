"""Market-structure observatory contracts."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dynamicgraph.graphs.base import DirectedSnapshot, GraphSnapshot
from dynamicgraph.network.communities import CommunityResult
from dynamicgraph.observatory.community_tracking import track_communities
from dynamicgraph.observatory.node_roles import build_node_roles
from dynamicgraph.observatory.scenario import run_shock_scenario
from dynamicgraph.observatory.structure_state import (
    build_market_structure_state,
    structural_break_table,
)


def _series(n_dates: int = 40) -> tuple[list[GraphSnapshot], dict]:
    nodes = ["A", "B", "C", "D"]
    snapshots = []
    communities = {}
    for position, date in enumerate(pd.bdate_range("2023-01-01", periods=n_dates)):
        scale = 0.2 + position * 0.002
        raw = np.array(
            [
                [0, scale, 0.03, 0.01],
                [scale, 0, 0.02, 0.01],
                [0.03, 0.02, 0, scale * 0.8],
                [0.01, 0.01, scale * 0.8, 0],
            ],
            dtype=float,
        )
        inference = raw * (np.abs(raw) >= 0.05)
        display = raw * (np.abs(raw) >= scale * 0.9)
        snapshots.append(
            GraphSnapshot(
                date=date,
                nodes=nodes,
                adjacency=inference,
                adjacency_raw=raw,
                adjacency_inference=inference,
                adjacency_display=display,
                stability=np.full((4, 4), 0.8),
                metadata={
                    "glasso_converged": True,
                    "filter_method": "quantile",
                    "representations": {
                        "raw": "weights",
                        "inference": "topology",
                        "display": "visualization",
                    },
                },
            )
        )
        labels = {"A": 0, "B": 0, "C": 1, "D": 1}
        communities[date] = CommunityResult(
            labels, 0.4, "test", 2, {0: 2, 1: 2}
        )
    return snapshots, communities


def test_structure_state_has_required_point_in_time_fields():
    snapshots, communities = _series()
    state = build_market_structure_state(
        snapshots, communities, estimator="glasso"
    )
    required = {
        "date",
        "n_nodes",
        "mean_absolute_raw_dependence",
        "market_mode_share",
        "spectral_concentration",
        "strength_concentration",
        "community_count",
        "community_entropy",
        "modularity",
        "edge_turnover",
        "edge_stability",
        "centrality_concentration",
        "convergence_status",
        "uncertainty_lower",
        "uncertainty_upper",
        "change_score",
        "structural_break_flag",
    }
    assert required.issubset(state.columns)
    assert (state["display_density"] <= 1).all()
    assert state["metric_representation_contract"].str.contains("display").all()


def test_online_change_scores_do_not_move_when_only_the_future_changes():
    snapshots, communities = _series()
    baseline = build_market_structure_state(snapshots, communities)
    changed, changed_communities = _series()
    changed[-1].adjacency_raw *= 100.0
    after = build_market_structure_state(changed, changed_communities)
    pd.testing.assert_series_equal(
        baseline["change_score"].iloc[:-1],
        after["change_score"].iloc[:-1],
    )


def test_community_tracking_aligns_permuted_labels():
    dates = pd.bdate_range("2024-01-01", periods=2)
    results = {
        dates[0]: CommunityResult(
            {"A": 0, "B": 0, "C": 1, "D": 1}, 0.4, "test", 2, {0: 2, 1: 2}
        ),
        dates[1]: CommunityResult(
            {"A": 9, "B": 9, "C": 4, "D": 4}, 0.4, "test", 2, {9: 2, 4: 2}
        ),
    }
    tracked = track_communities(results)
    first = tracked[(tracked["date"] == dates[0]) & ~tracked["death"]]
    second = tracked[(tracked["date"] == dates[1]) & ~tracked["death"]]
    assert set(first["community_id"]) == set(second["community_id"])
    assert not second["birth"].any()
    assert (second["member_turnover"] == 0).all()


def test_node_role_output_is_transparent_and_has_no_importance_claim():
    snapshots, _ = _series(2)
    rows = []
    for snapshot in snapshots:
        for position, ticker in enumerate(snapshot.nodes):
            rows.append(
                {
                    "date": snapshot.date,
                    "ticker": ticker,
                    "strength": 4 - position,
                    "degree_centrality": 0.5,
                    "eigenvector_centrality": 1 / (position + 1),
                    "betweenness_centrality": position / 10,
                    "participation_coefficient": position / 4,
                    "community": position // 2,
                    "avg_neighbor_risk": 0.1,
                }
            )
    roles = build_node_roles(pd.DataFrame(rows), snapshots)
    required = {
        "weighted_strength",
        "normalized_degree",
        "within_community_strength",
        "participation_coefficient",
        "bridge_score",
        "role_persistence",
        "centrality_change",
        "role_confidence",
        "role_label",
    }
    assert required.issubset(roles.columns)
    assert not roles.astype(str).apply(
        lambda column: column.str.contains("systemically important").any()
    ).any()


def test_scenario_propagates_in_the_directed_edge_direction():
    directed = DirectedSnapshot(
        date=pd.Timestamp("2024-01-31"),
        nodes=["A", "B", "C"],
        adjacency=np.array([[0, 1, 0], [0, 0, 1], [0, 0, 0]], dtype=float),
        layer="spillover",
    )
    report = run_shock_scenario(directed, {"A": 1.0}, horizon=3, damping=1.0)
    by_node = report.set_index("node")
    assert by_node.loc["B", "direct_impact"] == 1.0
    assert by_node.loc["C", "second_order_impact"] == 1.0
    assert report["interpretation"].str.contains("not a forecast").all()


def test_sector_and_community_scenarios_expand_to_member_nodes():
    from dynamicgraph.observatory.scenario import (
        run_community_shock,
        run_sector_shock,
    )

    directed = DirectedSnapshot(
        date=pd.Timestamp("2024-01-31"),
        nodes=["A", "B", "C"],
        adjacency=np.array([[0, 0, 1], [0, 0, 1], [0, 0, 0]], dtype=float),
        layer="spillover",
    )
    sector = run_sector_shock(
        directed, {"A": "Bank", "B": "Bank", "C": "Tech"}, "Bank"
    )
    community = run_community_shock(
        directed, {"A": 7, "B": 7, "C": 9}, 7
    )
    assert '"A": 1.0' in sector["shocked_nodes"].iloc[0]
    assert '"B": 1.0' in sector["shocked_nodes"].iloc[0]
    assert community["scenario_type"].iloc[0] == "community_shock:7"


def test_break_records_always_include_an_explanation():
    snapshots, communities = _series(45)
    snapshots[-1].adjacency_raw *= 50.0
    state = build_market_structure_state(snapshots, communities)
    breaks = structural_break_table(state)
    if not breaks.empty:
        assert breaks["explanation"].str.len().gt(20).all()
        assert breaks["contributions"].str.startswith("{").all()
