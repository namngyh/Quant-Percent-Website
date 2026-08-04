"""Nested purged CPU experiment for an additive binary Risk-off head."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from raemf_mc import CLASS_ORDER
from raemf_mc.calibration.temperature_scaling import apply_temperature, fit_temperature
from raemf_mc.config import write_config_snapshot
from raemf_mc.data.loader import load_price_data, sha256_file
from raemf_mc.evaluation.classification import evaluate_predictions
from raemf_mc.evaluation.oos_distribution_benchmark import make_distribution_folds
from raemf_mc.features.downside import build_downside_features
from raemf_mc.features.selection import select_features
from raemf_mc.features.technical import build_features
from raemf_mc.models.base import fill_features
from raemf_mc.models.ebm_forecaster import EBMForecaster
from raemf_mc.models.risk_off import (
    BinaryTemperatureCalibrator,
    RiskOffHead,
    aggregate_multiclass_risk_off,
    downside_sample_weights,
)
from raemf_mc.regime.filtered_hmm import fit_filtered_hmm
from raemf_mc.reporting.downside_report import build_downside_report
from raemf_mc.risk.egarch_t import fit_egarch_features
from raemf_mc.risk.experiment_risk import (
    bootstrap_risk_differences,
    evaluate_model_risk,
    paper_risk_overlay_backtest,
)
from raemf_mc.risk.threshold_selection import select_threshold, threshold_sweep
from raemf_mc.runtime.cache import ArtifactCache, cache_key
from raemf_mc.runtime.cpu import StageProfiler, configure_cpu_runtime
from raemf_mc.shadow.registry import REGISTRY_COLUMNS
from raemf_mc.targets.downside_targets import create_downside_targets
from raemf_mc.targets.regime_targets import create_multihorizon_targets
from raemf_mc.tuning.objective import downside_candidate_is_admissible, downside_composite_loss
from raemf_mc.uncertainty.block_bootstrap import bootstrap_multiclass_class_metrics
from raemf_mc.validation.leakage_checks import (
    assert_no_future_feature_columns,
    assert_target_end_before_boundary,
)
from raemf_mc.validation.purged_split import PurgedWalkForwardSplit


BASELINE_NAME = "multiclass_probability_sum"
CANDIDATE_NAME = "candidate_risk_off"
LEGACY_AUDIT_START = pd.Timestamp("2021-04-02")
REQUIRED_DOWNSIDE_ARTIFACTS = (
    "run_metadata.json",
    "resolved_config.yaml",
    "data_manifest.json",
    "runtime_profile.json",
    "runtime_benchmark.csv",
    "memory_usage.csv",
    "fold_metadata.csv",
    "risk_off_metrics_by_fold.csv",
    "risk_off_metrics_summary.csv",
    "risk_off_class_metrics.csv",
    "risk_off_confusion_matrices.csv",
    "risk_off_threshold_curve.csv",
    "risk_off_selected_thresholds.json",
    "risk_off_bootstrap_differences.csv",
    "multiclass_oos_probabilities.csv",
    "multiclass_metrics_by_fold.csv",
    "multiclass_class_metrics_by_fold.csv",
    "multiclass_confusion_matrices.csv",
    "multiclass_class_bootstrap.csv",
    "legacy_multiclass_probabilities.csv",
    "downside_feature_ablation.csv",
    "downside_feature_importance.csv",
    "missed_downside_events.csv",
    "false_positive_events.csv",
    "experiment_risk_summary.json",
    "risk_overlay_backtest.csv",
    "risk_overlay_equity.csv",
    "risk_overlay_drawdown.csv",
    "forecast_registry.csv",
    "report.md",
)
RUNTIME_BENCHMARK_COLUMNS = {
    "stage",
    "horizon",
    "fold",
    "wall_time",
    "cpu_time",
    "peak_rss",
    "cache_status",
    "thread_count",
}
MULTICLASS_PROBABILITY_COLUMNS = [
    f"prob_{class_name.lower()}" for class_name in CLASS_ORDER
]
RAW_MULTICLASS_PROBABILITY_COLUMNS = [
    f"raw_prob_{class_name.lower()}" for class_name in CLASS_ORDER
]


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "nogit"


def _json_checksum(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
        newline="\n",
    )


def validate_downside_artifacts(run_dir: str | Path) -> None:
    """Fail a completed run if required files or core schemas are missing."""
    directory = Path(run_dir)
    missing = [
        name for name in REQUIRED_DOWNSIDE_ARTIFACTS if not (directory / name).is_file()
    ]
    if missing:
        raise AssertionError(f"Downside run is missing required artifacts: {missing}")
    runtime = pd.read_csv(directory / "runtime_benchmark.csv")
    missing_runtime = sorted(RUNTIME_BENCHMARK_COLUMNS - set(runtime.columns))
    if missing_runtime:
        raise AssertionError(f"runtime_benchmark.csv missing columns: {missing_runtime}")
    metrics = pd.read_csv(directory / "risk_off_metrics_by_fold.csv")
    metric_columns = {"model", "horizon", "fold", "recall", "precision", "pr_auc", "expected_cost"}
    missing_metrics = sorted(metric_columns - set(metrics.columns))
    if metrics.empty or missing_metrics:
        raise AssertionError(
            f"risk_off_metrics_by_fold.csv invalid; missing={missing_metrics}, empty={metrics.empty}"
        )
    probabilities = pd.read_csv(directory / "multiclass_oos_probabilities.csv")
    required_probabilities = {
        "date",
        "horizon",
        "fold",
        "actual_class",
        "predicted_class",
        "candidate_risk_off_probability",
        *MULTICLASS_PROBABILITY_COLUMNS,
        *RAW_MULTICLASS_PROBABILITY_COLUMNS,
    }
    missing_probabilities = sorted(required_probabilities - set(probabilities.columns))
    if probabilities.empty or missing_probabilities:
        raise AssertionError(
            "multiclass_oos_probabilities.csv invalid; "
            f"missing={missing_probabilities}, empty={probabilities.empty}"
        )
    calibrated = probabilities[MULTICLASS_PROBABILITY_COLUMNS].to_numpy(dtype=float)
    raw = probabilities[RAW_MULTICLASS_PROBABILITY_COLUMNS].to_numpy(dtype=float)
    if (
        not np.isfinite(calibrated).all()
        or not np.isfinite(raw).all()
        or (calibrated < 0).any()
        or (calibrated > 1).any()
        or (raw < 0).any()
        or (raw > 1).any()
        or not np.allclose(calibrated.sum(axis=1), 1.0, atol=1e-6)
        or not np.allclose(raw.sum(axis=1), 1.0, atol=1e-6)
    ):
        raise AssertionError("Multiclass probabilities must be finite, bounded, and sum to one")
    valid_classes = set(CLASS_ORDER)
    if (
        not set(probabilities["actual_class"].astype(str)).issubset(valid_classes)
        or not set(probabilities["predicted_class"].astype(str)).issubset(valid_classes)
    ):
        raise AssertionError("Multiclass probability artifact contains unknown classes")


def _run_directory(config: dict[str, Any]) -> Path:
    configured = config.get("downside_experiment", {}).get("output_root", "outputs/experiments/downside_cpu")
    identifier = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_git_sha()}"
    return Path(configured) / identifier


def _numeric_hmm(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.select_dtypes(include=[np.number])


def _feature_groups(
    base: pd.DataFrame,
    downside: pd.DataFrame,
    requested: list[str],
) -> dict[str, pd.DataFrame]:
    price_columns = [
        column
        for column in downside.columns
        if "hmm_" not in column and "sigma_" not in column and "conditional_volatility" not in column
    ]
    available = {
        "base": base,
        "base_plus_downside_price": pd.concat([base, downside[price_columns]], axis=1),
        "base_plus_downside_all": pd.concat([base, downside], axis=1),
    }
    unknown = sorted(set(requested) - set(available))
    if unknown:
        raise ValueError(f"Unknown downside feature groups: {unknown}")
    internal_names = list(dict.fromkeys(["base", *requested]))
    return {name: available[name] for name in internal_names}


def _fit_multiclass_baseline(
    features: pd.DataFrame,
    target: pd.Series,
    train: np.ndarray,
    validation: np.ndarray,
    test: np.ndarray,
    config: dict[str, Any],
    seed: int,
    fixed_temperature: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, float], list[str]]:
    selected, _ = select_features(
        features,
        train,
        float(config["features"]["missing_threshold"]),
        float(config["features"]["correlation_threshold"]),
    )
    x_train, x_validation, x_test = fill_features(
        features.loc[train, selected],
        features.loc[validation, selected],
        features.loc[test, selected],
    )
    model = EBMForecaster(seed, **config["models"]["ebm"]).fit(x_train, target.iloc[train])
    raw_validation_probability = model.predict_proba(x_validation)
    raw_test_probability = model.predict_proba(x_test)
    validation_probability = raw_validation_probability.copy()
    test_probability = raw_test_probability.copy()
    if fixed_temperature is None:
        temperature, _, use_calibration = fit_temperature(validation_probability, target.iloc[validation])
    else:
        temperature = float(fixed_temperature)
        use_calibration = not np.isclose(temperature, 1.0)
    if use_calibration:
        validation_probability = apply_temperature(validation_probability, temperature)
        test_probability = apply_temperature(test_probability, temperature)
    test_metrics, _, _ = evaluate_predictions(target.iloc[test], test_probability, "multiclass_baseline", 0)
    return (
        validation_probability,
        test_probability,
        raw_validation_probability,
        raw_test_probability,
        {
            "macro_f1": float(test_metrics["macro_f1"]),
            "temperature": float(temperature if use_calibration else 1.0),
        },
        selected,
    )


def _prepare_binary_features(
    frame: pd.DataFrame,
    train: np.ndarray,
    validation: np.ndarray,
    test: np.ndarray,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    selected, _ = select_features(
        frame,
        train,
        float(config["features"]["missing_threshold"]),
        float(config["features"]["correlation_threshold"]),
    )
    x_train, x_validation, x_test = fill_features(
        frame.loc[train, selected],
        frame.loc[validation, selected],
        frame.loc[test, selected],
    )
    return x_train, x_validation, x_test, selected


def _multiclass_probability_frame(
    *,
    dates: pd.Series,
    actual_class: pd.Series,
    calibrated_probability: np.ndarray,
    raw_probability: np.ndarray,
    candidate_probability: np.ndarray,
    raw_candidate_probability: np.ndarray,
    horizon: int,
    fold: int,
    baseline_threshold: float,
    candidate_threshold: float,
    baseline_temperature: float,
    candidate_temperature: float,
    forward_return: pd.Series,
    future_mae: pd.Series,
    evaluation_scope: str,
) -> pd.DataFrame:
    calibrated = np.asarray(calibrated_probability, dtype=float)
    raw = np.asarray(raw_probability, dtype=float)
    candidate = np.asarray(candidate_probability, dtype=float)
    raw_candidate = np.asarray(raw_candidate_probability, dtype=float)
    n_rows = len(dates)
    if (
        calibrated.shape != (n_rows, len(CLASS_ORDER))
        or raw.shape != (n_rows, len(CLASS_ORDER))
        or candidate.shape != (n_rows,)
        or raw_candidate.shape != (n_rows,)
    ):
        raise ValueError("Probability output arrays do not align with the requested dates")
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(dates).to_numpy(),
            "horizon": int(horizon),
            "fold": int(fold),
            "evaluation_scope": evaluation_scope,
            "actual_class": actual_class.astype(str).to_numpy(),
            "predicted_class": np.asarray(CLASS_ORDER, dtype=object)[
                calibrated.argmax(axis=1)
            ],
        }
    )
    for index, class_name in enumerate(CLASS_ORDER):
        frame[f"raw_prob_{class_name.lower()}"] = raw[:, index]
        frame[f"prob_{class_name.lower()}"] = calibrated[:, index]
    frame["raw_baseline_risk_off_probability"] = aggregate_multiclass_risk_off(raw)
    frame["baseline_risk_off_probability"] = aggregate_multiclass_risk_off(calibrated)
    frame["raw_candidate_risk_off_probability"] = raw_candidate
    frame["candidate_risk_off_probability"] = candidate
    frame["baseline_risk_off_threshold"] = float(baseline_threshold)
    frame["candidate_risk_off_threshold"] = float(candidate_threshold)
    frame["baseline_risk_off_alert"] = (
        frame["baseline_risk_off_probability"] >= float(baseline_threshold)
    ).astype(int)
    frame["candidate_risk_off_alert"] = (
        frame["candidate_risk_off_probability"] >= float(candidate_threshold)
    ).astype(int)
    frame["baseline_temperature"] = float(baseline_temperature)
    frame["candidate_temperature"] = float(candidate_temperature)
    frame["actual_risk_off"] = frame["actual_class"].isin(["Bear", "Stress"]).astype(int)
    frame["forward_return"] = forward_return.to_numpy()
    frame["future_mae"] = future_mae.to_numpy()
    return frame


def _weight_summary(
    weights: np.ndarray,
    *,
    horizon: int,
    fold: int,
    model: str,
) -> dict[str, Any]:
    return {
        "horizon": horizon,
        "fold": fold,
        "model": model,
        "minimum": float(np.min(weights)),
        "q05": float(np.quantile(weights, 0.05)),
        "median": float(np.median(weights)),
        "q95": float(np.quantile(weights, 0.95)),
        "maximum": float(np.max(weights)),
        "mean": float(np.mean(weights)),
    }


def _inner_candidate_search(
    feature_groups: dict[str, pd.DataFrame],
    sub: pd.DataFrame,
    outer_train: np.ndarray,
    horizon: int,
    config: dict[str, Any],
    seed: int,
) -> tuple[str, str, pd.DataFrame]:
    """Select kind/group inside outer train only using purged inner folds."""
    experiment = dict(config["downside_experiment"])
    model_kinds = list(experiment.get("model_kinds", ["logistic", "hist_gradient_boosting", "ebm"]))
    inner_folds = int(experiment.get("inner_folds", 2))
    validation_size = experiment.get("inner_validation_size")
    inner_dates = sub["date"].iloc[outer_train].reset_index(drop=True)
    inner_ends = sub[f"target_end_date_{horizon}"].iloc[outer_train].reset_index(drop=True)
    splitter = PurgedWalkForwardSplit(
        n_splits=inner_folds,
        validation_size=int(validation_size) if validation_size else None,
        horizon=horizon,
    )
    splits = list(splitter.split(inner_dates, inner_ends))
    if not splits:
        raise ValueError("No inner purged fold available for downside candidate selection")
    threshold_config = dict(config["risk_off"]["threshold_selection"])
    objective_config = dict(config["risk_off"]["objective"])
    constraints = dict(config["risk_off"]["constraints"])
    baseline_by_fold: list[dict[str, float]] = []
    base_inner = feature_groups["base"].iloc[outer_train].reset_index(drop=True)
    multiclass_target = sub[f"target_{horizon}"].iloc[outer_train].astype(str).reset_index(drop=True)
    for inner_fold, (train, validation) in enumerate(splits):
        selected, _ = select_features(
            base_inner,
            train,
            float(config["features"]["missing_threshold"]),
            float(config["features"]["correlation_threshold"]),
        )
        x_train, x_validation = fill_features(
            base_inner.loc[train, selected],
            base_inner.loc[validation, selected],
        )
        model = EBMForecaster(seed + inner_fold, **config["models"]["ebm"]).fit(
            x_train,
            multiclass_target.iloc[train],
        )
        multiclass_probability = model.predict_proba(x_validation)
        risk_probability = aggregate_multiclass_risk_off(multiclass_probability)
        validation_original = outer_train[validation]
        curve = threshold_sweep(
            sub[f"risk_off_{horizon}"].iloc[validation_original].astype(int),
            risk_probability,
            sub[f"forward_return_{horizon}"].iloc[validation_original],
            sub[f"future_mae_{horizon}"].iloc[validation_original],
            threshold_config,
        )
        selection = select_threshold(curve, threshold_config)
        multiclass_metrics, _, _ = evaluate_predictions(
            multiclass_target.iloc[validation],
            multiclass_probability,
            "inner_multiclass_baseline",
            horizon,
        )
        baseline = {
            key: float(value)
            for key, value in selection.metrics.items()
            if isinstance(value, (int, float))
        }
        baseline["macro_f1"] = float(multiclass_metrics["macro_f1"])
        baseline_by_fold.append(baseline)
    rows: list[dict[str, Any]] = []
    candidate_group_names = list(experiment.get("feature_groups", ["base", "base_plus_downside_all"]))
    for group_name in candidate_group_names:
        group = feature_groups[group_name]
        inner_frame = group.iloc[outer_train].reset_index(drop=True)
        prepared_folds: list[dict[str, Any]] = []
        for train, validation in splits:
            selected, _ = select_features(
                inner_frame,
                train,
                float(config["features"]["missing_threshold"]),
                float(config["features"]["correlation_threshold"]),
            )
            x_train, x_validation = fill_features(
                inner_frame.loc[train, selected],
                inner_frame.loc[validation, selected],
            )
            train_original = outer_train[train]
            validation_original = outer_train[validation]
            y_train = sub[f"risk_off_{horizon}"].iloc[train_original].astype(int)
            prepared_folds.append(
                {
                    "x_train": x_train,
                    "x_validation": x_validation,
                    "y_train": y_train,
                    "y_validation": sub[f"risk_off_{horizon}"]
                    .iloc[validation_original]
                    .astype(int),
                    "validation_original": validation_original,
                    "weights": downside_sample_weights(
                        y_train,
                        sub[f"future_mae_{horizon}"].iloc[train_original],
                        sub["target_sigma"].iloc[train_original],
                        horizon,
                        config["risk_off"]["sample_weight"],
                    ),
                }
            )
        for kind in model_kinds:
            fold_metrics: list[dict[str, float]] = []
            failures: list[str] = []
            for inner_fold, prepared in enumerate(prepared_folds):
                head = RiskOffHead(
                    kind,
                    random_state=seed + inner_fold,
                    params=dict(config["risk_off"]["models"].get(kind, {})),
                ).fit(
                    prepared["x_train"],
                    prepared["y_train"],
                    sample_weight=prepared["weights"],
                    compute_importance=False,
                )
                probability = head.predict_proba(prepared["x_validation"])
                curve = threshold_sweep(
                    prepared["y_validation"],
                    probability,
                    sub[f"forward_return_{horizon}"].iloc[prepared["validation_original"]],
                    sub[f"future_mae_{horizon}"].iloc[prepared["validation_original"]],
                    threshold_config,
                )
                selection = select_threshold(curve, threshold_config)
                candidate = dict(selection.metrics)
                baseline = baseline_by_fold[inner_fold]
                candidate["macro_f1"] = baseline["macro_f1"]
                admissible, fold_failures = downside_candidate_is_admissible(candidate, baseline, constraints)
                failures.extend(fold_failures)
                candidate["objective"] = downside_composite_loss(candidate, objective_config)
                candidate["admissible"] = float(admissible)
                fold_metrics.append({key: float(value) for key, value in candidate.items() if isinstance(value, (int, float))})
            aggregate = pd.DataFrame(fold_metrics).mean(numeric_only=True).to_dict()
            rows.append(
                {
                    "model_kind": kind,
                    "feature_group": group_name,
                    "objective": float(aggregate["objective"]),
                    "recall": float(aggregate["recall"]),
                    "precision": float(aggregate["precision"]),
                    "pr_auc": float(aggregate["pr_auc"]),
                    "brier": float(aggregate["brier"]),
                    "ece": float(aggregate["ece"]),
                    "expected_cost": float(aggregate["expected_cost"]),
                    "admissible": bool(aggregate.get("admissible", 0.0) >= 1.0),
                    "constraint_failures": ";".join(sorted(set(failures))),
                    "inner_folds": len(splits),
                }
            )
    trials = pd.DataFrame(rows)
    pool = trials.loc[trials["admissible"]]
    if pool.empty:
        pool = trials
    choice = pool.sort_values(["objective", "model_kind", "feature_group"]).iloc[0]
    return str(choice["model_kind"]), str(choice["feature_group"]), trials


def _class_rows(metrics: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "model": metrics["model"],
                "horizon": metrics["horizon"],
                "fold": metrics["fold"],
                "class": "Safe",
                "recall": metrics["specificity"],
                "support": metrics["tn"] + metrics["fp"],
            },
            {
                "model": metrics["model"],
                "horizon": metrics["horizon"],
                "fold": metrics["fold"],
                "class": "Risk-off",
                "recall": metrics["recall"],
                "precision": metrics["precision"],
                "f1": metrics["f1"],
                "support": metrics["tp"] + metrics["fn"],
            },
        ]
    )


def _confusion_row(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": metrics["model"],
        "horizon": metrics["horizon"],
        "fold": metrics["fold"],
        "tn": metrics["tn"],
        "fp": metrics["fp"],
        "fn": metrics["fn"],
        "tp": metrics["tp"],
    }


def _acceptance(
    summary: pd.DataFrame,
    by_fold: pd.DataFrame,
    bootstrap: pd.DataFrame,
    criteria: dict[str, Any],
    *,
    folds: int,
    peak_memory_bytes: int | None,
    memory_budget_mb: float,
) -> dict[str, Any]:
    baseline = summary[summary["model"] == BASELINE_NAME].set_index("horizon")
    candidate = summary[summary["model"] == CANDIDATE_NAME].set_index("horizon")
    comparable = sorted(set(baseline.index) & set(candidate.index))
    if not comparable:
        return {"status": "inconclusive", "reason": "no_comparable_horizon"}
    recall_gain = float((candidate.loc[comparable, "recall"] - baseline.loc[comparable, "recall"]).mean())
    precision = float(candidate.loc[comparable, "precision"].mean())
    pr_auc_gain = float((candidate.loc[comparable, "pr_auc"] - baseline.loc[comparable, "pr_auc"]).mean())
    base_cost = float(baseline.loc[comparable, "expected_cost"].mean())
    candidate_cost = float(candidate.loc[comparable, "expected_cost"].mean())
    cost_reduction = (base_cost - candidate_cost) / max(abs(base_cost), 1e-12)
    brier_delta = float((candidate.loc[comparable, "brier"] - baseline.loc[comparable, "brier"]).mean())
    macro_delta = float(
        (candidate.loc[comparable, "multiclass_macro_f1"] - baseline.loc[comparable, "multiclass_macro_f1"]).mean()
    )
    fold_pair = by_fold.pivot_table(index=["horizon", "fold"], columns="model", values="recall")
    consistent_folds = int(
        (fold_pair.get(CANDIDATE_NAME, pd.Series(dtype=float)) > fold_pair.get(BASELINE_NAME, pd.Series(dtype=float))).sum()
    )
    evidence = bootstrap[
        (bootstrap["metric"].isin(["recall", "expected_cost"]))
        & bootstrap["ci_excludes_zero"].astype(bool)
    ]
    supported_horizons = set(
        evidence.loc[
            ((evidence["metric"] == "recall") & (evidence["mean_difference"] > 0))
            | ((evidence["metric"] == "expected_cost") & (evidence["mean_difference"] < 0)),
            "horizon",
        ].astype(int)
    )
    required_folds = math.ceil(2 * folds / 3)
    required_fold_comparisons = required_folds * len(comparable)
    required_bootstrap_horizons = math.ceil(2 * len(comparable) / 3)
    bootstrap_support = len(supported_horizons) >= required_bootstrap_horizons
    checks = {
        "recall_gain_at_least_10pp": recall_gain >= float(criteria.get("minimum_recall_gain", 0.10)),
        "precision_at_least_25pct": precision >= float(criteria.get("minimum_precision", 0.25)),
        "pr_auc_improved": pr_auc_gain > 0,
        "expected_cost_reduced_10pct": cost_reduction >= float(criteria.get("minimum_cost_reduction", 0.10)),
        "brier_within_tolerance": brier_delta <= float(criteria.get("brier_tolerance", 0.02)),
        "multiclass_macro_f1_within_tolerance": macro_delta >= -float(criteria.get("macro_f1_tolerance", 0.03)),
        "fold_consistency": consistent_folds >= required_fold_comparisons,
        "bootstrap_support": bootstrap_support,
        "cpu_only": True,
        "memory_within_budget": peak_memory_bytes is None
        or peak_memory_bytes <= float(memory_budget_mb) * 1024**2,
    }
    return {
        "status": "accepted_for_shadow_test" if all(checks.values()) else "inconclusive_or_rejected",
        "checks": checks,
        "recall_gain": recall_gain,
        "precision": precision,
        "pr_auc_gain": pr_auc_gain,
        "expected_cost_reduction": cost_reduction,
        "brier_delta": brier_delta,
        "macro_f1_delta": macro_delta,
        "folds_with_recall_improvement": consistent_folds,
        "required_fold_comparisons": required_fold_comparisons,
        "bootstrap_supported_horizons": sorted(supported_horizons),
        "required_bootstrap_horizons": required_bootstrap_horizons,
        "fold_comparisons": int(len(fold_pair)),
    }


def _post_selection_legacy_audit(
    targeted: pd.DataFrame,
    technical: pd.DataFrame,
    downside_base: pd.DataFrame,
    returns: pd.Series,
    horizons: list[int],
    frozen_decision: dict[str, Any],
    config: dict[str, Any],
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Evaluate one locked configuration from 2021-04-02 without feeding selection."""
    metric_rows: list[dict[str, Any]] = []
    event_rows: list[pd.DataFrame] = []
    probability_rows: list[pd.DataFrame] = []
    kind = str(frozen_decision["model_kind"])
    feature_group = str(frozen_decision["feature_group"])
    threshold_config = dict(frozen_decision["threshold_selection_config"])
    sample_weight_config = dict(frozen_decision["sample_weight_config"])

    for horizon in horizons:
        train_mask = (
            targeted[f"risk_off_{horizon}"].notna()
            & (targeted[f"target_end_date_{horizon}"] < LEGACY_AUDIT_START)
        )
        audit_mask = (
            targeted[f"risk_off_{horizon}"].notna()
            & (targeted["date"] >= LEGACY_AUDIT_START)
        )
        train = np.flatnonzero(train_mask.to_numpy())
        audit = np.flatnonzero(audit_mask.to_numpy())
        if not len(train) or not len(audit):
            continue
        assert_target_end_before_boundary(
            targeted[f"target_end_date_{horizon}"],
            train,
            LEGACY_AUDIT_START,
            f"legacy audit train h={horizon}",
        )
        hmm = fit_filtered_hmm(
            technical,
            returns,
            train,
            int(config["hmm"]["n_states"]),
            list(config["hmm"]["seeds"]),
        )
        risk = fit_egarch_features(returns, train)
        hmm_numeric = _numeric_hmm(hmm.probabilities)
        downside_dynamic = build_downside_features(
            targeted,
            hmm_probabilities=hmm_numeric,
            egarch_features=risk.features,
        )[0]
        downside = downside_base.combine_first(downside_dynamic)
        downside[downside_dynamic.columns] = downside_dynamic
        base = pd.concat([technical, hmm_numeric, risk.features], axis=1)
        groups = _feature_groups(base, downside, [feature_group])
        candidate_features = groups[feature_group]
        for frame in (base, candidate_features):
            assert_no_future_feature_columns(list(frame.columns))

        candidate_selected, _ = select_features(
            candidate_features,
            train,
            float(config["features"]["missing_threshold"]),
            float(config["features"]["correlation_threshold"]),
        )
        candidate_train, candidate_audit = fill_features(
            candidate_features.loc[train, candidate_selected],
            candidate_features.loc[audit, candidate_selected],
        )
        y_train = targeted[f"risk_off_{horizon}"].iloc[train].astype(int)
        weights = downside_sample_weights(
            y_train,
            targeted[f"future_mae_{horizon}"].iloc[train],
            targeted["target_sigma"].iloc[train],
            horizon,
            sample_weight_config,
        )
        candidate_head = RiskOffHead(
            kind,
            random_state=seed,
            params=dict(frozen_decision["model_params"]),
        ).fit(
            candidate_train,
            y_train,
            sample_weight=weights,
            compute_importance=False,
        )
        raw_candidate_probability = candidate_head.predict_proba(candidate_audit)
        candidate_probability = BinaryTemperatureCalibrator.apply(
            raw_candidate_probability,
            float(frozen_decision["calibration_temperature_by_horizon"][str(horizon)]),
        )

        baseline_selected, _ = select_features(
            base,
            train,
            float(config["features"]["missing_threshold"]),
            float(config["features"]["correlation_threshold"]),
        )
        baseline_train, baseline_audit = fill_features(
            base.loc[train, baseline_selected],
            base.loc[audit, baseline_selected],
        )
        baseline_model = EBMForecaster(
            seed,
            **dict(frozen_decision["baseline_ebm_params"]),
        ).fit(
            baseline_train,
            targeted[f"target_{horizon}"].iloc[train].astype(str),
        )
        raw_multiclass_probability = baseline_model.predict_proba(baseline_audit)
        multiclass_probability = raw_multiclass_probability.copy()
        baseline_temperature = float(
            frozen_decision.get("baseline_calibration_temperature_by_horizon", {}).get(
                str(horizon),
                1.0,
            )
        )
        if not np.isclose(baseline_temperature, 1.0):
            multiclass_probability = apply_temperature(
                multiclass_probability,
                baseline_temperature,
            )
        baseline_probability = aggregate_multiclass_risk_off(multiclass_probability)
        common = {
            "dates": targeted["date"].iloc[audit],
            "target": targeted[f"risk_off_{horizon}"].iloc[audit].astype(int),
            "forward_return": targeted[f"forward_return_{horizon}"].iloc[audit],
            "future_mae": targeted[f"future_mae_{horizon}"].iloc[audit],
            "horizon": horizon,
            "fold": -1,
            "fn_cost_multiplier": float(threshold_config["fn_cost_multiplier"]),
            "fp_cost_multiplier": float(threshold_config["fp_cost_multiplier"]),
        }
        evaluations = (
            (
                BASELINE_NAME,
                baseline_probability,
                float(frozen_decision["baseline_threshold_by_horizon"][str(horizon)]),
            ),
            (
                CANDIDATE_NAME,
                candidate_probability,
                float(frozen_decision["threshold_by_horizon"][str(horizon)]),
            ),
        )
        for model_name, probability, threshold in evaluations:
            metrics, _, _, _, _ = evaluate_model_risk(
                probability=probability,
                threshold=threshold,
                model=model_name,
                **common,
            )
            metrics["evaluation_scope"] = "post_selection_legacy_audit"
            metric_rows.append(metrics)
            event_rows.append(
                pd.DataFrame(
                    {
                        "date": common["dates"].to_numpy(),
                        "horizon": horizon,
                        "fold": -1,
                        "model": model_name,
                        "actual_risk_off": common["target"].to_numpy(),
                        "probability": probability,
                        "threshold": threshold,
                        "alert": (probability >= threshold).astype(int),
                        "forward_return": common["forward_return"].to_numpy(),
                        "future_mae": common["future_mae"].to_numpy(),
                        "evaluation_scope": "post_selection_legacy_audit",
                    }
                )
            )
        probability_rows.append(
            _multiclass_probability_frame(
                dates=common["dates"],
                actual_class=targeted[f"target_{horizon}"].iloc[audit],
                calibrated_probability=multiclass_probability,
                raw_probability=raw_multiclass_probability,
                candidate_probability=candidate_probability,
                raw_candidate_probability=raw_candidate_probability,
                horizon=horizon,
                fold=-1,
                baseline_threshold=float(
                    frozen_decision["baseline_threshold_by_horizon"][str(horizon)]
                ),
                candidate_threshold=float(
                    frozen_decision["threshold_by_horizon"][str(horizon)]
                ),
                baseline_temperature=baseline_temperature,
                candidate_temperature=float(
                    frozen_decision["calibration_temperature_by_horizon"][str(horizon)]
                ),
                forward_return=common["forward_return"],
                future_mae=common["future_mae"],
                evaluation_scope="post_selection_legacy_audit",
            )
        )
    return (
        pd.DataFrame(metric_rows),
        pd.concat(event_rows, ignore_index=True) if event_rows else pd.DataFrame(),
        pd.concat(probability_rows, ignore_index=True)
        if probability_rows
        else pd.DataFrame(),
    )


