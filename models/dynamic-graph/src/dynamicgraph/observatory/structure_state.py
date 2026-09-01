"""Point-in-time market-structure state and online break detection."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS
from dynamicgraph.graphs.base import GraphSnapshot
from dynamicgraph.graphs.stability import edge_turnover
from dynamicgraph.network.communities import CommunityResult, compare_partitions


def _normalised_hhi(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    total = float(np.nansum(values))
    n = len(values)
    if total <= EPS or n <= 1:
        return float("nan")
    hhi = float(np.sum((values / total) ** 2))
    return float((hhi - 1.0 / n) / (1.0 - 1.0 / n))


def _spectral_summary(matrix: np.ndarray) -> tuple[float, float, float]:
    values = np.abs(np.linalg.eigvalsh(0.5 * (matrix + matrix.T)))
    total = float(values.sum())
    if total <= EPS:
        return float("nan"), float("nan"), float("nan")
    shares = values / total
    entropy = -float(np.sum(shares[shares > 0] * np.log(shares[shares > 0])))
    normalised_entropy = entropy / np.log(len(values)) if len(values) > 1 else 0.0
    return float(shares.max()), float(np.sum(shares**2)), normalised_entropy


def _aligned_matrix(
    snapshot: GraphSnapshot, nodes: Sequence[str], representation: str
) -> np.ndarray:
    return (
        pd.DataFrame(
            snapshot.matrix(representation),
            index=snapshot.nodes,
            columns=snapshot.nodes,
        )
        .reindex(index=nodes, columns=nodes, fill_value=0.0)
        .to_numpy()
    )


def build_market_structure_state(
    snapshots: Sequence[GraphSnapshot],
    communities: Mapping[pd.Timestamp, CommunityResult] | None = None,
    coverage: pd.DataFrame | None = None,
    estimator: str = "unknown",
    cross_method_agreement: Mapping[pd.Timestamp, float] | None = None,
) -> pd.DataFrame:
    """Create one auditable, point-in-time structure row per snapshot."""
    rows: list[dict[str, Any]] = []
    previous: GraphSnapshot | None = None
    coverage_by_date = (
        coverage.set_index("date") if coverage is not None and not coverage.empty else None
    )

    for snapshot in sorted(snapshots, key=lambda item: item.date):
        raw = np.asarray(snapshot.adjacency_raw, dtype=float)
        inference = np.asarray(snapshot.adjacency_inference, dtype=float)
        n = len(snapshot.nodes)
        upper = np.abs(raw[np.triu_indices(n, 1)])
        raw_strength = np.abs(raw).sum(axis=1)
        leading_share, spectral_concentration, spectral_entropy = _spectral_summary(raw)
        community = (communities or {}).get(snapshot.date)
        sizes = (
            np.asarray(list(community.sizes.values()), dtype=float)
            if community is not None and community.sizes
            else np.asarray([n], dtype=float)
        )
        size_shares = sizes / max(float(sizes.sum()), EPS)
        community_entropy = -float(
            np.sum(size_shares[size_shares > 0] * np.log(size_shares[size_shares > 0]))
        )
        if len(sizes) > 1:
            community_entropy /= np.log(len(sizes))

        turnover = np.nan
        raw_distance = spectral_distance = community_similarity = np.nan
        if previous is not None:
            shared = sorted(set(snapshot.nodes) & set(previous.nodes))
            if len(shared) >= 3:
                now_i = _aligned_matrix(snapshot, shared, "inference")
                before_i = _aligned_matrix(previous, shared, "inference")
                turnover = edge_turnover(now_i, before_i)
                now_raw = _aligned_matrix(snapshot, shared, "raw")
                before_raw = _aligned_matrix(previous, shared, "raw")
                denominator = np.linalg.norm(before_raw, ord="fro") + EPS
                raw_distance = float(
                    np.linalg.norm(now_raw - before_raw, ord="fro") / denominator
                )
                now_eigen = np.linalg.eigvalsh(now_raw)
                before_eigen = np.linalg.eigvalsh(before_raw)
                spectral_distance = float(
                    np.linalg.norm(now_eigen - before_eigen)
                    / (np.linalg.norm(before_eigen) + EPS)
                )
            current_community = (communities or {}).get(snapshot.date)
            previous_community = (communities or {}).get(previous.date)
            if current_community is not None and previous_community is not None:
                community_similarity = compare_partitions(
                    current_community.labels, previous_community.labels
                )["nmi"]

        coverage_ratio = np.nan
        if coverage_by_date is not None and snapshot.date in coverage_by_date.index:
            value = coverage_by_date.loc[snapshot.date, "coverage_ratio"]
            coverage_ratio = float(value.iloc[-1] if isinstance(value, pd.Series) else value)

        stability_values = (
            snapshot.stability[np.triu_indices(n, 1)]
            if snapshot.stability is not None
            else np.asarray([], dtype=float)
        )
        uncertainty = (
            1.96 * float(np.nanstd(upper, ddof=1)) / np.sqrt(max(1, np.isfinite(upper).sum()))
            if np.isfinite(upper).sum() > 1
            else np.nan
        )
        rows.append(
            {
                "date": snapshot.date,
                "n_nodes": n,
                "universe_coverage": coverage_ratio,
                "estimator": estimator,
                "window": snapshot.window,
                "residualization_type": snapshot.return_type,
                "mean_absolute_raw_dependence": float(np.nanmean(upper)),
                "median_absolute_raw_dependence": float(np.nanmedian(upper)),
                "upper_tail_edge_weight_mean": (
                    float(np.nanmean(upper[upper >= np.nanquantile(upper, 0.9)]))
                    if np.isfinite(upper).any()
                    else np.nan
                ),
                "market_mode_share": leading_share,
                "leading_eigenvalue_share": leading_share,
                "spectral_concentration": spectral_concentration,
                "spectral_entropy": spectral_entropy,
                "strength_concentration": _normalised_hhi(raw_strength),
                "community_count": (
                    community.n_communities if community is not None else np.nan
                ),
                "community_entropy": community_entropy,
                "community_concentration": _normalised_hhi(sizes),
                "modularity": community.modularity if community is not None else np.nan,
                "edge_turnover": turnover,
                "edge_stability": (
                    float(np.nanmean(stability_values))
                    if stability_values.size
                    else np.nan
                ),
                "centrality_concentration": _normalised_hhi(raw_strength),
                "cross_method_agreement": (cross_method_agreement or {}).get(
                    snapshot.date, np.nan
                ),
                "convergence_status": bool(
                    snapshot.metadata.get("glasso_converged", True)
                ),
                "convergence_warning": snapshot.metadata.get("glasso_warning"),
                "uncertainty_lower": float(np.nanmean(upper) - uncertainty),
                "uncertainty_upper": float(np.nanmean(upper) + uncertainty),
                "raw_adjacency_distance": raw_distance,
                "spectral_distance": spectral_distance,
                "community_similarity": community_similarity,
                "inference_density": float(
                    np.count_nonzero(np.triu(inference, 1))
                    * 2
                    / max(n * (n - 1), 1)
                ),
                "display_density": snapshot.to_dict()["display_density"],
                "display_threshold_rule": snapshot.metadata.get("filter_method"),
                "display_expected_density": snapshot.metadata.get(
                    "display_expected_density"
                ),
                "metric_representation_contract": json.dumps(
                    snapshot.metadata.get("representations", {}), sort_keys=True
                ),
            }
        )
        previous = snapshot

    frame = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    if frame.empty:
        return frame

    change_components = [
        "raw_adjacency_distance",
        "spectral_distance",
        "edge_turnover",
        "community_similarity",
        "market_mode_share",
        "strength_concentration",
        "community_concentration",
    ]
    component_scores = []
    for column in change_components:
        series = frame[column].astype(float)
        if column == "community_similarity":
            change = 1.0 - series
        elif "distance" in column or column == "edge_turnover":
            change = series
        else:
            change = series.diff().abs()
        prior_mean = change.shift(1).expanding(min_periods=10).mean()
        prior_std = change.shift(1).expanding(min_periods=10).std(ddof=1)
        score = ((change - prior_mean) / (prior_std + EPS)).clip(lower=0.0)
        frame[f"change_component_{column}"] = score
        component_scores.append(score)
    frame["change_score"] = pd.concat(component_scores, axis=1).mean(axis=1)
    prior_threshold = (
        frame["change_score"].shift(1).expanding(min_periods=20).quantile(0.95)
    )
    frame["structural_break_threshold"] = prior_threshold
    frame["structural_break_flag"] = (
        frame["change_score"] > prior_threshold
    ) & prior_threshold.notna()
    frame["break_severity"] = frame["change_score"] / (prior_threshold + EPS)
    return frame


def structural_break_table(state: pd.DataFrame) -> pd.DataFrame:
    """Explanation records for online structural-break flags."""
    if state.empty or "structural_break_flag" not in state:
        return pd.DataFrame()
    component_columns = [
        column for column in state if column.startswith("change_component_")
    ]
    rows = []
    for _, item in state[state["structural_break_flag"]].iterrows():
        contributions = {
            column.removeprefix("change_component_"): float(item[column])
            for column in component_columns
            if pd.notna(item[column])
        }
        ordered = sorted(contributions, key=contributions.get, reverse=True)
        rows.append(
            {
                "date": item["date"],
                "change_score": item["change_score"],
                "threshold": item["structural_break_threshold"],
                "break_severity": item["break_severity"],
                "top_contributors": json.dumps(ordered[:3]),
                "contributions": json.dumps(contributions, sort_keys=True),
                "explanation": (
                    "Online structure score exceeded its expanding 95th-percentile "
                    f"history; largest changes: {', '.join(ordered[:3])}."
                ),
            }
        )
    return pd.DataFrame(rows)
