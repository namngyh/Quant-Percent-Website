"""Transparent, multi-signal node-role classification."""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from dynamicgraph.graphs.base import DirectedSnapshot, GraphSnapshot


def build_node_roles(
    history: pd.DataFrame,
    snapshots: Sequence[GraphSnapshot],
    directed_snapshots: Sequence[DirectedSnapshot] | None = None,
    cross_method_agreement: Mapping[pd.Timestamp, float] | None = None,
) -> pd.DataFrame:
    """Add structural roles, persistence and confidence to node metrics."""
    if history is None or history.empty:
        return pd.DataFrame()
    frame = history.sort_values(["date", "ticker"]).copy()
    snapshots_by_date = {pd.Timestamp(item.date): item for item in snapshots}

    frame["normalized_degree"] = frame.get(
        "degree_centrality", frame.get("degree", np.nan)
    )
    frame["weighted_strength"] = frame.get("strength", np.nan)
    frame["within_community_strength"] = np.nan
    frame["bridge_score"] = np.nan
    frame["uncertainty_stability"] = np.nan

    for date, positions in frame.groupby("date").groups.items():
        snapshot = snapshots_by_date.get(pd.Timestamp(date))
        if snapshot is None:
            continue
        block = frame.loc[positions]
        node_position = {node: i for i, node in enumerate(snapshot.nodes)}
        absolute = np.abs(snapshot.adjacency_inference)
        within_values = []
        stability_values = []
        for row in block.itertuples():
            i = node_position.get(row.ticker)
            if i is None:
                within_values.append(np.nan)
                stability_values.append(np.nan)
                continue
            labels = block.set_index("ticker")["community"]
            peers = [
                node_position[node]
                for node in snapshot.nodes
                if node in labels.index and labels[node] == row.community
            ]
            within_values.append(float(absolute[i, peers].sum()))
            stability_values.append(
                float(np.nanmean(snapshot.stability[i]))
                if snapshot.stability is not None
                else np.nan
            )
        frame.loc[positions, "within_community_strength"] = within_values
        frame.loc[positions, "uncertainty_stability"] = stability_values
        participation = block["participation_coefficient"].rank(pct=True)
        betweenness = block["betweenness_centrality"].rank(pct=True)
        frame.loc[positions, "bridge_score"] = (
            pd.concat([participation, betweenness], axis=1).mean(axis=1).to_numpy()
        )

    frame["systemic_transmitter"] = np.nan
    frame["systemic_receiver"] = np.nan
    if directed_snapshots:
        directed_by_date = {pd.Timestamp(item.date): item for item in directed_snapshots}
        available_dates = sorted(directed_by_date)
        for date, positions in frame.groupby("date").groups.items():
            eligible = [value for value in available_dates if value <= pd.Timestamp(date)]
            if not eligible:
                continue
            snapshot = directed_by_date[eligible[-1]]
            out_strength = snapshot.out_strength
            in_strength = snapshot.in_strength
            tickers = frame.loc[positions, "ticker"]
            frame.loc[positions, "systemic_transmitter"] = tickers.map(out_strength).to_numpy()
            frame.loc[positions, "systemic_receiver"] = tickers.map(in_strength).to_numpy()

    role_labels: list[str] = []
    for _, block in frame.groupby("date", sort=True):
        strength_pct = block["weighted_strength"].rank(pct=True)
        eigen_pct = block["eigenvector_centrality"].rank(pct=True)
        bridge_pct = block["bridge_score"].rank(pct=True)
        within_pct = block["within_community_strength"].rank(pct=True)
        tx_pct = block["systemic_transmitter"].rank(pct=True)
        rx_pct = block["systemic_receiver"].rank(pct=True)
        unstable = block["uncertainty_stability"].fillna(1.0) < 0.5
        labels = np.select(
            [
                unstable,
                tx_pct >= 0.8,
                rx_pct >= 0.8,
                (strength_pct >= 0.8) & (eigen_pct >= 0.8),
                bridge_pct >= 0.8,
                within_pct >= 0.8,
            ],
            [
                "unstable",
                "transmitter",
                "receiver",
                "hub",
                "bridge",
                "community_core",
            ],
            default="peripheral",
        )
        role_labels.extend(labels.tolist())
    frame["role_label"] = role_labels

    grouped = frame.groupby("ticker", sort=False)
    frame["role_persistence"] = grouped["role_label"].transform(
        lambda values: values.eq(values.shift(1)).rolling(20, min_periods=1).mean()
    )
    frame["centrality_change"] = frame.get(
        "eigenvector_centrality_change_1d",
        grouped["eigenvector_centrality"].diff(),
    )
    frame["cross_window_method_agreement"] = pd.to_datetime(frame["date"]).map(
        cross_method_agreement or {}
    )
    confidence_parts = [
        frame["role_persistence"],
        frame["uncertainty_stability"],
        frame["cross_window_method_agreement"],
    ]
    frame["role_confidence"] = (
        pd.concat(confidence_parts, axis=1).mean(axis=1, skipna=True).clip(0.0, 1.0)
    )
    frame["role_rule"] = (
        "unstable<0.5 stability; directed top-quintile transmitter/receiver; "
        "joint top-quintile strength+eigenvector hub; top-quintile bridge; "
        "top-quintile within-community core; otherwise peripheral"
    )
    return frame
