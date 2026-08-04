"""Validation-only Risk-off threshold sweep with magnitude-aware cost."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)


@dataclass(frozen=True)
class ThresholdSelection:
    threshold: float
    constraint_satisfied: bool
    reason: str
    metrics: dict[str, float | int | bool]


def binary_ece(target: np.ndarray, probability: np.ndarray, bins: int = 10) -> float:
    """Expected calibration error for one binary event."""
    y = np.asarray(target, dtype=int)
    p = np.asarray(probability, dtype=float)
    total = 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    for index in range(bins):
        mask = (p >= edges[index]) & (p < edges[index + 1] if index < bins - 1 else p <= edges[index + 1])
        if mask.any():
            total += float(mask.mean() * abs(y[mask].mean() - p[mask].mean()))
    return total


def _safe_ranking_metrics(target: np.ndarray, probability: np.ndarray) -> tuple[float, float]:
    if len(np.unique(target)) < 2:
        return float("nan"), float("nan")
    return float(average_precision_score(target, probability)), float(roc_auc_score(target, probability))


def threshold_sweep(
    target: pd.Series | np.ndarray,
    probability: np.ndarray,
    forward_return: pd.Series | np.ndarray,
    future_mae: pd.Series | np.ndarray,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Evaluate registered thresholds on validation observations only."""
    y = np.asarray(target, dtype=int)
    p = np.clip(np.asarray(probability, dtype=float), 1e-8, 1 - 1e-8)
    forward = np.asarray(forward_return, dtype=float)
    mae = np.asarray(future_mae, dtype=float)
    if not (len(y) == len(p) == len(forward) == len(mae)):
        raise ValueError("Threshold inputs must have equal length")
    start = float(config.get("start", 0.05))
    stop = float(config.get("stop", 0.80))
    step = float(config.get("step", 0.01))
    if step <= 0 or stop < start:
        raise ValueError("Invalid threshold grid")
    thresholds = np.arange(start, stop + step / 2, step)
    pr_auc, roc_auc = _safe_ranking_metrics(y, p)
    brier = float(brier_score_loss(y, p))
    logloss = float(log_loss(y, p, labels=[0, 1]))
    ece = binary_ece(y, p)
    fn_multiplier = float(config.get("fn_cost_multiplier", 3.0))
    fp_multiplier = float(config.get("fp_cost_multiplier", 1.0))
    rows: list[dict[str, float | int]] = []
    for threshold in thresholds:
        predicted = p >= threshold
        positive = y == 1
        negative = ~positive
        tp = int(np.sum(predicted & positive))
        fp = int(np.sum(predicted & negative))
        fn = int(np.sum(~predicted & positive))
        tn = int(np.sum(~predicted & negative))
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        specificity = tn / max(tn + fp, 1)
        fn_loss = float(np.abs(np.minimum(mae[~predicted & positive], 0.0)).sum())
        fp_opportunity = float(np.maximum(forward[predicted & negative], 0.0).sum())
        expected_cost = (fn_multiplier * fn_loss + fp_multiplier * fp_opportunity) / max(len(y), 1)
        warned = predicted
        rows.append(
            {
                "threshold": float(np.round(threshold, 6)),
                "recall": float(recall),
                "precision": float(precision),
                "f1": float(2 * precision * recall / max(precision + recall, 1e-12)),
                "specificity": float(specificity),
                "false_positive_rate": float(fp / max(fp + tn, 1)),
                "false_negative_rate": float(fn / max(fn + tp, 1)),
                "pr_auc": pr_auc,
                "roc_auc": roc_auc,
                "brier": brier,
                "log_loss": logloss,
                "ece": ece,
                "alert_days": int(warned.sum()),
                "alert_fraction": float(warned.mean()),
                "mean_forward_return_when_alert": float(np.mean(forward[warned])) if warned.any() else float("nan"),
                "mean_future_mae_when_alert": float(np.mean(mae[warned])) if warned.any() else float("nan"),
                "false_negative_loss": fn_loss,
                "false_positive_opportunity_cost": fp_opportunity,
                "expected_cost": float(expected_cost),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
            }
        )
    return pd.DataFrame(rows)


def select_threshold(curve: pd.DataFrame, config: dict[str, Any]) -> ThresholdSelection:
    """Select only from a validation curve; never accepts test inputs."""
    required = {"threshold", "precision", "recall", "expected_cost"}
    missing = sorted(required - set(curve.columns))
    if missing or curve.empty:
        raise ValueError(f"Invalid threshold curve; missing={missing}")
    minimum_precision = float(config.get("min_precision", 0.25))
    minimum_recall = float(config.get("min_recall", 0.40))
    eligible = curve[(curve["precision"] >= minimum_precision) & (curve["recall"] >= minimum_recall)]
    satisfied = not eligible.empty
    pool = eligible if satisfied else curve
    chosen = pool.sort_values(["expected_cost", "threshold"], ascending=[True, True]).iloc[0]
    reason = "minimum precision/recall constraints satisfied" if satisfied else "constraint_failure_minimum_expected_cost"
    return ThresholdSelection(
        threshold=float(chosen["threshold"]),
        constraint_satisfied=satisfied,
        reason=reason,
        metrics={key: (int(value) if key in {"tp", "fp", "fn", "tn", "alert_days"} else float(value)) for key, value in chosen.items()},
    )
