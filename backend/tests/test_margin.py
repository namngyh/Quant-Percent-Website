"""Tests for the margin block.

Every identity is checked against a hand-worked example, because the block
exists to show a reader arithmetic they cannot easily do themselves — a
wrong sign or a swapped numerator here would be presented as fact.

Worked example throughout: stocks 1,000m, cash 50m, loan 500m, 12%/year,
warning at 35%, forced sale at 30%.

    A = 1,050m   E = 550m   L = 1.9091   R = 0.52381
    fall to 35%: (1,050 - 500/0.65) / 1,000 = 0.28077
    fall to 30%: (1,050 - 500/0.70) / 1,000 = 0.33571
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.schemas.portfolio import MarginInput, MarginStatus
from app.services.margin import (
    HORIZONS,
    SCENARIO_DROPS,
    compute_margin,
    historical_frequency,
    rolling_max_drawdown,
)
from app.services.portfolio import _exceedance_at

BASE = 20
LIVE_CURVE = [(0.03, 0.62), (0.05, 0.41), (0.07, 0.27), (0.10, 0.14), (0.15, 0.05)]

M = 1_000_000.0


def _example(**overrides):
    kwargs = dict(
        stock_value=1_000 * M,
        cash=50 * M,
        measured_value=1_000 * M,
        var_95=-0.02,
        expected_shortfall_95=-0.03,
        max_drawdown=-0.18,
        beta=0.8,
        exceedance=lambda d: _exceedance_at(LIVE_CURVE, d),
        base_horizon_days=BASE,
        index_closes=_index(),
    )
    kwargs.update(overrides)
    inp = kwargs.pop("inp", _loan(500 * M))
    return compute_margin(inp, **kwargs)


def _loan(debt: float) -> MarginInput:
    """The worked example's thresholds, independent of the schema defaults."""
    return MarginInput(debt=debt, rate=0.12, call_ratio=0.35, force_ratio=0.30)


