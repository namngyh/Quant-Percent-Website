"""Figures for the regime-head OOS benchmark (EBM vs Bayesian head vs baselines)."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

MODEL_ORDER = [
    "EBM",
    "EBM calibrated",
    "Bayesian regime head",
    "Bayesian regime head calibrated",
    "XGBoost",
    "Random Forest",
    "MACD probabilistic",
]
COLORS = {
    "EBM": "#1f77b4",
    "EBM calibrated": "#6baed6",
    "Bayesian regime head": "#d62728",
    "Bayesian regime head calibrated": "#fc9272",
    "XGBoost": "#2ca02c",
    "Random Forest": "#98df8a",
    "MACD probabilistic": "#7f7f7f",
}


def _save(fig, output: Path, name: str) -> Path:
    fig.tight_layout()
    path = output / name
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def _bars(ax, frame: pd.DataFrame, metric: str) -> None:
    horizons = sorted(frame["horizon"].unique())
    models = [m for m in MODEL_ORDER if m in frame["model"].unique()]
    x = np.arange(len(horizons), dtype=float)
    width = 0.8 / len(models)
    for index, model in enumerate(models):
        values = (
            frame.loc[frame["model"] == model]
            .set_index("horizon")
            .reindex(horizons)[metric]
            .to_numpy(dtype=float)
        )
        ax.bar(x + (index - (len(models) - 1) / 2) * width, values, width, label=model, color=COLORS.get(model))
    ax.set_xticks(x, [f"h{h}" for h in horizons])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", default="outputs/regime_head_benchmark")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    aggregated = pd.read_csv(run_dir / "classification_metrics_aggregated.csv")
    output = run_dir / "figures"
    output.mkdir(parents=True, exist_ok=True)

    panels = [
        ("macro_f1", "Macro F1 (cao hơn tốt hơn)"),
        ("balanced_accuracy", "Balanced accuracy"),
        ("brier", "Brier score (thấp hơn tốt hơn)"),
        ("log_loss", "Log loss (thấp hơn tốt hơn)"),
        ("recall_bear", "Recall Bear"),
        ("recall_stress", "Recall Stress"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(16.5, 8.5))
    for ax, (metric, title) in zip(axes.ravel(), panels, strict=True):
        _bars(ax, aggregated, metric)
        ax.set_title(title, fontsize=10)
    axes[0, 0].legend(fontsize=7, loc="upper right")
    fig.suptitle("So sánh OOS: EBM vs Bayesian regime head vs baselines (trung bình qua fold)")
    _save(fig, output, "regime_head_comparison.png")

    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    _bars(ax, aggregated, "objective_j")
    ax.set_title("Hàm mục tiêu J = 0.30·MacroF1 + 0.20·BalAcc + 0.15·RecBear + 0.15·RecStress + 0.20·(1−Brier/2)")
    ax.legend(fontsize=7)
    _save(fig, output, "regime_head_objective.png")

    intervals = pd.read_csv(run_dir / "probability_intervals.csv", parse_dates=["date"])
    subset = intervals[(intervals["horizon"] == 20)].sort_values("date")
    if len(subset):
        fig, ax = plt.subplots(figsize=(11, 4.2))
        for class_name, color in (("Bear", "#d62728"), ("Stress", "#7f0000")):
            ax.plot(subset["date"], subset[f"prob_{class_name}"], color=color, linewidth=1.0, label=f"P({class_name})")
            ax.fill_between(
                subset["date"],
                subset[f"prob_{class_name}_q05"],
                subset[f"prob_{class_name}_q95"],
                color=color,
                alpha=0.18,
            )
        ax.set(title="Bayesian regime head h=20: xác suất Bear/Stress với khoảng tin cậy 90%", ylabel="Xác suất")
        ax.legend()
        _save(fig, output, "bayesian_head_credible_intervals.png")

    ablation_path = run_dir / "feature_family_ablation.csv"
    if ablation_path.exists():
        ablation = pd.read_csv(ablation_path)
        grouped = ablation.groupby("feature_family", as_index=False).mean(numeric_only=True)
        order = ["technical_only", "technical_plus_hmm", "technical_plus_egarch", "full"]
        grouped["order"] = grouped["feature_family"].map({name: i for i, name in enumerate(order)})
        grouped = grouped.sort_values("order")
        fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.0))
        for ax, metric, title in (
            (axes[0], "macro_f1", "Macro F1"),
            (axes[1], "brier", "Brier score"),
        ):
            ax.bar(grouped["feature_family"], grouped[metric], color="#1f77b4", alpha=0.85)
            ax.set_title(f"Ablation nhóm feature (EBM, h=20): {title}", fontsize=10)
            ax.tick_params(axis="x", rotation=15)
        _save(fig, output, "feature_family_ablation.png")
    print(f"figures written to {output}")


if __name__ == "__main__":
    main()
