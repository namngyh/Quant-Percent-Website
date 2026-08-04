r"""Risk transmitters and receivers.

TERMINOLOGY DISCIPLINE (enforced, not merely documented):

* An **undirected** graph -- correlation or partial correlation -- can only
  support the label `high_influence_node`. Degree or eigenvector centrality
  says a stock sits at the centre of the dependence structure; it says nothing
  about which way a shock travels.

* The labels `directed_risk_transmitter` / `directed_risk_receiver` are emitted
  ONLY when a directed layer (lead-lag or VAR spillover) exists, using

      s_i^out = sum_j A_{i->j},   s_i^in = sum_j A_{j->i},
      NET_i   = s_i^out - s_i^in

  NET > 0 -> net transmitter, NET < 0 -> net receiver.

* Even then these are predictive associations under a specific model, not
  identified causal effects. `causal_language_allowed` is always False.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.constants import INFLUENCE_LABEL, RECEIVER_LABEL, TRANSMITTER_LABEL
from dynamicgraph.graphs.base import DirectedSnapshot
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

DIRECTED_DISCLAIMER = (
    "Directional labels come from lagged-correlation or VAR forecast-error decompositions. "
    "They are predictive associations under an assumed model, not identified causal effects."
)


@dataclass
class DirectedRoles:
    frame: pd.DataFrame
    layer: str
    date: pd.Timestamp
    available: bool = True
    causal_language_allowed: bool = False
    disclaimer: str = DIRECTED_DISCLAIMER
    metadata: dict[str, Any] = field(default_factory=dict)

    def transmitters(self, top_n: int = 10) -> pd.DataFrame:
        if not self.available:
            return self.frame.head(0)
        return (
            self.frame[self.frame["net_spillover"] > 0]
            .sort_values("net_spillover", ascending=False)
            .head(top_n)
        )

    def receivers(self, top_n: int = 10) -> pd.DataFrame:
        if not self.available:
            return self.frame.head(0)
        return (
            self.frame[self.frame["net_spillover"] < 0]
            .sort_values("net_spillover")
            .head(top_n)
        )


def directed_roles(snapshot: DirectedSnapshot | None) -> DirectedRoles:
    """Out/in strength and net spillover per node from a directed snapshot."""
    if snapshot is None:
        logger.info(
            "No directed layer available; only `%s` labels will be emitted. %s",
            INFLUENCE_LABEL,
            "Enable graph.enable_lead_lag or graph.enable_spillover for directional roles.",
        )
        return DirectedRoles(
            frame=pd.DataFrame(
                columns=["ticker", "out_strength", "in_strength", "net_spillover", "role"]
            ),
            layer="none",
            date=pd.NaT,
            available=False,
        )

    out_strength = snapshot.out_strength
    in_strength = snapshot.in_strength
    net = out_strength - in_strength
    total = out_strength + in_strength

    frame = pd.DataFrame(
        {
            "ticker": snapshot.nodes,
            "out_strength": out_strength.to_numpy(),
            "in_strength": in_strength.to_numpy(),
            "net_spillover": net.to_numpy(),
            "total_connectedness": total.to_numpy(),
        }
    )
    frame["net_spillover_normalized"] = frame["net_spillover"] / (frame["total_connectedness"].abs().max() + 1e-12)
    frame["role"] = np.where(
        frame["net_spillover"] > 0, TRANSMITTER_LABEL,
        np.where(frame["net_spillover"] < 0, RECEIVER_LABEL, "neutral"),
    )
    frame["date"] = snapshot.date
    frame["layer"] = snapshot.layer
    frame = frame.sort_values("net_spillover", ascending=False).reset_index(drop=True)

    return DirectedRoles(
        frame=frame,
        layer=snapshot.layer,
        date=snapshot.date,
        available=True,
        metadata=dict(snapshot.metadata),
    )


def influence_nodes(node_metrics: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Undirected influence ranking. Never labelled a transmitter."""
    components = ["strength", "eigenvector_centrality", "pagerank", "betweenness_centrality"]
    available = [c for c in components if c in node_metrics.columns and node_metrics[c].notna().any()]
    if not available:
        return node_metrics.head(0)

    frame = node_metrics.copy()
    frame["influence_score"] = frame[available].rank(pct=True).mean(axis=1)
    if "strength_change_20d" in frame.columns:
        frame["centrality_acceleration_rank"] = frame["strength_change_20d"].rank(pct=True)
    frame["role"] = INFLUENCE_LABEL
    frame["causal_language_allowed"] = False
    return frame.sort_values("influence_score", ascending=False).head(top_n).reset_index(drop=True)


def role_history(snapshots: list[DirectedSnapshot]) -> pd.DataFrame:
    """Net spillover per node over time (date x ticker)."""
    rows = []
    for snapshot in snapshots:
        net = snapshot.net_spillover
        for ticker, value in net.items():
            rows.append({"date": snapshot.date, "ticker": ticker, "net_spillover": float(value)})
    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "net_spillover"])
    return pd.DataFrame(rows).pivot_table(
        index="date", columns="ticker", values="net_spillover"
    ).sort_index()


def total_connectedness_series(snapshots: list[DirectedSnapshot]) -> pd.Series:
    """Total connectedness index over time, when the spillover layer supplies it."""
    data = {
        snapshot.date: snapshot.metadata.get("total_connectedness", np.nan)
        for snapshot in snapshots
    }
    return pd.Series(data, name="total_connectedness").sort_index()
