"""Explainability.

Three levels of claim are kept distinct throughout:

  association          -- X and Y move together
  predictive importance -- X improves out-of-sample prediction of Y
  causal effect        -- intervening on X changes Y

Nothing in DynamicGraph identifies a causal effect. Attention weights, SHAP
values and permutation importances are all *predictive importance* at best,
and the word "cause" never appears in generated output.
"""

from __future__ import annotations

from dynamicgraph.explainability.tabular import (
    logistic_coefficients,
    partial_dependence_frame,
    permutation_importance_frame,
    shap_values_frame,
)
from dynamicgraph.explainability.graph import (
    edge_contributions,
    node_centrality_contributions,
    stress_contribution_breakdown,
)

__all__ = [
    "permutation_importance_frame",
    "logistic_coefficients",
    "shap_values_frame",
    "partial_dependence_frame",
    "node_centrality_contributions",
    "edge_contributions",
    "stress_contribution_breakdown",
]

CLAIM_LEVELS = {
    "association": "X and Y co-move in the observed sample.",
    "predictive_importance": "Removing or permuting X degrades out-of-sample prediction of Y.",
    "causal_effect": "NOT ESTABLISHED by DynamicGraph. Requires an identification strategy.",
}
