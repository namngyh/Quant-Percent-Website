"""Feature-set assembly.

Three sets exist so incremental value can be attributed:

  A  `market`    -- VN30 price/vol/drawdown/breadth only, no network information
  B  `graph`     -- network metrics only, no direct index price information
  C  `combined`  -- A + B

Ablation variants (no-community, no-spectral, no-centrality, single-scale ...)
are produced by filtering set B with the column-group rules below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

#: Substrings that identify each family of graph columns.
GRAPH_COLUMN_GROUPS: dict[str, tuple[str, ...]] = {
    "community": ("modularity", "communit", "sector_purity", "ari", "nmi", "jaccard"),
    "spectral": (
        "spectral", "algebraic", "laplacian", "eigenvalue", "market_mode_share",
        "eigenvector",
    ),
    "centrality": ("centrality", "strength", "degree", "coreness", "herfindahl", "concentration"),
    "density": ("density", "number_of_edges", "edge_weight", "clustering", "transitivity",
                "assortativity", "largest_cc"),
    "turnover": ("turnover",),
    "correlation": ("correlation", "diversification", "mst"),
    "connectedness": ("total_connectedness", "net_spillover"),
}


@dataclass
class FeatureSetBuilder:
    """Builds the aligned design matrices for each feature set."""

    market_features: pd.DataFrame
    graph_features: pd.DataFrame
    index: pd.DatetimeIndex = field(default_factory=pd.DatetimeIndex)
    min_coverage: float = 0.60

    def __post_init__(self) -> None:
        if len(self.index) == 0:
            shared = self.market_features.index.intersection(self.graph_features.index)
            self.index = pd.DatetimeIndex(sorted(shared))
        self.market_features = self.market_features.reindex(self.index)
        self.graph_features = self.graph_features.reindex(self.index)

    # -- column selection ------------------------------------------------
    def _usable(self, frame: pd.DataFrame) -> pd.DataFrame:
        numeric = frame.select_dtypes(include=[np.number])
        coverage = numeric.notna().mean()
        keep = coverage[coverage >= self.min_coverage].index
        dropped = sorted(set(numeric.columns) - set(keep))
        if dropped:
            logger.debug("Dropping %d low-coverage feature(s): %s", len(dropped), dropped[:10])
        usable = numeric[keep]
        # Constant columns carry no information and destabilise scalers.
        variance = usable.std(ddof=0)
        constant = variance[variance.fillna(0.0) <= 1e-12].index
        return usable.drop(columns=list(constant))

    def market(self) -> pd.DataFrame:
        return self._usable(self.market_features)

    def graph(self, exclude_groups: Iterable[str] = (), only_windows: Iterable[int] | None = None) -> pd.DataFrame:
        frame = self._usable(self.graph_features)
        exclude_groups = list(exclude_groups)

        if exclude_groups:
            patterns = tuple(p for g in exclude_groups for p in GRAPH_COLUMN_GROUPS.get(g, ()))
            if patterns:
                drop = [c for c in frame.columns if any(p in c.lower() for p in patterns)]
                frame = frame.drop(columns=drop)
                logger.debug("Ablation removed %d %s column(s).", len(drop), exclude_groups)

        if only_windows is not None:
            wanted = {f"_w{int(w)}" for w in only_windows}
            keep = [c for c in frame.columns if any(tag in c for tag in wanted)]
            if keep:
                frame = frame[keep]
        return frame

    def combined(self, **graph_kwargs: Any) -> pd.DataFrame:
        market = self.market()
        graph = self.graph(**graph_kwargs)
        overlap = set(market.columns) & set(graph.columns)
        if overlap:
            graph = graph.drop(columns=list(overlap))
        return pd.concat([market, graph], axis=1)

    def build(self, feature_set: str, **kwargs: Any) -> pd.DataFrame:
        if feature_set == "market":
            return self.market()
        if feature_set == "graph":
            return self.graph(**kwargs)
        if feature_set == "combined":
            return self.combined(**kwargs)
        raise ValueError(f"Unknown feature set `{feature_set}`.")

    def describe(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"feature_set": "market", "n_features": self.market().shape[1]},
                {"feature_set": "graph", "n_features": self.graph().shape[1]},
                {"feature_set": "combined", "n_features": self.combined().shape[1]},
            ]
        )


#: Graph metrics that carry distinct information about network state. Every
#: numeric column in the metric frame would be ~53 per layer; with 10 layers and
#: 4 derived series each that is >2000 features against ~3600 observations,
#: which is hopeless p >> n regardless of the model. This whitelist keeps one
#: representative per concept.
CORE_GRAPH_METRICS: tuple[str, ...] = (
    "graph_density",
    "average_strength",
    "avg_abs_partial_correlation",
    "average_absolute_correlation",
    "spectral_radius",
    "algebraic_connectivity",
    "laplacian_entropy",
    "eigenvalue_concentration",
    "market_mode_share",
    "negative_diversification",
    "centrality_concentration",
    "largest_cc_share",
    "average_clustering",
    "assortativity",
    "modularity",
    "number_of_communities",
    "largest_community_share",
    "community_compression",
    "edge_turnover",
    "community_nmi",
    "positive_edge_ratio",
    "mst_length",
    "network_fragility",
)


def flatten_graph_metrics(
    metrics_by_key: dict[str, pd.DataFrame],
    index: pd.DatetimeIndex,
    include_dynamics: bool = True,
    metrics: tuple[str, ...] | None = CORE_GRAPH_METRICS,
) -> pd.DataFrame:
    """Flatten `{layer__returns__wNN: metric frame}` into one wide frame.

    Column names become `{metric}__{layer}_{return_type}_w{window}` so the
    ablation filters can address a specific scale or family. Pass
    `metrics=None` to keep every numeric column (useful for diagnostics, not for
    modelling).
    """
    parts: list[pd.DataFrame] = []
    for key, frame in metrics_by_key.items():
        if frame is None or frame.empty:
            continue
        numeric = frame.select_dtypes(include=[np.number])
        if metrics is not None:
            keep = [c for c in numeric.columns if c in metrics]
            if keep:
                numeric = numeric[keep]
        suffix = key.replace("partial_correlation", "pc").replace("correlation", "corr")
        suffix = suffix.replace("__", "_")
        renamed = numeric.rename(columns={c: f"{c}__{suffix}" for c in numeric.columns})
        parts.append(renamed)

    if not parts:
        return pd.DataFrame(index=index)

    wide = pd.concat(parts, axis=1)
    wide = wide.reindex(index)
    # Snapshots may be strided; carry the last known network state forward. This
    # is backward-looking (ffill only) and therefore introduces no look-ahead.
    wide = wide.ffill(limit=10)
    if include_dynamics:
        wide = _add_dynamics(wide)
    return wide


def _add_dynamics(frame: pd.DataFrame, windows: tuple[int, ...] = (20,)) -> pd.DataFrame:
    """Add trailing changes, z-scores and percentile ranks of every column.

    Columns are collected and concatenated once: assigning several hundred
    columns one at a time fragments the block manager and is roughly an order of
    magnitude slower.
    """
    parts: list[pd.DataFrame] = [frame]
    for window in windows:
        diffs = frame.diff(window)
        parts.append(diffs.rename(columns={c: f"{c}_chg{window}" for c in diffs.columns}))

    rolling_mean = frame.rolling(60, min_periods=20).mean()
    rolling_std = frame.rolling(60, min_periods=20).std(ddof=1)
    z = (frame - rolling_mean) / (rolling_std + 1e-12)
    parts.append(z.rename(columns={c: f"{c}_z60" for c in z.columns}))

    # `pct252` is deliberately omitted: it is a monotone transform of the level
    # over a trailing window and near-duplicates `z60`, while doubling the
    # feature count.
    out = pd.concat(parts, axis=1)
    return out.replace([np.inf, -np.inf], np.nan)


ABLATION_VARIANTS: dict[str, dict[str, Any]] = {
    "market_only": {"feature_set": "market"},
    "graph_only": {"feature_set": "graph"},
    "market_plus_graph": {"feature_set": "combined"},
    "correlation_graph": {"feature_set": "graph", "layer_filter": "corr"},
    "partial_correlation_graph": {"feature_set": "graph", "layer_filter": "pc"},
    "raw_return_graph": {"feature_set": "graph", "return_filter": "raw"},
    "residual_return_graph": {"feature_set": "graph", "return_filter": "residual"},
    "single_scale_60": {"feature_set": "graph", "only_windows": [60]},
    "single_scale_120": {"feature_set": "graph", "only_windows": [120]},
    "multi_scale": {"feature_set": "graph"},
    "no_community_features": {"feature_set": "combined", "exclude_groups": ["community"]},
    "no_spectral_features": {"feature_set": "combined", "exclude_groups": ["spectral"]},
    "no_centrality_features": {"feature_set": "combined", "exclude_groups": ["centrality"]},
    "baseline_tabular": {"feature_set": "market"},
}


def apply_variant_filters(frame: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    """Apply layer / return-type / scale filters for an ablation variant.

    A filter that matches nothing returns an EMPTY frame rather than silently
    falling back to the unfiltered set. Reporting the full-graph result under a
    label such as "raw_return_graph" -- when the raw-return layer was never
    built -- would be a fabricated ablation row. The caller skips empty variants
    and says so.
    """
    out = frame
    if spec.get("layer_filter"):
        tag = spec["layer_filter"]
        keep = [c for c in out.columns if f"__{tag}_" in c or c.endswith(f"__{tag}")]
        out = out[keep]
        if not keep:
            logger.info("Ablation filter layer=`%s` matched no column; variant is unavailable.", tag)
            return out
    if spec.get("return_filter"):
        tag = spec["return_filter"]
        keep = [c for c in out.columns if f"_{tag}_" in c]
        out = out[keep]
        if not keep:
            logger.info(
                "Ablation filter return_type=`%s` matched no column; the layer was not built, "
                "so this variant is unavailable.", tag,
            )
            return out
    if spec.get("only_windows"):
        wanted = {f"_w{int(w)}" for w in spec["only_windows"]}
        keep = [c for c in out.columns if any(t in c for t in wanted)]
        out = out[keep]
        if not keep:
            logger.info(
                "Ablation filter windows=%s matched no column; those scales were not built.",
                spec["only_windows"],
            )
    return out