def run_downside_experiment(data_path: str | Path, config: dict[str, Any]) -> Path:
    """Run nested development OOS only; legacy audit never selects a candidate."""
    config = copy.deepcopy(config)
    experiment = dict(config["downside_experiment"])
    frozen: dict[str, Any] | None = None
    if str(experiment.get("mode", "")).lower() == "frozen":
        frozen_path = Path(str(experiment.get("frozen_artifact", "")))
        if not frozen_path.exists():
            raise FileNotFoundError(
                f"CPU final requires an accepted frozen artifact; not found: {frozen_path}"
            )
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        if frozen.get("acceptance_status") != "accepted_for_shadow_test":
            raise ValueError("CPU final requires a candidate accepted on nested development OOS")
        kind = str(frozen["model_kind"])
        config["risk_off"]["models"][kind] = dict(
            frozen.get("model_params", config["risk_off"]["models"].get(kind, {}))
        )
        config["models"]["ebm"] = dict(
            frozen.get("baseline_ebm_params", config["models"]["ebm"])
        )
        locked_threshold_config = dict(frozen.get("threshold_selection_config", {}))
        config["risk_off"]["threshold_selection"].update(locked_threshold_config)
        config["risk_off"]["sample_weight"] = dict(
            frozen.get("sample_weight_config", config["risk_off"]["sample_weight"])
        )
        config["features"].update(dict(frozen.get("feature_selection_config", {})))
        experiment = dict(config["downside_experiment"])
    runtime_profile = configure_cpu_runtime(config)
    run_dir = _run_directory(config)
    run_dir.mkdir(parents=True, exist_ok=False)
    figures = run_dir / "figures"
    figures.mkdir()
    write_config_snapshot(config, run_dir / "resolved_config.yaml")
    started = time.time()
    runtime_rows: list[dict[str, Any]] = []
    memory_rows: list[dict[str, Any]] = []
    seed = int(config["runtime"].get("seed", 42))
    threads = int(runtime_profile["max_threads"])
    data_checksum = sha256_file(data_path)
    cache = ArtifactCache(
        config["runtime"].get("cache_dir", "outputs/cache/downside_cpu"),
        enabled=bool(config["runtime"].get("cache_features", True)),
    )
    requested_horizons = [
        int(value) for value in config["downside_experiment"]["horizons"]
    ]

    with StageProfiler(runtime_rows, "load_and_targets", thread_count=threads) as load_profile:
        prices, data_metadata = load_price_data(data_path)
        target_key = cache_key(
            data_checksum=data_checksum,
            feature_config={
                "target": config["target"],
                "horizons": requested_horizons,
            },
            artifact="target_table",
        )
        targeted, target_cache = cache.get_or_compute(
            target_key,
            lambda: create_downside_targets(
                create_multihorizon_targets(
                    prices,
                    horizons=requested_horizons,
                    bull_threshold=float(config["target"]["bull_threshold"]),
                    bear_threshold=float(config["target"]["bear_threshold"]),
                    stress_threshold=float(config["target"]["stress_threshold"]),
                    volatility_window=int(config["target"]["volatility_window"]),
                ),
                horizons=requested_horizons,
                bear_threshold=float(config["target"]["bear_threshold"]),
                stress_threshold=float(config["target"]["stress_threshold"]),
            ),
        )
        feature_key = cache_key(
            data_checksum=data_checksum,
            feature_config=config["features"],
            artifact="causal_base_features",
        )
        cached_features, feature_cache = cache.get_or_compute(
            feature_key,
            lambda: (build_features(targeted)[0], build_downside_features(targeted)[0]),
        )
        technical, downside_base = cached_features
        load_profile.cache_status = f"targets:{target_cache};features:{feature_cache}"

    metric_rows: list[dict[str, Any]] = []
    class_rows: list[pd.DataFrame] = []
    confusion_rows: list[dict[str, Any]] = []
    threshold_rows: list[pd.DataFrame] = []
    selected_thresholds: dict[str, Any] = {}
    ablation_rows: list[pd.DataFrame] = []
    importance_rows: list[pd.DataFrame] = []
    missed_rows: list[pd.DataFrame] = []
    false_positive_rows: list[pd.DataFrame] = []
    event_rows: list[pd.DataFrame] = []
    rolling_rows: list[pd.DataFrame] = []
    segment_rows: list[pd.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []
    weight_rows: list[dict[str, Any]] = []
    selected_candidate_rows: list[dict[str, Any]] = []
    multiclass_probability_rows: list[pd.DataFrame] = []
    multiclass_metric_rows: list[dict[str, Any]] = []
    multiclass_class_rows: list[pd.DataFrame] = []
    multiclass_confusion_rows: list[pd.DataFrame] = []
    horizons = [int(value) for value in experiment["horizons"]]
    outer_folds = int(experiment["folds"])
    returns = np.log(targeted["close"] / targeted["close"].shift(1))
    print(
        f"[downside] start horizons={horizons} outer_folds={outer_folds} "
        f"mode={experiment.get('mode')}",
        flush=True,
    )

    for horizon in horizons:
        development = (
            targeted[f"risk_off_{horizon}"].notna()
            & (targeted[f"target_end_date_{horizon}"] < LEGACY_AUDIT_START)
        )
        sub = targeted.loc[development].reset_index()
        fold_index_key = cache_key(
            data_checksum=data_checksum,
            feature_config={
                "legacy_audit_start": str(LEGACY_AUDIT_START),
                "test_fraction": float(experiment.get("test_fraction", 0.30)),
                "validation_fraction": float(
                    experiment.get("validation_fraction", 0.10)
                ),
                "outer_folds": outer_folds,
            },
            artifact="purged_outer_fold_indices",
            horizon=horizon,
        )
        folds, fold_index_cache = cache.get_or_compute(
            fold_index_key,
            lambda: make_distribution_folds(
                sub["date"],
                sub[f"target_end_date_{horizon}"],
                n_folds=outer_folds,
                test_fraction=float(experiment.get("test_fraction", 0.30)),
                validation_fraction=float(
                    experiment.get("validation_fraction", 0.10)
                ),
            ),
        )
        for fold in folds:
            with StageProfiler(
                runtime_rows,
                "outer_fold",
                horizon=horizon,
                fold=fold.fold,
                thread_count=threads,
            ) as fold_profile:
                assert_target_end_before_boundary(
                    sub[f"target_end_date_{horizon}"],
                    fold.train,
                    fold.validation_start,
                    f"downside train h={horizon} fold={fold.fold}",
                )
                assert_target_end_before_boundary(
                    sub[f"target_end_date_{horizon}"],
                    fold.validation,
                    fold.test_start,
                    f"downside validation h={horizon} fold={fold.fold}",
                )
                train_global = sub["index"].to_numpy()[fold.train]
                boundary_config = {
                    "horizon": horizon,
                    "fold": fold.fold,
                    "validation_start": fold.validation_start,
                    "test_start": fold.test_start,
                }
                risk_key = cache_key(
                    data_checksum=data_checksum,
                    feature_config=config["features"],
                    artifact="hmm_egarch",
                    horizon=horizon,
                    split_boundaries=boundary_config,
                    model_config={"hmm": config["hmm"], "risk": config["risk"]},
                )
                (hmm, risk), risk_feature_cache = cache.get_or_compute(
                    risk_key,
                    lambda: (
                        fit_filtered_hmm(
                            technical,
                            returns,
                            train_global,
                            int(config["hmm"]["n_states"]),
                            list(config["hmm"]["seeds"]),
                        ),
                        fit_egarch_features(returns, train_global),
                    ),
                )
                fold_profile.cache_status = (
                    f"fold_indices:{fold_index_cache};"
                    f"hmm_egarch:{risk_feature_cache}"
                )
                index = sub["index"].to_numpy()
                hmm_sub = _numeric_hmm(hmm.probabilities).loc[index].reset_index(drop=True)
                risk_sub = risk.features.loc[index].reset_index(drop=True)
                technical_sub = technical.loc[index].reset_index(drop=True)
                downside_dynamic = build_downside_features(
                    sub,
                    hmm_probabilities=hmm_sub,
                    egarch_features=risk_sub,
                )[0]
                downside_sub = downside_base.loc[index].reset_index(drop=True).combine_first(downside_dynamic)
                downside_sub[downside_dynamic.columns] = downside_dynamic
                base = pd.concat([technical_sub, hmm_sub, risk_sub], axis=1)
                groups = _feature_groups(
                    base,
                    downside_sub,
                    list(experiment.get("feature_groups", ["base", "base_plus_downside_all"])),
                )
                for frame in groups.values():
                    assert_no_future_feature_columns(list(frame.columns))

                (
                    validation_multi,
                    test_multi,
                    _raw_validation_multi,
                    raw_test_multi,
                    multiclass_meta,
                    baseline_features,
                ) = _fit_multiclass_baseline(
                    base,
                    sub[f"target_{horizon}"].astype(str),
                    fold.train,
                    fold.validation,
                    fold.test,
                    config,
                    seed + fold.fold,
                    None
                    if frozen is None
                    else float(
                        frozen.get("baseline_calibration_temperature_by_horizon", {}).get(
                            str(horizon),
                            1.0,
                        )
                    ),
                )
                validation_baseline = aggregate_multiclass_risk_off(validation_multi)
                test_baseline = aggregate_multiclass_risk_off(test_multi)
                threshold_config = dict(config["risk_off"]["threshold_selection"])
                baseline_curve = threshold_sweep(
                    sub[f"risk_off_{horizon}"].iloc[fold.validation].astype(int),
                    validation_baseline,
                    sub[f"forward_return_{horizon}"].iloc[fold.validation],
                    sub[f"future_mae_{horizon}"].iloc[fold.validation],
                    threshold_config,
                )
                baseline_selection = select_threshold(baseline_curve, threshold_config)

                if frozen is None:
                    kind, feature_group, inner_trials = _inner_candidate_search(
                        groups,
                        sub,
                        fold.train,
                        horizon,
                        config,
                        seed + fold.fold,
                    )
                else:
                    kind = str(frozen["model_kind"])
                    feature_group = str(frozen["feature_group"])
                    inner_trials = pd.DataFrame(
                        [
                            {
                                "model_kind": kind,
                                "feature_group": feature_group,
                                "objective": np.nan,
                                "admissible": True,
                                "constraint_failures": "",
                                "inner_folds": 0,
                                "selection_source": "frozen_artifact",
                            }
                        ]
                    )
                inner_trials.insert(0, "outer_fold", fold.fold)
                inner_trials.insert(0, "horizon", horizon)
                ablation_rows.append(inner_trials)
                selected_candidate_rows.append(
                    {
                        "horizon": horizon,
                        "fold": fold.fold,
                        "model_kind": kind,
                        "feature_group": feature_group,
                    }
                )
                x_train, x_validation, x_test, selected = _prepare_binary_features(
                    groups[feature_group],
                    fold.train,
                    fold.validation,
                    fold.test,
                    config,
                )
                y_train = sub[f"risk_off_{horizon}"].iloc[fold.train].astype(int)
                weights = downside_sample_weights(
                    y_train,
                    sub[f"future_mae_{horizon}"].iloc[fold.train],
                    sub["target_sigma"].iloc[fold.train],
                    horizon,
                    config["risk_off"]["sample_weight"],
                )
                weight_rows.append(_weight_summary(weights, horizon=horizon, fold=fold.fold, model=kind))
                head = RiskOffHead(
                    kind,
                    random_state=seed + fold.fold,
                    params=dict(config["risk_off"]["models"].get(kind, {})),
                ).fit(x_train, y_train, sample_weight=weights)
                raw_validation = head.predict_proba(x_validation)
                raw_test_candidate = head.predict_proba(x_test)
                if frozen is None:
                    calibrator = BinaryTemperatureCalibrator().fit(
                        raw_validation,
                        sub[f"risk_off_{horizon}"].iloc[fold.validation].astype(int),
                    )
                    validation_candidate = calibrator.transform(raw_validation)
                    test_candidate = calibrator.transform(raw_test_candidate)
                else:
                    calibrator = BinaryTemperatureCalibrator()
                    calibrator.temperature = float(
                        frozen.get("calibration_temperature_by_horizon", {}).get(str(horizon), 1.0)
                    )
                    calibrator.used = not np.isclose(calibrator.temperature, 1.0)
                    validation_candidate = calibrator.transform(raw_validation)
                    test_candidate = calibrator.transform(raw_test_candidate)
                candidate_curve = threshold_sweep(
                    sub[f"risk_off_{horizon}"].iloc[fold.validation].astype(int),
                    validation_candidate,
                    sub[f"forward_return_{horizon}"].iloc[fold.validation],
                    sub[f"future_mae_{horizon}"].iloc[fold.validation],
                    threshold_config,
                )
                candidate_selection = select_threshold(candidate_curve, threshold_config)
                if frozen is not None:
                    frozen_candidate_threshold = float(frozen["threshold_by_horizon"][str(horizon)])
                    candidate_selection = type(candidate_selection)(
                        threshold=frozen_candidate_threshold,
                        constraint_satisfied=True,
                        reason="frozen_artifact",
                        metrics=dict(candidate_selection.metrics),
                    )
                    frozen_baseline_threshold = float(
                        frozen.get("baseline_threshold_by_horizon", {}).get(
                            str(horizon),
                            baseline_selection.threshold,
                        )
                    )
                    baseline_selection = type(baseline_selection)(
                        threshold=frozen_baseline_threshold,
                        constraint_satisfied=True,
                        reason="frozen_artifact",
                        metrics=dict(baseline_selection.metrics),
                    )
                for name, curve in ((BASELINE_NAME, baseline_curve), (CANDIDATE_NAME, candidate_curve)):
                    curve = curve.copy()
                    curve.insert(0, "model", name)
                    curve.insert(1, "horizon", horizon)
                    curve.insert(2, "fold", fold.fold)
                    threshold_rows.append(curve)
                selected_thresholds[f"h{horizon}_fold{fold.fold}"] = {
                    "baseline": {
                        "threshold": baseline_selection.threshold,
                        "constraint_satisfied": baseline_selection.constraint_satisfied,
                        "reason": baseline_selection.reason,
                        "calibration_temperature": multiclass_meta["temperature"],
                    },
                    "candidate": {
                        "threshold": candidate_selection.threshold,
                        "constraint_satisfied": candidate_selection.constraint_satisfied,
                        "reason": candidate_selection.reason,
                        "model_kind": kind,
                        "feature_group": feature_group,
                        "calibration_temperature": calibrator.temperature,
                        "calibration_used": calibrator.used,
                    },
                    "selection_scope": "outer_validation_only",
                }

                common = {
                    "dates": sub["date"].iloc[fold.test],
                    "target": sub[f"risk_off_{horizon}"].iloc[fold.test].astype(int),
                    "forward_return": sub[f"forward_return_{horizon}"].iloc[fold.test],
                    "future_mae": sub[f"future_mae_{horizon}"].iloc[fold.test],
                    "horizon": horizon,
                    "fold": fold.fold,
                    "fn_cost_multiplier": float(threshold_config["fn_cost_multiplier"]),
                    "fp_cost_multiplier": float(threshold_config["fp_cost_multiplier"]),
                }
                (
                    multiclass_metrics,
                    multiclass_classes,
                    multiclass_confusion,
                ) = evaluate_predictions(
                    sub[f"target_{horizon}"].iloc[fold.test].astype(str),
                    test_multi,
                    "multiclass_ebm_baseline",
                    horizon,
                )
                multiclass_metrics["fold"] = fold.fold
                multiclass_metrics["evaluation_scope"] = (
                    "nested_purged_development_oos"
                )
                multiclass_metric_rows.append(multiclass_metrics)
                multiclass_classes.insert(2, "fold", fold.fold)
                multiclass_classes["evaluation_scope"] = (
                    "nested_purged_development_oos"
                )
                multiclass_class_rows.append(multiclass_classes)
                multiclass_confusion.insert(2, "fold", fold.fold)
                multiclass_confusion["evaluation_scope"] = (
                    "nested_purged_development_oos"
                )
                multiclass_confusion_rows.append(multiclass_confusion)
                multiclass_probability_rows.append(
                    _multiclass_probability_frame(
                        dates=common["dates"],
                        actual_class=sub[f"target_{horizon}"].iloc[fold.test],
                        calibrated_probability=test_multi,
                        raw_probability=raw_test_multi,
                        candidate_probability=test_candidate,
                        raw_candidate_probability=raw_test_candidate,
                        horizon=horizon,
                        fold=fold.fold,
                        baseline_threshold=baseline_selection.threshold,
                        candidate_threshold=candidate_selection.threshold,
                        baseline_temperature=multiclass_meta["temperature"],
                        candidate_temperature=calibrator.temperature,
                        forward_return=common["forward_return"],
                        future_mae=common["future_mae"],
                        evaluation_scope="nested_purged_development_oos",
                    )
                )
                baseline_result = evaluate_model_risk(
                    probability=test_baseline,
                    threshold=baseline_selection.threshold,
                    model=BASELINE_NAME,
                    **common,
                )
                candidate_result = evaluate_model_risk(
                    probability=test_candidate,
                    threshold=candidate_selection.threshold,
                    model=CANDIDATE_NAME,
                    **common,
                )
                for result in (baseline_result, candidate_result):
                    metrics, missed, false_positive, rolling, segments = result
                    metrics["multiclass_macro_f1"] = multiclass_meta["macro_f1"]
                    metrics["selected_kind"] = kind if metrics["model"] == CANDIDATE_NAME else "EBM_probability_sum"
                    metrics["selected_feature_group"] = feature_group if metrics["model"] == CANDIDATE_NAME else "base"
                    metric_rows.append(metrics)
                    class_rows.append(_class_rows(metrics))
                    confusion_rows.append(_confusion_row(metrics))
                    if not missed.empty:
                        missed_rows.append(missed)
                    if not false_positive.empty:
                        false_positive_rows.append(false_positive)
                    if not rolling.empty:
                        rolling_rows.append(rolling)
                    if not segments.empty:
                        segment_rows.append(segments)
                    event_frame = pd.DataFrame(
                        {
                            "date": common["dates"].to_numpy(),
                            "horizon": horizon,
                            "fold": fold.fold,
                            "model": metrics["model"],
                            "actual_risk_off": common["target"].to_numpy(),
                            "probability": test_baseline if metrics["model"] == BASELINE_NAME else test_candidate,
                            "threshold": baseline_selection.threshold
                            if metrics["model"] == BASELINE_NAME
                            else candidate_selection.threshold,
                        }
                    )
                    event_frame["alert"] = (event_frame["probability"] >= event_frame["threshold"]).astype(int)
                    event_frame["forward_return"] = common["forward_return"].to_numpy()
                    event_frame["future_mae"] = common["future_mae"].to_numpy()
                    if metrics["model"] == CANDIDATE_NAME:
                        event_frame["baseline_exposure"] = test_multi @ np.array([1.0, 0.50, 0.15, 0.0])
                    event_rows.append(event_frame)
                importance = head.importance()
                importance.insert(0, "horizon", horizon)
                importance.insert(1, "fold", fold.fold)
                importance.insert(2, "model_kind", kind)
                importance.insert(3, "feature_group", feature_group)
                importance_rows.append(importance)
                fold_rows.append(
                    {
                        "horizon": horizon,
                        "fold": fold.fold,
                        "train_start": sub["date"].iloc[fold.train[0]],
                        "train_end": sub["date"].iloc[fold.train[-1]],
                        "validation_start": fold.validation_start,
                        "validation_end": sub["date"].iloc[fold.validation[-1]],
                        "test_start": fold.test_start,
                        "test_end": sub["date"].iloc[fold.test[-1]],
                        "train_observations": len(fold.train),
                        "validation_observations": len(fold.validation),
                        "test_observations": len(fold.test),
                        "selected_model_kind": kind,
                        "selected_feature_group": feature_group,
                        "selected_feature_count": len(selected),
                        "baseline_feature_count": len(baseline_features),
                        "cache_status": (
                            f"fold_indices:{fold_index_cache};"
                            f"hmm_egarch:{risk_feature_cache}"
                        ),
                        "candidate_warning": head.warning or "",
                        "evaluation_scope": "nested_purged_development_oos",
                    }
                )
                print(
                    f"[downside] completed horizon={horizon} fold={fold.fold} "
                    f"candidate={kind}/{feature_group}",
                    flush=True,
                )

    metrics_by_fold = pd.DataFrame(metric_rows)
    numeric_columns = [
        column
        for column in metrics_by_fold.select_dtypes(include=[np.number]).columns
        if column not in {"fold", "horizon"}
    ]
    summary = metrics_by_fold.groupby(["model", "horizon"], as_index=False)[numeric_columns].mean()
    events = pd.concat(event_rows, ignore_index=True)
    bootstrap = bootstrap_risk_differences(
        events,
        CANDIDATE_NAME,
        BASELINE_NAME,
        replicates=int(config["bootstrap"]["metric_replicates"]),
        block_length=int(config["bootstrap"]["block_length"]),
        seed=seed,
        fn_cost_multiplier=float(config["risk_off"]["threshold_selection"]["fn_cost_multiplier"]),
        fp_cost_multiplier=float(config["risk_off"]["threshold_selection"]["fp_cost_multiplier"]),
    )
    multiclass_probabilities = pd.concat(
        multiclass_probability_rows,
        ignore_index=True,
    )
    multiclass_metrics_by_fold = pd.DataFrame(multiclass_metric_rows)
    multiclass_class_metrics = pd.concat(
        multiclass_class_rows,
        ignore_index=True,
    )
    multiclass_confusion = pd.concat(
        multiclass_confusion_rows,
        ignore_index=True,
    )
    multiclass_bootstrap = bootstrap_multiclass_class_metrics(
        multiclass_probabilities,
        replicates=int(config["bootstrap"]["metric_replicates"]),
        block_length=int(config["bootstrap"]["block_length"]),
        seed=seed,
    )
    peak_values = [
        int(value)
        for value in pd.DataFrame(runtime_rows).get("peak_rss", pd.Series(dtype=object))
        if isinstance(value, (int, np.integer))
    ]
    peak_rss = max(peak_values) if peak_values else None
    acceptance = _acceptance(
        summary,
        metrics_by_fold,
        bootstrap,
        dict(config["risk_off"]["acceptance_criteria"]),
        folds=outer_folds,
        peak_memory_bytes=peak_rss,
        memory_budget_mb=float(config["runtime"].get("memory_budget_mb", 4096)),
    )
    selection_frame = pd.DataFrame(selected_candidate_rows)
    locked_kind = Counter(selection_frame["model_kind"]).most_common(1)[0][0]
    locked_group = Counter(selection_frame["feature_group"]).most_common(1)[0][0]
    frozen_decision = {
        "model_kind": locked_kind,
        "feature_group": locked_group,
        "threshold_by_horizon": {
            str(horizon): float(
                np.median(
                    [
                        value["candidate"]["threshold"]
                        for key, value in selected_thresholds.items()
                        if key.startswith(f"h{horizon}_")
                    ]
                )
            )
            for horizon in horizons
        },
        "baseline_threshold_by_horizon": {
            str(horizon): float(
                np.median(
                    [
                        value["baseline"]["threshold"]
                        for key, value in selected_thresholds.items()
                        if key.startswith(f"h{horizon}_")
                    ]
                )
            )
            for horizon in horizons
        },
        "calibration_temperature_by_horizon": {
            str(horizon): float(
                np.median(
                    [
                        value["candidate"]["calibration_temperature"]
                        for key, value in selected_thresholds.items()
                        if key.startswith(f"h{horizon}_")
                    ]
                )
            )
            for horizon in horizons
        },
        "baseline_calibration_temperature_by_horizon": {
            str(horizon): float(
                np.median(
                    [
                        value["baseline"]["calibration_temperature"]
                        for key, value in selected_thresholds.items()
                        if key.startswith(f"h{horizon}_")
                    ]
                )
            )
            for horizon in horizons
        },
        "model_params": dict(config["risk_off"]["models"].get(locked_kind, {})),
        "baseline_ebm_params": dict(config["models"]["ebm"]),
        "threshold_selection_config": dict(config["risk_off"]["threshold_selection"]),
        "sample_weight_config": dict(config["risk_off"]["sample_weight"]),
        "feature_selection_config": {
            "missing_threshold": config["features"]["missing_threshold"],
            "correlation_threshold": config["features"]["correlation_threshold"],
        },
        "acceptance_status": acceptance["status"],
        "selection_source": "nested_purged_development_oos_only",
        "legacy_audit_used_for_selection": False,
    }

    legacy_metrics = pd.DataFrame()
    legacy_events = pd.DataFrame()
    legacy_multiclass_probabilities = pd.DataFrame()
    if experiment.get("run_legacy_audit", False):
        with StageProfiler(
            runtime_rows,
            "post_selection_legacy_audit",
            thread_count=threads,
        ):
            (
                legacy_metrics,
                legacy_events,
                legacy_multiclass_probabilities,
            ) = _post_selection_legacy_audit(
                targeted,
                technical,
                downside_base,
                returns,
                horizons,
                frozen_decision,
                config,
                seed,
            )
        print("[downside] completed post-selection legacy audit", flush=True)

    peak_values = [
        int(value)
        for value in pd.DataFrame(runtime_rows).get("peak_rss", pd.Series(dtype=object))
        if isinstance(value, (int, np.integer))
    ]
    peak_rss = max(peak_values) if peak_values else None
    acceptance["checks"]["memory_within_budget"] = (
        peak_rss is None
        or peak_rss
        <= float(config["runtime"].get("memory_budget_mb", 4096)) * 1024**2
    )
    acceptance["status"] = (
        "accepted_for_shadow_test"
        if all(acceptance["checks"].values())
        else "inconclusive_or_rejected"
    )
    frozen_decision["acceptance_status"] = acceptance["status"]

    overlay_events = events[
        (events["model"] == CANDIDATE_NAME)
        & (events["horizon"] == min(horizons))
    ].sort_values(["date", "fold"])
    overlay_events = overlay_events.drop_duplicates("date", keep="last")
    close_by_date = targeted.set_index("date")["close"]
    if not overlay_events.empty:
        overlay_time_series, overlay_summary = paper_risk_overlay_backtest(
            overlay_events["date"],
            close_by_date.reindex(pd.to_datetime(overlay_events["date"])).reset_index(drop=True),
            overlay_events["baseline_exposure"],
            overlay_events["probability"],
            list(config["risk_overlay"]["probability_bands"]),
            transaction_cost_bps=float(config["backtest"]["transaction_cost_bps"]),
        )
    else:
        overlay_time_series = pd.DataFrame()
        overlay_summary = pd.DataFrame()

    metrics_by_fold.to_csv(run_dir / "risk_off_metrics_by_fold.csv", index=False)
    summary.to_csv(run_dir / "risk_off_metrics_summary.csv", index=False)
    pd.concat(class_rows, ignore_index=True).to_csv(run_dir / "risk_off_class_metrics.csv", index=False)
    pd.DataFrame(confusion_rows).to_csv(run_dir / "risk_off_confusion_matrices.csv", index=False)
    pd.concat(threshold_rows, ignore_index=True).to_csv(run_dir / "risk_off_threshold_curve.csv", index=False)
    _write_json(run_dir / "risk_off_selected_thresholds.json", selected_thresholds)
    bootstrap.to_csv(run_dir / "risk_off_bootstrap_differences.csv", index=False)
    multiclass_probabilities.to_csv(
        run_dir / "multiclass_oos_probabilities.csv",
        index=False,
    )
    multiclass_metrics_by_fold.to_csv(
        run_dir / "multiclass_metrics_by_fold.csv",
        index=False,
    )
    multiclass_class_metrics.to_csv(
        run_dir / "multiclass_class_metrics_by_fold.csv",
        index=False,
    )
    multiclass_confusion.to_csv(
        run_dir / "multiclass_confusion_matrices.csv",
        index=False,
    )
    multiclass_bootstrap.to_csv(
        run_dir / "multiclass_class_bootstrap.csv",
        index=False,
    )
    pd.concat(ablation_rows, ignore_index=True).to_csv(run_dir / "downside_feature_ablation.csv", index=False)
    pd.concat(importance_rows, ignore_index=True).to_csv(run_dir / "downside_feature_importance.csv", index=False)
    pd.DataFrame(weight_rows).to_csv(run_dir / "sample_weight_distribution.csv", index=False)
    (pd.concat(missed_rows, ignore_index=True) if missed_rows else pd.DataFrame()).to_csv(
        run_dir / "missed_downside_events.csv",
        index=False,
    )
    (pd.concat(false_positive_rows, ignore_index=True) if false_positive_rows else pd.DataFrame()).to_csv(
        run_dir / "false_positive_events.csv",
        index=False,
    )
    events.to_csv(run_dir / "risk_off_oos_events.csv", index=False)
    (pd.concat(rolling_rows, ignore_index=True) if rolling_rows else pd.DataFrame()).to_csv(
        run_dir / "risk_off_rolling_metrics.csv",
        index=False,
    )
    (pd.concat(segment_rows, ignore_index=True) if segment_rows else pd.DataFrame()).to_csv(
        run_dir / "risk_off_segment_metrics.csv",
        index=False,
    )
    pd.DataFrame(fold_rows).to_csv(run_dir / "fold_metadata.csv", index=False)
    overlay_summary.to_csv(run_dir / "risk_overlay_backtest.csv", index=False)
    if not overlay_time_series.empty:
        overlay_time_series[["date", "strategy", "equity"]].to_csv(run_dir / "risk_overlay_equity.csv", index=False)
        overlay_time_series[["date", "strategy", "drawdown"]].to_csv(run_dir / "risk_overlay_drawdown.csv", index=False)
    else:
        pd.DataFrame(columns=["date", "strategy", "equity"]).to_csv(run_dir / "risk_overlay_equity.csv", index=False)
        pd.DataFrame(columns=["date", "strategy", "drawdown"]).to_csv(run_dir / "risk_overlay_drawdown.csv", index=False)
    pd.DataFrame(columns=REGISTRY_COLUMNS).to_csv(run_dir / "forecast_registry.csv", index=False)
    legacy_metrics.to_csv(run_dir / "legacy_audit_metrics.csv", index=False)
    legacy_events.to_csv(run_dir / "legacy_audit_events.csv", index=False)
    legacy_multiclass_probabilities.to_csv(
        run_dir / "legacy_multiclass_probabilities.csv",
        index=False,
    )
    _write_json(run_dir / "frozen_decision.json", frozen_decision)

    runtime_frame = pd.DataFrame(runtime_rows)
    runtime_frame.to_csv(run_dir / "runtime_benchmark.csv", index=False)
    if not runtime_frame.empty:
        memory_rows = runtime_frame[
            ["stage", "horizon", "fold", "peak_rss", "peak_python_bytes"]
        ].to_dict("records")
    pd.DataFrame(memory_rows).to_csv(run_dir / "memory_usage.csv", index=False)
    runtime_profile.update(
        {
            "wall_time_seconds": time.time() - started,
            "peak_rss_bytes": peak_rss if peak_rss is not None else "not_available",
            "memory_budget_mb": config["runtime"].get("memory_budget_mb"),
            "target_cache": target_cache,
            "feature_cache": feature_cache,
        }
    )
    _write_json(run_dir / "runtime_profile.json", runtime_profile)
    run_metadata = {
        "started_at_utc": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "seed": seed,
        "data_checksum": data_checksum,
        "config_checksum": _json_checksum(config),
        "evaluation_scope": "nested_purged_development_oos",
        "legacy_audit_period": "post_selection_legacy_audit_not_run"
        if not experiment.get("run_legacy_audit", False)
        else "post_selection_legacy_audit_from_2021-04-02_not_used_for_acceptance",
        "production_changed": False,
    }
    _write_json(run_dir / "run_metadata.json", run_metadata)
    _write_json(
        run_dir / "data_manifest.json",
        {
            "path": str(data_path),
            "sha256": data_checksum,
            "metadata": data_metadata,
            "development_target_end_before": str(LEGACY_AUDIT_START.date()),
            "legacy_audit_start": str(LEGACY_AUDIT_START.date()),
        },
    )
    _write_json(
        run_dir / "experiment_risk_summary.json",
        {
            "model_risk": acceptance,
            "distribution_risk": {
                "status": "not_available",
                "reason": "Downside classifier run does not retune or replace the registered point-estimate distribution model",
                "production_scenario_mode": "point_estimate",
            },
            "capital_risk": {
                "status": "paper_overlay_only",
                "futures_note": "Exposure is notional; margin cash must not be substituted for notional exposure.",
            },
            "acceptance": acceptance,
        },
    )
    build_downside_report(run_dir)
    validate_downside_artifacts(run_dir)
    return run_dir