def _index(n: int = 2_000, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100.0 * np.exp(np.cumsum(rng.standard_normal(n) * 0.012))


class TestIdentities:
    def test_balance_sheet(self):
        m = _example()
        assert m.assets == pytest.approx(1_050 * M)
        assert m.equity == pytest.approx(550 * M)
        assert m.leverage == pytest.approx(1050 / 550, rel=1e-4)
        assert m.margin_ratio == pytest.approx(550 / 1050, rel=1e-5)
        assert m.status is MarginStatus.above_call

    def test_distances(self):
        m = _example()
        assert m.distance_to_call.drop == pytest.approx(0.28077, abs=1e-5)
        assert m.distance_to_call.amount == pytest.approx(280.77 * M, rel=1e-4)
        assert m.distance_to_force.drop == pytest.approx(0.33571, abs=1e-5)
        # Forced sale is always further away than the warning.
        assert m.distance_to_force.drop > m.distance_to_call.drop

    def test_distance_is_a_fall_in_stocks_not_assets(self):
        """Cash does not fall, so the fall is measured on the stocks alone.

        With no cash the two coincide; with cash the stocks must fall further
        than a naive 1 - A_critical/A suggests.
        """
        no_cash = _example(cash=0.0)
        assert no_cash.distance_to_call.drop == pytest.approx(
            1 - (500 / 0.65) / 1_000, abs=1e-5
        )
        with_cash = _example(cash=200 * M)
        assert with_cash.distance_to_call.drop > no_cash.distance_to_call.drop

    def test_idle_cash_costs_the_rate(self):
        m = _example()
        assert m.idle_cash_cost_per_year == pytest.approx(50 * M * 0.12)
        assert _example(cash=0.0).idle_cash_cost_per_year is None
        # Cash beyond the loan is not borrowed money.
        assert _example(cash=900 * M).idle_cash_cost_per_year == pytest.approx(
            500 * M * 0.12
        )

    def test_equity_risk_is_scaled_by_leverage_on_the_measured_part(self):
        m = _example()
        # 2% of 1,000m measured, against 550m of equity.
        assert m.equity_var_95 == pytest.approx(-0.02 * 1_000 / 550, abs=1e-6)
        assert m.equity_max_drawdown == pytest.approx(-0.18 * 1_000 / 550, abs=1e-6)
        # Only the measured part carries a VaR; an unmeasured position adds
        # to equity but not to the loss figure.
        wider = _example(stock_value=1_200 * M)
        assert abs(wider.equity_var_95) < abs(m.equity_var_95)


class TestStatus:
    def test_between_thresholds(self):
        # 1,000 stocks + 0 cash - 680 debt: R = 0.32
        m = _example(cash=0.0, inp=_loan(680 * M))
        assert m.status is MarginStatus.between
        assert m.distance_to_call.drop == 0.0
        assert m.distance_to_force.drop > 0

    def test_below_force(self):
        m = _example(cash=0.0, inp=_loan(750 * M))
        assert m.status is MarginStatus.below_force
        assert m.distance_to_force.drop == 0.0

    def test_negative_equity(self):
        m = _example(cash=0.0, inp=_loan(1_200 * M))
        assert m.status is MarginStatus.negative_equity
        assert m.leverage is None
        assert m.equity_var_95 is None
        assert all(h.interest_pct_equity is None for h in m.by_horizon)

    def test_cash_only_account(self):
        m = _example(stock_value=0.0, measured_value=0.0, cash=600 * M)
        assert m.distance_to_call is None
        assert all(h.breakeven_return is None for h in m.by_horizon)
        # Interest is still owed.
        assert m.by_horizon[-1].interest == pytest.approx(500 * M * 0.12)


class TestHorizons:
    def test_grid(self):
        m = _example()
        assert [h.horizon_days for h in m.by_horizon] == list(HORIZONS)

    def test_interest_is_linear_in_time(self):
        m = _example()
        year = m.by_horizon[-1]
        assert year.interest == pytest.approx(500 * M * 0.12)
        assert year.interest_pct_equity == pytest.approx(60 / 550, rel=1e-5)
        assert year.breakeven_return == pytest.approx(60 / 1_000, rel=1e-5)
        month = m.by_horizon[0]
        assert month.interest == pytest.approx(year.interest * 21 / 252)

    def test_probability_rises_with_horizon(self):
        probs = [h.hit_call_probability for h in _example().by_horizon]
        assert all(p is not None for p in probs)
        assert probs == sorted(probs)
        assert probs[0] < probs[-1]

    def test_probability_matches_forward_panel_transformation(self):
        """The margin block must not invent its own scaling."""
        m = _example()
        depth = m.distance_to_call.drop / 0.8
        for h in m.by_horizon:
            scale = math.sqrt(h.horizon_days / BASE)
            expected = _exceedance_at(LIVE_CURVE, depth / scale)
            assert h.hit_call_probability == pytest.approx(expected, abs=1e-6)

    def test_without_beta_nothing_is_scaled(self):
        m = _example(beta=None)
        for h in m.by_horizon:
            assert h.hit_call_probability is None
            assert h.historical_frequency is None
            assert h.historical_windows == 0
            # Interest does not need beta.
            assert h.interest > 0

    def test_without_a_run_history_still_answers(self):
        m = _example(exceedance=None)
        for h in m.by_horizon:
            assert h.hit_call_probability is None
            assert h.historical_frequency is not None
            assert h.historical_windows > 0

    def test_already_past_threshold_is_certain(self):
        m = _example(cash=0.0, inp=_loan(680 * M))
        for h in m.by_horizon:
            assert h.hit_call_probability == pytest.approx(1.0)
            assert h.historical_frequency == pytest.approx(1.0)


class TestScenarios:
    def test_grid_and_arithmetic(self):
        m = _example()
        assert [s.drop for s in m.scenarios] == list(SCENARIO_DROPS)
        twenty = next(s for s in m.scenarios if s.drop == 0.20)
        assert twenty.assets == pytest.approx(800 * M + 50 * M)
        assert twenty.equity == pytest.approx(350 * M)
        assert twenty.margin_ratio == pytest.approx(350 / 850, rel=1e-5)
        assert twenty.status is MarginStatus.above_call
        assert twenty.top_up == 0.0

    def test_top_up_restores_the_warning_ratio(self):
        m = _example()
        thirty = next(s for s in m.scenarios if s.drop == 0.30)
        assert thirty.status is MarginStatus.between
        assert thirty.top_up > 0
        after = thirty.assets + thirty.top_up
        restored = (after - 500 * M) / after
        assert restored == pytest.approx(0.35, abs=1e-6)

    def test_statuses_only_get_worse_down_the_table(self):
        order = [
            MarginStatus.above_call,
            MarginStatus.between,
            MarginStatus.below_force,
            MarginStatus.negative_equity,
        ]
        ranks = [order.index(s.status) for s in _example().scenarios]
        assert ranks == sorted(ranks)


class TestRollingDrawdown:
    def test_against_brute_force(self):
        closes = _index(400)
        fast = rolling_max_drawdown(closes, 21)
        slow = []
        for i in range(closes.size - 21 + 1):
            w = closes[i : i + 21]
            slow.append(min(w[j] / w[: j + 1].max() - 1 for j in range(21)))
        assert fast == pytest.approx(np.array(slow))

    def test_window_longer_than_history(self):
        assert rolling_max_drawdown(np.arange(10.0), 21).size == 0
        assert historical_frequency(np.arange(10.0), 21, 0.1) == (None, 0)

    def test_frequency_is_monotone_in_depth_and_horizon(self):
        closes = _index(3_000)
        shallow, _ = historical_frequency(closes, 63, 0.05)
        deep, _ = historical_frequency(closes, 63, 0.20)
        assert shallow >= deep
        short, _ = historical_frequency(closes, 21, 0.10)
        long, _ = historical_frequency(closes, 252, 0.10)
        assert long >= short

    def test_monotonic_rise_never_falls(self):
        freq, n = historical_frequency(np.linspace(100, 200, 500), 63, 0.01)
        assert freq == 0.0
        assert n == 500 - 63 + 1


class TestInput:
    def test_force_must_be_below_call(self):
        with pytest.raises(ValueError):
            MarginInput(debt=1.0, call_ratio=0.30, force_ratio=0.35)

    def test_defaults_are_the_common_vietnamese_figures(self):
        inp = MarginInput(debt=1.0)
        assert (inp.rate, inp.call_ratio, inp.force_ratio) == (0.12, 0.30, 0.28)
