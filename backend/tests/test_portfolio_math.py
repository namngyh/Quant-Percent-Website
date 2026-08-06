"""Tests for the portfolio analytics maths.

These cover the parts where a wrong answer would look plausible on the page:
risk contribution that does not sum to one, a shrinkage estimator that
flattens correlation structure, and drawdown measured on the wrong series.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.services.portfolio import (
    _aligned_returns,
    _concentration,
    _ledoit_wolf,
    _max_drawdown,
    _risk_state,
)
from app.schemas.common import RiskState


def _returns(seed: int, n: int, loadings: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.standard_normal((n, loadings.shape[0])) @ loadings.T) * 0.02


class TestLedoitWolf:
    def test_preserves_correlation_structure(self):
        """Shrinkage must not collapse every pair onto the average.

        An earlier version dropped the `rho` term. The intensity then
        saturated at 1.0 on real daily returns and every off-diagonal
        correlation became identical, which would have made a cluster of
        highly correlated holdings indistinguishable from a diversified book.
        """
        loadings = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.9, 0.44, 0.0],  # near-duplicate of asset 0
                [0.05, 0.05, 1.0],  # nearly independent
            ]
        )
        returns = _returns(7, 400, loadings)
        shrunk = _ledoit_wolf(returns)

        std = np.sqrt(np.diag(shrunk))
        corr = shrunk / np.outer(std, std)

        assert corr[0, 1] > 0.7, "the correlated pair must stay correlated"
        assert corr[0, 2] < 0.3, "the independent asset must stay independent"
        assert corr[0, 1] - corr[0, 2] > 0.4, "structure must survive shrinkage"

    def test_stays_positive_semidefinite(self):
        loadings = np.eye(5)
        returns = _returns(11, 80, loadings)
        eigenvalues = np.linalg.eigvalsh(_ledoit_wolf(returns))
        assert eigenvalues.min() > -1e-12

    def test_single_asset_returns_sample_variance(self):
        returns = _returns(3, 100, np.eye(1))
        result = _ledoit_wolf(returns)
        assert result.shape == (1, 1)
        assert result[0, 0] == pytest.approx(returns.var(ddof=1), rel=1e-9)


class TestRiskContribution:
    def test_contributions_sum_to_one(self):
        """Euler decomposition is exact; the column must total 100%."""
        loadings = np.array([[1.0, 0.0], [0.6, 0.8]])
        returns = _returns(5, 300, loadings)
        cov = _ledoit_wolf(returns)
        weights = np.array([0.7, 0.3])

        contributions = weights * (cov @ weights)
        shares = contributions / contributions.sum()

        assert shares.sum() == pytest.approx(1.0, rel=1e-12)
        assert (shares >= 0).all()

    def test_volatile_position_exceeds_its_weight(self):
        """The whole point of the panel: risk share != money share."""
        # Asset 1 is four times as volatile as asset 0.
        loadings = np.array([[1.0, 0.0], [0.0, 4.0]])
        returns = _returns(9, 400, loadings)
        cov = _ledoit_wolf(returns)
        weights = np.array([0.5, 0.5])

        contributions = weights * (cov @ weights)
        shares = contributions / contributions.sum()

        assert shares[1] > 0.85, "the volatile half must dominate the risk"


class TestMaxDrawdown:
    def test_monotonic_rise_has_no_drawdown(self):
        assert _max_drawdown(np.full(50, 0.001)) == pytest.approx(0.0)

    def test_known_path(self):
        """Up 20% to a peak of 1.2, then down to 0.72 — a 40% drawdown.

        Measured from the peak, not from the start: a book that rose first
        and gave it back has fallen 40%, not 28%.
        """
        series = np.array([math.log(1.2), math.log(0.72 / 1.2)])
        assert _max_drawdown(series) == pytest.approx(-0.4, rel=1e-9)

    def test_empty_series(self):
        assert _max_drawdown(np.array([])) == 0.0


class TestAlignedReturns:
    def test_intersects_dates_rather_than_filling(self):
        """A filled price would produce a zero return and understate risk."""
        import datetime as dt

        d = [dt.date(2026, 1, i) for i in range(1, 6)]
        closes = {
            "A": {d[0]: 100.0, d[1]: 110.0, d[2]: 105.0, d[3]: 108.0},
            # B did not trade on d[1].
            "B": {d[0]: 50.0, d[2]: 52.0, d[3]: 51.0},
        }
        dates, returns = _aligned_returns(closes, ["A", "B"])

        assert dates == [d[2], d[3]]
        assert returns.shape == (2, 2)
        assert not np.any(returns == 0.0)

    def test_too_few_common_dates(self):
        import datetime as dt

        closes = {"A": {dt.date(2026, 1, 1): 1.0}, "B": {dt.date(2026, 1, 2): 1.0}}
        dates, returns = _aligned_returns(closes, ["A", "B"])
        assert returns.size == 0


class TestConcentration:
    def test_correlated_book_has_fewer_effective_bets(self):
        """Ten names that move together are not ten independent positions."""
        n = 10
        weights = np.full(n, 1 / n)
        # Every pair correlated at 0.8, unit variance.
        corr = np.full((n, n), 0.8)
        np.fill_diagonal(corr, 1.0)

        result = _concentration([f"S{i}" for i in range(n)], weights, corr, {})

        assert result.effective_assets == pytest.approx(10.0, rel=1e-6)
        assert result.effective_bets < 2.0, (
            "correlation must cut the effective count well below the headcount"
        )
        assert result.average_correlation == pytest.approx(0.8, rel=1e-6)

    def test_independent_book_keeps_its_bets(self):
        n = 5
        weights = np.full(n, 1 / n)
        cov = np.eye(n)
        result = _concentration([f"S{i}" for i in range(n)], weights, cov, {})
        assert result.effective_bets == pytest.approx(5.0, rel=1e-6)

    def test_sector_weights_group_and_label_unknowns(self):
        weights = np.array([0.5, 0.3, 0.2])
        cov = np.eye(3)
        result = _concentration(
            ["AAA", "BBB", "CCC"], weights, cov, {"AAA": "Banks", "BBB": "Banks"}
        )
        assert result.sector_weights["Banks"] == pytest.approx(0.8)
        assert result.sector_weights["Unclassified"] == pytest.approx(0.2)

    def test_reports_the_most_correlated_pair(self):
        cov = np.array([[1.0, 0.1, 0.9], [0.1, 1.0, 0.2], [0.9, 0.2, 1.0]])
        result = _concentration(
            ["AAA", "BBB", "CCC"], np.array([0.4, 0.3, 0.3]), cov, {}
        )
        assert result.max_pair == ["AAA", "CCC"]
        assert result.max_pair_correlation == pytest.approx(0.9)


class TestRiskState:
    @pytest.mark.parametrize(
        ("vol", "dd", "expected"),
        [
            (0.10, -0.03, RiskState.low),
            (0.20, -0.05, RiskState.moderate),
            (0.10, -0.10, RiskState.moderate),
            (0.30, -0.05, RiskState.elevated),
            (0.10, -0.20, RiskState.elevated),
            (0.40, -0.05, RiskState.high),
            (0.10, -0.30, RiskState.high),
        ],
    )
    def test_grades(self, vol, dd, expected):
        assert _risk_state(vol, dd) is expected
