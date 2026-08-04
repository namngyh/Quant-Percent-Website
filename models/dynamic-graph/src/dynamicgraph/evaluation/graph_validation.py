"""Graph-specific validation.

A network picture is not evidence. This module runs the checks that decide
whether the estimated structure is real or an artefact of the estimator:

  1-3  edge stability, centrality rank stability, community persistence
  4-6  sensitivity to window length, graphical-lasso alpha, edge threshold
  7-8  raw vs residual returns, correlation vs partial correlation
  11-15 robustness across regimes, to sector removal, to hub removal, to
        missing data and to constituent changes
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from dynamicgraph.graphs.base import GraphSnapshot, SnapshotSeries
from dynamicgraph.graphs.snapshots import SnapshotBuildConfig, build_snapshot_series
from dynamicgraph.graphs.stability import centrality_rank_stability, edge_survival, edge_turnover
from dynamicgraph.logging_config import get_logger
from dynamicgraph.network.communities import compare_partitions, detect_communities
from dynamicgraph.network.node_metrics import compute_node_metrics

logger = get_logger(__name__)


def edge_stability_report(series: SnapshotSeries) -> pd.DataFrame:
    """Edge survival and turnover between consecutive snapshots."""
    rows = []
    previous: GraphSnapshot | None = None
    for snapshot in series:
        if previous is not None:
            shared = [n for n in snapshot.nodes if n in set(previous.nodes)]
            if len(shared) >= 3:
                current = pd.DataFrame(
                    snapshot.adjacency, index=snapshot.nodes, columns=snapshot.nodes
                ).loc[shared, shared].to_numpy()
                before = pd.DataFrame(
                    previous.adjacency, index=previous.nodes, columns=previous.nodes
                ).loc[shared, shared].to_numpy()
                rows.append(
                    {
                        "date": snapshot.date,
                        "edge_survival": edge_survival(current, before),
                        "edge_turnover": edge_turnover(current, before),
                        "n_shared_nodes": len(shared),
                        "bootstrap_mean_stability": (
                            float(np.nanmean(snapshot.stability[np.triu_indices(snapshot.n_nodes, 1)]))
                            if snapshot.stability is not None else np.nan
                        ),
                    }
                )
        previous = snapshot
    return pd.DataFrame(rows)


def centrality_stability_report(
    series: SnapshotSeries, metric: str = "strength", stride: int = 1
) -> pd.DataFrame:
    """Spearman rank correlation of a centrality between consecutive snapshots."""
    rows = []
    previous_values: dict[str, float] | None = None
    previous_date = None
    for i, snapshot in enumerate(series):
        if i % stride:
            continue
        metrics = compute_node_metrics(
            snapshot, compute_betweenness=False, compute_closeness=False
        ).set_index("ticker")
        if metric not in metrics.columns:
            continue
        values = metrics[metric].to_dict()
        if previous_values is not None:
            rows.append(
                {
                    "date": snapshot.date,
                    "previous_date": previous_date,
                    "metric": metric,
                    "rank_stability": centrality_rank_stability(values, previous_values),
                }
            )
        previous_values, previous_date = values, snapshot.date
    return pd.DataFrame(rows)


def community_persistence_report(
    series: SnapshotSeries, sector_of: dict[str, str] | None = None, seed: int = 42
) -> pd.DataFrame:
    """ARI / NMI / Jaccard between consecutive partitions, plus sector purity."""
    rows = []
    previous_labels: dict[str, int] | None = None
    for snapshot in series:
        community = detect_communities(
            np.abs(snapshot.adjacency), snapshot.nodes, seed=seed, sector_of=sector_of
        )
        row: dict[str, Any] = {
            "date": snapshot.date,
            "n_communities": community.n_communities,
            "modularity": community.modularity,
            "sector_purity": community.sector_purity,
            "method": community.method,
        }
        if previous_labels is not None:
            row.update(compare_partitions(community.labels, previous_labels))
        rows.append(row)
        previous_labels = community.labels
    return pd.DataFrame(rows)


def window_sensitivity(
    returns: pd.DataFrame,
    config: Any,
    windows: Sequence[int] = (20, 60, 120, 252),
    layer: str = "partial_correlation",
    return_type: str = "residual",
    stride: int = 20,
) -> pd.DataFrame:
    """How density / mean strength / hub identity change with window length."""
    rows = []
    per_window_top: dict[int, list[str]] = {}
    for window in windows:
        build = SnapshotBuildConfig.from_config(config, layer, window, return_type)
        build.stride = stride
        build.bootstrap_iterations = 0
        series = build_snapshot_series(returns, build, progress_every=0)
        if not len(series):
            continue
        densities = [s.density for s in series]
        latest = series.latest()
        strength = pd.Series(np.abs(latest.adjacency).sum(axis=1), index=latest.nodes)
        per_window_top[window] = strength.sort_values(ascending=False).head(5).index.tolist()
        rows.append(
            {
                "window": window,
                "n_snapshots": len(series),
                "mean_density": float(np.mean(densities)),
                "std_density": float(np.std(densities)),
                "mean_strength": float(strength.mean()),
                "top5_nodes": ", ".join(per_window_top[window]),
            }
        )

    frame = pd.DataFrame(rows)
    if len(per_window_top) > 1:
        reference = set(per_window_top[min(per_window_top)])
        frame["top5_overlap_with_shortest_window"] = [
            len(set(per_window_top[w]) & reference) / 5.0 for w in frame["window"]
        ]
    return frame


def alpha_sensitivity(
    returns: pd.DataFrame,
    config: Any,
    alphas: Iterable[float],
    window: int = 60,
    return_type: str = "residual",
    stride: int = 40,
) -> pd.DataFrame:
    """Density / edge count / hub identity as a function of the lasso penalty."""
    rows = []
    reference_top: list[str] | None = None
    for alpha in alphas:
        build = SnapshotBuildConfig.from_config(config, "partial_correlation", window, return_type)
        build.alpha = float(alpha)
        build.stride = stride
        build.bootstrap_iterations = 0
        build.edge_filter_method = "none"
        series = build_snapshot_series(returns, build, progress_every=0)
        if not len(series):
            continue
        latest = series.latest()
        strength = pd.Series(np.abs(latest.adjacency).sum(axis=1), index=latest.nodes)
        top = strength.sort_values(ascending=False).head(5).index.tolist()
        reference_top = reference_top or top
        rows.append(
            {
                "alpha": float(alpha),
                "n_snapshots": len(series),
                "mean_density": float(np.mean([s.density for s in series])),
                "mean_edges": float(np.mean([s.n_edges for s in series])),
                "top5_nodes": ", ".join(top),
                "top5_overlap_with_smallest_alpha": len(set(top) & set(reference_top)) / 5.0,
            }
        )
    return pd.DataFrame(rows)


def threshold_sensitivity(
    series: SnapshotSeries, thresholds: Sequence[float] = (0.02, 0.05, 0.10, 0.15, 0.20)
) -> pd.DataFrame:
    """Density and hub identity as the absolute edge threshold is raised."""
    rows = []
    for threshold in thresholds:
        densities, overlaps = [], []
        reference_top: list[str] | None = None
        for snapshot in series:
            filtered = snapshot.adjacency.copy()
            filtered[np.abs(filtered) < threshold] = 0.0
            n = snapshot.n_nodes
            n_edges = int(np.count_nonzero(np.triu(filtered, 1)))
            densities.append(2.0 * n_edges / (n * (n - 1)) if n > 1 else np.nan)
            strength = pd.Series(np.abs(filtered).sum(axis=1), index=snapshot.nodes)
            top = strength.sort_values(ascending=False).head(5).index.tolist()
            if reference_top is None:
                reference_top = top
            overlaps.append(len(set(top) & set(reference_top)) / 5.0)
        rows.append(
            {
                "threshold": threshold,
                "mean_density": float(np.nanmean(densities)),
                "mean_top5_overlap": float(np.nanmean(overlaps)),
            }
        )
    return pd.DataFrame(rows)


def compare_graph_variants(
    variants: Mapping[str, SnapshotSeries], metric: str = "strength"
) -> pd.DataFrame:
    """Cross-variant agreement: how similar are the centrality rankings?

    Answers "does it matter whether I use raw or residual returns / correlation
    or partial correlation?" -- if the rankings agree, the choice is cosmetic;
    if they do not, the choice is a modelling decision that must be justified.
    """
    from scipy.stats import spearmanr

    names = list(variants)
    latest: dict[str, pd.Series] = {}
    for name in names:
        snapshot = variants[name].latest()
        if snapshot is None:
            continue
        latest[name] = pd.Series(np.abs(snapshot.adjacency).sum(axis=1), index=snapshot.nodes)

    rows = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if a not in latest or b not in latest:
                continue
            shared = latest[a].index.intersection(latest[b].index)
            if len(shared) < 5:
                continue
            rho, _ = spearmanr(latest[a][shared], latest[b][shared])
            top_a = set(latest[a][shared].sort_values(ascending=False).head(5).index)
            top_b = set(latest[b][shared].sort_values(ascending=False).head(5).index)
            rows.append(
                {
                    "variant_a": a,
                    "variant_b": b,
                    "spearman_centrality": float(rho) if pd.notna(rho) else np.nan,
                    "top5_overlap": len(top_a & top_b) / 5.0,
                    "n_shared_nodes": len(shared),
                }
            )
    return pd.DataFrame(rows)


def node_removal_robustness(
    returns: pd.DataFrame,
    config: Any,
    remove: Sequence[str],
    window: int = 60,
    layer: str = "partial_correlation",
    return_type: str = "residual",
    stride: int = 40,
) -> pd.DataFrame:
    """Rebuild the graph without given nodes/sectors and compare graph metrics."""
    from dynamicgraph.network.graph_metrics import compute_metric_series

    build = SnapshotBuildConfig.from_config(config, layer, window, return_type)
    build.stride = stride
    build.bootstrap_iterations = 0

    baseline_series = build_snapshot_series(returns, build, progress_every=0)
    baseline_metrics, _ = compute_metric_series(list(baseline_series))

    reduced_returns = returns.drop(columns=[c for c in remove if c in returns.columns])
    if reduced_returns.shape[1] < 5:
        return pd.DataFrame()
    reduced_series = build_snapshot_series(reduced_returns, build, progress_every=0)
    reduced_metrics, _ = compute_metric_series(list(reduced_series))

    columns = [
        "graph_density", "spectral_radius", "modularity", "centrality_concentration",
        "average_strength", "number_of_communities",
    ]
    rows = []
    for column in columns:
        if column not in baseline_metrics.columns or column not in reduced_metrics.columns:
            continue
        base = baseline_metrics[column].dropna()
        reduced = reduced_metrics[column].dropna()
        shared = base.index.intersection(reduced.index)
        if len(shared) < 5:
            continue
        rows.append(
            {
                "metric": column,
                "baseline_mean": float(base[shared].mean()),
                "reduced_mean": float(reduced[shared].mean()),
                "relative_change": float(
                    (reduced[shared].mean() - base[shared].mean()) / (abs(base[shared].mean()) + 1e-12)
                ),
                "correlation": float(base[shared].corr(reduced[shared])),
                "removed": ", ".join(remove),
            }
        )
    return pd.DataFrame(rows)


def missing_data_robustness(
    returns: pd.DataFrame,
    config: Any,
    missing_rates: Sequence[float] = (0.0, 0.05, 0.10, 0.20),
    window: int = 60,
    stride: int = 40,
    seed: int = 42,
) -> pd.DataFrame:
    """Inject missing returns at random and measure how the graph degrades."""
    from dynamicgraph.network.graph_metrics import compute_metric_series

    rng = np.random.default_rng(seed)
    build = SnapshotBuildConfig.from_config(config, "partial_correlation", window, "residual")
    build.stride = stride
    build.bootstrap_iterations = 0

    reference: pd.Series | None = None
    rows = []
    for rate in missing_rates:
        corrupted = returns.copy()
        if rate > 0:
            mask = rng.random(corrupted.shape) < rate
            corrupted = corrupted.mask(mask)
        series = build_snapshot_series(corrupted, build, progress_every=0)
        if not len(series):
            rows.append({"missing_rate": rate, "n_snapshots": 0})
            continue
        metrics, _ = compute_metric_series(list(series))
        density = metrics["graph_density"]
        if reference is None:
            reference = density
        shared = reference.index.intersection(density.index)
        rows.append(
            {
                "missing_rate": rate,
                "n_snapshots": len(series),
                "mean_density": float(density.mean()),
                "mean_nodes": float(metrics["number_of_nodes"].mean()),
                "density_correlation_with_clean": (
                    float(reference[shared].corr(density[shared])) if len(shared) > 5 else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def regime_robustness(
    metrics: pd.DataFrame, market_returns: pd.Series, n_regimes: int = 3
) -> pd.DataFrame:
    """Graph metrics split by trailing-volatility regime (calm / normal / stressed)."""
    volatility = market_returns.rolling(60, min_periods=30).std(ddof=1) * np.sqrt(252)
    aligned = volatility.reindex(metrics.index)
    try:
        regime = pd.qcut(aligned, n_regimes, labels=["calm", "normal", "stressed"][:n_regimes])
    except Exception:
        return pd.DataFrame()

    columns = [
        c for c in (
            "graph_density", "spectral_radius", "modularity", "market_mode_share",
            "centrality_concentration", "avg_abs_partial_correlation", "edge_turnover",
        ) if c in metrics.columns
    ]
    frame = metrics[columns].copy()
    frame["regime"] = regime
    return frame.groupby("regime", observed=True).agg(["mean", "std", "count"]).round(4)


def run_graph_validation(
    series_by_key: Mapping[str, SnapshotSeries],
    returns_by_type: Mapping[str, pd.DataFrame],
    config: Any,
    sector_of: dict[str, str] | None = None,
    core_key: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Run the whole validation battery. Missing pieces degrade to empty frames."""
    out: dict[str, pd.DataFrame] = {}
    core_key = core_key or next(iter(series_by_key), None)
    if core_key is None:
        return out
    core = series_by_key[core_key]

    logger.info("Graph validation: edge and centrality stability ...")
    out["edge_stability"] = edge_stability_report(core)
    out["centrality_stability"] = centrality_stability_report(core, "strength", stride=5)
    out["community_persistence"] = community_persistence_report(core, sector_of, int(config.project.seed))

    residual = returns_by_type.get("residual")
    if residual is not None and not residual.empty:
        tail = residual.tail(1000)
        logger.info("Graph validation: window and alpha sensitivity ...")
        out["window_sensitivity"] = window_sensitivity(
            tail, config, windows=config.graph.windows, stride=40
        )
        out["alpha_sensitivity"] = alpha_sensitivity(
            tail, config, alphas=config.graph.graphical_lasso_alpha_grid, stride=60
        )
        out["missing_data_robustness"] = missing_data_robustness(tail, config, stride=60)

        if sector_of:
            sectors = pd.Series(sector_of)
            biggest = sectors[sectors.index.isin(residual.columns)].value_counts()
            if not biggest.empty:
                target_sector = biggest.index[0]
                members = [t for t in residual.columns if sector_of.get(t) == target_sector]
                out["sector_removal_robustness"] = node_removal_robustness(
                    tail, config, members, stride=60
                )

        latest = core.latest()
        if latest is not None:
            strength = pd.Series(np.abs(latest.adjacency).sum(axis=1), index=latest.nodes)
            hub = strength.idxmax()
            out["hub_removal_robustness"] = node_removal_robustness(tail, config, [hub], stride=60)

    out["threshold_sensitivity"] = threshold_sensitivity(core)
    if len(series_by_key) > 1:
        out["variant_comparison"] = compare_graph_variants(series_by_key)

    logger.info("Graph validation complete: %d report(s).", len(out))
    return out
