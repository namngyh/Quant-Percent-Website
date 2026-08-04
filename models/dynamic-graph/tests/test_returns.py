"""Return, volatility and drawdown primitives."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.constants import TRADING_DAYS_PER_YEAR
from dynamicgraph.features import returns as R


def test_log_return_formula():
    prices = pd.DataFrame({"A": [100.0, 110.0, 99.0]})
    result = R.compute_log_returns(prices, 1)["A"]
    assert np.isnan(result.iloc[0])
    assert result.iloc[1] == pytest.approx(np.log(110 / 100))
    assert result.iloc[2] == pytest.approx(np.log(99 / 110))


def test_multi_period_log_return_is_additive():
    rng = np.random.default_rng(0)
    prices = pd.DataFrame({"A": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 200)))})
    daily = R.compute_log_returns(prices, 1)["A"]
    five_day = R.compute_log_returns(prices, 5)["A"]
    assert five_day.iloc[10] == pytest.approx(daily.iloc[6:11].sum())


def test_non_positive_prices_produce_nan():
    prices = pd.DataFrame({"A": [100.0, 0.0, -5.0, 120.0]})
    result = R.compute_log_returns(prices, 1)["A"]
    assert result.isna().iloc[1:3].all()


def test_rolling_volatility_annualisation():
    rng = np.random.default_rng(7)
    returns = pd.DataFrame({"A": rng.normal(0, 0.02, 500)})
    annualised = R.rolling_volatility(returns, 60, annualize=True)["A"].iloc[-1]
    daily = R.rolling_volatility(returns, 60, annualize=False)["A"].iloc[-1]
    assert annualised == pytest.approx(daily * np.sqrt(TRADING_DAYS_PER_YEAR))
    assert 0.20 < annualised < 0.45          # ~0.02 * sqrt(252) = 0.317


def test_downside_volatility_ignores_upside():
    returns = pd.DataFrame({"A": [0.05] * 50})
    assert R.downside_volatility(returns, 20)["A"].iloc[-1] == pytest.approx(0.0)
    negatives = pd.DataFrame({"A": [-0.02] * 50})
    assert R.downside_volatility(negatives, 20)["A"].iloc[-1] > 0


def test_drawdown_is_non_positive_and_zero_at_peak():
    prices = pd.DataFrame({"A": [100.0, 120.0, 90.0, 150.0]})
    drawdown = R.drawdown_series(prices)["A"]
    assert (drawdown <= 1e-12).all()
    assert drawdown.iloc[0] == pytest.approx(0.0)
    assert drawdown.iloc[1] == pytest.approx(0.0)
    assert drawdown.iloc[2] == pytest.approx(90 / 120 - 1)
    assert drawdown.iloc[3] == pytest.approx(0.0)


def test_days_since_peak_counts_correctly():
    prices = pd.DataFrame({"A": [100.0, 120.0, 110.0, 105.0, 130.0]})
    since = R.days_since_peak(prices)["A"]
    assert since.iloc[1] == 0
    assert since.iloc[2] == 1
    assert since.iloc[3] == 2
    assert since.iloc[4] == 0


def test_rolling_max_drawdown_bounded_by_window():
    prices = pd.DataFrame({"A": [100.0] * 30 + [50.0] + [100.0] * 30})
    short = R.rolling_max_drawdown(prices, 10)["A"].iloc[-1]
    long = R.rolling_max_drawdown(prices, 60)["A"].iloc[-1]
    assert short == pytest.approx(0.0, abs=1e-9)
    assert long < -0.4


def test_short_term_reversal_sign():
    returns = pd.DataFrame({"A": [0.01] * 20})
    assert R.short_term_reversal(returns, 5)["A"].iloc[-1] == pytest.approx(-0.05)


def test_robust_zscore_is_outlier_resistant():
    frame = pd.DataFrame({"A": [1.0], "B": [1.0], "C": [1.0], "D": [1.0], "E": [1000.0]})
    z = R.robust_zscore(frame, axis=1, clip=None)
    assert abs(z.loc[0, "A"]) < 1.0
    assert z.loc[0, "E"] > 10


def test_expected_shortfall_exceeds_var():
    rng = np.random.default_rng(3)
    returns = pd.DataFrame({"A": rng.standard_t(4, 600) * 0.01})
    var = R.historical_var(returns, 250, 0.05)["A"].iloc[-1]
    es = R.historical_expected_shortfall(returns, 250, 0.05)["A"].iloc[-1]
    assert es >= var > 0


def test_zero_return_ratio_range():
    returns = pd.DataFrame({"A": [0.0] * 10 + [0.01] * 10})
    ratio = R.zero_return_ratio(returns, 20)["A"].iloc[-1]
    assert ratio == pytest.approx(0.5)
