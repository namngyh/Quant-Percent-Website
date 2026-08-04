import numpy as np
import pandas as pd

from raemf_mc import CLASS_ORDER
from raemf_mc.uncertainty.block_bootstrap import (
    bootstrap_multiclass_class_metrics,
    moving_block_indices,
)


def test_bootstrap_preserves_length():
    idx = moving_block_indices(100, 10, np.random.default_rng(1))
    assert len(idx) == 100
    assert idx.min() >= 0 and idx.max() < 100


def test_multiclass_class_bootstrap_reports_bear_interval():
    actual = np.resize(np.asarray(CLASS_ORDER, dtype=object), 80)
    probabilities = np.full((len(actual), len(CLASS_ORDER)), 0.05)
    for row, class_name in enumerate(actual):
        probabilities[row, CLASS_ORDER.index(class_name)] = 0.85
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=len(actual)),
            "horizon": 20,
            "fold": np.repeat([0, 1], len(actual) // 2),
            "actual_class": actual,
        }
    )
    for index, class_name in enumerate(CLASS_ORDER):
        frame[f"prob_{class_name.lower()}"] = probabilities[:, index]
    result = bootstrap_multiclass_class_metrics(
        frame,
        replicates=30,
        block_length=8,
        seed=7,
    )
    bear_recall = result[
        (result["class"] == "Bear") & (result["metric"] == "recall")
    ].iloc[0]
    assert len(result) == len(CLASS_ORDER) * 5
    assert bear_recall["estimate"] == 1.0
    assert bear_recall["ci_low"] == 1.0
    assert bear_recall["ci_high"] == 1.0
