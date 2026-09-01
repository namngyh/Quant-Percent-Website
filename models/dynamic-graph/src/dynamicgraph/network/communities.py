r"""Community detection and community-comparison metrics.

    Q = (1/2m) sum_ij [A_ij - k_i k_j / 2m] * 1[c_i = c_j]

Method resolution: Leiden -> Louvain -> greedy modularity, with spectral
clustering available for comparison. Optional dependencies are probed once and
the fallback is recorded, so a missing `leidenalg` never breaks the pipeline.

Communities are *not* assumed to coincide with sectors; sector purity is
reported as a diagnostic, not enforced.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

_AVAILABILITY: dict[str, bool] | None = None


def available_methods() -> dict[str, bool]:
    global _AVAILABILITY
    if _AVAILABILITY is not None:
        return _AVAILABILITY
    availability = {"leiden": False, "louvain": False, "greedy": True, "spectral": False}
    try:
        import igraph  # noqa: F401
        import leidenalg  # noqa: F401

        availability["leiden"] = True
    except Exception:
        pass
    try:
        import community as community_louvain  # noqa: F401

        availability["louvain"] = True
    except Exception:
        pass
    try:
        from sklearn.cluster import SpectralClustering  # noqa: F401

        availability["spectral"] = True
    except Exception:
        pass
    _AVAILABILITY = availability
    missing = [k for k, v in availability.items() if not v]
    if missing:
        logger.info("Community backends unavailable: %s (fallbacks are in place).", missing)
    return availability


@dataclass
class CommunityResult:
    labels: dict[str, int]
    modularity: float
    method: str
    n_communities: int
    sizes: dict[int, int] = field(default_factory=dict)
    sector_purity: float | None = None

    def as_series(self) -> pd.Series:
        return pd.Series(self.labels, name="community")


def modularity(adjacency: np.ndarray, labels: np.ndarray) -> float:
    r"""Newman modularity of a weighted undirected partition."""
    weights = np.abs(adjacency)
    total = weights.sum()
    if total <= 0:
        return float("nan")
    degrees = weights.sum(axis=1)
    same = labels[:, None] == labels[None, :]
    expected = np.outer(degrees, degrees) / total
    return float(((weights - expected) * same).sum() / total)


def detect_communities(
    adjacency: np.ndarray,
    nodes: list[str],
    method: str = "auto",
    resolution: float = 1.0,
    seed: int = 42,
    sector_of: dict[str, str] | None = None,
) -> CommunityResult:
    """Partition the (absolute-weight) graph into communities."""
    weights = np.abs(np.asarray(adjacency, dtype=float))
    np.fill_diagonal(weights, 0.0)
    n = len(nodes)

    if n < 3 or weights.sum() == 0:
        labels = {node: 0 for node in nodes}
        return CommunityResult(labels, float("nan"), "trivial", 1, {0: n})

    availability = available_methods()
    if method == "auto":
        method = (
            "leiden" if availability["leiden"]
            else "louvain" if availability["louvain"]
            else "greedy"
        )

    label_array: np.ndarray | None = None
    used = method

    if method == "leiden" and availability["leiden"]:
        try:
            import igraph as ig
            import leidenalg

            sources, targets = np.triu_indices(n, k=1)
            mask = weights[sources, targets] > 0
            graph = ig.Graph(n=n, edges=list(zip(sources[mask], targets[mask])))
            graph.es["weight"] = weights[sources, targets][mask].tolist()
            partition = leidenalg.find_partition(
                graph,
                leidenalg.RBConfigurationVertexPartition,
                weights="weight",
                resolution_parameter=resolution,
                seed=seed,
            )
            label_array = np.array(partition.membership)
        except Exception as exc:
            logger.debug("Leiden failed (%s); falling back.", exc)
            used = "louvain" if availability["louvain"] else "greedy"

    if label_array is None and used == "louvain" and availability["louvain"]:
        try:
            import community as community_louvain
            import networkx as nx

            graph = nx.from_numpy_array(weights)
            mapping = community_louvain.best_partition(
                graph, weight="weight", resolution=resolution, random_state=seed
            )
            label_array = np.array([mapping[i] for i in range(n)])
        except Exception as exc:
            logger.debug("Louvain failed (%s); falling back to greedy modularity.", exc)
            used = "greedy"

    if label_array is None and used == "spectral" and availability["spectral"]:
        try:
            from sklearn.cluster import SpectralClustering

            k = max(2, min(6, n // 5))
            model = SpectralClustering(
                n_clusters=k, affinity="precomputed", random_state=seed, assign_labels="kmeans"
            )
            label_array = model.fit_predict(weights)
        except Exception as exc:
            logger.debug("Spectral clustering failed (%s); falling back to greedy.", exc)
            used = "greedy"

    if label_array is None:
        import networkx as nx
        from networkx.algorithms.community import greedy_modularity_communities

        graph = nx.from_numpy_array(weights)
        graph.remove_edges_from([(u, v) for u, v, w in graph.edges(data="weight") if w == 0])
        try:
            communities = list(greedy_modularity_communities(graph, weight="weight", resolution=resolution))
        except Exception:
            communities = list(greedy_modularity_communities(graph, weight="weight"))
        label_array = np.zeros(n, dtype=int)
        for cluster_id, members in enumerate(communities):
            for member in members:
                label_array[member] = cluster_id
        used = "greedy"

    labels = {nodes[i]: int(label_array[i]) for i in range(n)}
    sizes = pd.Series(label_array).value_counts().to_dict()

    purity = None
    if sector_of:
        purity = sector_purity(labels, sector_of)

    return CommunityResult(
        labels=labels,
        modularity=modularity(weights, label_array),
        method=used,
        n_communities=int(len(set(label_array))),
        sizes={int(k): int(v) for k, v in sizes.items()},
        sector_purity=purity,
    )


def sector_purity(labels: dict[str, int], sector_of: dict[str, str]) -> float:
    """Weighted share of each community occupied by its dominant sector."""
    frame = pd.DataFrame(
        {
            "ticker": list(labels),
            "community": [labels[t] for t in labels],
            "sector": [sector_of.get(t, "UNKNOWN") for t in labels],
        }
    )
    if frame.empty:
        return float("nan")
    total = 0.0
    for _, group in frame.groupby("community"):
        total += group["sector"].value_counts().iloc[0]
    return float(total / len(frame))


def compare_partitions(current: dict[str, int], previous: dict[str, int]) -> dict[str, float]:
    """ARI / NMI / mean matched-Jaccard between two partitions."""
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    shared = sorted(set(current) & set(previous))
    if len(shared) < 3:
        return {"ari": float("nan"), "nmi": float("nan"), "jaccard": float("nan")}

    a = [current[t] for t in shared]
    b = [previous[t] for t in shared]
    metrics = {
        "ari": float(adjusted_rand_score(b, a)),
        "nmi": float(normalized_mutual_info_score(b, a)),
    }

    groups_a = {label: {t for t in shared if current[t] == label} for label in set(a)}
    groups_b = {label: {t for t in shared if previous[t] == label} for label in set(b)}
    scores = []
    for members_b in groups_b.values():
        best = 0.0
        for members_a in groups_a.values():
            union = len(members_a | members_b)
            if union:
                best = max(best, len(members_a & members_b) / union)
        scores.append(best)
    metrics["jaccard"] = float(np.mean(scores)) if scores else float("nan")
    return metrics


def community_migration(
    history: pd.DataFrame, window: int = 20
) -> pd.DataFrame:
    """Per-ticker count of community changes over a rolling window.

    `history` is a date x ticker frame of community labels.
    """
    changed = history.ne(history.shift(1)) & history.notna() & history.shift(1).notna()
    return changed.rolling(window, min_periods=max(2, window // 2)).sum()


def participation_coefficient(adjacency: np.ndarray, labels: np.ndarray) -> np.ndarray:
    r"""P_i = 1 - sum_c (k_{i,c} / k_i)^2.

    Near 0 when a node's links stay inside its own community, near 1 when they
    are spread evenly across communities.
    """
    weights = np.abs(adjacency)
    strength = weights.sum(axis=1)
    out = np.zeros(len(labels))
    for community in np.unique(labels):
        mask = labels == community
        within = weights[:, mask].sum(axis=1)
        out += np.where(strength > 0, (within / np.clip(strength, 1e-12, None)) ** 2, 0.0)
    return np.where(strength > 0, 1.0 - out, 0.0)


def within_community_degree_z(adjacency: np.ndarray, labels: np.ndarray) -> np.ndarray:
    r"""z_i = (k_{i,within} - mean_c) / std_c, computed inside each community."""
    weights = np.abs(adjacency)
    out = np.zeros(len(labels))
    for community in np.unique(labels):
        mask = labels == community
        if mask.sum() < 2:
            continue
        within = weights[np.ix_(mask, mask)].sum(axis=1)
        std = within.std(ddof=1)
        out[mask] = (within - within.mean()) / std if std > 1e-12 else 0.0
    return out
