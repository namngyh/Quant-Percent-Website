"""Tests for the portfolio analytics maths.

These cover the parts where a wrong answer would look plausible on the page:
risk contribution that does not sum to one, a shrinkage estimator that
flattens correlation structure, and drawdown measured on the wrong series.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.schemas.common import RiskState
from app.services.portfolio import (
    DRAWDOWN_THRESHOLDS,
    MC_BASE_HORIZON_DAYS,
    MIN_OBSERVATIONS,
    _aligned_returns,
    _concentration,
    _daily_log_returns,
    _exceedance_at,
    _ledoit_wolf,
    _max_drawdown,
    _risk_state,
)


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


# The curve the RARF-FHE run published on 2026-08-06, as depth/probability
# pairs. Real numbers rather than round ones, so a regression that happens to
# work on a synthetic curve still gets caught.
LIVE_CURVE = [(0.03, 0.932425), (0.05, 0.744), (0.07, 0.5339), (0.10, 0.295025)]


class TestExceedanceCurve:
    def test_anchored_at_certainty(self):
        """A fall of at least nothing is certain.

        The anchor is what a long horizon interpolates against: it pulls the
        lookup depth towards zero, and without (0, 1) on the left there is
        nothing there.
        """
        assert _exceedance_at(LIVE_CURVE, 0.0) == 1.0
        assert _exceedance_at(LIVE_CURVE, -0.01) == 1.0

    def test_reproduces_published_points(self):
        for depth, probability in LIVE_CURVE:
            assert _exceedance_at(LIVE_CURVE, depth) == pytest.approx(
                probability, rel=1e-9
            )

    def test_monotone_decreasing(self):
        depths = [d / 1000 for d in range(0, 300, 3)]
        values = [_exceedance_at(LIVE_CURVE, d) for d in depths]
        assert all(a >= b for a, b in zip(values, values[1:], strict=False))

    def test_stays_a_probability_past_the_deepest_point(self):
        """Extrapolation extends the tail; it must not leave [0, 1]."""
        for depth in (0.15, 0.30, 0.80, 5.0):
            assert 0.0 <= _exceedance_at(LIVE_CURVE, depth) <= 1.0

    def test_interpolates_below_the_endpoints(self):
        """Log-linear, so the midpoint sits under the arithmetic mean."""
        mid = _exceedance_at(LIVE_CURVE, 0.04)
        assert 0.744 < mid < 0.932425
        assert mid < (0.744 + 0.932425) / 2

    def test_empty_curve_yields_no_probability(self):
        assert _exceedance_at([], 0.05) == 0.0


class TestForwardScaling:
    """The two transformations that made the panel inert before.

    Previously `horizon_days` was echoed back unused and `probability` was
    copied straight from the index run, so neither the holdings nor the horizon
    changed a single plotted value. These assert that both now move.
    """

    @staticmethod
    def _probabilities(beta: float, horizon: int) -> list[float]:
        scale = math.sqrt(horizon / MC_BASE_HORIZON_DAYS)
        return [
            _exceedance_at(LIVE_CURVE, depth / abs(beta) / scale)
            for depth in DRAWDOWN_THRESHOLDS
        ]

    def test_longer_horizon_raises_every_probability(self):
        short = self._probabilities(1.0, 21)
        long = self._probabilities(1.0, 252)
        assert all(b > a for a, b in zip(short, long, strict=False))

    def test_higher_beta_raises_every_probability(self):
        calm = self._probabilities(0.6, 63)
        punchy = self._probabilities(1.4, 63)
        assert all(b > a for a, b in zip(calm, punchy, strict=False))

    def test_base_horizon_and_unit_beta_return_the_run_unchanged(self):
        """At beta 1 over the simulated horizon there is nothing to scale.

        Only the depths the run actually published are checked; the grid
        continues past them into extrapolated territory.
        """
        published = dict(LIVE_CURVE)
        # strict: one probability per threshold, or the grid and the
        # computation have drifted apart.
        scaled = dict(
            zip(
                DRAWDOWN_THRESHOLDS,
                self._probabilities(1.0, MC_BASE_HORIZON_DAYS),
                strict=True,
            )
        )
        for depth, probability in published.items():
            assert scaled[depth] == pytest.approx(probability, rel=1e-9)

    def test_thresholds_are_a_fixed_ascending_grid(self):
        """The axis must not move, or two books cannot be compared."""
        assert all(0.0 < d < 1.0 for d in DRAWDOWN_THRESHOLDS)
        assert list(DRAWDOWN_THRESHOLDS) == sorted(DRAWDOWN_THRESHOLDS)
        assert len(set(DRAWDOWN_THRESHOLDS)) == len(DRAWDOWN_THRESHOLDS)
        # The published curve has to be inside the grid, otherwise every
        # plotted point is an extrapolation.
        assert set(d for d, _ in LIVE_CURVE) <= set(DRAWDOWN_THRESHOLDS)

    def test_grid_keeps_a_readable_spread_at_every_horizon(self):
        """A curve pinned near 100% across the board tells a reader nothing.

        This is why the grid runs past 10%: over a year a 3% fall is close to
        certain, and a shallow grid draws a flat line just under the top.
        """
        for horizon in (21, 63, 126, 252):
            values = self._probabilities(1.0, horizon)
            assert max(values) - min(values) > 0.4


class TestBenchmarkAlignment:
    """Beta must survive an index that does not cover every session.

    The window is the most recent `lookback` rows per symbol, so a stock whose
    daily bars lag the index reaches further back and lands on dates the index
    window does not hold. Requiring full coverage set beta to None, which took
    the whole forward panel and both of its charts off the page — on ordinary
    holdings, with nothing shown to explain it.
    """

    @staticmethod
    def _closes(start: int, n: int) -> dict:
        import datetime as dt

        base = dt.date(2026, 1, 1)
        return {
            base + dt.timedelta(days=start + i): 100.0 + i for i in range(n)
        }

    def test_returns_are_keyed_by_the_later_session(self):
        import datetime as dt

        closes = {
            dt.date(2026, 1, 2): 100.0,
            dt.date(2026, 1, 5): 110.0,
            dt.date(2026, 1, 6): 121.0,
        }
        out = _daily_log_returns(closes)

        # The first session has nothing before it, so it carries no return.
        assert dt.date(2026, 1, 2) not in out
        assert out[dt.date(2026, 1, 5)] == pytest.approx(math.log(1.1))
        assert out[dt.date(2026, 1, 6)] == pytest.approx(math.log(1.1))

    def test_partial_overlap_still_produces_a_series(self):
        """The index starting three sessions late must not wipe out beta."""
        stock = self._closes(0, 120)
        index = self._closes(3, 120)

        stock_returns = _daily_log_returns(stock)
        index_returns = _daily_log_returns(index)
        shared = [d for d in stock_returns if d in index_returns]

        assert len(shared) >= MIN_OBSERVATIONS, (
            "a three-session offset must leave plenty of paired sessions"
        )

    def test_non_positive_closes_are_dropped(self):
        import datetime as dt

        closes = {
            dt.date(2026, 1, 2): 100.0,
            dt.date(2026, 1, 5): 0.0,
            dt.date(2026, 1, 6): 121.0,
        }
        out = _daily_log_returns(closes)
        # A zero close cannot produce a log return on either side of itself.
        assert dt.date(2026, 1, 5) not in out
        assert dt.date(2026, 1, 6) not in out

    def test_empty_series(self):
        assert _daily_log_returns({}) == {}
