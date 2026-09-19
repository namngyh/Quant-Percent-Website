"""Cross-configuration graph robustness diagnostics."""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from dynamicgraph.graphs.base import SnapshotSeries
from dynamicgraph.network.communities import compare_partitions, detect_communities


def build_robustness_report(
    series_by_key: Mapping[str, SnapshotSeries],
    coverage: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Report stability and cross-method rank agreement per configuration/date."""
    coverage_map = (
        coverage.set_index("date")["coverage_ratio"].to_dict()
        if coverage is not None and not coverage.empty
        else {}
    )
    rows: list[dict[str, object]] = []
    strength_by_date: dict[pd.Timestamp, list[tuple[str, pd.Series]]] = {}
    partitions_by_date: dict[pd.Timestamp, list[dict[str, int]]] = {}

    for key, series in series_by_key.items():
        for snapshot in series:
            strength = pd.Series(
                np.abs(snapshot.adjacency_raw).sum(axis=1), index=snapshot.nodes
            )
            strength_by_date.setdefault(snapshot.date, []).append((key, strength))
            partitions_by_date.setdefault(snapshot.date, []).append(
                detect_communities(
                    snapshot.adjacency_inference,
                    snapshot.nodes,
                    method="greedy",
                ).labels
            )
            upper_stability = (
                snapshot.stability[np.triu_indices(len(snapshot.nodes), 1)]
                if snapshot.stability is not None
                else np.asarray([], dtype=float)
            )
            rows.append(
                {
                    "date": snapshot.date,
                    "configuration": key,
                    "estimator": snapshot.metadata.get("covariance_estimator"),
                    "window": snapshot.window,
                    "alpha": snapshot.alpha,
                    "residualization": snapshot.return_type,
                    "universe": "point_in_time",
                    "filtering_rule": snapshot.metadata.get("filter_method"),
                    "bootstrap_sample": snapshot.metadata.get("n_bootstrap", 0),
                    "data_coverage": coverage_map.get(snapshot.date, np.nan),
                    "edge_stability": (
                        float(np.nanmean(upper_stability))
                        if upper_stability.size
                        else np.nan
                    ),
                    "metric_ci_lower": (
                        float(np.nanquantile(upper_stability, 0.025))
                        if upper_stability.size
                        else np.nan
                    ),
                    "metric_ci_upper": (
                        float(np.nanquantile(upper_stability, 0.975))
                        if upper_stability.size
                        else np.nan
                    ),
                    "converged": snapshot.metadata.get("glasso_converged", True),
                    "node_role_stability": np.nan,
                    "community_stability": np.nan,
                    "cross_method_rank_correlation": np.nan,
                }
            )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    for date, variants in strength_by_date.items():
        correlations = []
        for index, (_, first) in enumerate(variants):
            for _, second in variants[index + 1 :]:
                shared = first.index.intersection(second.index)
                if len(shared) < 3:
                    continue
                rho = spearmanr(first.reindex(shared), second.reindex(shared)).statistic
                if np.isfinite(rho):
                    correlations.append(float(rho))
        if correlations:
            frame.loc[
                frame["date"] == date, "cross_method_rank_correlation"
            ] = float(np.mean(correlations))
            frame.loc[
                frame["date"] == date, "node_role_stability"
            ] = float(np.mean(correlations))
        partition_scores = []
        partitions = partitions_by_date.get(date, [])
        for index, first in enumerate(partitions):
            for second in partitions[index + 1 :]:
                comparison = compare_partitions(first, second)
                if np.isfinite(comparison["nmi"]):
                    partition_scores.append(comparison["nmi"])
        if partition_scores:
            frame.loc[
                frame["date"] == date, "community_stability"
            ] = float(np.mean(partition_scores))
    frame["configuration_convergence_rate"] = frame.groupby("configuration")[
        "converged"
    ].transform("mean")
    return frame
