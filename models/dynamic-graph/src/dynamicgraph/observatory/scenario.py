"""Conditional network shock propagation; deliberately not a forecast."""

from __future__ import annotations

import json
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS
from dynamicgraph.graphs.base import DirectedSnapshot


def run_shock_scenario(
    snapshot: DirectedSnapshot,
    shocked_nodes: Mapping[str, float],
    horizon: int = 5,
    damping: float = 0.85,
    scenario_type: str = "multi_node_shock",
    remove_nodes: Iterable[str] = (),
    remove_edges: Iterable[tuple[str, str]] = (),
    estimator: str = "directed_network",
    uncertainty: float | None = None,
) -> pd.DataFrame:
    """Propagate an imposed shock along i->j directed adjacency."""
    nodes = list(snapshot.nodes)
    positions = {node: index for index, node in enumerate(nodes)}
    adjacency = np.abs(np.asarray(snapshot.adjacency, dtype=float)).copy()
    for node in remove_nodes:
        if node in positions:
            index = positions[node]
            adjacency[index, :] = 0.0
            adjacency[:, index] = 0.0
    for source, target in remove_edges:
        if source in positions and target in positions:
            adjacency[positions[source], positions[target]] = 0.0
    row_sum = adjacency.sum(axis=1, keepdims=True)
    transition = np.divide(
        adjacency, row_sum, out=np.zeros_like(adjacency), where=row_sum > EPS
    )

    initial = np.zeros(len(nodes))
    for node, magnitude in shocked_nodes.items():
        if node in positions:
            initial[positions[node]] += float(magnitude)
    impacts = [initial]
    current = initial
    for _ in range(max(1, horizon)):
        current = damping * (current @ transition)
        impacts.append(current)
    direct = impacts[1] if len(impacts) > 1 else np.zeros_like(initial)
    second = impacts[2] if len(impacts) > 2 else np.zeros_like(initial)
    cumulative = np.sum(impacts, axis=0)
    total = float(np.abs(cumulative).sum())
    concentration = (
        float(np.sum((np.abs(cumulative) / total) ** 2)) if total > EPS else np.nan
    )

    return pd.DataFrame(
        {
            "date": snapshot.date,
            "scenario_type": scenario_type,
            "shocked_nodes": json.dumps(dict(shocked_nodes), sort_keys=True),
            "node": nodes,
            "direct_impact": direct,
            "second_order_impact": second,
            "cumulative_impact": cumulative,
            "affected": np.abs(cumulative) > EPS,
            "propagation_path": [
                f"conditional paths from {','.join(shocked_nodes)} to {node}"
                for node in nodes
            ],
            "receiver_concentration": concentration,
            "time_horizon": horizon,
            "estimator": estimator,
            "uncertainty": uncertainty,
            "interpretation": (
                "Conditional impact under an imposed shock; this is not a forecast."
            ),
        }
    )


def run_sector_shock(
    snapshot: DirectedSnapshot,
    sector_of: Mapping[str, str],
    sector: str,
    magnitude: float = 1.0,
    **kwargs,
) -> pd.DataFrame:
    nodes = [node for node in snapshot.nodes if sector_of.get(node) == sector]
    return run_shock_scenario(
        snapshot,
        {node: magnitude for node in nodes},
        scenario_type=f"sector_shock:{sector}",
        **kwargs,
    )


def run_community_shock(
    snapshot: DirectedSnapshot,
    community_of: Mapping[str, int],
    community: int,
    magnitude: float = 1.0,
    **kwargs,
) -> pd.DataFrame:
    nodes = [node for node in snapshot.nodes if community_of.get(node) == community]
    return run_shock_scenario(
        snapshot,
        {node: magnitude for node in nodes},
        scenario_type=f"community_shock:{community}",
        **kwargs,
    )


def run_volatility_increase(
    snapshot: DirectedSnapshot,
    volatility_increase: Mapping[str, float],
    **kwargs,
) -> pd.DataFrame:
    return run_shock_scenario(
        snapshot,
        volatility_increase,
        scenario_type="group_volatility_increase",
        **kwargs,
    )
