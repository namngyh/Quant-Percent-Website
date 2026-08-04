"""Feature set A - market-only baseline.

Thin wrappers that make the three feature sets explicit and self-documenting at
the call site (`market_baseline.build(...)` reads better than a string literal).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from dynamicgraph.models.registry import FeatureSetBuilder

DESCRIPTION = (
    "VN30 index return, momentum, volatility, drawdown, volume and pooled "
    "cross-sectional aggregates. No pairwise dependence structure, so any "
    "improvement from feature sets B/C is attributable to the network."
)


def build(builder: FeatureSetBuilder) -> pd.DataFrame:
    return builder.market()


def describe() -> dict[str, Any]:
    return {"feature_set": "market", "label": "A", "description": DESCRIPTION}
