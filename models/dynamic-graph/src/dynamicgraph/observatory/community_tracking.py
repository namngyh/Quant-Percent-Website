"""Align arbitrary community labels through time and record lifecycle events."""

from __future__ import annotations

import json
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from dynamicgraph.graphs.base import GraphSnapshot
from dynamicgraph.network.communities import CommunityResult


def _groups(labels: Mapping[str, int]) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for node, label in labels.items():
        out.setdefault(int(label), set()).add(node)
    return out


def track_communities(
    communities: Mapping[pd.Timestamp, CommunityResult],
    snapshots: Sequence[GraphSnapshot] | None = None,
    sector_of: Mapping[str, str] | None = None,
    node_roles: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Map labels by maximum overlap (Hungarian assignment) across snapshots."""
    rows: list[dict[str, object]] = []
    previous: dict[int, set[str]] = {}
    next_id = 0
    persistence_count: dict[int, int] = {}

    for date in sorted(communities):
        result = communities[date]
        current_local = _groups(result.labels)
        current_persistent: dict[int, set[str]] = {}
        local_to_persistent: dict[int, int] = {}

        if previous and current_local:
            from scipy.optimize import linear_sum_assignment

            previous_ids = list(previous)
            local_ids = list(current_local)
            overlap = np.zeros((len(previous_ids), len(local_ids)))
            for i, persistent_id in enumerate(previous_ids):
                for j, local_id in enumerate(local_ids):
                    overlap[i, j] = len(previous[persistent_id] & current_local[local_id])
            for i, j in zip(*linear_sum_assignment(-overlap)):
                if overlap[i, j] > 0:
                    local_to_persistent[local_ids[j]] = previous_ids[i]

        for local_id, members in current_local.items():
            persistent_id = local_to_persistent.get(local_id)
            birth = persistent_id is None
            if persistent_id is None:
                persistent_id = next_id
                next_id += 1
            current_persistent[persistent_id] = members
            persistence_count[persistent_id] = persistence_count.get(persistent_id, 0) + 1

            predecessor_overlaps = {
                old_id: len(members & old_members)
                for old_id, old_members in previous.items()
                if members & old_members
            }
            merge = len(predecessor_overlaps) > 1
            predecessor = previous.get(persistent_id, set())
            union = members | predecessor
            member_turnover = (
                1.0 - len(members & predecessor) / len(union)
                if union and predecessor
                else np.nan
            )
            purity = np.nan
            if sector_of and members:
                sectors = pd.Series([sector_of.get(node, "UNKNOWN") for node in members])
                purity = float(sectors.value_counts().iloc[0] / len(sectors))

            risk = centrality = np.nan
            if node_roles is not None and not node_roles.empty:
                block = node_roles[
                    (pd.to_datetime(node_roles["date"]) == pd.Timestamp(date))
                    & node_roles["ticker"].isin(members)
                ]
                risk = float(block.get("avg_neighbor_risk", pd.Series(dtype=float)).mean())
                centrality = float(block.get("weighted_strength", pd.Series(dtype=float)).sum())

            rows.append(
                {
                    "date": pd.Timestamp(date),
                    "community_id": persistent_id,
                    "source_label": local_id,
                    "members": json.dumps(sorted(members)),
                    "n_members": len(members),
                    "birth": birth,
                    "death": False,
                    "merge": merge,
                    "split": False,
                    "member_turnover": member_turnover,
                    "sector_purity": purity,
                    "persistence_snapshots": persistence_count[persistent_id],
                    "community_risk": risk,
                    "community_centrality": centrality,
                    "modularity": result.modularity,
                }
            )

        # A predecessor contributing to several current groups split.
        for persistent_id, old_members in previous.items():
            descendants = sum(bool(old_members & members) for members in current_local.values())
            if descendants > 1:
                for row in reversed(rows):
                    if row["date"] != pd.Timestamp(date):
                        break
                    if old_members & set(json.loads(str(row["members"]))):
                        row["split"] = True
        for dead_id in set(previous) - set(current_persistent):
            rows.append(
                {
                    "date": pd.Timestamp(date),
                    "community_id": dead_id,
                    "source_label": np.nan,
                    "members": json.dumps(sorted(previous[dead_id])),
                    "n_members": 0,
                    "birth": False,
                    "death": True,
                    "merge": False,
                    "split": False,
                    "member_turnover": 1.0,
                    "sector_purity": np.nan,
                    "persistence_snapshots": persistence_count.get(dead_id, 0),
                    "community_risk": np.nan,
                    "community_centrality": np.nan,
                    "modularity": result.modularity,
                }
            )
        previous = current_persistent

    return pd.DataFrame(rows)
