"""Graphical lasso, covariance shrinkage and alpha selection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.graphs.graphical_lasso import (
    fit_graphical_lasso,
    graph_density_from_precision,
    select_alpha,
)
from dynamicgraph.graphs.shrinkage import estimate_covariance, nearest_positive_definite


def _block_returns(n: int = 600, block_size: int = 4, n_blocks: int = 3, seed: int = 21) -> np.ndarray:
    """Returns with a block structure: dependence inside blocks only."""
    rng = np.random.default_rng(seed)
    columns = []
    for _ in range(n_blocks):
        factor = rng.normal(0, 0.01, n)
        for _ in range(block_size):
            columns.append(0.9 * factor + rng.normal(0, 0.004, n))
    return np.column_stack(columns)


def test_ledoit_wolf_is_better_conditioned_than_sample():
    rng = np.random.default_rng(22)
    returns = rng.normal(0, 0.01, (25, 20))     # T < N territory
    shrunk = estimate_covariance(returns, "ledoit_wolf")
    sample = estimate_covariance(returns, "sample")
    assert 0.0 <= shrunk.shrinkage <= 1.0
    assert shrunk.condition_number < sample.condition_number


def test_shrunk_covariance_is_positive_definite():
    rng = np.random.default_rng(23)
    returns = rng.normal(0, 0.01, (30, 30))
    estimate = estimate_covariance(returns, "ledoit_wolf")
    assert np.linalg.eigvalsh(estimate.covariance).min() > 0


def test_correlation_matrix_properties():
    returns = _block_returns()
    estimate = estimate_covariance(returns, "ledoit_wolf")
    correlation = estimate.correlation
    np.testing.assert_allclose(np.diag(correlation), 1.0, atol=1e-8)
    np.testing.assert_allclose(correlation, correlation.T, atol=1e-10)
    assert correlation.min() >= -1.0 and correlation.max() <= 1.0


def test_graphical_lasso_sparsity_increases_with_alpha():
    returns = _block_returns()
    correlation = estimate_covariance(returns, "ledoit_wolf").correlation
    densities = [
        graph_density_from_precision(fit_graphical_lasso(correlation, a).precision)
        for a in (0.001, 0.02, 0.10, 0.30)
    ]
    assert densities == sorted(densities, reverse=True), f"density not monotone in alpha: {densities}"
    assert densities[0] > densities[-1]


def test_graphical_lasso_recovers_block_structure():
    """Within-block partial correlations should dominate cross-block ones."""
    from dynamicgraph.graphs.partial_correlation import partial_correlation_from_precision

    returns = _block_returns(n=1500, block_size=4, n_blocks=3, seed=24)
    correlation = estimate_covariance(returns, "ledoit_wolf").correlation
    partial = partial_correlation_from_precision(fit_graphical_lasso(correlation, 0.02).precision)

    within, across = [], []
    for i in range(12):
        for j in range(i + 1, 12):
            (within if i // 4 == j // 4 else across).append(abs(partial[i, j]))
    assert np.mean(within) > np.mean(across) * 2, (
        f"block structure not recovered: within {np.mean(within):.4f} vs across {np.mean(across):.4f}"
    )


def test_graphical_lasso_output_is_symmetric_positive_definite():
    returns = _block_returns()
    correlation = estimate_covariance(returns, "ledoit_wolf").correlation
    fit = fit_graphical_lasso(correlation, 0.05)
    np.testing.assert_allclose(fit.precision, fit.precision.T, atol=1e-8)
    assert np.linalg.eigvalsh(fit.precision).min() > -1e-8


def test_glasso_on_covariance_scale_would_be_degenerate():
    """Documents WHY the pipeline fits on the correlation matrix.

    Daily return covariances are ~1e-4, so alpha=0.02 on that scale kills every
    off-diagonal entry. The pipeline therefore fits on the correlation matrix.
    """
    returns = _block_returns()
    estimate = estimate_covariance(returns, "ledoit_wolf")
    on_covariance = graph_density_from_precision(
        fit_graphical_lasso(estimate.covariance, 0.02).precision
    )
    on_correlation = graph_density_from_precision(
        fit_graphical_lasso(estimate.correlation, 0.02).precision
    )
    assert on_covariance == pytest.approx(0.0, abs=1e-9)
    assert on_correlation > 0.05


def test_alpha_selection_uses_only_supplied_training_windows():
    rng = np.random.default_rng(25)
    train_windows = [_block_returns(n=120, seed=s) for s in range(30, 36)]
    alpha, diagnostics = select_alpha(train_windows, [0.01, 0.05, 0.2], method="stability", max_density=0.5)
    assert alpha in (0.01, 0.05, 0.2)
    assert not diagnostics.empty
    assert (diagnostics["mean_density"].diff().dropna() <= 1e-9).all()


def test_nearest_positive_definite_fixes_indefinite_matrix():
    matrix = np.array([[1.0, 2.0], [2.0, 1.0]])          # eigenvalues 3, -1
    fixed = nearest_positive_definite(matrix)
    assert np.linalg.eigvalsh(fixed).min() > 0


def test_estimate_covariance_rejects_short_windows():
    with pytest.raises(ValueError):
        estimate_covariance(np.zeros((2, 5)), "ledoit_wolf")
