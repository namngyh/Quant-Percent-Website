r"""Graph snapshot containers.

A snapshot is `G_t = (V_t, E_t, X_t, A_t)`:
  * `V_t` -- nodes valid at t (a ticker with too much missing data inside the
    rolling window is dropped from the snapshot rather than silently imputed);
  * `A_t` -- signed weighted adjacency (partial correlation by default);
  * `X_t` -- node features at t, attached lazily by the consumer.

Both the signed and the absolute adjacency are kept, because several centrality
measures are undefined on negative weights. Which one a metric used is recorded
in the snapshot metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class GraphSnapshot:
    """One graph at one date, for one (layer, window, return_type)."""

    date: pd.Timestamp
    nodes: list[str]
    adjacency: np.ndarray           # signed, symmetric, zero diagonal
    layer: str = "partial_correlation"
    window: int = 60
    return_type: str = "residual"
    directed: bool = False
    stability: np.ndarray | None = None   # per-edge bootstrap selection frequency
    alpha: float | None = None            # graphical-lasso penalty actually used
    n_excluded_nodes: int = 0
    excluded_nodes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # float32 halves the memory of a long snapshot series (a 14-year daily
        # history across several layers and scales is tens of thousands of
        # matrices) and is far more precision than correlation estimates from
        # 20-252 observations can support.
        self.adjacency = np.asarray(self.adjacency, dtype=np.float32)
        if self.adjacency.shape != (len(self.nodes), len(self.nodes)):
            raise ValueError(
                f"Adjacency shape {self.adjacency.shape} does not match {len(self.nodes)} nodes."
            )
        np.fill_diagonal(self.adjacency, 0.0)
        if self.stability is not None:
            self.stability = np.asarray(self.stability, dtype=np.float32)
        # `metadata['nodes']` duplicates `self.nodes` for every snapshot; keep
        # the reference rather than a second list.
        if self.metadata.get("nodes") is not None:
            self.metadata["nodes"] = self.nodes

    # -- views ----------------------------------------------------------
    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    @property
    def absolute(self) -> np.ndarray:
        return np.abs(self.adjacency)

    @property
    def n_edges(self) -> int:
        return int(np.count_nonzero(np.triu(self.adjacency, k=1)))

    @property
    def density(self) -> float:
        n = self.n_nodes
        return (2.0 * self.n_edges / (n * (n - 1))) if n > 1 else 0.0

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.adjacency, index=self.nodes, columns=self.nodes)

    def edge_list(self, include_zero: bool = False) -> pd.DataFrame:
        """Upper-triangular edge list with signed / absolute weights."""
        i, j = np.triu_indices(self.n_nodes, k=1)
        weight = self.adjacency[i, j]
        keep = np.ones_like(weight, dtype=bool) if include_zero else weight != 0.0
        stability = (
            self.stability[i, j][keep]
            if self.stability is not None
            else np.full(int(keep.sum()), np.nan)
        )
        return pd.DataFrame(
            {
                "date": self.date,
                "source": [self.nodes[a] for a in i[keep]],
                "target": [self.nodes[b] for b in j[keep]],
                "signed_weight": weight[keep],
                "absolute_weight": np.abs(weight[keep]),
                "edge_sign": np.sign(weight[keep]).astype(int),
                "edge_type": self.layer,
                "window": self.window,
                "return_type": self.return_type,
                "stability": stability,
            }
        )

    def to_networkx(self, use_absolute: bool = True):
        """Build a NetworkX graph. `use_absolute` is recorded on the graph so a
        downstream metric can never silently forget which weights it consumed."""
        import networkx as nx

        matrix = self.absolute if use_absolute else self.adjacency
        graph = nx.from_numpy_array(matrix)
        graph = nx.relabel_nodes(graph, {i: n for i, n in enumerate(self.nodes)})
        graph.graph.update(
            {
                "date": str(self.date.date()),
                "layer": self.layer,
                "window": self.window,
                "return_type": self.return_type,
                "weights": "absolute" if use_absolute else "signed",
            }
        )
        # Drop zero-weight edges that `from_numpy_array` materialises.
        graph.remove_edges_from([(u, v) for u, v, w in graph.edges(data="weight") if w == 0.0])
        return graph

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": str(self.date.date()),
            "layer": self.layer,
            "window": self.window,
            "return_type": self.return_type,
            "n_nodes": self.n_nodes,
            "n_edges": self.n_edges,
            "density": self.density,
            "alpha": self.alpha,
            "excluded_nodes": self.excluded_nodes,
            "metadata": self.metadata,
        }


@dataclass
class DirectedSnapshot:
    """Directed layer (lead-lag or spillover). `adjacency[i, j]` is i -> j."""

    date: pd.Timestamp
    nodes: list[str]
    adjacency: np.ndarray
    layer: str = "lead_lag"
    window: int = 120
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def out_strength(self) -> pd.Series:
        return pd.Series(np.abs(self.adjacency).sum(axis=1), index=self.nodes)

    @property
    def in_strength(self) -> pd.Series:
        return pd.Series(np.abs(self.adjacency).sum(axis=0), index=self.nodes)

    @property
    def net_spillover(self) -> pd.Series:
        return self.out_strength - self.in_strength

    def edge_list(self) -> pd.DataFrame:
        i, j = np.nonzero(self.adjacency)
        return pd.DataFrame(
            {
                "date": self.date,
                "source": [self.nodes[a] for a in i],
                "target": [self.nodes[b] for b in j],
                "weight": self.adjacency[i, j],
                "edge_type": self.layer,
                "window": self.window,
                "direction": "directed",
            }
        )


@dataclass
class SnapshotSeries:
    """Ordered collection of snapshots for one (layer, window, return_type)."""

    snapshots: list[GraphSnapshot] = field(default_factory=list)
    layer: str = "partial_correlation"
    window: int = 60
    return_type: str = "residual"

    def __len__(self) -> int:
        return len(self.snapshots)

    def __iter__(self) -> Iterator[GraphSnapshot]:
        return iter(self.snapshots)

    def __getitem__(self, item: int) -> GraphSnapshot:
        return self.snapshots[item]

    @property
    def key(self) -> str:
        return f"{self.layer}__{self.return_type}__w{self.window}"

    @property
    def dates(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex([s.date for s in self.snapshots])

    def by_date(self) -> dict[pd.Timestamp, GraphSnapshot]:
        return {s.date: s for s in self.snapshots}

    def latest(self) -> GraphSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None

    def edge_frame(self) -> pd.DataFrame:
        if not self.snapshots:
            return pd.DataFrame()
        return pd.concat([s.edge_list() for s in self.snapshots], ignore_index=True)

    # -- persistence ----------------------------------------------------
    def save(self, directory: Path) -> Path:
        """Persist as a compressed edge list + a NumPy archive of adjacencies."""
        directory.mkdir(parents=True, exist_ok=True)
        base = directory / self.key

        edges = self.edge_frame()
        edge_path = base.with_suffix(".edges.parquet")
        try:
            edges.to_parquet(edge_path, index=False)
        except Exception:
            edge_path = base.with_suffix(".edges.csv.gz")
            edges.to_csv(edge_path, index=False, compression="gzip")

        arrays = {}
        for snapshot in self.snapshots:
            stamp = snapshot.date.strftime("%Y%m%d")
            arrays[f"A_{stamp}"] = snapshot.adjacency.astype(np.float32)
            if snapshot.stability is not None:
                arrays[f"S_{stamp}"] = snapshot.stability.astype(np.float32)
        np.savez_compressed(base.with_suffix(".adj.npz"), **arrays)

        meta = {
            "layer": self.layer,
            "window": self.window,
            "return_type": self.return_type,
            "n_snapshots": len(self.snapshots),
            "snapshots": [s.to_dict() for s in self.snapshots],
        }
        base.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
        logger.info("Saved %d snapshot(s) to %s.*", len(self.snapshots), base)
        return base

    @classmethod
    def load(cls, directory: Path, key: str) -> "SnapshotSeries":
        base = directory / key
        meta = json.loads(base.with_suffix(".meta.json").read_text(encoding="utf-8"))
        archive = np.load(base.with_suffix(".adj.npz"))
        snapshots: list[GraphSnapshot] = []
        for entry in meta["snapshots"]:
            date = pd.Timestamp(entry["date"])
            stamp = date.strftime("%Y%m%d")
            nodes = entry["metadata"].get("nodes")
            if nodes is None:
                raise ValueError("Snapshot metadata is missing its node list; rebuild the graphs.")
            adjacency = archive[f"A_{stamp}"].astype(float)
            stability = archive[f"S_{stamp}"].astype(float) if f"S_{stamp}" in archive else None
            snapshots.append(
                GraphSnapshot(
                    date=date,
                    nodes=list(nodes),
                    adjacency=adjacency,
                    layer=entry["layer"],
                    window=entry["window"],
                    return_type=entry["return_type"],
                    stability=stability,
                    alpha=entry.get("alpha"),
                    excluded_nodes=entry.get("excluded_nodes", []),
                    metadata=entry.get("metadata", {}),
                )
            )
        return cls(
            snapshots=snapshots,
            layer=meta["layer"],
            window=meta["window"],
            return_type=meta["return_type"],
        )
