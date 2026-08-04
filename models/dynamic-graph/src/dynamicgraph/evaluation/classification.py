"""Classification metrics for the stress-probability models.

Accuracy is reported but never optimised: with a 10-15% positive rate a model
that always predicts "no stress" scores 85-90% accuracy while being useless.
Brier score, AUPRC and MCC are the metrics that matter here.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def classification_metrics(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    threshold: float = 0.5,
    n_days: int | None = None,
) -> dict[str, Any]:
    """Full classification metric suite for one prediction series."""
    from sklearn.metrics import (
        average_precision_score,
        balanced_accuracy_score,
        brier_score_loss,
        confusion_matrix,
        f1_score,
        log_loss,
        matthews_corrcoef,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    mask = ~np.isnan(y) & ~np.isnan(p)
    y, p = y[mask], np.clip(p[mask], 1e-7, 1 - 1e-7)

    out: dict[str, Any] = {
        "n": int(y.size),
        "n_positive": int(y.sum()),
        "base_rate": float(y.mean()) if y.size else np.nan,
        "threshold": float(threshold),
    }
    if y.size < 10 or y.sum() == 0 or y.sum() == y.size:
        out["note"] = "degenerate label distribution; most metrics undefined"
        out.update({k: np.nan for k in ("auroc", "auprc", "brier", "log_loss", "mcc")})
        return out

    predicted = (p >= threshold).astype(int)

    out["auroc"] = float(roc_auc_score(y, p))
    out["auprc"] = float(average_precision_score(y, p))
    out["auprc_lift_over_base"] = float(out["auprc"] / out["base_rate"]) if out["base_rate"] > 0 else np.nan
    out["brier"] = float(brier_score_loss(y, p))
    out["brier_skill_score"] = float(
        1.0 - out["brier"] / max(out["base_rate"] * (1 - out["base_rate"]), 1e-12)
    )
    out["log_loss"] = float(log_loss(y, p, labels=[0, 1]))

    out["balanced_accuracy"] = float(balanced_accuracy_score(y, predicted))
    out["accuracy"] = float((predicted == y).mean())
    out["mcc"] = float(matthews_corrcoef(y, predicted)) if len(set(predicted)) > 1 else 0.0
    out["precision"] = float(precision_score(y, predicted, zero_division=0))
    out["recall"] = float(recall_score(y, predicted, zero_division=0))
    out["f1"] = float(f1_score(y, predicted, zero_division=0))

    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    out.update(
        {
            "true_negatives": int(tn),
            "false_positives": int(fp),
            "false_negatives": int(fn),
            "true_positives": int(tp),
            "specificity": float(tn / (tn + fp)) if (tn + fp) else np.nan,
            "false_positive_rate": float(fp / (fp + tn)) if (fp + tn) else np.nan,
            "false_negative_rate": float(fn / (fn + tp)) if (fn + tp) else np.nan,
            "recall_stress": float(tp / (tp + fn)) if (tp + fn) else np.nan,
            "precision_stress": float(tp / (tp + fp)) if (tp + fp) else np.nan,
        }
    )
    days = n_days or y.size
    out["false_alarms_per_year"] = float(fp * 252.0 / days) if days else np.nan
    out["alerts_per_year"] = float(predicted.sum() * 252.0 / days) if days else np.nan
    return out


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """MAE / RMSE / OOS R^2 / rank correlations / directional accuracy."""
    from scipy.stats import kendalltau, spearmanr
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    mask = ~np.isnan(y) & ~np.isnan(p)
    y, p = y[mask], p[mask]
    if y.size < 10:
        return {"n": int(y.size), "note": "too few observations"}

    residual_ss = float(np.sum((y - p) ** 2))
    total_ss = float(np.sum((y - y.mean()) ** 2))
    spearman, _ = spearmanr(y, p)
    kendall, _ = kendalltau(y, p)

    return {
        "n": int(y.size),
        "mae": float(mean_absolute_error(y, p)),
        "rmse": float(np.sqrt(mean_squared_error(y, p))),
        "r2_oos": float(1.0 - residual_ss / total_ss) if total_ss > 0 else np.nan,
        "spearman": float(spearman) if pd.notna(spearman) else np.nan,
        "kendall_tau": float(kendall) if pd.notna(kendall) else np.nan,
        "directional_accuracy": float(np.mean(np.sign(y) == np.sign(p))),
    }


def confusion_frame(y_true: np.ndarray, probabilities: np.ndarray, threshold: float) -> pd.DataFrame:
    from sklearn.metrics import confusion_matrix

    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    mask = ~np.isnan(y) & ~np.isnan(p)
    matrix = confusion_matrix(y[mask], (p[mask] >= threshold).astype(int), labels=[0, 1])
    return pd.DataFrame(
        matrix,
        index=pd.Index(["actual_no_stress", "actual_stress"], name="actual"),
        columns=pd.Index(["predicted_no_stress", "predicted_stress"], name="predicted"),
    )


def roc_curve_frame(y_true: np.ndarray, probabilities: np.ndarray) -> pd.DataFrame:
    from sklearn.metrics import roc_curve

    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    mask = ~np.isnan(y) & ~np.isnan(p)
    if mask.sum() < 10 or len(set(y[mask])) < 2:
        return pd.DataFrame(columns=["fpr", "tpr", "threshold"])
    fpr, tpr, thresholds = roc_curve(y[mask], p[mask])
    return pd.DataFrame({"fpr": fpr, "tpr": tpr, "threshold": thresholds})


def precision_recall_frame(y_true: np.ndarray, probabilities: np.ndarray) -> pd.DataFrame:
    from sklearn.metrics import precision_recall_curve

    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    mask = ~np.isnan(y) & ~np.isnan(p)
    if mask.sum() < 10 or len(set(y[mask])) < 2:
        return pd.DataFrame(columns=["precision", "recall", "threshold"])
    precision, recall, thresholds = precision_recall_curve(y[mask], p[mask])
    return pd.DataFrame(
        {
            "precision": precision[:-1],
            "recall": recall[:-1],
            "threshold": thresholds,
        }
    )
