r"""Snapshot construction.

For each date t with a complete trailing window of length W:

  1. select the nodes valid at t (missing-data ratio inside the window
     <= `data.max_missing_ratio_per_window`);
  2. estimate the covariance (Ledoit-Wolf by default);
  3. build the layer:
       correlation          -> A = rho
       partial_correlation  -> Theta via graphical lasso, then
                               rho^partial = -Theta_ij / sqrt(Theta_ii Theta_jj)
  4. optionally compute bootstrap edge stability;
  5. filter edges and cap density.

Nothing in this module reads data past t.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from dynamicgraph.graphs.base import GraphSnapshot, SnapshotSeries
from dynamicgraph.graphs.correlation import correlation_matrix
from dynamicgraph.graphs.filtering import filter_adjacency
from dynamicgraph.graphs.graphical_lasso import fit_graphical_lasso
from dynamicgraph.graphs.partial_correlation import partial_correlation_from_precision
from dynamicgraph.graphs.shrinkage import estimate_covariance
from dynamicgraph.graphs.stability import edge_stability
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SnapshotBuildConfig:
    """Flattened build parameters (keeps the hot loop free of attribute lookups)."""

    layer: str = "partial_correlation"
    window: int = 60
    return_type: str = "residual"
    covariance_estimator: str = "ledoit_wolf"
    alpha: float = 0.02
    edge_filter_method: str = "quantile"
    absolute_threshold: float = 0.10
    top_edge_quantile: float = 0.25
    max_density: float = 0.60
    bootstrap_iterations: int = 0
    block_length: Any = "auto"
    edge_stability_threshold: float = 0.60
    max_missing_ratio: float = 0.10
    min_nodes: int = 5
    stride: int = 1
    seed: int = 42
    n_jobs: int = 1

    @classmethod
    def from_config(
        cls, config: Any, layer: str, window: int, return_type: str
    ) -> "SnapshotBuildConfig":
        graph = config.graph
        return cls(
            layer=layer,
            window=window,
            return_type=return_type,
            covariance_estimator=str(graph.covariance_estimator),
            alpha=float(graph.graphical_lasso_alpha),
            edge_filter_method=str(graph.edge_filter_method),
            absolute_threshold=float(graph.absolute_threshold),
            top_edge_quantile=float(graph.top_edge_quantile),
            max_density=float(graph.max_graph_density),
            bootstrap_iterations=int(graph.bootstrap_iterations),
            block_length=graph.block_length,
            edge_stability_threshold=float(graph.edge_stability_threshold),
            max_missing_ratio=float(config.data.max_missing_ratio_per_window),
            stride=int(graph.snapshot_stride),
            seed=int(config.project.seed),
            n_jobs=int(config.training.n_jobs),
        )


def _build_raw_adjacency(
    block: np.ndarray, build: SnapshotBuildConfig
) -> tuple[np.ndarray, dict[str, Any]]:
    """Unfiltered signed adjacency for one return window."""
    estimate = estimate_covariance(block, build.covariance_estimator)
    info: dict[str, Any] = {
        "covariance_estimator": estimate.estimator,
        "shrinkage": estimate.shrinkage,
        "condition_number": estimate.condition_number,
    }
    if build.layer == "correlation":
        return estimate.correlation - np.eye(estimate.correlation.shape[0]), info
    if build.layer == "partial_correlation":
        # The graphical lasso is fitted on the CORRELATION matrix, not the
        # covariance. Daily return covariances have entries around 1e-4, so a
        # penalty of 0.02 on the covariance scale annihilates every off-diagonal
        # term and yields an empty graph. Partial correlation is scale
        # invariant, so working in correlation space leaves the result unchanged
        # while making alpha interpretable and comparable across windows.
        fit = fit_graphical_lasso(estimate.correlation, build.alpha)
        info.update({"alpha": fit.alpha, "glasso_converged": fit.converged, "glasso_note": fit.note})
        info["glasso_input"] = "correlation"
        return partial_correlation_from_precision(fit.precision), info
    raise ValueError(f"Unsupported graph layer `{build.layer}`.")


def build_snapshot(
    window_returns: pd.DataFrame,
    date: pd.Timestamp,
    build: SnapshotBuildConfig,
) -> GraphSnapshot | None:
    """Build one snapshot from an already-sliced trailing return window."""
    coverage = window_returns.notna().mean()
    valid = coverage[coverage >= (1.0 - build.max_missing_ratio)].index.tolist()
    excluded = [c for c in window_returns.columns if c not in valid]

    block_frame = window_returns[valid].dropna(axis=0, how="any")
    if len(valid) < build.min_nodes or len(block_frame) < max(10, build.window // 3):
        return None

    block = block_frame.to_numpy(dtype=float)
    raw, info = _build_raw_adjacency(block, build)

    stability: np.ndarray | None = None
    if build.bootstrap_iterations > 0:
        def _rebuild(resample: np.ndarray) -> np.ndarray:
            adjacency, _ = _build_raw_adjacency(resample, build)
            filtered, _ = filter_adjacency(
                adjacency,
                method="quantile" if build.edge_filter_method == "stability" else build.edge_filter_method,
                absolute_threshold=build.absolute_threshold,
                keep_fraction=build.top_edge_quantile,
                max_density=build.max_density,
            )
            return filtered

        stability = edge_stability(
            block,
            _rebuild,
            n_bootstrap=build.bootstrap_iterations,
            block_length=build.block_length,
            seed=build.seed + int(pd.Timestamp(date).value % 100000),
            n_jobs=build.n_jobs,
        )

    filtered, filter_info = filter_adjacency(
        raw,
        method=build.edge_filter_method,
        absolute_threshold=build.absolute_threshold,
        keep_fraction=build.top_edge_quantile,
        stability=stability,
        stability_threshold=build.edge_stability_threshold,
        max_density=build.max_density,
    )

    metadata = {
        **info,
        **filter_info,
        "nodes": list(valid),
        "n_window_observations": int(len(block_frame)),
        "raw_avg_abs_weight": float(np.abs(raw[np.triu_indices(len(valid), 1)]).mean())
        if len(valid) > 1
        else float("nan"),
    }
    return GraphSnapshot(
        date=pd.Timestamp(date),
        nodes=list(valid),
        adjacency=filtered,
        layer=build.layer,
        window=build.window,
        return_type=build.return_type,
        stability=stability,
        alpha=info.get("alpha"),
        n_excluded_nodes=len(excluded),
        excluded_nodes=excluded,
        metadata=metadata,
    )


def build_snapshot_series(
    returns: pd.DataFrame,
    build: SnapshotBuildConfig,
    dates: Sequence[pd.Timestamp] | None = None,
    progress_every: int = 250,
) -> SnapshotSeries:
    """Build snapshots for every (strided) date with a full trailing window."""
    returns = returns.sort_index()
    index = returns.index
    if dates is None:
        positions = range(build.window - 1, len(index), max(1, build.stride))
    else:
        wanted = set(pd.DatetimeIndex(dates))
        positions = [
            p for p in range(build.window - 1, len(index)) if index[p] in wanted
        ]

    snapshots: list[GraphSnapshot] = []
    skipped = 0
    for count, position in enumerate(positions, start=1):
        window_returns = returns.iloc[position - build.window + 1 : position + 1]
        snapshot = build_snapshot(window_returns, index[position], build)
        if snapshot is None:
            skipped += 1
            continue
        snapshots.append(snapshot)
        if progress_every and count % progress_every == 0:
            logger.info(
                "  %s w=%d: %d/%d snapshot(s) built ...",
                build.layer,
                build.window,
                len(snapshots),
                len(list(positions)) if not isinstance(positions, range) else len(positions),
            )

    if skipped:
        logger.warning(
            "%s w=%d: skipped %d date(s) with insufficient node coverage.",
            build.layer,
            build.window,
            skipped,
        )
    logger.info(
        "Built %d snapshot(s) for layer=%s window=%d returns=%s.",
        len(snapshots),
        build.layer,
        build.window,
        build.return_type,
    )
    return SnapshotSeries(
        snapshots=snapshots,
        layer=build.layer,
        window=build.window,
        return_type=build.return_type,
    )


def training_windows(
    returns: pd.DataFrame, window: int, train_end: pd.Timestamp, n_windows: int = 12
) -> list[np.ndarray]:
    """Sample return blocks from the TRAINING period only.

    Used to select the graphical-lasso alpha without ever touching validation or
    test data.
    """
    train = returns.loc[returns.index <= train_end]
    if len(train) < window + 5:
        raise ValueError("Training period is shorter than one graph window.")
    positions = np.linspace(window - 1, len(train) - 1, num=n_windows, dtype=int)
    blocks: list[np.ndarray] = []
    for position in np.unique(positions):
        block = train.iloc[position - window + 1 : position + 1].dropna(axis=1, how="any")
        block = block.dropna(axis=0, how="any")
        if block.shape[0] >= max(10, window // 2) and block.shape[1] >= 5:
            blocks.append(block.to_numpy(dtype=float))
    return blocks
