"""Orchestration of the full predictive experiment.

Runs every (target horizon) x (feature set) x (model) combination through the
purged walk-forward engine, collects the OOS predictions, and produces the
comparison table that decides whether graph features add anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.evaluation.bootstrap import paired_bootstrap_difference
from dynamicgraph.evaluation.calibration import calibration_metrics
from dynamicgraph.evaluation.event_metrics import event_detection_metrics
from dynamicgraph.logging_config import get_logger
from dynamicgraph.models.baselines import build_model_zoo
from dynamicgraph.models.registry import FeatureSetBuilder
from dynamicgraph.training.splits import Fold
from dynamicgraph.training.tuning import make_tuner
from dynamicgraph.training.walk_forward import WalkForwardResult, run_walk_forward

logger = get_logger(__name__)


@dataclass
class ExperimentResults:
    """Everything the reporting layer needs from the predictive stage."""

    results: dict[str, WalkForwardResult] = field(default_factory=dict)
    metrics: pd.DataFrame = field(default_factory=pd.DataFrame)
    comparisons: pd.DataFrame = field(default_factory=pd.DataFrame)
    fold_metrics: pd.DataFrame = field(default_factory=pd.DataFrame)
    predictions: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes: list[str] = field(default_factory=list)

    def best(self, horizon: int, metric: str = "brier", lower_is_better: bool = True) -> pd.Series | None:
        if self.metrics.empty:
            return None
        subset = self.metrics[
            (self.metrics["horizon"] == horizon) & (self.metrics["model"] != "naive_frequency")
        ]
        subset = subset[subset[metric].notna()]
        if subset.empty:
            return None
        idx = subset[metric].idxmin() if lower_is_better else subset[metric].idxmax()
        return subset.loc[idx]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        if not self.metrics.empty:
            self.metrics.to_csv(directory / "oos_metrics.csv", index=False)
        if not self.comparisons.empty:
            self.comparisons.to_csv(directory / "model_comparisons.csv", index=False)
        if not self.fold_metrics.empty:
            self.fold_metrics.to_csv(directory / "fold_metrics.csv", index=False)
        if not self.predictions.empty:
            self.predictions.to_csv(directory / "oos_predictions.csv", index=False)
        logger.info("Experiment artifacts written to %s", directory)


def run_experiment(
    builder: FeatureSetBuilder,
    forward_values: pd.DataFrame,
    absolute_labels: pd.DataFrame,
    folds: list[Fold],
    config: Any,
    feature_sets: list[str] | None = None,
    horizons: list[int] | None = None,
) -> ExperimentResults:
    """Full walk-forward experiment across horizons, feature sets and models."""
    horizons = horizons or [int(h) for h in config.targets.horizons]
    feature_sets = feature_sets or list(config.models.feature_sets)
    zoo = build_model_zoo(config, "classification")
    tuner = make_tuner(config)

    definition = str(config.targets.primary_stress_definition)
    both = str(config.targets.stress_definition) == "both"
    quantile = float(config.targets.stress_quantile)

    experiment = ExperimentResults()
    metric_rows: list[dict[str, Any]] = []
    fold_frames: list[pd.DataFrame] = []
    prediction_frames: list[pd.DataFrame] = []

    label_specs: list[tuple[str, float | None, pd.Series | None]] = []
    if definition == "quantile" or both:
        label_specs.append(("quantile", quantile, None))
    if definition == "absolute" or both:
        label_specs.append(("absolute", None, None))

    for horizon in horizons:
        forward_column = f"future_drawdown_{horizon}d"
        if forward_column not in forward_values.columns:
            logger.warning("Missing %s; skipping horizon %d.", forward_column, horizon)
            continue
        target_values = forward_values[forward_column]

        for label_kind, q, _ in label_specs:
            if label_kind == "absolute":
                column = f"stress_abs_{horizon}d"
                if column not in absolute_labels.columns:
                    continue
                labels = absolute_labels[column]
                positive_rate = float(labels.mean())
                if positive_rate < 0.01 or positive_rate > 0.6:
                    logger.warning(
                        "Absolute label %s has a %.1f%% positive rate; skipping as degenerate.",
                        column, 100 * positive_rate,
                    )
                    continue
                target_name = f"stress_abs_{horizon}d"
                q_arg, label_arg = None, labels
            else:
                target_name = f"stress_q{int(quantile * 100)}_{horizon}d"
                q_arg, label_arg = q, None

            for feature_set in feature_sets:
                try:
                    features = builder.build(feature_set)
                except Exception as exc:
                    logger.warning("Could not build feature set `%s`: %s", feature_set, exc)
                    continue
                if features.empty or features.shape[1] == 0:
                    logger.warning("Feature set `%s` is empty; skipping.", feature_set)
                    continue

                for model_name, spec in zoo.items():
                    result = run_walk_forward(
                        features=features,
                        target_values=target_values,
                        folds=folds,
                        model_spec=spec,
                        config=config,
                        horizon=horizon,
                        target_name=target_name,
                        feature_set=feature_set,
                        quantile=q_arg,
                        absolute_labels=label_arg,
                        tuner=tuner if model_name != "naive_frequency" else None,
                    )
                    if result.predictions.empty:
                        continue

                    experiment.results[result.key] = result
                    metrics = result.oos_metrics()
                    metrics.update(
                        calibration_metrics(
                            result.predictions["y_true"].to_numpy(),
                            result.predictions["probability"].to_numpy(),
                            n_bins=int(config.evaluation.calibration_bins),
                        )
                    )
                    threshold = float(np.median(list(result.thresholds.values()))) if result.thresholds else 0.5
                    series = result.predictions.set_index("date")
                    metrics.update(
                        event_detection_metrics(
                            series["y_true"],
                            series["probability"],
                            threshold=threshold,
                            min_gap_days=int(config.evaluation.event_min_gap_days),
                        )
                    )
                    metrics["label_kind"] = label_kind
                    metrics["calibration_method"] = (
                        max(set(result.calibration_methods.values()),
                            key=list(result.calibration_methods.values()).count)
                        if result.calibration_methods else "none"
                    )
                    metric_rows.append(metrics)

                    if not result.fold_metrics.empty:
                        frame = result.fold_metrics.copy()
                        frame["key"] = result.key
                        fold_frames.append(frame)
                    prediction_frames.append(result.predictions)

    experiment.metrics = pd.DataFrame(metric_rows)
    experiment.fold_metrics = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    experiment.predictions = (
        pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()
    )
    experiment.comparisons = compare_feature_sets(experiment, config)
    return experiment


def compare_feature_sets(experiment: ExperimentResults, config: Any) -> pd.DataFrame:
    """Paired block-bootstrap tests of graph / combined against market-only.

    This is the table that decides the project's central question. A positive
    point estimate is not enough: the CI on the paired difference has to exclude
    zero before the result may be described as an improvement.
    """
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    if experiment.metrics.empty:
        return pd.DataFrame()

    n_bootstrap = int(config.evaluation.bootstrap_iterations)
    block_length = int(config.evaluation.bootstrap_block_length)
    seed = int(config.project.seed)

    metric_functions = {
        "brier": (brier_score_loss, False),
        "auprc": (average_precision_score, True),
        "auroc": (roc_auc_score, True),
    }

    rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], dict[str, WalkForwardResult]] = {}
    for key, result in experiment.results.items():
        grouped.setdefault((result.target_name, result.model_name), {})[result.feature_set] = result

    for (target_name, model_name), by_set in grouped.items():
        if "market" not in by_set:
            continue
        baseline = by_set["market"]
        for feature_set, candidate in by_set.items():
            if feature_set == "market":
                continue
            merged = baseline.predictions.merge(
                candidate.predictions, on="date", suffixes=("_base", "_cand")
            )
            if len(merged) < 50:
                continue
            row: dict[str, Any] = {
                "target": target_name,
                "model": model_name,
                "challenger": feature_set,
                "baseline": "market",
                "n": len(merged),
                "horizon": candidate.horizon,
            }
            for metric_name, (fn, higher_is_better) in metric_functions.items():
                test = paired_bootstrap_difference(
                    merged["y_true_base"].to_numpy(),
                    merged["probability_cand"].to_numpy(),
                    merged["probability_base"].to_numpy(),
                    metric_fn=fn,
                    n_bootstrap=n_bootstrap,
                    block_length=block_length,
                    seed=seed,
                    higher_is_better=higher_is_better,
                )
                row[f"{metric_name}_challenger"] = test["metric_a"]
                row[f"{metric_name}_baseline"] = test["metric_b"]
                row[f"{metric_name}_difference"] = test["difference"]
                row[f"{metric_name}_ci_lower"] = test["lower"]
                row[f"{metric_name}_ci_upper"] = test["upper"]
                row[f"{metric_name}_p_value"] = test["p_value"]
                row[f"{metric_name}_significant"] = test["significant"]
            rows.append(row)

    frame = pd.DataFrame(rows)
    if not frame.empty:
        n_significant = int(frame["brier_significant"].sum())
        logger.info(
            "Feature-set comparisons: %d/%d show a statistically significant Brier improvement "
            "over the market-only baseline.",
            n_significant, len(frame),
        )
    return frame


def summarize_incremental_value(
    comparisons: pd.DataFrame, metrics: pd.DataFrame | None = None
) -> dict[str, Any]:
    """Verdict on whether graph features add OOS value. Deliberately strict.

    Two separate questions are answered, because they have different answers:

    1. *Relative* -- does adding graph features beat the market-only baseline?
    2. *Absolute* -- does any model beat a constant base-rate forecast?

    A system can win (1) while failing (2), which is exactly what happens when
    the market-only baseline is badly calibrated. Reporting only (1) would let a
    reader conclude the model works.
    """
    if comparisons.empty:
        return {
            "verdict": "inconclusive",
            "reason": "no paired comparisons could be computed",
        }

    combined = comparisons[comparisons["challenger"] == "market_plus_graph"]
    if combined.empty:
        combined = comparisons[comparisons["challenger"] == "combined"]
    if combined.empty:
        combined = comparisons

    n = len(combined)
    n_significant_brier = int(combined["brier_significant"].sum())
    n_significant_auprc = int(combined["auprc_significant"].sum())
    mean_brier_difference = float(combined["brier_difference"].mean())

    if n_significant_brier >= max(1, n // 2):
        verdict = "graph_features_add_value"
    elif n_significant_brier > 0 or n_significant_auprc > 0:
        verdict = "mixed"
    else:
        verdict = "no_incremental_value"

    absolute_skill: dict[str, Any] = {}
    if metrics is not None and not metrics.empty and "brier_skill_score" in metrics.columns:
        scored = metrics[metrics["model"] != "naive_frequency"].dropna(subset=["brier_skill_score"])
        if not scored.empty:
            n_skilful = int((scored["brier_skill_score"] > 0).sum())
            absolute_skill = {
                "n_configurations": int(len(scored)),
                "n_with_positive_brier_skill": n_skilful,
                "best_brier_skill_score": float(scored["brier_skill_score"].max()),
                "beats_climatology": bool(n_skilful > 0),
            }
            if n_skilful == 0:
                absolute_skill["note"] = (
                    "No configuration beat a constant forecast at the realised base rate. Any "
                    "relative improvement below is an improvement over a poorly calibrated "
                    "baseline, not evidence of usable forecasting skill."
                )

    return {
        "verdict": verdict,
        "n_comparisons": n,
        "n_significant_brier": n_significant_brier,
        "n_significant_auprc": n_significant_auprc,
        "mean_brier_difference": mean_brier_difference,
        "absolute_skill": absolute_skill,
        "interpretation": {
            "graph_features_add_value": (
                "Adding graph features improved the Brier score against the market-only baseline "
                "with a paired block-bootstrap CI excluding zero in the majority of settings."
            ),
            "mixed": (
                "Some settings improved significantly and others did not. The evidence does not "
                "support a general claim that graph features help."
            ),
            "no_incremental_value": (
                "Graph features did NOT produce a statistically significant out-of-sample "
                "improvement over the market-only baseline. The network layer should be used for "
                "structural description, not as a forecasting input."
            ),
            "inconclusive": "Not enough out-of-sample data to decide.",
        }[verdict],
    }
