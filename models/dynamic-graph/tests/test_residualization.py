"""Rolling beta and market residualization."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.features.residualization import (
    downside_upside_beta,
    residualize_returns,
    rolling_beta,
    sector_return_matrix,
)


def test_rolling_beta_recovers_a_known_loading():
    rng = np.random.default_rng(11)
    n = 600
    market = pd.Series(rng.normal(0, 0.01, n))
    true_beta = 1.4
    stock = pd.DataFrame({"A": true_beta * market + rng.normal(0, 0.002, n)})

    _, beta = rolling_beta(stock, market, window=250)
    assert beta["A"].iloc[-1] == pytest.approx(true_beta, abs=0.06)


def test_rolling_beta_matches_closed_form_ols():
    rng = np.random.default_rng(12)
    n, window = 300, 120
    market = pd.Series(rng.normal(0, 0.01, n))
    stock = pd.DataFrame({"A": 0.8 * market + rng.normal(0, 0.005, n)})

    alpha, beta = rolling_beta(stock, market, window=window)

    m = market.iloc[-window:].to_numpy()
    s = stock["A"].iloc[-window:].to_numpy()
    expected_beta = np.cov(s, m, ddof=1)[0, 1] / np.var(m, ddof=1)
    expected_alpha = s.mean() - expected_beta * m.mean()

    assert beta["A"].iloc[-1] == pytest.approx(expected_beta, rel=1e-6)
    assert alpha["A"].iloc[-1] == pytest.approx(expected_alpha, rel=1e-5, abs=1e-9)


def test_residuals_are_uncorrelated_with_the_market():
    rng = np.random.default_rng(13)
    n = 1000
    market = pd.Series(rng.normal(0, 0.012, n))
    stocks = pd.DataFrame(
        {f"S{i}": b * market + rng.normal(0, 0.008, n) for i, b in enumerate([0.7, 1.0, 1.3])}
    )
    residuals = residualize_returns(stocks, market, window=120).residuals

    tail = residuals.iloc[200:]
    for column in tail.columns:
        correlation = tail[column].corr(market.iloc[200:])
        assert abs(correlation) < 0.15, f"{column} residual still tracks the market ({correlation:.3f})"


def test_residualization_reduces_average_pairwise_correlation():
    """The whole point: stripping the market mode should decorrelate the panel."""
    rng = np.random.default_rng(14)
    n = 900
    market = pd.Series(rng.normal(0, 0.013, n))
    stocks = pd.DataFrame(
        {f"S{i}": 1.0 * market + rng.normal(0, 0.007, n) for i in range(8)}
    )
    residuals = residualize_returns(stocks, market, window=120).residuals.iloc[150:]

    def mean_abs_corr(frame: pd.DataFrame) -> float:
        matrix = frame.corr().to_numpy()
        i, j = np.triu_indices(matrix.shape[0], k=1)
        return float(np.abs(matrix[i, j]).mean())

    assert mean_abs_corr(residuals) < mean_abs_corr(stocks.iloc[150:])


def test_idiosyncratic_volatility_is_below_total_volatility():
    rng = np.random.default_rng(15)
    n = 800
    market = pd.Series(rng.normal(0, 0.014, n))
    stocks = pd.DataFrame({"A": 1.2 * market + rng.normal(0, 0.006, n)})
    result = residualize_returns(stocks, market, window=120)

    total = stocks["A"].iloc[200:].std(ddof=1) * np.sqrt(252)
    ivol = result.idiosyncratic_volatility["A"].iloc[-1]
    assert 0 < ivol < total


def test_r_squared_within_bounds():
    rng = np.random.default_rng(16)
    n = 600
    market = pd.Series(rng.normal(0, 0.01, n))
    stocks = pd.DataFrame({"A": market + rng.normal(0, 0.004, n)})
    r2 = residualize_returns(stocks, market, window=120).r_squared["A"].dropna()
    assert (r2 <= 1.0 + 1e-9).all()
    assert r2.iloc[-1] > 0.5


def test_downside_beta_differs_when_asymmetry_is_present():
    rng = np.random.default_rng(17)
    n = 1200
    market = pd.Series(rng.normal(0, 0.013, n))
    # Beta 1.8 when the market falls, 0.4 when it rises.
    stock = pd.DataFrame({"A": np.where(market < 0, 1.8 * market, 0.4 * market) + rng.normal(0, 0.003, n)})

    down, up = downside_upside_beta(stock, market, window=400)
    assert down["A"].iloc[-1] > up["A"].iloc[-1]
    assert down["A"].iloc[-1] == pytest.approx(1.8, abs=0.35)


def test_sector_return_matrix_averages_members():
    frame = pd.DataFrame({"A": [0.01, 0.02], "B": [0.03, 0.04], "C": [-0.01, -0.02]})
    sectors = {"A": "X", "B": "X", "C": "Y"}
    result = sector_return_matrix(frame, sectors)
    assert result.loc[0, "X"] == pytest.approx(0.02)
    assert result.loc[1, "Y"] == pytest.approx(-0.02)
