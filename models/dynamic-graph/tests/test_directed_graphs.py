"""Directed graph conventions and multiple-testing controls."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.graphs.spillover import VARFit


def test_spillover_adjacency_transposes_fevd_shock_convention(monkeypatch):
    """FEVD theta[i,j] is receiver i due to shock j; graph edges are j -> i."""
    import dynamicgraph.graphs.spillover as module

    theta = np.eye(5) * 0.8
    theta[1, 0] = 0.20  # Shock in A explains B: A must transmit to B.
    theta[1, 1] = 0.60
    theta = theta / theta.sum(axis=1, keepdims=True)
    fit = VARFit(
        coefficients=np.zeros((1, 5, 5)),
        residual_covariance=np.eye(5),
        lags=1,
        estimator="ridge",
        n_observations=80,
    )
    monkeypatch.setattr(module, "fit_regularized_var", lambda *args, **kwargs: (fit, None))
    monkeypatch.setattr(module, "generalized_fevd", lambda *args, **kwargs: theta)

    values = pd.DataFrame(
        np.random.default_rng(5).normal(size=(80, 5)),
        index=pd.bdate_range("2024-01-01", periods=80),
        columns=list("ABCDE"),
    )
    snapshot = module.build_spillover_snapshot(values, values.index[-1], lags=1)
    assert snapshot is not None
    assert snapshot.adjacency[0, 1] == pytest.approx(theta[1, 0])
    assert snapshot.adjacency[1, 0] == pytest.approx(theta[0, 1])
    assert snapshot.out_strength["A"] > snapshot.in_strength["A"]
    assert snapshot.metadata["fevd_convention"] == "theta[i,j] = variance of i due to shock j"
    assert snapshot.metadata["adjacency_convention"] == "adjacency[j,i] = theta[i,j]"
    assert snapshot.metadata["directional_spillover_sum"] == pytest.approx(
        theta.sum() - np.trace(theta)
    )


def test_asymmetric_var_identifies_known_transmitter():
    """A synthetic A -> B VAR must label A as the stronger transmitter."""
    from dynamicgraph.graphs.spillover import build_spillover_snapshot

    rng = np.random.default_rng(17)
    n = 800
    values = np.zeros((n, 5))
    shocks = rng.normal(scale=0.5, size=(n, 5))
    for position in range(1, n):
        values[position, 0] = 0.25 * values[position - 1, 0] + shocks[position, 0]
        values[position, 1] = (
            0.85 * values[position - 1, 0]
            + 0.10 * values[position - 1, 1]
            + 0.25 * shocks[position, 1]
        )
        values[position, 2:] = 0.10 * values[position - 1, 2:] + shocks[position, 2:]
    frame = pd.DataFrame(
        values,
        index=pd.bdate_range("2020-01-01", periods=n),
        columns=list("ABCDE"),
    )
    snapshot = build_spillover_snapshot(
        frame, frame.index[-1], horizon=8, lags=1, alpha=0.01
    )
    assert snapshot is not None
    assert snapshot.adjacency[0, 1] > snapshot.adjacency[1, 0]
    assert snapshot.net_spillover["A"] > snapshot.net_spillover["B"]


def test_lead_lag_fdr_receives_full_pair_by_lag_family(monkeypatch):
    import dynamicgraph.graphs.lead_lag as module

    lags = (1, 2, 3)
    correlations = {}
    for lag in lags:
        matrix = np.zeros((5, 5))
        matrix[0, 1] = 0.75 if lag == 2 else 0.10
        matrix[1, 0] = 0.05
        correlations[lag] = matrix

    monkeypatch.setattr(
        module, "lagged_correlation_matrix", lambda frame, lag: correlations[lag]
    )
    monkeypatch.setattr(
        module,
        "fisher_z_pvalues",
        lambda correlation, n_obs: np.where(np.abs(correlation) > 0.7, 1e-8, 0.5),
    )
    captured = {}

    def fake_bh(pvalues, alpha):
        captured["shape"] = pvalues.shape
        selected = np.zeros_like(pvalues, dtype=bool)
        selected[1, 0, 1] = True
        return selected

    monkeypatch.setattr(module, "benjamini_hochberg", fake_bh)
    frame = pd.DataFrame(
        np.random.default_rng(8).normal(size=(100, 5)),
        index=pd.bdate_range("2024-01-01", periods=100),
        columns=list("ABCDE"),
    )
    snapshot = module.build_lead_lag_snapshot(
        frame, frame.index[-1], lags=lags, threshold=1.1, min_abs_corr=0.05
    )
    assert snapshot is not None
    assert captured["shape"] == (3, 5, 5)
    assert snapshot.adjacency[0, 1] == pytest.approx(0.75)
    assert snapshot.metadata["n_hypotheses"] == 5 * 4 * len(lags)
    assert snapshot.metadata["n_rejections"] == 1
    assert snapshot.metadata["lag_selection_rule"] == "strongest absolute correlation among FDR rejections"


def test_more_null_lags_do_not_create_post_selection_discoveries():
    from dynamicgraph.graphs.lead_lag import build_lead_lag_snapshot

    rng = np.random.default_rng(1234)
    frame = pd.DataFrame(
        rng.normal(size=(500, 10)),
        index=pd.bdate_range("2020-01-01", periods=500),
        columns=[f"N{i}" for i in range(10)],
    )
    few = build_lead_lag_snapshot(
        frame, frame.index[-1], lags=(1,), threshold=1.1, min_abs_corr=0.0, fdr_alpha=0.05
    )
    many = build_lead_lag_snapshot(
        frame,
        frame.index[-1],
        lags=(1, 2, 3, 4, 5, 6, 7, 8),
        threshold=1.1,
        min_abs_corr=0.0,
        fdr_alpha=0.05,
    )
    assert few is not None and many is not None
    assert few.metadata["n_rejections"] == 0
    assert many.metadata["n_rejections"] == 0
