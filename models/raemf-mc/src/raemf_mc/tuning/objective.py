"""Resource-aware multiclass tuning objective."""

from __future__ import annotations

import numpy as np
from typing import Any


def composite_loss(metrics: dict[str, float]) -> float:
    """Lower-is-better normalized loss emphasizing probability quality and tails."""
    log_scale = float(np.log(4.0))
    return float(
        0.25 * np.clip(metrics["brier"] / 2.0, 0.0, 2.0)
        + 0.20 * np.clip(metrics["log_loss"] / log_scale, 0.0, 3.0)
        + 0.20 * (1.0 - metrics["macro_f1"])
        + 0.10 * (1.0 - metrics["balanced_accuracy"])
        + 0.075 * (1.0 - metrics["recall_bear"])
        + 0.075 * (1.0 - metrics["recall_stress"])
        + 0.10 * np.clip(metrics["ece"], 0.0, 1.0)
    )


def composite_score(macro_f1: float, balanced_accuracy: float, brier: float) -> float:
    """Backward-compatible higher-is-better score."""
    return 0.45 * macro_f1 + 0.25 * balanced_accuracy + 0.30 * (1.0 - brier / 2.0)


def downside_composite_loss(metrics: dict[str, float], config: dict[str, Any]) -> float:
    """Registered lower-is-better objective for additive Risk-off experiments."""
    weights = dict(config.get("weights", {}))
    defaults = {
        "recall": 0.25,
        "pr_auc": 0.20,
        "expected_cost": 0.20,
        "macro_f1": 0.10,
        "brier": 0.10,
        "ece": 0.05,
        "false_positive_exposure": 0.10,
    }
    weights = {**defaults, **weights}
    if any(float(value) < 0 for value in weights.values()):
        raise ValueError("Downside objective weights must be non-negative")
    total = float(sum(weights.values()))
    if total <= 0:
        raise ValueError("At least one downside objective weight must be positive")
    weights = {key: float(value) / total for key, value in weights.items()}
    cost_scale = max(float(config.get("expected_cost_scale", 0.05)), 1e-8)
    normalized_cost = np.clip(float(metrics["expected_cost"]) / cost_scale, 0.0, 3.0)
    normalized_brier = np.clip(float(metrics["brier"]), 0.0, 1.0)
    return float(
        weights["recall"] * (1.0 - float(metrics["recall"]))
        + weights["pr_auc"] * (1.0 - float(metrics["pr_auc"]))
        + weights["expected_cost"] * normalized_cost
        + weights["macro_f1"] * (1.0 - float(metrics.get("macro_f1", 0.0)))
        + weights["brier"] * normalized_brier
        + weights["ece"] * np.clip(float(metrics["ece"]), 0.0, 1.0)
        + weights["false_positive_exposure"]
        * np.clip(float(metrics.get("false_positive_exposure", metrics.get("false_positive_rate", 0.0))), 0.0, 1.0)
    )


def downside_candidate_is_admissible(
    candidate: dict[str, float],
    baseline: dict[str, float],
    config: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Apply pre-registered validation constraints before candidate selection."""
    failures: list[str] = []
    if candidate["recall"] < baseline["recall"]:
        failures.append("recall_below_baseline")
    if candidate["precision"] < float(config.get("min_precision", 0.25)):
        failures.append("precision_below_minimum")
    if candidate["brier"] > baseline["brier"] + float(config.get("brier_tolerance", 0.02)):
        failures.append("brier_tolerance_exceeded")
    if candidate.get("macro_f1", baseline.get("macro_f1", 0.0)) < baseline.get("macro_f1", 0.0) - float(
        config.get("macro_f1_tolerance", 0.03)
    ):
        failures.append("macro_f1_tolerance_exceeded")
    return not failures, failures
