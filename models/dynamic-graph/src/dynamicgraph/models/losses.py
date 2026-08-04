"""Loss functions for the Temporal GNN.

Imports torch lazily so the module can be imported (and skipped) without it.
"""

from __future__ import annotations

from typing import Any


def _torch():
    import torch

    return torch


def focal_loss_with_logits(
    logits: Any, targets: Any, alpha: float = 0.25, gamma: float = 2.0, reduction: str = "mean"
) -> Any:
    r"""Focal loss: FL = -alpha_t (1 - p_t)^gamma log(p_t).

    Down-weights easy negatives, which dominate a 10% positive-rate stress
    target and otherwise swamp the gradient.
    """
    torch = _torch()
    import torch.nn.functional as F

    targets = targets.float()
    bce = F.binary_cross_entropy_with_logits(logits, targets, reduction="none")
    p = torch.sigmoid(logits)
    p_t = p * targets + (1 - p) * (1 - targets)
    alpha_t = alpha * targets + (1 - alpha) * (1 - targets)
    loss = alpha_t * (1 - p_t).pow(gamma) * bce
    if reduction == "mean":
        return loss.mean()
    if reduction == "sum":
        return loss.sum()
    return loss


def weighted_bce_with_logits(
    logits: Any, targets: Any, pos_weight: float | None = None, reduction: str = "mean"
) -> Any:
    """Binary cross-entropy with an explicit positive-class weight."""
    torch = _torch()
    import torch.nn.functional as F

    weight = torch.tensor(pos_weight, device=logits.device, dtype=logits.dtype) if pos_weight else None
    return F.binary_cross_entropy_with_logits(
        logits, targets.float(), pos_weight=weight, reduction=reduction
    )


def build_loss(name: str = "focal", gamma: float = 2.0, pos_weight: float | None = None):
    """Return a `(logits, targets) -> loss` callable."""
    if name == "focal":
        return lambda logits, targets: focal_loss_with_logits(logits, targets, gamma=gamma)
    return lambda logits, targets: weighted_bce_with_logits(logits, targets, pos_weight=pos_weight)
