"""Figure generation.

Matplotlib only (Agg backend) so the pipeline runs headless. Every figure is
quantitative: no decorative chart is produced. Any figure whose inputs are
missing is skipped with a log line rather than failing the run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from dynamicgraph.logging_config import get_logger  # noqa: E402

logger = get_logger(__name__)

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "savefig.dpi": 140,
        "savefig.bbox": "tight",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "figure.autolayout": False,
    }
)

PALETTE = {
    "primary": "#2E5EAA",
    "secondary": "#D1495B",
    "accent": "#00798C",
    "warm": "#EDAE49",
    "muted": "#8D99AE",
    "dark": "#1D3557",
}


class FigureWriter:
    """Saves figures into `artifacts/figures` and records what was produced."""

    def __init__(self, directory: Path, enabled: bool = True) -> None:
        self.directory = Path(directory)
        self.enabled = enabled
        self.written: list[str] = []
        self.skipped: list[str] = []
        if enabled:
            self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, figure: Figure, name: str) -> Path | None:
        if not self.enabled:
            plt.close(figure)
            return None
        path = self.directory / f"{name}.png"
        try:
            figure.savefig(path)
            self.written.append(name)
            return path
        except Exception as exc:
            logger.warning("Could not save figure %s: %s", name, exc)
            return None
        finally:
            plt.close(figure)

    def skip(self, name: str, reason: str) -> None:
        self.skipped.append(name)
        logger.info("Figure `%s` skipped: %s", name, reason)


# ---------------------------------------------------------------------------
# Network figures
# ---------------------------------------------------------------------------
def plot_network(
    snapshot: Any,
    communities: Any = None,
    node_metrics: pd.DataFrame | None = None,
    title: str | None = None,
) -> Figure:
    """Spring-layout network coloured by community, sized by strength."""
    import networkx as nx

    graph = snapshot.to_networkx(use_absolute=True)
    figure, ax = plt.subplots(figsize=(9, 8))

    labels = getattr(communities, "labels", {}) or {}
    community_ids = sorted(set(labels.values())) or [0]
    colormap = plt.get_cmap("tab10")
    colors = [colormap(community_ids.index(labels.get(n, 0)) % 10) for n in graph.nodes]

    strength = np.abs(snapshot.adjacency).sum(axis=1)
    strength_map = dict(zip(snapshot.nodes, strength))
    sizes = [200 + 1400 * (strength_map.get(n, 0) / (strength.max() + 1e-12)) for n in graph.nodes]

    try:
        positions = nx.spring_layout(graph, weight="weight", seed=42, k=0.9, iterations=200)
    except Exception:
        positions = nx.circular_layout(graph)

    weights = np.array([d.get("weight", 0.0) for _, _, d in graph.edges(data=True)])
    if weights.size:
        normalized = weights / (weights.max() + 1e-12)
        widths = 0.5 + 4.0 * normalized
        # Fade weak edges rather than drawing every edge at one alpha, so edge
        # strength is readable without the strong edges being lost in the mesh.
        alphas = 0.18 + 0.62 * normalized
        nx.draw_networkx_edges(
            graph, positions, ax=ax, width=widths, alpha=alphas, edge_color=PALETTE["dark"]
        )
    nx.draw_networkx_nodes(graph, positions, ax=ax, node_size=sizes, node_color=colors,
                           edgecolors="white", linewidths=1.2)
    nx.draw_networkx_labels(graph, positions, ax=ax, font_size=8, font_weight="bold")

    ax.set_title(
        title
        or f"VN30 {snapshot.layer.replace('_', ' ')} network - "
           f"{pd.Timestamp(snapshot.date).date()} (window {snapshot.window}d, {snapshot.return_type} returns)"
    )
    ax.axis("off")
    ax.text(
        0.01, 0.01,
        f"{snapshot.n_nodes} nodes | {snapshot.n_edges} edges | density {snapshot.density:.3f}\n"
        "Node size = network strength; colour = community. Edges are statistical associations.",
        transform=ax.transAxes, fontsize=8, color=PALETTE["muted"], va="bottom",
    )
    return figure


def plot_network_grid(snapshots: list[Any], communities_by_date: Mapping[Any, Any] | None = None) -> Figure:
    """Small multiples of the network at several points in time."""
    import networkx as nx

    n = len(snapshots)
    cols = min(3, n)
    rows = int(np.ceil(n / cols))
    figure, axes = plt.subplots(rows, cols, figsize=(5 * cols, 4.6 * rows))
    axes = np.atleast_1d(axes).ravel()

    for ax, snapshot in zip(axes, snapshots):
        graph = snapshot.to_networkx(use_absolute=True)
        labels = getattr((communities_by_date or {}).get(snapshot.date), "labels", {}) or {}
        ids = sorted(set(labels.values())) or [0]
        colormap = plt.get_cmap("tab10")
        colors = [colormap(ids.index(labels.get(node, 0)) % 10) for node in graph.nodes]
        try:
            positions = nx.spring_layout(graph, weight="weight", seed=42, k=1.0, iterations=120)
        except Exception:
            positions = nx.circular_layout(graph)
        nx.draw_networkx_edges(graph, positions, ax=ax, alpha=0.2, edge_color=PALETTE["muted"])
        nx.draw_networkx_nodes(graph, positions, ax=ax, node_size=90, node_color=colors)
        ax.set_title(
            f"{pd.Timestamp(snapshot.date).date()}\ndensity {snapshot.density:.3f}", fontsize=10
        )
        ax.axis("off")
    for ax in axes[n:]:
        ax.axis("off")
    figure.suptitle("VN30 network structure through time", fontsize=13)
    return figure


# ---------------------------------------------------------------------------
# Time-series figures
# ---------------------------------------------------------------------------
def plot_stress_history(
    stress: pd.DataFrame, index_price: pd.Series | None = None, states: pd.Series | None = None
) -> Figure:
    figure, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, height_ratios=[2, 1])

    axes[0].plot(stress.index, stress["stress_score"], color=PALETTE["secondary"], lw=1.4,
                 label="Network Stress Score")
    axes[0].axhline(50, color=PALETTE["muted"], ls="--", lw=0.8, alpha=0.7)
    if states is not None:
        high = states[states == "high_stress"]
        if len(high):
            axes[0].scatter(high.index, stress.loc[high.index, "stress_score"],
                            s=8, color=PALETTE["dark"], label="high stress state", zorder=3)
    axes[0].set_ylabel("Stress score (0-100)")
    axes[0].set_title("Network Stress Score history")
    axes[0].legend(loc="upper left")

    if index_price is not None:
        aligned = index_price.reindex(stress.index)
        axes[1].plot(aligned.index, aligned, color=PALETTE["primary"], lw=1.2)
        axes[1].set_ylabel("VN30 (adjusted)")
        axes[1].set_title("VN30 index level")
    axes[1].set_xlabel("Date")
    return figure


def plot_stress_vs_drawdown(stress: pd.DataFrame, drawdown: pd.Series) -> Figure:
    figure, ax = plt.subplots(figsize=(12, 5))
    ax.plot(stress.index, stress["stress_score"], color=PALETTE["secondary"], lw=1.3,
            label="Network Stress Score")
    ax.set_ylabel("Stress score (0-100)", color=PALETTE["secondary"])
    ax.tick_params(axis="y", labelcolor=PALETTE["secondary"])

    twin = ax.twinx()
    aligned = drawdown.reindex(stress.index)
    twin.fill_between(aligned.index, aligned * 100, 0, color=PALETTE["primary"], alpha=0.25)
    twin.set_ylabel("VN30 drawdown (%)", color=PALETTE["primary"])
    twin.tick_params(axis="y", labelcolor=PALETTE["primary"])
    twin.grid(False)

    ax.set_title("Network Stress Score vs VN30 drawdown")
    ax.set_xlabel("Date")
    return figure


def plot_metric_history(metrics: pd.DataFrame, column: str, title: str, ylabel: str | None = None) -> Figure:
    figure, ax = plt.subplots(figsize=(11, 4))
    series = metrics[column].dropna()
    ax.plot(series.index, series, color=PALETTE["primary"], lw=1.2)
    rolling = series.rolling(60, min_periods=20).mean()
    ax.plot(rolling.index, rolling, color=PALETTE["secondary"], lw=1.6, label="60-day mean")
    ax.set_title(title)
    ax.set_ylabel(ylabel or column.replace("_", " "))
    ax.set_xlabel("Date")
    ax.legend()
    return figure


def plot_multi_metric_history(metrics: pd.DataFrame, columns: list[str], title: str) -> Figure:
    available = [c for c in columns if c in metrics.columns and metrics[c].notna().any()]
    figure, axes = plt.subplots(len(available), 1, figsize=(11, 2.4 * len(available)), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, column in zip(axes, available):
        series = metrics[column].dropna()
        ax.plot(series.index, series, color=PALETTE["primary"], lw=1.1)
        ax.set_ylabel(column.replace("_", " ")[:26], fontsize=9)
    axes[0].set_title(title)
    axes[-1].set_xlabel("Date")
    return figure


def plot_centrality_heatmap(history: pd.DataFrame, title: str = "Node centrality through time") -> Figure:
    figure, ax = plt.subplots(figsize=(13, 7))
    data = history.T
    image = ax.imshow(data.to_numpy(dtype=float), aspect="auto", cmap="RdYlBu_r", interpolation="nearest")
    ax.set_yticks(range(len(data.index)))
    ax.set_yticklabels(data.index, fontsize=8)
    step = max(1, len(data.columns) // 12)
    ax.set_xticks(range(0, len(data.columns), step))
    ax.set_xticklabels(
        [pd.Timestamp(d).strftime("%Y-%m") for d in data.columns[::step]], rotation=45, ha="right", fontsize=8
    )
    ax.set_title(title)
    ax.grid(False)
    figure.colorbar(image, ax=ax, label="centrality (cross-sectional percentile)")
    return figure


def plot_top_nodes_over_time(history: pd.DataFrame, top_n: int = 8) -> Figure:
    figure, ax = plt.subplots(figsize=(12, 5))
    ranking = history.mean().sort_values(ascending=False).head(top_n)
    colormap = plt.get_cmap("tab10")
    for i, ticker in enumerate(ranking.index):
        series = history[ticker].rolling(20, min_periods=5).mean()
        ax.plot(series.index, series, lw=1.4, label=ticker, color=colormap(i % 10))
    ax.set_title(f"Top {top_n} influence nodes by average network strength (20-day smoothed)")
    ax.set_ylabel("Network strength")
    ax.set_xlabel("Date")
    ax.legend(ncol=4, fontsize=8)
    return figure


# ---------------------------------------------------------------------------
# Model-evaluation figures
# ---------------------------------------------------------------------------
def plot_calibration_curve(reliability: pd.DataFrame, title: str = "Calibration") -> Figure:
    figure, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], ls="--", color=PALETTE["muted"], label="perfect calibration")
    if not reliability.empty:
        ax.plot(reliability["mean_predicted"], reliability["observed_frequency"],
                "o-", color=PALETTE["secondary"], lw=1.6, label="model")
        for _, row in reliability.iterrows():
            ax.annotate(f"n={int(row['n'])}", (row["mean_predicted"], row["observed_frequency"]),
                        fontsize=7, xytext=(3, -9), textcoords="offset points", color=PALETTE["muted"])
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed frequency")
    ax.set_title(title)
    # Rare-event models predict in a narrow low range; a fixed 0-1 box hides the
    # entire curve in the bottom-left corner. Zoom to the data, keeping the
    # diagonal in view so miscalibration stays visually obvious.
    if not reliability.empty:
        upper = float(
            max(reliability["mean_predicted"].max(), reliability["observed_frequency"].max())
        )
        limit = min(1.0, max(0.2, upper * 1.25))
    else:
        limit = 1.0
    ax.set_xlim(0, limit)
    ax.set_ylim(0, limit)
    ax.set_aspect("equal", adjustable="box")
    ax.legend()
    return figure


def plot_roc_pr(roc: pd.DataFrame, pr: pd.DataFrame, base_rate: float, title: str = "") -> Figure:
    figure, axes = plt.subplots(1, 2, figsize=(11, 5))
    if not roc.empty:
        axes[0].plot(roc["fpr"], roc["tpr"], color=PALETTE["primary"], lw=1.6)
    axes[0].plot([0, 1], [0, 1], ls="--", color=PALETTE["muted"])
    axes[0].set_xlabel("False positive rate")
    axes[0].set_ylabel("True positive rate")
    axes[0].set_title("ROC curve")

    if not pr.empty:
        axes[1].plot(pr["recall"], pr["precision"], color=PALETTE["secondary"], lw=1.6)
    axes[1].axhline(base_rate, ls="--", color=PALETTE["muted"], label=f"base rate {base_rate:.3f}")
    axes[1].set_xlabel("Recall")
    axes[1].set_ylabel("Precision")
    axes[1].set_title("Precision-recall curve")
    axes[1].legend()
    figure.suptitle(title)
    return figure


def plot_confusion_matrix(matrix: pd.DataFrame, title: str = "Confusion matrix") -> Figure:
    figure, ax = plt.subplots(figsize=(5.5, 5))
    values = matrix.to_numpy(dtype=float)
    ax.imshow(values, cmap="Blues")
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            ax.text(j, i, f"{int(values[i, j])}", ha="center", va="center",
                    color="white" if values[i, j] > values.max() / 2 else "black", fontsize=13)
    ax.set_xticks(range(len(matrix.columns)))
    ax.set_xticklabels([c.replace("predicted_", "") for c in matrix.columns])
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels([i.replace("actual_", "") for i in matrix.index])
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(title)
    ax.grid(False)
    return figure


def plot_probability_timeline(predictions: pd.DataFrame, threshold: float = 0.5) -> Figure:
    figure, ax = plt.subplots(figsize=(12, 4.5))
    frame = predictions.set_index("date").sort_index()
    ax.plot(frame.index, frame["probability"], color=PALETTE["secondary"], lw=1.0, label="OOS probability")
    ax.axhline(threshold, ls="--", color=PALETTE["muted"], lw=0.9, label=f"threshold {threshold:.2f}")
    stress = frame[frame["y_true"] > 0.5]
    if len(stress):
        ax.scatter(stress.index, np.full(len(stress), -0.03), s=6, color=PALETTE["dark"],
                   marker="|", label="realised stress")
    ax.set_ylim(-0.06, 1.02)
    ax.set_ylabel("P(stress)")
    ax.set_xlabel("Date")
    ax.set_title("Out-of-sample stress probability timeline")
    ax.legend(ncol=3, fontsize=8)
    return figure


def plot_feature_importance(importance: pd.DataFrame, top_n: int = 20, title: str = "Feature importance") -> Figure:
    frame = importance.head(top_n).iloc[::-1]
    value_column = "importance_mean" if "importance_mean" in frame.columns else frame.columns[1]
    figure, ax = plt.subplots(figsize=(9, max(4, 0.32 * len(frame))))
    ax.barh(frame["feature"], frame[value_column], color=PALETTE["primary"])
    if "importance_std" in frame.columns:
        ax.errorbar(frame[value_column], frame["feature"], xerr=frame["importance_std"],
                    fmt="none", ecolor=PALETTE["muted"], elinewidth=1)
    ax.set_xlabel(value_column.replace("_", " "))
    ax.set_title(f"{title}\n(permutation importance on out-of-sample data - predictive, not causal)")
    ax.tick_params(axis="y", labelsize=8)
    return figure


def plot_ablation(ablation: pd.DataFrame) -> Figure:
    frame = ablation.sort_values("brier").iloc[::-1]
    figure, axes = plt.subplots(1, 2, figsize=(13, max(4, 0.36 * len(frame))))
    axes[0].barh(frame["variant"], frame["brier"], color=PALETTE["primary"])
    axes[0].set_xlabel("Brier score (lower is better)")
    axes[0].set_title("Ablation: Brier score by feature variant")
    axes[0].tick_params(axis="y", labelsize=8)

    if "auprc" in frame.columns:
        axes[1].barh(frame["variant"], frame["auprc"], color=PALETTE["accent"])
        if "base_rate" in frame.columns and frame["base_rate"].notna().any():
            # AUPRC must be read against the positive base rate, not against
            # 0.5: a random model scores the base rate by construction.
            base_rate = float(frame["base_rate"].median())
            axes[1].axvline(
                base_rate, ls="--", lw=1.2, color=PALETTE["secondary"],
                label=f"base rate {base_rate:.3f} (random model)",
            )
            axes[1].legend(fontsize=8, loc="lower right")
        axes[1].set_xlabel("AUPRC (higher is better)")
        axes[1].set_title("Ablation: AUPRC by feature variant")
        axes[1].set_yticklabels([])
    return figure


def plot_model_comparison(metrics: pd.DataFrame, metric: str = "brier") -> Figure:
    frame = metrics.dropna(subset=[metric]).copy()
    if frame.empty:
        raise ValueError("no metrics to plot")
    frame["label"] = frame["model"] + " / " + frame["feature_set"]
    pivot = frame.pivot_table(index="label", columns="horizon", values=metric, aggfunc="mean")
    figure, ax = plt.subplots(figsize=(11, max(4, 0.4 * len(pivot))))
    pivot.plot(kind="barh", ax=ax, colormap="viridis", width=0.8)
    ax.set_xlabel(f"{metric} ({'lower' if metric in {'brier', 'log_loss'} else 'higher'} is better)")
    ax.set_ylabel("")
    ax.set_title(f"Out-of-sample {metric} by model and feature set")
    ax.legend(title="horizon (days)", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    return figure


def plot_walk_forward_performance(fold_metrics: pd.DataFrame, metric: str = "brier") -> Figure:
    """Per-fold stability of out-of-sample performance.

    Plotting every (target x feature set x model) combination individually
    produces an unreadable spaghetti chart with a legend larger than the axes.
    Instead each feature set is summarised by its median across models and
    targets, with an inter-quartile band, which is what "is performance stable
    across folds?" actually asks.
    """
    frame = fold_metrics.dropna(subset=[metric]).copy()
    if frame.empty or "key" not in frame.columns:
        raise ValueError("no fold metrics to plot")

    # `key` is "<target>__<feature_set>__<model>".
    parts = frame["key"].astype(str).str.split("__", expand=True)
    frame["feature_set"] = parts[1] if parts.shape[1] > 1 else "all"
    frame["model"] = parts[2] if parts.shape[1] > 2 else "all"

    figure, ax = plt.subplots(figsize=(11.5, 5))
    colours = {"market": PALETTE["primary"], "graph": PALETTE["accent"],
               "combined": PALETTE["secondary"]}

    for feature_set, group in frame[frame["model"] != "naive_frequency"].groupby("feature_set"):
        summary = group.groupby("fold")[metric].agg(["median", lambda s: s.quantile(0.25),
                                                     lambda s: s.quantile(0.75)])
        summary.columns = ["median", "q25", "q75"]
        colour = colours.get(str(feature_set), PALETTE["muted"])
        ax.plot(summary.index, summary["median"], "o-", lw=1.8, ms=4, color=colour,
                label=f"{feature_set} (median over models)")
        ax.fill_between(summary.index, summary["q25"], summary["q75"], color=colour, alpha=0.15)

    naive = frame[frame["model"] == "naive_frequency"]
    if not naive.empty:
        reference = naive.groupby("fold")[metric].median()
        ax.plot(reference.index, reference, "--", lw=1.6, color=PALETTE["dark"],
                label="naive base-rate baseline")

    ax.set_xlabel("Walk-forward fold (chronological)")
    ax.set_ylabel(f"{metric} ({'lower' if metric in {'brier', 'log_loss'} else 'higher'} is better)")
    ax.set_title(
        f"Per-fold out-of-sample {metric} by feature set\n"
        "(line = median across models and horizons, band = inter-quartile range)"
    )
    ax.legend(fontsize=9)
    return figure


def plot_graph_comparison(comparison: pd.DataFrame) -> Figure:
    figure, ax = plt.subplots(figsize=(9, max(3.5, 0.45 * len(comparison))))
    labels = comparison["variant_a"] + "\nvs " + comparison["variant_b"]
    ax.barh(labels, comparison["spearman_centrality"], color=PALETTE["accent"])
    ax.axvline(0.7, ls="--", color=PALETTE["muted"], label="0.7 agreement")
    ax.set_xlabel("Spearman correlation of node centrality")
    ax.set_title("Agreement between graph construction variants")
    ax.tick_params(axis="y", labelsize=8)
    ax.legend()
    return figure


def plot_sensitivity(frame: pd.DataFrame, x: str, y: str, title: str) -> Figure:
    figure, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(frame[x], frame[y], "o-", color=PALETTE["primary"], lw=1.6)
    ax.set_xlabel(x.replace("_", " "))
    ax.set_ylabel(y.replace("_", " "))
    ax.set_title(title)
    if x == "alpha":
        ax.set_xscale("log")
    return figure


def plot_graph_stability(stability: pd.DataFrame) -> Figure:
    figure, ax = plt.subplots(figsize=(11, 4.5))
    if "edge_survival" in stability.columns:
        ax.plot(stability["date"], stability["edge_survival"], color=PALETTE["primary"],
                lw=1.1, label="edge survival")
    if "edge_turnover" in stability.columns:
        ax.plot(stability["date"], stability["edge_turnover"], color=PALETTE["secondary"],
                lw=1.1, label="edge turnover")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Fraction")
    ax.set_xlabel("Date")
    ax.set_title("Graph stability: edge survival and turnover between consecutive snapshots")
    ax.legend()
    return figure


def plot_community_migration(history: pd.DataFrame) -> Figure:
    figure, ax = plt.subplots(figsize=(13, 7))
    data = history.T
    image = ax.imshow(data.to_numpy(dtype=float), aspect="auto", cmap="tab10", interpolation="nearest")
    ax.set_yticks(range(len(data.index)))
    ax.set_yticklabels(data.index, fontsize=8)
    step = max(1, len(data.columns) // 12)
    ax.set_xticks(range(0, len(data.columns), step))
    ax.set_xticklabels(
        [pd.Timestamp(d).strftime("%Y-%m") for d in data.columns[::step]], rotation=45, ha="right", fontsize=8
    )
    ax.set_title("Community membership through time (colour = community id)")
    ax.grid(False)
    figure.colorbar(image, ax=ax, label="community id")
    return figure


def plot_node_risk_map(nodes: pd.DataFrame) -> Figure:
    figure, ax = plt.subplots(figsize=(9, 7))
    x = nodes["strength"]
    y = nodes.get("volatility_20d", pd.Series(np.nan, index=nodes.index))
    size = 80 + 900 * nodes.get("risk_score", pd.Series(0.5, index=nodes.index)).fillna(0.5)
    colors = -nodes.get("current_drawdown", pd.Series(0.0, index=nodes.index)).fillna(0.0)

    scatter = ax.scatter(x, y, s=size, c=colors, cmap="Reds", alpha=0.85, edgecolors="white", linewidths=1)
    for ticker, xi, yi in zip(nodes.index, x, y):
        ax.annotate(str(ticker), (xi, yi), fontsize=8, xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("Network strength (centrality)")
    ax.set_ylabel("20-day annualised volatility")
    ax.set_title("Node risk map: centrality vs volatility\n(marker size = composite risk, colour = drawdown depth)")
    figure.colorbar(scatter, ax=ax, label="current drawdown depth")
    return figure


def plot_correlation_vs_partial(
    correlation: np.ndarray, partial: np.ndarray, nodes: list[str]
) -> Figure:
    figure, axes = plt.subplots(1, 3, figsize=(17, 5.4))
    for ax, matrix, title in (
        (axes[0], correlation, "Correlation"),
        (axes[1], partial, "Partial correlation (graphical lasso)"),
    ):
        off_diagonal = matrix[np.triu_indices(len(nodes), k=1)]
        # Each panel gets its own symmetric scale: partial correlations live in
        # a much narrower band than raw correlations, and a shared -1..1 scale
        # renders the partial panel almost blank.
        limit = float(max(np.abs(off_diagonal).max(), 0.05))
        image = ax.imshow(matrix, cmap="RdBu_r", vmin=-limit, vmax=limit)
        ax.set_xticks(range(len(nodes)))
        ax.set_xticklabels(nodes, rotation=90, fontsize=6)
        ax.set_yticks(range(len(nodes)))
        ax.set_yticklabels(nodes, fontsize=6)
        ax.set_title(f"{title}\n(scale +/-{limit:.2f})", fontsize=11)
        ax.grid(False)
        figure.colorbar(image, ax=ax, fraction=0.046, pad=0.02)

    i, j = np.triu_indices(len(nodes), k=1)
    x, y = correlation[i, j], partial[i, j]
    dropped = y == 0.0
    axes[2].scatter(x[dropped], y[dropped], s=10, alpha=0.35, color=PALETTE["muted"],
                    label=f"edge removed by conditioning (n={int(dropped.sum())})")
    axes[2].scatter(x[~dropped], y[~dropped], s=16, alpha=0.7, color=PALETTE["primary"],
                    label=f"edge retained (n={int((~dropped).sum())})")
    axes[2].axhline(0, color=PALETTE["muted"], lw=0.8)
    axes[2].axvline(0, color=PALETTE["muted"], lw=0.8)
    axes[2].set_xlabel("Correlation")
    axes[2].set_ylabel("Partial correlation")
    axes[2].set_title("Correlation vs partial correlation\n(conditioning removes indirect links)")
    axes[2].legend(fontsize=8, loc="upper left")
    figure.tight_layout()
    return figure


def plot_multiscale_comparison(scale_table: pd.DataFrame) -> Figure:
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].bar(scale_table["window"].astype(str), scale_table["mean_density"], color=PALETTE["primary"])
    axes[0].set_xlabel("Rolling window (days)")
    axes[0].set_ylabel("Mean graph density")
    axes[0].set_title("Graph density by scale")

    axes[1].bar(scale_table["window"].astype(str), scale_table["mean_node_strength"], color=PALETTE["accent"])
    axes[1].set_xlabel("Rolling window (days)")
    axes[1].set_ylabel("Mean node strength")
    axes[1].set_title("Node strength by scale")
    return figure


def sector_community_sankey(
    communities: Any, sector_of: dict[str, str], output_path: Path
) -> Path | None:
    """Sector -> community flow diagram.

    Requires Plotly (optional extra `viz`); returns None when it is unavailable.
    A matplotlib alternating-bar fallback is not attempted because a Sankey
    without curved links conveys nothing the community table does not already.
    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        logger.info("Plotly not installed; skipping the sector-community Sankey (extra `viz`).")
        return None

    labels_map = getattr(communities, "labels", {}) or {}
    if not labels_map:
        return None

    pairs = pd.DataFrame(
        {
            "ticker": list(labels_map),
            "sector": [sector_of.get(t, "UNKNOWN") for t in labels_map],
            "community": [f"Community {labels_map[t]}" for t in labels_map],
        }
    )
    flows = pairs.groupby(["sector", "community"]).size().reset_index(name="count")

    sectors = sorted(pairs["sector"].unique())
    communities_list = sorted(pairs["community"].unique())
    nodes = sectors + communities_list
    index = {name: i for i, name in enumerate(nodes)}

    figure = go.Figure(
        go.Sankey(
            node=dict(
                label=nodes,
                pad=16,
                thickness=16,
                color=[PALETTE["primary"]] * len(sectors) + [PALETTE["accent"]] * len(communities_list),
            ),
            link=dict(
                source=[index[s] for s in flows["sector"]],
                target=[index[c] for c in flows["community"]],
                value=flows["count"].tolist(),
            ),
        )
    )
    figure.update_layout(
        title_text=(
            "ICB sector -> detected community<br>"
            "<sub>Communities are inferred from return co-movement, not from sector labels. "
            "Where a sector splits across communities, sector membership is not the dominant "
            "structure.</sub>"
        ),
        font_size=11,
        height=620,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(str(output_path), include_plotlyjs="cdn")
    return output_path


def plot_allocation_risk_return(summary: pd.DataFrame) -> Figure:
    """Realised volatility against realised return, one point per portfolio.

    Volatility is on the x axis because it is the metric these rules were built
    to control; return is the side effect the reader still has to be shown.
    """
    figure, axis = plt.subplots(figsize=(9, 6))
    if summary.empty:
        return figure
    rules = sorted(summary["rule"].unique())
    colors = plt.cm.tab10(np.linspace(0, 1, max(len(rules), 2)))
    for color, rule in zip(colors, rules):
        subset = summary[summary["rule"] == rule]
        axis.scatter(
            100 * subset["annual_volatility"],
            100 * subset["annual_return"],
            s=90, color=color, label=rule, edgecolor="white", zorder=3,
        )
        for _, row in subset.iterrows():
            axis.annotate(
                row["estimator"],
                (100 * row["annual_volatility"], 100 * row["annual_return"]),
                textcoords="offset points", xytext=(7, 3), fontsize=7, color=PALETTE["dark"],
            )
    benchmark = summary[summary["key"] == "equal_weight__sample"]
    if not benchmark.empty:
        axis.axvline(
            100 * float(benchmark["annual_volatility"].iloc[0]),
            color=PALETTE["secondary"], linestyle="--", linewidth=1, zorder=1,
            label="equal-weight volatility",
        )
    axis.set_xlabel("Realised annual volatility (%, out of sample)")
    axis.set_ylabel("Realised annual return (%, net of costs)")
    axis.set_title("Allocation rules: realised risk and return")
    axis.legend(fontsize=8, loc="best")
    return figure


def plot_allocation_equity_curves(curves: pd.DataFrame, highlight: list[str] | None = None) -> Figure:
    """Growth of one unit. Log scale, because 14 years of compounding is not linear."""
    figure, axis = plt.subplots(figsize=(12, 6))
    if curves.empty:
        return figure
    highlight = highlight or []
    for column in curves.columns:
        is_key = column in highlight
        axis.plot(
            curves.index, curves[column],
            linewidth=1.8 if is_key else 0.8,
            alpha=1.0 if is_key else 0.45,
            label=column if is_key else None,
            zorder=3 if is_key else 2,
        )
    axis.set_yscale("log")
    axis.set_ylabel("Growth of 1 unit (log scale)")
    axis.set_title("Allocation rules: cumulative out-of-sample growth, net of costs")
    if highlight:
        axis.legend(fontsize=8, loc="upper left")
    return figure


def plot_allocation_rolling_volatility(rolling: pd.DataFrame, keys: list[str] | None = None) -> Figure:
    """Rolling realised volatility -- does any estimator win consistently or once?"""
    figure, axis = plt.subplots(figsize=(12, 5.5))
    if rolling.empty:
        return figure
    columns = [c for c in (keys or list(rolling.columns)) if c in rolling.columns]
    for column in columns:
        axis.plot(rolling.index, 100 * rolling[column], linewidth=1.2, label=column, alpha=0.85)
    axis.set_ylabel("Rolling annualised volatility (%)")
    axis.set_title("Realised volatility through time (126-day rolling window)")
    axis.legend(fontsize=8, ncol=2)
    return figure


def plot_effective_bets(diagnostics: pd.DataFrame) -> Figure:
    """Effective number of independent bets over time, per portfolio.

    The gap between this and the position count is the point: holding 30 names
    in one index does not buy 30 bets, and the gap widens exactly when
    correlations rise.
    """
    figure, axis = plt.subplots(figsize=(12, 5.5))
    if diagnostics.empty or "effective_n_bets" not in diagnostics.columns:
        return figure
    for key, group in diagnostics.groupby("key"):
        axis.plot(group.index, group["effective_n_bets"], linewidth=1.1, label=str(key), alpha=0.85)
    if "n_assets" in diagnostics.columns:
        counts = diagnostics.groupby(level=0)["n_assets"].max()
        axis.plot(
            counts.index, counts.to_numpy(), color=PALETTE["muted"],
            linestyle=":", linewidth=1.4, label="positions held",
        )
    axis.set_ylabel("Effective number of independent bets")
    axis.set_title("Diversification actually achieved, versus positions held")
    axis.legend(fontsize=7, ncol=2)
    return figure


def plot_event_detection(event_table: pd.DataFrame) -> Figure:
    if event_table.empty:
        raise ValueError("no events")
    figure, ax = plt.subplots(figsize=(11, max(3.5, 0.4 * len(event_table))))
    labels = [f"{pd.Timestamp(d).date()}" for d in event_table["event_start"]]
    colors = [PALETTE["accent"] if d else PALETTE["secondary"] for d in event_table["detected"]]
    lead = event_table["warning_lead_days"].fillna(0)
    ax.barh(labels, lead, color=colors)
    ax.set_xlabel("Warning lead time (trading days before the episode began)")
    ax.set_title("Stress-episode detection\n(teal = detected, red = missed)")
    ax.tick_params(axis="y", labelsize=8)
    return figure
