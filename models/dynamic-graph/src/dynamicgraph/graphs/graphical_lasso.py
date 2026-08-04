r"""Sparse inverse covariance (Graphical Lasso).

    Theta_hat = argmin_{Theta > 0}  tr(S Theta) - log det Theta + lambda * sum_{i!=j} |Theta_ij|

The penalty controls how many conditional dependencies survive, so it directly
controls graph density. Selection modes:

`fixed`
    use `graph.graphical_lasso_alpha`.
`cv_train_only`
    `GraphicalLassoCV` fitted **only** on the training period, then frozen. The
    chosen alpha is reused unchanged for validation and test snapshots.
`stability`
    pick the smallest alpha whose resulting density stays under
    `graph.max_graph_density` while keeping the graph connected enough to be
    informative -- again computed on the training period only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from dynamicgraph.graphs.shrinkage import nearest_positive_definite
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class GraphicalLassoFit:
    precision: np.ndarray
    covariance: np.ndarray
    alpha: float
    converged: bool
    n_iter: int | None = None
    note: str = ""


def fit_graphical_lasso(
    covariance: np.ndarray,
    alpha: float,
    max_iter: int = 200,
    tol: float = 1e-4,
    enet_tol: float = 1e-4,
) -> GraphicalLassoFit:
    """Fit the graphical lasso on a covariance matrix.

    Falls back progressively: raise alpha, then regularise the diagonal, then
    (last resort) return the plain inverse of a PD-projected covariance. Each
    fallback is recorded in `note` so it shows up in snapshot metadata.
    """
    from sklearn.covariance import graphical_lasso

    covariance = 0.5 * (covariance + covariance.T)
    note = ""

    for attempt, scale in enumerate((1.0, 2.0, 5.0)):
        try:
            _, precision = graphical_lasso(
                covariance,
                alpha=alpha * scale,
                max_iter=max_iter,
                tol=tol,
                enet_tol=enet_tol,
            )
            if attempt:
                note = f"alpha scaled x{scale} after convergence failure"
            return GraphicalLassoFit(
                precision=np.asarray(precision),
                covariance=covariance,
                alpha=alpha * scale,
                converged=True,
                note=note,
            )
        except (FloatingPointError, ValueError, ArithmeticError) as exc:
            note = f"graphical_lasso failed at alpha={alpha * scale:.4g}: {exc}"
            continue

    # Diagonal loading, then plain inversion.
    try:
        loaded = nearest_positive_definite(covariance, epsilon=1e-6)
        from sklearn.covariance import graphical_lasso as _gl

        _, precision = _gl(loaded, alpha=alpha, max_iter=max_iter, tol=tol)
        return GraphicalLassoFit(
            precision=np.asarray(precision),
            covariance=loaded,
            alpha=alpha,
            converged=True,
            note=note + "; recovered after PD projection",
        )
    except Exception:
        loaded = nearest_positive_definite(covariance, epsilon=1e-6)
        precision = np.linalg.pinv(loaded)
        logger.warning("Graphical lasso failed; fell back to the pseudo-inverse (dense precision).")
        return GraphicalLassoFit(
            precision=precision,
            covariance=loaded,
            alpha=alpha,
            converged=False,
            note=note + "; fell back to pseudo-inverse - graph will be dense",
        )


def graph_density_from_precision(precision: np.ndarray, tolerance: float = 1e-8) -> float:
    n = precision.shape[0]
    if n < 2:
        return 0.0
    i, j = np.triu_indices(n, k=1)
    return float(np.mean(np.abs(precision[i, j]) > tolerance))


def select_alpha(
    train_windows: Sequence[np.ndarray],
    alpha_grid: Iterable[float],
    method: str = "cv_train_only",
    max_density: float = 0.60,
    target_density: float = 0.20,
    n_folds: int = 3,
    seed: int = 42,
) -> tuple[float, pd.DataFrame]:
    """Choose the graphical-lasso penalty using TRAINING windows only.

    `train_windows` is a list of `(T, N)` return blocks drawn from the training
    period. Returns `(alpha, diagnostics)`.
    """
    grid = sorted(float(a) for a in alpha_grid)
    if not grid:
        raise ValueError("`alpha_grid` is empty.")

    if method == "fixed":
        return grid[len(grid) // 2], pd.DataFrame()

    from dynamicgraph.graphs.shrinkage import estimate_covariance

    rows: list[dict] = []

    if method == "cv_train_only":
        from sklearn.covariance import GraphicalLassoCV

        scores: dict[float, list[float]] = {a: [] for a in grid}
        for block in train_windows:
            try:
                # Standardise so the penalty operates on the correlation scale,
                # matching how snapshots are built.
                standardized = (block - block.mean(axis=0)) / (block.std(axis=0, ddof=1) + 1e-12)
                model = GraphicalLassoCV(alphas=grid, cv=n_folds, max_iter=150, n_jobs=1)
                model.fit(standardized)
                scores[float(model.alpha_)].append(1.0)
            except Exception as exc:
                logger.debug("GraphicalLassoCV failed on one window: %s", exc)
                continue
        votes = {a: len(v) for a, v in scores.items()}
        if sum(votes.values()) == 0:
            logger.warning("GraphicalLassoCV never converged; falling back to density targeting.")
            method = "stability"
        else:
            best = max(votes, key=lambda a: votes[a])
            rows = [{"alpha": a, "cv_votes": votes[a]} for a in grid]
            diagnostics = pd.DataFrame(rows)
            logger.info("Selected graphical-lasso alpha=%.4g by training-only CV.", best)
            return best, diagnostics

    # Density-targeting / stability selection.
    for alpha in grid:
        densities, connected = [], []
        for block in train_windows:
            estimate = estimate_covariance(block, "ledoit_wolf")
            fit = fit_graphical_lasso(estimate.correlation, alpha)
            density = graph_density_from_precision(fit.precision)
            densities.append(density)
            connected.append(float(density > 0.02))
        rows.append(
            {
                "alpha": alpha,
                "mean_density": float(np.mean(densities)) if densities else np.nan,
                "std_density": float(np.std(densities)) if densities else np.nan,
                "connected_fraction": float(np.mean(connected)) if connected else np.nan,
            }
        )

    diagnostics = pd.DataFrame(rows)
    feasible = diagnostics[
        (diagnostics["mean_density"] <= max_density) & (diagnostics["connected_fraction"] >= 0.9)
    ]
    if feasible.empty:
        best = float(diagnostics.loc[diagnostics["mean_density"].idxmin(), "alpha"])
        logger.warning(
            "No alpha satisfies density<=%.2f with a connected graph; using the sparsest (%.4g).",
            max_density,
            best,
        )
    else:
        idx = (feasible["mean_density"] - target_density).abs().idxmin()
        best = float(feasible.loc[idx, "alpha"])
        logger.info(
            "Selected graphical-lasso alpha=%.4g (mean training density %.3f).",
            best,
            float(feasible.loc[idx, "mean_density"]),
        )
    return best, diagnostics
