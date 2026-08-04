"""Moving block bootstrap for metric differences."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_fscore_support,
)

from raemf_mc import CLASS_ORDER
from raemf_mc.evaluation.classification import evaluate_predictions


def moving_block_indices(n: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    """Sample consecutive blocks until n positions are obtained."""
    if n <= 0:
        return np.array([], dtype=int)
    starts = np.arange(max(n - block_length + 1, 1))
    out: list[int] = []
    while len(out) < n:
        s = int(rng.choice(starts))
        out.extend(range(s, min(s + block_length, n)))
    return np.asarray(out[:n], dtype=int)


def bootstrap_mean_ci(values: np.ndarray, replicates: int = 200, block_length: int = 20, seed: int = 42) -> tuple[float, float, float]:
    """Moving-block confidence interval for a mean."""
    rng = np.random.default_rng(seed)
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return float("nan"), float("nan"), float("nan")
    boots = [float(values[moving_block_indices(len(values), block_length, rng)].mean()) for _ in range(replicates)]
    return float(values.mean()), float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))


def bootstrap_difference_frame(rows: list[dict[str, object]], replicates: int, block_length: int, seed: int = 42) -> pd.DataFrame:
    out = []
    for row in rows:
        mean, lo, hi = bootstrap_mean_ci(row["diff"], replicates=replicates, block_length=block_length, seed=seed)
        out.append({k: v for k, v in row.items() if k != "diff"} | {"mean_diff": mean, "ci_low": lo, "ci_high": hi})
    return pd.DataFrame(out)


def bootstrap_prediction_differences(
    predictions: pd.DataFrame,
    reference_model: str,
    benchmarks: list[str],
    replicates: int,
    block_length: int,
    seed: int = 42,
) -> pd.DataFrame:
    """Block-bootstrap paired differences for decomposable and class metrics."""
    probability_columns = [f"prob_{name}" for name in CLASS_ORDER]
    metrics = ["brier", "log_loss", "macro_f1", "recall_bear", "recall_stress"]
    output: list[dict[str, object]] = []
    for horizon, horizon_frame in predictions.groupby("horizon"):
        indexed = {
            model: frame.sort_values("date").reset_index(drop=True)
            for model, frame in horizon_frame.groupby("model")
        }
        if reference_model not in indexed:
            continue
        reference = indexed[reference_model]
        for benchmark in benchmarks:
            if benchmark not in indexed:
                continue
            comparison = indexed[benchmark]
            common_dates = sorted(set(reference["date"]) & set(comparison["date"]))
            left = reference.set_index("date").loc[common_dates].reset_index()
            right = comparison.set_index("date").loc[common_dates].reset_index()
            n = len(common_dates)
            if n == 0:
                continue
            rng = np.random.default_rng(seed + int(horizon) + len(benchmark))
            differences = {metric: [] for metric in metrics}
            for _ in range(replicates):
                idx = moving_block_indices(n, block_length, rng)
                y = left["actual"].iloc[idx].reset_index(drop=True)
                ref_metrics, _, _ = evaluate_predictions(
                    y,
                    left[probability_columns].to_numpy()[idx],
                    reference_model,
                    int(horizon),
                )
                bench_metrics, _, _ = evaluate_predictions(
                    y,
                    right[probability_columns].to_numpy()[idx],
                    benchmark,
                    int(horizon),
                )
                for metric in metrics:
                    differences[metric].append(float(ref_metrics[metric]) - float(bench_metrics[metric]))
            for metric, values in differences.items():
                direction = "lower_is_better" if metric in {"brier", "log_loss"} else "higher_is_better"
                output.append(
                    {
                        "horizon": int(horizon),
                        "benchmark": benchmark,
                        "metric": metric,
                        "mean_diff": float(np.mean(values)),
                        "ci_low": float(np.quantile(values, 0.025)),
                        "ci_high": float(np.quantile(values, 0.975)),
                        "direction": direction,
                        "replicates": replicates,
                    }
                )
    return pd.DataFrame(output)


def bootstrap_multiclass_class_metrics(
    predictions: pd.DataFrame,
    *,
    replicates: int,
    block_length: int,
    seed: int = 42,
) -> pd.DataFrame:
    """Moving-block intervals for one-vs-rest metrics of every output class."""
    probability_columns = [f"prob_{class_name.lower()}" for class_name in CLASS_ORDER]
    required = {"horizon", "date", "fold", "actual_class", *probability_columns}
    missing = sorted(required - set(predictions.columns))
    if missing:
        raise ValueError(f"Multiclass probability frame missing columns: {missing}")
    rows: list[dict[str, object]] = []
    for horizon, horizon_frame in predictions.groupby("horizon"):
        frame = horizon_frame.sort_values(["date", "fold"]).reset_index(drop=True)
        probabilities = frame[probability_columns].to_numpy(dtype=float)
        actual = frame["actual_class"].astype(str).to_numpy()
        predicted = np.asarray(CLASS_ORDER, dtype=object)[probabilities.argmax(axis=1)]
        rng = np.random.default_rng(seed + int(horizon))
        bootstrap_indices = [
            moving_block_indices(
                len(frame),
                min(int(block_length), len(frame)),
                rng,
            )
            for _ in range(int(replicates))
        ]
        for class_index, class_name in enumerate(CLASS_ORDER):
            target = (actual == class_name).astype(int)
            decision = (predicted == class_name).astype(int)

            def metric_values(index: np.ndarray) -> dict[str, float]:
                sample_target = target[index]
                sample_decision = decision[index]
                sample_probability = probabilities[index, class_index]
                precision, recall, f1, _ = precision_recall_fscore_support(
                    sample_target,
                    sample_decision,
                    labels=[0, 1],
                    zero_division=0,
                )
                return {
                    "recall": float(recall[1]),
                    "precision": float(precision[1]),
                    "f1": float(f1[1]),
                    "pr_auc": (
                        float(average_precision_score(sample_target, sample_probability))
                        if sample_target.sum()
                        else float("nan")
                    ),
                    "brier": float(brier_score_loss(sample_target, sample_probability)),
                }

            point = metric_values(np.arange(len(frame)))
            distributions = {metric: [] for metric in point}
            for index in bootstrap_indices:
                values = metric_values(index)
                for metric, value in values.items():
                    distributions[metric].append(value)
            for metric, values in distributions.items():
                array = np.asarray(values, dtype=float)
                rows.append(
                    {
                        "horizon": int(horizon),
                        "class": class_name,
                        "metric": metric,
                        "estimate": point[metric],
                        "ci_low": float(np.nanquantile(array, 0.025)),
                        "ci_high": float(np.nanquantile(array, 0.975)),
                        "support": int(target.sum()),
                        "replicates": int(replicates),
                        "block_length": int(min(block_length, len(frame))),
                    }
                )
    return pd.DataFrame(rows)
