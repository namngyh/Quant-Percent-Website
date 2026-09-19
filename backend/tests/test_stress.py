"""Tests for the crisis replay, liquidity, VaR check and risk budget."""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pytest

from app.schemas.portfolio import CrisisScenario, RiskBudgetInput
from app.services.margin import historical_frequency
from app.services.stress import (
    PARTICIPATION,
    SLOW_DAYS,
    VAR_CHECK_WINDOW,
    days_to_sell,
    liquidity_summary,
    no_diversification,
    replay,
    risk_budget,
    var_check,
)


def _path(n: int, daily: float, start: dt.date) -> dict[dt.date, float]:
    """A close series drifting by `daily`, with a wobble so it has variance."""
    out, level = {}, 100.0
    for i in range(n):
        out[start + dt.timedelta(days=i)] = level
        level *= 1 + daily * (1 + 0.5 * math.sin(i))
    return out


class TestReplay:
    def test_fall_is_measured_on_the_book(self):
        start = dt.date(2020, 1, 22)
        closes = {"A": _path(40, -0.01, start), "B": _path(40, -0.02, start)}
        index = _path(40, -0.015, start)
        figures, covered, sessions = replay(
            closes, ["A", "B"], np.array([0.5, 0.5]), index
        )
        assert covered == ["A", "B"]
        assert sessions == 39
        # A monotonic fall: the drawdown is the whole move.
        assert figures["max_drawdown"] == pytest.approx(
            figures["total_return"], abs=1e-6
        )
        assert figures["max_drawdown"] < -0.3
        assert figures["index_max_drawdown"] < -0.3
        # B's log returns are a multiple of A's: correlation one.
        assert figures["average_correlation"] == pytest.approx(1.0, abs=1e-3)

    def test_unlisted_holding_is_left_out_and_weights_renormalised(self):
        start = dt.date(2020, 1, 22)
        closes = {"A": _path(40, -0.01, start), "B": {}}
        f1, covered, _ = replay(closes, ["A", "B"], np.array([0.3, 0.7]), {})
        assert covered == ["A"]
        f2, _, _ = replay({"A": _path(40, -0.01, start)}, ["A"], np.array([1.0]), {})
        # Same book once B is dropped and A renormalised to 100%.
        assert f1["max_drawdown"] == pytest.approx(f2["max_drawdown"])

    def test_too_few_sessions(self):
        closes = {"A": _path(5, -0.01, dt.date(2020, 1, 22))}
        assert replay(closes, ["A"], np.array([1.0]), {}) is None


class TestNoDiversification:
    def test_is_weighted_sum_of_vols(self):
        got = no_diversification(np.array([0.5, 0.5]), np.array([0.2, 0.4]))
        assert got == pytest.approx(0.3)

    def test_never_below_any_correlated_estimate(self):
        w = np.array([0.6, 0.4])
        vols = np.array([0.3, 0.2])
        corr = np.array([[1, 0.3], [0.3, 1]])
        cov = np.outer(vols, vols) * corr
        assert no_diversification(w, vols) >= math.sqrt(w @ cov @ w)


class TestLiquidity:
    def test_days(self):
        expected = 10_000 / (PARTICIPATION * 100_000)
        assert days_to_sell(10_000, 100_000) == pytest.approx(expected)
        assert days_to_sell(10_000, None) is None
        assert days_to_sell(10_000, 0) is None

    def test_summary(self):
        days = {"A": 0.5, "B": 12.0, "C": None}
        s = liquidity_summary(["A", "B", "C"], np.array([0.5, 0.3, 0.2]), days)
        assert s.slow == ["B"]
        assert s.slow_weight == pytest.approx(0.3)
        assert s.slowest_symbol == "B" and s.slowest_days == 12.0
        assert s.book_days == 12.0
        assert s.participation == PARTICIPATION and s.slow_days == SLOW_DAYS

    def test_all_liquid(self):
        s = liquidity_summary(["A"], np.array([1.0]), {"A": 0.2})
        assert s.slow == [] and s.slow_weight == 0.0


class TestVarCheck:
    def test_normal_returns_breach_about_five_percent(self):
        rng = np.random.default_rng(3)
        r = rng.standard_normal(2_000) * 0.01
        c = var_check(r)
        assert c is not None
        assert c.tested == 2_000 - VAR_CHECK_WINDOW
        assert 0.03 < c.breach_rate < 0.08

    def test_too_short(self):
        assert var_check(np.zeros(100)) is None

    def test_fat_left_tail_breaches_more(self):
        rng = np.random.default_rng(4)
        calm = rng.standard_normal(1_000) * 0.01
        # A crash in the second half that the first-half VaR never saw.
        shocked = calm.copy()
        shocked[600:] -= 0.02
        assert var_check(shocked).breach_rate > var_check(calm).breach_rate


class TestRiskBudget:
    CURVE = [(0.03, 0.62), (0.05, 0.41), (0.07, 0.27), (0.10, 0.14), (0.15, 0.05)]

    def _crisis(self, key: str, dd: float) -> CrisisScenario:
        return CrisisScenario(
            key=key,
            start=dt.date(2020, 1, 22),
            end=dt.date(2020, 3, 31),
            sessions=40,
            covered=["A"],
            covered_weight=1.0,
            total_return=dd,
            max_drawdown=dd,
            volatility=0.3,
            var_95=-0.03,
            expected_shortfall_95=-0.04,
            average_correlation=0.5,
            index_max_drawdown=dd,
        )

    def _budget(self, **kw):
        from app.services.portfolio import _exceedance_at

        args = dict(
            horizon_days=63,
            measured_value=1_000.0,
            equity=None,
            realised_max_drawdown=-0.12,
            crises=[self._crisis("covid_2020", -0.30), self._crisis("y2022", -0.08)],
            beta=1.0,
            exceedance=lambda d: _exceedance_at(self.CURVE, d),
            base_horizon_days=20,
            index_closes=np.exp(
                np.cumsum(np.random.default_rng(1).standard_normal(800) * 0.012)
            ),
            history_frequency=historical_frequency,
        )
        args.update(kw)
        return risk_budget(RiskBudgetInput(max_loss_pct=0.15), **args)

    def test_without_loan_basis_is_portfolio(self):
        b = self._budget()
        assert b.basis == "portfolio"
        assert b.limit_amount == pytest.approx(150.0)
        assert b.drop_to_limit == pytest.approx(0.15)
        assert b.realised_max_loss == pytest.approx(0.12)
        assert b.realised_within is True
        assert b.crisis_breaches == ["covid_2020"]
        assert b.hit_probability is not None and 0 < b.hit_probability < 1
        assert b.historical_frequency is not None

    def test_with_loan_leverage_shrinks_the_drop(self):
        """15% of 500 equity is 75; the stocks need only fall 7.5%."""
        b = self._budget(equity=500.0)
        assert b.basis == "equity"
        assert b.limit_amount == pytest.approx(75.0)
        assert b.drop_to_limit == pytest.approx(0.075)
        # The realised 12% stock fall is 24% of equity: over budget.
        assert b.realised_max_loss == pytest.approx(0.24)
        assert b.realised_within is False
        assert set(b.crisis_breaches) == {"covid_2020", "y2022"}

    def test_without_beta_no_probability(self):
        b = self._budget(beta=None)
        assert b.hit_probability is None and b.historical_frequency is None
        assert b.drop_to_limit == pytest.approx(0.15)
