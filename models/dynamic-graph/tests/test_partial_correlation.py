"""Partial correlation and edge filtering."""

from __future__ import annotations

import numpy as np
import pytest

from dynamicgraph.graphs.filtering import (
    apply_absolute_threshold,
    apply_quantile_threshold,
    enforce_max_density,
    filter_adjacency,
)
from dynamicgraph.graphs.partial_correlation import (
    average_absolute_partial_correlation,
    partial_correlation_from_covariance,
    partial_correlation_from_precision,
    signed_edge_shares,
)


def test_partial_correlation_formula():
    precision = np.array([[2.0, -1.0, 0.0], [-1.0, 3.0, -0.5], [0.0, -0.5, 4.0]])
    partial = partial_correlation_from_precision(precision)
    assert partial[0, 1] == pytest.approx(1.0 / np.sqrt(2.0 * 3.0))
    assert partial[1, 2] == pytest.approx(0.5 / np.sqrt(3.0 * 4.0))
    assert partial[0, 2] == pytest.approx(0.0)
    np.testing.assert_allclose(np.diag(partial), 0.0)


def test_partial_correlation_is_symmetric_and_bounded():
    rng = np.random.default_rng(31)
    data = rng.normal(0, 1, (500, 6))
    covariance = np.cov(data, rowvar=False)
    partial = partial_correlation_from_covariance(covariance)
    np.testing.assert_allclose(partial, partial.T, atol=1e-10)
    assert partial.min() >= -1.0 and partial.max() <= 1.0


def test_partial_correlation_removes_indirect_dependence():
    """X -> Y -> Z chain: corr(X, Z) is large, partial corr(X, Z | Y) is near zero."""
    rng = np.random.default_rng(32)
    n = 4000
    x = rng.normal(0, 1, n)
    y = x + rng.normal(0, 0.3, n)
    z = y + rng.normal(0, 0.3, n)
    data = np.column_stack([x, y, z])

    correlation = np.corrcoef(data, rowvar=False)
    partial = partial_correlation_from_covariance(np.cov(data, rowvar=False))

    assert correlation[0, 2] > 0.7, "the indirect correlation should be strong"
    assert abs(partial[0, 2]) < 0.15, (
        f"conditioning on Y should remove the X-Z link, got {partial[0, 2]:.3f}"
    )


def test_partial_correlation_is_scale_invariant():
    rng = np.random.default_rng(33)
    data = rng.normal(0, 1, (800, 5))
    base = partial_correlation_from_covariance(np.cov(data, rowvar=False))

    scaled = data * np.array([1.0, 100.0, 0.01, 5.0, 1000.0])
    scaled_partial = partial_correlation_from_covariance(np.cov(scaled, rowvar=False))
    np.testing.assert_allclose(base, scaled_partial, atol=1e-6)


def test_signed_edge_shares_sum_to_one():
    adjacency = np.array([[0.0, 0.5, -0.3], [0.5, 0.0, 0.0], [-0.3, 0.0, 0.0]])
    positive, negative = signed_edge_shares(adjacency)
    assert positive + negative == pytest.approx(1.0)
    assert positive == pytest.approx(0.5)


def test_absolute_threshold_removes_weak_edges():
    adjacency = np.array([[0.0, 0.05, 0.4], [0.05, 0.0, -0.2], [0.4, -0.2, 0.0]])
    filtered = apply_absolute_threshold(adjacency, 0.1)
    assert filtered[0, 1] == 0.0
    assert filtered[0, 2] == pytest.approx(0.4)
    assert filtered[1, 2] == pytest.approx(-0.2)


def test_quantile_threshold_keeps_the_requested_share():
    rng = np.random.default_rng(34)
    n = 20
    adjacency = rng.normal(0, 1, (n, n))
    adjacency = (adjacency + adjacency.T) / 2
    np.fill_diagonal(adjacency, 0.0)

    filtered = apply_quantile_threshold(adjacency, 0.25)
    i, j = np.triu_indices(n, k=1)
    kept = int((np.abs(filtered[i, j]) > 0).sum())
    assert kept == pytest.approx(0.25 * len(i), rel=0.15)


def test_quantile_threshold_preserves_the_strongest_edge():
    rng = np.random.default_rng(35)
    n = 12
    adjacency = rng.normal(0, 0.1, (n, n))
    adjacency = (adjacency + adjacency.T) / 2
    np.fill_diagonal(adjacency, 0.0)
    adjacency[0, 1] = adjacency[1, 0] = 5.0

    filtered = apply_quantile_threshold(adjacency, 0.1)
    assert filtered[0, 1] == pytest.approx(5.0)


def test_density_cap_is_enforced():
    rng = np.random.default_rng(36)
    n = 20
    adjacency = rng.normal(0, 1, (n, n))
    adjacency = (adjacency + adjacency.T) / 2
    np.fill_diagonal(adjacency, 0.0)

    capped = enforce_max_density(adjacency, 0.2)
    i, j = np.triu_indices(n, k=1)
    density = (np.abs(capped[i, j]) > 0).mean()
    assert density <= 0.2 + 1e-9


def test_filter_adjacency_reports_what_it_did():
    rng = np.random.default_rng(37)
    n = 15
    adjacency = rng.normal(0, 1, (n, n))
    adjacency = (adjacency + adjacency.T) / 2
    np.fill_diagonal(adjacency, 0.0)

    filtered, info = filter_adjacency(adjacency, method="quantile", keep_fraction=0.3, max_density=0.9)
    assert info["filter_method"] == "quantile"
    assert info["n_edges"] > 0
    assert 0 < info["density"] <= 0.9
    assert np.all(np.diag(filtered) == 0.0)


def test_stability_filter_falls_back_without_a_stability_matrix():
    adjacency = np.array([[0.0, 0.5], [0.5, 0.0]])
    _, info = filter_adjacency(adjacency, method="stability", stability=None, keep_fraction=1.0)
    assert info["filter_method"] == "quantile_fallback"


def test_average_absolute_partial_correlation():
    adjacency = np.array([[0.0, 0.2, -0.4], [0.2, 0.0, 0.6], [-0.4, 0.6, 0.0]])
    assert average_absolute_partial_correlation(adjacency) == pytest.approx((0.2 + 0.4 + 0.6) / 3)
