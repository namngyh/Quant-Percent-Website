"""Feature engineering. Every feature at date t uses only data with
timestamp <= t; targets are the only forward-looking quantities and they are
kept in a separate module so they can never be mixed into a feature matrix by
accident."""

from __future__ import annotations

from dynamicgraph.features.market_features import build_market_features
from dynamicgraph.features.node_features import build_node_features
from dynamicgraph.features.residualization import residualize_returns
from dynamicgraph.features.returns import compute_log_returns, drawdown_series
from dynamicgraph.features.targets import build_targets

__all__ = [
    "compute_log_returns",
    "drawdown_series",
    "residualize_returns",
    "build_node_features",
    "build_market_features",
    "build_targets",
]
