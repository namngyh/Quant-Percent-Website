"""Feature drift diagnostics."""

from __future__ import annotations

import pandas as pd
from scipy.stats import ks_2samp


def feature_drift(train: pd.DataFrame, test: pd.DataFrame, top_n: int = 60) -> pd.DataFrame:
    rows = []
    for col in train.columns[:top_n]:
        a = train[col].dropna()
        b = test[col].dropna()
        if len(a) < 10 or len(b) < 10:
            continue
        rows.append(
            {
                "feature": col,
                "train_mean": float(a.mean()),
                "test_mean": float(b.mean()),
                "mean_shift": float(b.mean() - a.mean()),
                "ks_stat": float(ks_2samp(a, b).statistic),
                "outside_train_range_rate": float(((b < a.min()) | (b > a.max())).mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("ks_stat", ascending=False)
