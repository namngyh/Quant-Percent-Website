"""Deterministic random search over purged walk-forward folds."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from raemf_mc.evaluation.classification import evaluate_predictions
from raemf_mc.models.base import fill_features
from raemf_mc.models.ebm_forecaster import EBMForecaster
from raemf_mc.tuning.objective import composite_loss
from raemf_mc.validation.purged_split import PurgedWalkForwardSplit


@dataclass
class TuningResult:
    best_params: dict[str, float | int]
    best_objective: float
    trials: pd.DataFrame
    fold_metrics: pd.DataFrame
    runtime_seconds: float


def _parameter_candidates(base: dict[str, object]) -> list[dict[str, float | int]]:
    learning_rates = sorted({0.015, 0.025, 0.04, float(base.get("learning_rate", 0.03))})
    max_rounds = sorted({30, 50, 80, int(base.get("max_rounds", 80))})
    max_bins = sorted({64, 96, int(base.get("max_bins", 96))})
    min_samples_leaf = sorted({2, 5, 10, int(base.get("min_samples_leaf", 2))})
    return [
        {
            "learning_rate": lr,
            "max_rounds": rounds,
            "interactions": 0,
            "max_bins": bins,
            "min_samples_leaf": leaf,
            "outer_bags": int(base.get("outer_bags", 2)),
        }
        for lr in learning_rates
        for rounds in max_rounds
        for bins in max_bins
        for leaf in min_samples_leaf
    ]


def tune_ebm_random_search(
    features: pd.DataFrame,
    target: pd.Series,
    dates: pd.Series,
    target_end_dates: pd.Series,
    *,
    horizon: int,
    base_params: dict[str, object],
    n_trials: int,
    n_folds: int,
    seed: int,
    validation_size: int | None = None,
) -> TuningResult:
    """Tune EBM without exposing the final test period."""
    started = time.time()
    rng = np.random.default_rng(seed + horizon)
    candidates = _parameter_candidates(base_params)
    order = rng.permutation(len(candidates))[: min(n_trials, len(candidates))]
    splitter = PurgedWalkForwardSplit(n_splits=n_folds, validation_size=validation_size, horizon=horizon)
    splits = list(splitter.split(dates.reset_index(drop=True), target_end_dates.reset_index(drop=True)))
    trial_rows: list[dict[str, object]] = []
    fold_rows: list[dict[str, object]] = []
    best_params = dict(base_params)
    best_objective = float("inf")
    for trial_number, candidate_idx in enumerate(order):
        params = candidates[int(candidate_idx)]
        objectives: list[float] = []
        trial_started = time.time()
        status = "complete"
        for fold, (train_idx, val_idx) in enumerate(splits):
            try:
                x_train, x_val = fill_features(features.iloc[train_idx], features.iloc[val_idx])
                model = EBMForecaster(seed + trial_number, **params).fit(x_train, target.iloc[train_idx])
                probability = model.predict_proba(x_val)
                metrics, _, _ = evaluate_predictions(target.iloc[val_idx], probability, "EBM tuning", horizon)
                objective = composite_loss({key: float(value) for key, value in metrics.items() if isinstance(value, (int, float))})
                objectives.append(objective)
                fold_rows.append(
                    {
                        "trial": trial_number,
                        "fold": fold,
                        "horizon": horizon,
                        "objective": objective,
                        **params,
                        **{key: metrics[key] for key in ["macro_f1", "balanced_accuracy", "brier", "log_loss", "ece", "recall_bear", "recall_stress"]},
                    }
                )
            except Exception as exc:  # pragma: no cover - optimizer dependent
                status = f"failed: {type(exc).__name__}"
                objectives = []
                break
        mean_objective = float(np.mean(objectives)) if objectives else float("inf")
        trial_rows.append(
            {
                "trial": trial_number,
                "horizon": horizon,
                "objective": mean_objective,
                "status": status,
                "runtime_seconds": time.time() - trial_started,
                **params,
            }
        )
        if mean_objective < best_objective:
            best_objective = mean_objective
            best_params = params.copy()
    return TuningResult(
        best_params=best_params,
        best_objective=best_objective,
        trials=pd.DataFrame(trial_rows),
        fold_metrics=pd.DataFrame(fold_rows),
        runtime_seconds=time.time() - started,
    )
