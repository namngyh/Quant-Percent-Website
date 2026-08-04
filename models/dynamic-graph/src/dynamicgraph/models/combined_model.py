"""Feature set C - market + graph, plus the predictive stress score.

The predictive Network Stress Score is simply the calibrated probability from
the combined model: weights are learned against a future stress target rather
than assigned by hand, which is what separates it from the descriptive score in
`network.stress_score`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger
from dynamicgraph.models.registry import FeatureSetBuilder

logger = get_logger(__name__)

DESCRIPTION = "Union of the market-only and graph-only feature sets."


def build(builder: FeatureSetBuilder, **kwargs: Any) -> pd.DataFrame:
    return builder.combined(**kwargs)


def describe() -> dict[str, Any]:
    return {"feature_set": "combined", "label": "C", "description": DESCRIPTION}


def predictive_stress_score(probabilities: pd.Series) -> pd.DataFrame:
    """Convert calibrated probabilities into a 0-100 predictive stress score.

    The mapping is the identity scaled to 0-100 - deliberately not a further
    non-linear transform, so the published number remains a probability that can
    be checked against outcomes.
    """
    frame = pd.DataFrame({"probability": probabilities})
    frame["predictive_stress_score"] = 100.0 * probabilities.clip(0.0, 1.0)
    frame["percentile"] = probabilities.expanding(min_periods=60).rank(pct=True)
    for window in (1, 5, 20):
        frame[f"change_{window}d"] = frame["predictive_stress_score"].diff(window)
    return frame


def compare_to_descriptive(
    predictive: pd.Series, descriptive: pd.Series
) -> dict[str, Any]:
    """How much do the learned and hand-weighted scores agree?"""
    from scipy.stats import spearmanr

    shared = predictive.dropna().index.intersection(descriptive.dropna().index)
    if len(shared) < 60:
        return {"n": len(shared), "note": "too few shared observations"}
    rho, _ = spearmanr(predictive[shared], descriptive[shared])
    return {
        "n": int(len(shared)),
        "spearman": float(rho) if pd.notna(rho) else np.nan,
        "note": (
            "High agreement means the hand-weighted descriptive score is close to what a "
            "supervised model would have learned. Low agreement means the two answer different "
            "questions and should be presented separately."
        ),
    }
