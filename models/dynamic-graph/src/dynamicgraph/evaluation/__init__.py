"""Out-of-sample evaluation: classification, calibration, ranking, event-level
detection, block-bootstrap confidence intervals, graph-specific validation and
the ablation study."""

from __future__ import annotations

from dynamicgraph.evaluation.bootstrap import block_bootstrap_ci, paired_bootstrap_difference
from dynamicgraph.evaluation.calibration import calibration_metrics, reliability_table
from dynamicgraph.evaluation.classification import classification_metrics
from dynamicgraph.evaluation.event_metrics import event_detection_metrics

__all__ = [
    "classification_metrics",
    "calibration_metrics",
    "reliability_table",
    "event_detection_metrics",
    "block_bootstrap_ci",
    "paired_bootstrap_difference",
]
