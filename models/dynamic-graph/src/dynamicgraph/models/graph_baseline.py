"""Feature set B - graph-only.

Network metrics with no direct index price information, so that any predictive
skill demonstrated here comes from network structure alone.
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from dynamicgraph.models.registry import FeatureSetBuilder

DESCRIPTION = (
    "Graph-level metrics, centrality concentration, community statistics, edge "
    "turnover, spectral summaries and multi-scale network features."
)


def build(builder: FeatureSetBuilder, exclude_groups: Iterable[str] = (), only_windows=None) -> pd.DataFrame:
    return builder.graph(exclude_groups=exclude_groups, only_windows=only_windows)


def describe() -> dict[str, Any]:
    return {"feature_set": "graph", "label": "B", "description": DESCRIPTION}
