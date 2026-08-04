"""Classification metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    matthews_corrcoef,
    precision_recall_fscore_support,
)

from raemf_mc import CLASS_ORDER
from raemf_mc.calibration.metrics import expected_calibration_error, multiclass_brier, safe_log_loss


def evaluate_predictions(y_true: pd.Series, proba: np.ndarray, model: str, horizon: int) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    """Compute global and per-class metrics."""
    y_pred = [CLASS_ORDER[i] for i in proba.argmax(axis=1)]
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true.astype(str), y_pred, labels=CLASS_ORDER, zero_division=0
    )
    macro = precision_recall_fscore_support(y_true.astype(str), y_pred, labels=CLASS_ORDER, average="macro", zero_division=0)
    weighted = precision_recall_fscore_support(y_true.astype(str), y_pred, labels=CLASS_ORDER, average="weighted", zero_division=0)
    metrics = {
        "model": model,
        "horizon": horizon,
        "n_obs": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true.astype(str), y_pred)),
        "balanced_accuracy": float(np.mean(recall)),
        "macro_precision": float(macro[0]),
        "macro_recall": float(macro[1]),
        "macro_f1": float(macro[2]),
        "weighted_f1": float(weighted[2]),
        "mcc": float(matthews_corrcoef(y_true.astype(str), y_pred)),
        "brier": multiclass_brier(y_true, proba),
        "log_loss": safe_log_loss(y_true, proba),
        "ece": expected_calibration_error(y_true, proba),
        "recall_bull": float(recall[CLASS_ORDER.index("Bull")]),
        "recall_sideway": float(recall[CLASS_ORDER.index("Sideway")]),
        "recall_bear": float(recall[CLASS_ORDER.index("Bear")]),
        "recall_stress": float(recall[CLASS_ORDER.index("Stress")]),
    }
    class_metrics = pd.DataFrame(
        {
            "model": model,
            "horizon": horizon,
            "class": CLASS_ORDER,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
    )
    cm = pd.DataFrame(confusion_matrix(y_true.astype(str), y_pred, labels=CLASS_ORDER), index=CLASS_ORDER, columns=CLASS_ORDER)
    cm.insert(0, "actual", CLASS_ORDER)
    cm.insert(0, "horizon", horizon)
    cm.insert(0, "model", model)
    return metrics, class_metrics, cm
