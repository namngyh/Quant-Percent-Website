"""Temporal GNN explanations (optional).

Attention weights are a diagnostic of what the model attended to, not an
explanation of the market. They are reported with that caveat attached, and
masking analyses are preferred because they at least measure a change in the
model's own output.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

ATTENTION_DISCLAIMER = (
    "Attention weights show which neighbours the network up-weighted internally. They are a "
    "model diagnostic. They are not a measure of influence between companies and not a causal "
    "explanation."
)


def attention_frame(
    attention: "np.ndarray | None", nodes: list[str], date: Any = None, top_n: int = 25
) -> pd.DataFrame:
    """Flatten an attention matrix into a ranked edge list."""
    if attention is None:
        return pd.DataFrame(columns=["source", "target", "attention"])
    matrix = np.asarray(attention)
    if matrix.ndim == 3:
        matrix = matrix.mean(axis=0)
    i, j = np.nonzero(matrix)
    frame = pd.DataFrame(
        {
            "date": date,
            "source": [nodes[a] for a in i],
            "target": [nodes[b] for b in j],
            "attention": matrix[i, j],
        }
    )
    frame["claim_level"] = "model_diagnostic"
    frame["note"] = ATTENTION_DISCLAIMER
    return frame.sort_values("attention", ascending=False).head(top_n).reset_index(drop=True)


def node_masking(model: Any, batch: Any, nodes: list[str], device: str = "cpu") -> pd.DataFrame:
    """Zero out each node's features and record the change in predicted probability."""
    try:
        import torch
    except ImportError:
        logger.info("torch not installed; GNN masking analysis unavailable.")
        return pd.DataFrame()

    model.eval()
    with torch.no_grad():
        baseline = float(torch.sigmoid(model(*batch)[0]).mean().item())
        rows = []
        features = batch[0]
        for index, node in enumerate(nodes):
            masked = features.clone()
            masked[..., index, :] = 0.0
            value = float(torch.sigmoid(model(masked, *batch[1:])[0]).mean().item())
            rows.append(
                {
                    "node": node,
                    "baseline_probability": baseline,
                    "masked_probability": value,
                    "change": value - baseline,
                }
            )
    frame = pd.DataFrame(rows)
    frame["claim_level"] = "predictive_importance"
    return frame.reindex(frame["change"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def edge_masking(model: Any, batch: Any, edges: list[tuple[str, str]], device: str = "cpu") -> pd.DataFrame:
    """Zero individual edge weights and record the change in predicted probability."""
    try:
        import torch
    except ImportError:
        return pd.DataFrame()

    model.eval()
    features, adjacency = batch[0], batch[1]
    with torch.no_grad():
        baseline = float(torch.sigmoid(model(features, adjacency, *batch[2:])[0]).mean().item())
        rows = []
        for source_index, target_index, source, target in edges:
            masked = adjacency.clone()
            masked[..., source_index, target_index] = 0.0
            masked[..., target_index, source_index] = 0.0
            value = float(torch.sigmoid(model(features, masked, *batch[2:])[0]).mean().item())
            rows.append(
                {"source": source, "target": target, "change": value - baseline, "baseline": baseline}
            )
    frame = pd.DataFrame(rows)
    frame["claim_level"] = "predictive_importance"
    return frame


def try_gnn_explainer(model: Any, data: Any) -> pd.DataFrame:
    """Use torch-geometric's GNNExplainer when it is installed."""
    try:
        from torch_geometric.explain import Explainer, GNNExplainer
    except ImportError:
        logger.info("torch-geometric not installed; GNNExplainer unavailable.")
        return pd.DataFrame()
    try:
        explainer = Explainer(
            model=model,
            algorithm=GNNExplainer(epochs=100),
            explanation_type="model",
            node_mask_type="attributes",
            edge_mask_type="object",
            model_config=dict(mode="binary_classification", task_level="graph", return_type="raw"),
        )
        explanation = explainer(data.x, data.edge_index)
        return pd.DataFrame(
            {
                "edge_index_source": data.edge_index[0].cpu().numpy(),
                "edge_index_target": data.edge_index[1].cpu().numpy(),
                "edge_mask": explanation.edge_mask.detach().cpu().numpy(),
            }
        )
    except Exception as exc:
        logger.warning("GNNExplainer failed: %s", exc)
        return pd.DataFrame()
