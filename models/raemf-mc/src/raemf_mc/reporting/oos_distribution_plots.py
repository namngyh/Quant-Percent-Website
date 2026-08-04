"""Artifact-driven plots for the OOS distribution benchmark."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter


MODE_ORDER = ["point_estimate", "posterior_mean_mc", "variational_posterior"]
MODE_LABELS = {
    "point_estimate": "Point estimate",
    "posterior_mean_mc": "Posterior mean",
    "variational_posterior": "VB posterior draw",
}
MODE_COLORS = {
    "point_estimate": "#0072B2",
    "posterior_mean_mc": "#E69F00",
    "variational_posterior": "#009E73",
}
HORIZON_COLORS = {20: "#56B4E9", 40: "#E69F00", 60: "#CC79A7"}


def _style() -> None:
    plt.rcParams.update(
        {
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.alpha": 0.22,
            "grid.linewidth": 0.7,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def _save(fig: plt.Figure, output: Path, name: str) -> Path:
    path = output / name
    fig.tight_layout()
    fig.savefig(path, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _grouped_bars(
    ax: plt.Axes,
    frame: pd.DataFrame,
    metric: str,
    *,
    percent: bool = False,
) -> None:
    horizons = sorted(frame["horizon"].unique())
    x = np.arange(len(horizons), dtype=float)
    width = 0.24
    for index, mode in enumerate(MODE_ORDER):
        values = (
            frame.loc[frame["scenario_mode"] == mode]
            .set_index("horizon")
            .reindex(horizons)[metric]
            .to_numpy(dtype=float)
        )
        ax.bar(
            x + (index - 1) * width,
            values,
            width,
            label=MODE_LABELS[mode],
            color=MODE_COLORS[mode],
            alpha=0.9,
        )
    ax.set_xticks(x, [f"h{value}" for value in horizons])
    if percent:
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))


def _plot_proper_scores(summary: pd.DataFrame, output: Path) -> Path:
    has_wis = "wis" in summary.columns
    fig, axes = plt.subplots(1, 3 if has_wis else 2, figsize=(14.4 if has_wis else 10.8, 4.1))
    _grouped_bars(axes[0], summary, "crps")
    axes[0].set(title="CRPS theo horizon", xlabel="Horizon", ylabel="CRPS (thấp hơn tốt hơn)")
    _grouped_bars(axes[1], summary, "nlpd")
    axes[1].set(title="Negative log predictive density", xlabel="Horizon", ylabel="NLPD (thấp hơn tốt hơn)")
    if has_wis:
        _grouped_bars(axes[2], summary, "wis")
        axes[2].set(title="Weighted interval score", xlabel="Horizon", ylabel="WIS (thấp hơn tốt hơn)")
    axes[0].legend(loc="upper left")
    return _save(fig, output, "proper_scores_by_horizon.png")


def _plot_tail_brier(summary: pd.DataFrame, output: Path) -> Path | None:
    columns = ["brier_negative_return", "brier_drawdown_5pct", "brier_drawdown_10pct", "brier_drawdown_15pct"]
    if not all(column in summary.columns for column in columns):
        return None
    titles = ["Return < 0", "Drawdown > 5%", "Drawdown > 10%", "Drawdown > 15%"]
    fig, axes = plt.subplots(1, 4, figsize=(16.8, 3.9), sharey=False)
    for ax, column, title in zip(axes, columns, titles, strict=True):
        _grouped_bars(ax, summary, column)
        ax.set(title=f"Brier: {title}", xlabel="Horizon")
    axes[0].set_ylabel("Brier score (thấp hơn tốt hơn)")
    axes[0].legend(loc="upper left", fontsize=7)
    return _save(fig, output, "tail_event_brier.png")


def _plot_interval_calibration(summary: pd.DataFrame, output: Path) -> Path:
    levels = [50, 80, 90, 95]
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.0), sharex=True, sharey=True)
    for ax, horizon in zip(axes, sorted(summary["horizon"].unique()), strict=True):
        subset = summary.loc[summary["horizon"] == horizon].set_index("scenario_mode")
        nominal = np.asarray(levels, dtype=float) / 100
        ax.plot(nominal, nominal, color="#555555", linestyle="--", linewidth=1.1, label="Lý tưởng")
        for mode in MODE_ORDER:
            observed = np.asarray([subset.loc[mode, f"coverage_{level}"] for level in levels], dtype=float)
            ax.plot(
                nominal,
                observed,
                marker="o",
                linewidth=1.7,
                color=MODE_COLORS[mode],
                label=MODE_LABELS[mode],
            )
        ax.set(title=f"Horizon {horizon}", xlabel="Coverage danh nghĩa")
        ax.xaxis.set_major_formatter(PercentFormatter(1.0))
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_xlim(0.45, 0.98)
        ax.set_ylim(0.35, 1.01)
    axes[0].set_ylabel("Coverage OOS quan sát")
    axes[-1].legend(loc="lower right")
    fig.suptitle("Hiệu chỉnh khoảng dự báo: gần đường chéo là tốt hơn", fontsize=12, fontweight="bold", x=0.04, ha="left")
    return _save(fig, output, "interval_coverage_calibration.png")


def _plot_var_calibration(summary: pd.DataFrame, output: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.1), sharex=True)
    for ax, level, nominal in zip(axes, [95, 99], [0.05, 0.01], strict=True):
        _grouped_bars(ax, summary, f"kupiec_{level}_observed_rate", percent=True)
        ax.axhline(nominal, color="#D55E00", linestyle="--", linewidth=1.3, label=f"Kỳ vọng {nominal:.0%}")
        ax.set(
            title=f"Tỷ lệ vượt VaR {level}%",
            xlabel="Horizon",
            ylabel="Exceedance OOS",
        )
    axes[0].legend(loc="upper right")
    return _save(fig, output, "var_exceedance_calibration.png")


def _plot_pit(pit: pd.DataFrame, output: Path) -> Path:
    pit = pit.copy()
    pit["bin_left"] = pit["pit_bin"].str.extract(r"\(([-0-9.]+),")[0].astype(float)
    pit["bin_right"] = pit["pit_bin"].str.extract(r", ([-0-9.]+)\]")[0].astype(float)
    pit["bin_center"] = (pit["bin_left"] + pit["bin_right"]) / 2
    aggregate = pit.groupby(["horizon", "scenario_mode", "bin_center"], as_index=False)["count"].sum()
    aggregate["share"] = aggregate["count"] / aggregate.groupby(["horizon", "scenario_mode"])["count"].transform("sum")
    horizons = sorted(aggregate["horizon"].unique())
    fig, axes = plt.subplots(len(horizons), len(MODE_ORDER), figsize=(12.4, 8.0), sharex=True, sharey=True)
    for row, horizon in enumerate(horizons):
        for column, mode in enumerate(MODE_ORDER):
            ax = axes[row, column]
            subset = aggregate.loc[(aggregate["horizon"] == horizon) & (aggregate["scenario_mode"] == mode)]
            ax.bar(subset["bin_center"], subset["share"], width=0.088, color=MODE_COLORS[mode], alpha=0.86)
            ax.axhline(0.1, color="#D55E00", linestyle="--", linewidth=1)
            ax.set_title(f"h{horizon} · {MODE_LABELS[mode]}")
            ax.yaxis.set_major_formatter(PercentFormatter(1.0))
            if column == 0:
                ax.set_ylabel("Tỷ trọng")
            if row == len(horizons) - 1:
                ax.set_xlabel("PIT")
    fig.suptitle("PIT histogram qua ba MC seed; đường đứt là phân phối đều", fontsize=12, fontweight="bold", x=0.04, ha="left")
    return _save(fig, output, "pit_histograms.png")


def _plot_bootstrap(bootstrap: pd.DataFrame, output: Path) -> Path:
    metrics = [
        ("crps", "CRPS"),
        ("nlpd", "NLPD"),
        ("coverage_95_error", "|Coverage95 − 95%|"),
    ]
    benchmarks = ["point_estimate", "posterior_mean_mc"]
    fig, axes = plt.subplots(len(metrics), len(benchmarks), figsize=(11.2, 8.0))
    for row, (metric, label) in enumerate(metrics):
        for column, benchmark in enumerate(benchmarks):
            ax = axes[row, column]
            subset = bootstrap.loc[
                (bootstrap["metric"] == metric) & (bootstrap["benchmark"] == benchmark)
            ].sort_values("horizon")
            y = np.arange(len(subset))
            mean = subset["mean_diff_vb_minus_benchmark"].to_numpy(dtype=float)
            low = subset["ci_low"].to_numpy(dtype=float)
            high = subset["ci_high"].to_numpy(dtype=float)
            colors = ["#009E73" if value else "#999999" for value in subset["ci_excludes_zero"]]
            for pos, center, left, right, color in zip(y, mean, low, high, colors, strict=True):
                ax.errorbar(
                    center,
                    pos,
                    xerr=np.asarray([[center - left], [right - center]]),
                    fmt="o",
                    color=color,
                    capsize=3,
                    linewidth=1.4,
                )
            ax.axvline(0, color="#555555", linewidth=1, linestyle="--")
            ax.set_yticks(y, [f"h{value}" for value in subset["horizon"]])
            ax.set_xlabel("VB − benchmark (âm ưu thế cho VB)")
            ax.set_title(f"{label} so với {MODE_LABELS[benchmark]}")
    fig.suptitle("Paired moving-block bootstrap 95% CI", fontsize=12, fontweight="bold", x=0.04, ha="left")
    return _save(fig, output, "bootstrap_metric_differences.png")


def _plot_fold_stability(by_fold_seed: pd.DataFrame, output: Path) -> Path:
    folded = (
        by_fold_seed.groupby(["horizon", "scenario_mode", "fold"], as_index=False)
        .agg(crps=("crps", "mean"), coverage_95=("coverage_95", "mean"))
    )
    horizons = sorted(folded["horizon"].unique())
    fig, axes = plt.subplots(2, len(horizons), figsize=(12.7, 7.1), sharex=True)
    for column, horizon in enumerate(horizons):
        subset = folded.loc[folded["horizon"] == horizon]
        for mode in MODE_ORDER:
            line = subset.loc[subset["scenario_mode"] == mode].sort_values("fold")
            axes[0, column].plot(
                line["fold"] + 1,
                line["crps"],
                marker="o",
                color=MODE_COLORS[mode],
                label=MODE_LABELS[mode],
            )
            axes[1, column].plot(
                line["fold"] + 1,
                line["coverage_95"],
                marker="o",
                color=MODE_COLORS[mode],
                label=MODE_LABELS[mode],
            )
        axes[0, column].set_title(f"h{horizon} · CRPS")
        axes[1, column].set_title(f"h{horizon} · Coverage 95%")
        axes[1, column].axhline(0.95, color="#D55E00", linestyle="--", linewidth=1)
        axes[1, column].yaxis.set_major_formatter(PercentFormatter(1.0))
        axes[1, column].set_xlabel("Expanding-window fold")
        axes[1, column].set_xticks([1, 2, 3])
    axes[0, 0].set_ylabel("CRPS")
    axes[1, 0].set_ylabel("Coverage OOS")
    axes[0, -1].legend(loc="upper left")
    return _save(fig, output, "fold_stability.png")


def _plot_path_risk(summary: pd.DataFrame, output: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.1))
    drawdown = summary.copy()
    drawdown["drawdown_coverage_mean"] = (drawdown["drawdown_90_coverage"] + drawdown["drawdown_95_coverage"]) / 2
    _grouped_bars(axes[0], drawdown, "drawdown_coverage_mean", percent=True)
    axes[0].axhline(0.925, color="#D55E00", linestyle="--", linewidth=1.2, label="Nominal TB 92,5%")
    axes[0].set(
        title="Coverage drawdown trung bình (90%/95%)",
        xlabel="Horizon",
        ylabel="Coverage OOS",
    )
    _grouped_bars(axes[1], summary, "time_under_water_mae")
    axes[1].set(
        title="Sai số thời gian dưới đỉnh",
        xlabel="Horizon",
        ylabel="Time-under-water MAE (phiên)",
    )
    axes[0].legend(loc="lower left")
    return _save(fig, output, "path_risk_diagnostics.png")


def _plot_classification(classification: pd.DataFrame, output: Path) -> Path:
    metrics = {
        "balanced_accuracy": "Balanced accuracy",
        "macro_f1": "Macro F1",
        "mcc": "MCC",
        "ece": "ECE",
    }
    aggregate = classification.groupby("horizon", as_index=False)[list(metrics)].mean()
    fig, ax = plt.subplots(figsize=(9.2, 4.5))
    x = np.arange(len(aggregate))
    width = 0.18
    colors = ["#0072B2", "#009E73", "#E69F00", "#CC79A7"]
    for index, (metric, label) in enumerate(metrics.items()):
        ax.bar(
            x + (index - 1.5) * width,
            aggregate[metric],
            width,
            color=colors[index],
            label=label,
            alpha=0.9,
        )
    ax.axhline(0.25, color="#555555", linestyle="--", linewidth=1, label="Chance balanced accuracy")
    ax.set_xticks(x, [f"h{value}" for value in aggregate["horizon"]])
    ax.set(title="Chẩn đoán bộ phân loại trạng thái OOS", xlabel="Horizon", ylabel="Giá trị trung bình qua fold")
    ax.legend(ncol=3, loc="upper center")
    return _save(fig, output, "classification_diagnostics.png")


def _plot_runtime(metadata: pd.DataFrame, runtime: dict[str, object], output: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.1))
    for horizon in sorted(metadata["horizon"].unique()):
        subset = metadata.loc[metadata["horizon"] == horizon].sort_values("fold")
        axes[0].plot(
            subset["fold"] + 1,
            subset["runtime_seconds"] / 60,
            marker="o",
            color=HORIZON_COLORS[int(horizon)],
            label=f"h{horizon}",
        )
    axes[0].set(
        title="Runtime theo fold/horizon",
        xlabel="Expanding-window fold",
        ylabel="Phút",
        xticks=[1, 2, 3],
    )
    axes[0].legend()
    total_minutes = float(runtime["seconds"]) / 60
    peak_mib = float(runtime["peak_python_traced_memory_bytes"]) / 1024**2
    values = [total_minutes, peak_mib]
    labels = ["Runtime\n(phút)", "Peak traced\nmemory (MiB)"]
    bars = axes[1].bar(labels, values, color=["#0072B2", "#E69F00"], width=0.55)
    axes[1].bar_label(bars, fmt="%.1f", padding=3)
    axes[1].set(title="Tài nguyên profile laptop", ylabel="Giá trị đo")
    return _save(fig, output, "runtime_profile.png")


def generate_oos_distribution_plots(run_dir: str | Path) -> list[Path]:
    """Generate all benchmark figures from saved CSV/JSON artifacts."""
    run_dir = Path(run_dir)
    required = {
        "summary": run_dir / "distribution_metrics_summary.csv",
        "fold_seed": run_dir / "distribution_metrics_by_fold_seed.csv",
        "pit": run_dir / "pit_histogram.csv",
        "bootstrap": run_dir / "bootstrap_distribution_differences.csv",
        "classification": run_dir / "classification_metrics.csv",
        "metadata": run_dir / "fold_metadata.csv",
        "runtime": run_dir / "runtime.json",
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing benchmark artifacts: {missing}")

    output = run_dir / "figures"
    output.mkdir(parents=True, exist_ok=True)
    _style()
    summary = pd.read_csv(required["summary"])
    by_fold_seed = pd.read_csv(required["fold_seed"])
    pit = pd.read_csv(required["pit"])
    bootstrap = pd.read_csv(required["bootstrap"])
    classification = pd.read_csv(required["classification"])
    metadata = pd.read_csv(required["metadata"])
    runtime = json.loads(required["runtime"].read_text(encoding="utf-8"))

    figures = [
        _plot_proper_scores(summary, output),
        _plot_interval_calibration(summary, output),
        _plot_var_calibration(summary, output),
        _plot_pit(pit, output),
        _plot_bootstrap(bootstrap, output),
        _plot_fold_stability(by_fold_seed, output),
        _plot_path_risk(summary, output),
        _plot_classification(classification, output),
        _plot_runtime(metadata, runtime, output),
    ]
    tail_brier = _plot_tail_brier(summary, output)
    if tail_brier is not None:
        figures.append(tail_brier)
    return figures
