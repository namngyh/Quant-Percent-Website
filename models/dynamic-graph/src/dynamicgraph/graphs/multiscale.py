r"""Multi-scale graphs.

Separate graphs are kept per window (20 / 60 / 120 / 252 days) because merging
them destroys the interpretation: a 20-day edge is a *current* co-movement while
a 252-day edge is a structural one.

An optional aggregate is available:

    A^{multi}_t = sum_W pi_W * normalize(A^{W}_t),   pi_W >= 0, sum pi_W = 1

Weights default to equal. Learned weights must be fitted on training data only;
`learn_scale_weights` enforces that by requiring an explicit training mask.
"""

from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from dynamicgraph.graphs.base import GraphSnapshot, SnapshotSeries
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def normalize_adjacency(adjacency: np.ndarray, method: str = "max_abs") -> np.ndarray:
    """Scale an adjacency so different windows are comparable before mixing."""
    if method == "max_abs":
        scale = np.abs(adjacency).max()
        return adjacency / scale if scale > 0 else adjacency.copy()
    if method == "frobenius":
        scale = np.linalg.norm(adjacency)
        return adjacency / scale if scale > 0 else adjacency.copy()
    if method == "mean_abs":
        n = adjacency.shape[0]
        i, j = np.triu_indices(n, k=1)
        scale = np.abs(adjacency[i, j]).mean()
        return adjacency / scale if scale > 0 else adjacency.copy()
    raise ValueError(f"Unknown normalisation `{method}`.")


def aggregate_snapshots(
    snapshots: Mapping[int, GraphSnapshot],
    weights: Mapping[int, float] | None = None,
    normalization: str = "max_abs",
) -> GraphSnapshot | None:
    """Combine same-date snapshots from several windows into one graph.

    Only nodes present in *every* window contribute, so the aggregate never
    invents an edge for a node that one scale could not estimate.
    """
    if not snapshots:
        return None
    windows = sorted(snapshots)
    if weights is None:
        weights = {w: 1.0 / len(windows) for w in windows}
    total = sum(weights.get(w, 0.0) for w in windows)
    if total <= 0:
        raise ValueError("Scale weights must sum to a positive number.")
    weights = {w: weights.get(w, 0.0) / total for w in windows}

    shared = set(snapshots[windows[0]].nodes)
    for window in windows[1:]:
        shared &= set(snapshots[window].nodes)
    nodes = sorted(shared)
    if len(nodes) < 3:
        return None

    combined = np.zeros((len(nodes), len(nodes)))
    for window in windows:
        snapshot = snapshots[window]
        frame = pd.DataFrame(snapshot.adjacency, index=snapshot.nodes, columns=snapshot.nodes)
        block = frame.loc[nodes, nodes].to_numpy()
        combined += weights[window] * normalize_adjacency(block, normalization)

    reference = snapshots[windows[0]]
    return GraphSnapshot(
        date=reference.date,
        nodes=nodes,
        adjacency=combined,
        layer=f"{reference.layer}_multiscale",
        window=-1,
        return_type=reference.return_type,
        metadata={
            "windows": windows,
            "weights": {str(k): float(v) for k, v in weights.items()},
            "normalization": normalization,
            "nodes": nodes,
        },
    )


def build_multiscale_series(
    series_by_window: Mapping[int, SnapshotSeries],
    weights: Mapping[int, float] | None = None,
    normalization: str = "max_abs",
) -> SnapshotSeries:
    """Aggregate several `SnapshotSeries` on their shared dates."""
    windows = sorted(series_by_window)
    by_date = {w: series_by_window[w].by_date() for w in windows}
    shared_dates = set(by_date[windows[0]])
    for window in windows[1:]:
        shared_dates &= set(by_date[window])

    snapshots: list[GraphSnapshot] = []
    for date in sorted(shared_dates):
        aggregate = aggregate_snapshots(
            {w: by_date[w][date] for w in windows}, weights=weights, normalization=normalization
        )
        if aggregate is not None:
            snapshots.append(aggregate)

    reference = series_by_window[windows[0]]
    logger.info(
        "Built %d multi-scale snapshot(s) across windows %s.", len(snapshots), windows
    )
    return SnapshotSeries(
        snapshots=snapshots,
        layer=f"{reference.layer}_multiscale",
        window=-1,
        return_type=reference.return_type,
    )


def learn_scale_weights(
    metrics_by_window: Mapping[int, pd.DataFrame],
    target: pd.Series,
    train_mask: pd.Series,
    metric: str = "avg_abs_partial_correlation",
) -> dict[int, float]:
    """Fit non-negative scale weights on TRAINING rows only.

    Weights are proportional to each scale's |Spearman| correlation with the
    target inside the training window, then normalised. Deliberately simple:
    with ~30 nodes there is no budget for a richer learned mixture.
    """
    from scipy.stats import spearmanr

    weights: dict[int, float] = {}
    for window, frame in metrics_by_window.items():
        if metric not in frame.columns:
            weights[window] = 0.0
            continue
        aligned = frame[metric].reindex(target.index)
        mask = train_mask.reindex(target.index, fill_value=False) & aligned.notna() & target.notna()
        if mask.sum() < 30:
            weights[window] = 0.0
            continue
        rho, _ = spearmanr(aligned[mask], target[mask])
        weights[window] = float(abs(rho)) if pd.notna(rho) else 0.0

    total = sum(weights.values())
    if total <= 0:
        n = len(metrics_by_window)
        logger.warning("Learned scale weights collapsed to zero; falling back to equal weights.")
        return {w: 1.0 / n for w in metrics_by_window}
    normalized = {w: v / total for w, v in weights.items()}
    logger.info("Learned scale weights (training only): %s", {k: round(v, 3) for k, v in normalized.items()})
    return normalized


def scale_comparison_table(series_by_window: Mapping[int, SnapshotSeries]) -> pd.DataFrame:
    """Density / weight summary per scale - the input to the multi-scale figure."""
    rows = []
    for window in sorted(series_by_window):
        series = series_by_window[window]
        if not len(series):
            continue
        densities = [s.density for s in series]
        strengths = [float(np.abs(s.adjacency).sum() / max(s.n_nodes, 1)) for s in series]
        rows.append(
            {
                "window": window,
                "n_snapshots": len(series),
                "mean_density": float(np.mean(densities)),
                "std_density": float(np.std(densities)),
                "mean_node_strength": float(np.mean(strengths)),
                "first_date": str(series.dates.min().date()),
                "last_date": str(series.dates.max().date()),
            }
        )
    return pd.DataFrame(rows)
