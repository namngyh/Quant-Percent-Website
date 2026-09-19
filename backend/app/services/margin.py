"""Margin risk: the portfolio seen from the reader's own money.

Every figure here is arithmetic on numbers the portfolio service already
produced plus the loan the reader typed in. There is no model of the broker,
no assumed return, and no score. The one estimate is the probability of
reaching the warning threshold within a horizon, and it is served next to the
historical frequency of the same fall so the reader can see how far the two
agree.

The identities, with V the stock value, C cash and D the loan:

    A = V + C           assets
    E = A - D           equity, the reader's own money
    L = A / E           leverage: a 10% fall in the stocks is a 10%·L·V/A
                        fall in equity
    R = E / A           margin ratio, simple form

Brokers compute R on collateral discounted stock by stock, which is always
lower than this, so every distance below is optimistic and the page says so.

Only the stocks fall in a scenario; cash keeps its value. The ratio reaches a
threshold m when A' = D / (1 - m), so the fall in the stocks that gets there
is x = (A - D/(1-m)) / V.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.portfolio import (
    MarginDistance,
    MarginHorizon,
    MarginInput,
    MarginRisk,
    MarginScenario,
    MarginStatus,
)

TRADING_DAYS = 252
INDEX = "VNINDEX"

# The four holding periods the form offers. The table shows all of them at
# once: the point is the comparison, not any one row.
HORIZONS = (21, 63, 126, 252)

# Falls in the stocks for the scenario table. A fixed grid, for the same
# reason the forward panel uses one: the reader compares two books, or one
# book before and after a change, against the same rows.
SCENARIO_DROPS = (0.05, 0.10, 0.15, 0.20, 0.30)

# Plausibility checks on what was typed. None of these blocks the analysis:
# a reader who really is here deserves the numbers, and one who mistyped
# deserves to be told where to look. Each fires on a concrete condition.
#
#   debt_exceeds_stocks   A brokerage margin loan cannot exceed the stock it
#                         is secured on — initial margin is at most 50% — so
#                         either a zero was added, or the loan is not from
#                         the broker (see `MarginInput.external`).
#   already_past_threshold The ratio entered is already below the warning
#                         level. A broker would have acted; the page shows
#                         the balance sheet but not the odds of reaching a
#                         line the account is already past.
#   high_leverage         Assets above twice equity: beyond what brokerage
#                         margin normally allows, and worth a second look.
#   rate_unusual          Below 5% or above 25% a year is outside the range
#                         Vietnamese brokers charge on margin.
WARNINGS = (
    "debt_exceeds_stocks",
    "already_past_threshold",
    "high_leverage",
    "rate_unusual",
)
HIGH_LEVERAGE = 2.0
RATE_RANGE = (0.05, 0.25)


def _status(ratio: float, equity: float, inp: MarginInput) -> MarginStatus:
    if equity <= 0:
        return MarginStatus.negative_equity
    if inp.external:
        return MarginStatus.no_thresholds
    if ratio <= inp.force_ratio:
        return MarginStatus.below_force
    if ratio <= inp.call_ratio:
        return MarginStatus.between
    return MarginStatus.above_call


def _distance(
    assets: float, stock_value: float, debt: float, threshold: float
) -> MarginDistance | None:
    """Fall in the stocks that brings the ratio down to `threshold`."""
    if stock_value <= 0:
        return None
    drop = (assets - debt / (1.0 - threshold)) / stock_value
    drop = min(max(drop, 0.0), 1.0)
    return MarginDistance(drop=round(drop, 6), amount=round(drop * stock_value, 2))


def rolling_max_drawdown(closes: np.ndarray, window: int) -> np.ndarray:
    """Deepest peak-to-trough fall inside every window of `window` sessions.

    One value per window start. The peak is taken inside the window, so a
    window that opens at a high and slides down reports the whole slide,
    and one that opens after a crash reports only what it saw.
    """
    if closes.size < window:
        return np.empty(0)
    windows = sliding_window_view(closes, window)
    peaks = np.maximum.accumulate(windows, axis=1)
    return (windows / peaks - 1.0).min(axis=1)


def historical_frequency(
    closes: np.ndarray, window: int, depth: float
) -> tuple[float | None, int]:
    """Share of `window`-session windows in which the index fell >= `depth`."""
    mdd = rolling_max_drawdown(closes, window)
    if mdd.size == 0:
        return None, 0
    if depth <= 0:
        return 1.0, int(mdd.size)
    return float((mdd <= -depth).mean()), int(mdd.size)


async def load_index_history(session: AsyncSession) -> np.ndarray:
    """Every VN-Index close the database holds, oldest first.

    About 6,300 rows since 2000. Read in full on each request: the frequency
    lookup needs a window at every possible start, and the query is a single
    index scan that costs less than the covariance shrinkage it sits next to.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT close
                FROM api.v_history_1d
                WHERE symbol = :symbol AND close > 0
                ORDER BY trading_date
                """
            ),
            {"symbol": INDEX},
        )
    ).scalars().all()
    return np.asarray([float(c) for c in rows], dtype=float)


def compute_margin(
    inp: MarginInput,
    *,
    stock_value: float,
    cash: float,
    measured_value: float,
    var_95: float,
    expected_shortfall_95: float,
    max_drawdown: float,
    beta: float | None,
    exceedance: Callable[[float], float] | None,
    base_horizon_days: int,
    index_closes: np.ndarray,
) -> MarginRisk:
    """Pure: everything comes in as numbers, nothing is fetched.

    `exceedance(depth)` is the forward panel's probability that the *index*
    falls at least `depth` over the simulation's `base_horizon_days`,
    already anchored and interpolated; None when no run is loaded.
    `measured_value` is the part of the book the realised risk figures
    describe, which is what those percentages are converted to money
    against.
    """
    assets = stock_value + cash
    equity = assets - inp.debt
    ratio = equity / assets if assets > 0 else 0.0
    status = _status(ratio, equity, inp)
    leverage = assets / equity if equity > 0 else None

    to_call = None
    to_force = None
    if not inp.external:
        to_call = _distance(assets, stock_value, inp.debt, inp.call_ratio)
        to_force = _distance(assets, stock_value, inp.debt, inp.force_ratio)

    warnings: list[str] = []
    if not inp.external and inp.debt > stock_value:
        warnings.append("debt_exceeds_stocks")
    if status in (MarginStatus.between, MarginStatus.below_force):
        warnings.append("already_past_threshold")
    if leverage is not None and leverage > HIGH_LEVERAGE:
        warnings.append("high_leverage")
    if not RATE_RANGE[0] <= inp.rate <= RATE_RANGE[1]:
        warnings.append("rate_unusual")

    # Cash held while paying interest on a loan of at least that size is
    # borrowing money to leave it idle. Reported as a yearly cost; the reader
    # may have a reason, but they should see the price of it.
    idle = min(cash, inp.debt) * inp.rate if cash > 0 else None

    abs_beta = abs(beta) if beta is not None else None
    can_scale = abs_beta is not None and abs_beta > 0 and to_call is not None

    by_horizon: list[MarginHorizon] = []
    for h in HORIZONS:
        interest = inp.debt * inp.rate * h / TRADING_DAYS
        probability: float | None = None
        frequency: float | None = None
        windows = 0
        if can_scale:
            assert to_call is not None and abs_beta is not None
            # The book's fall to the threshold, as a fall in the index.
            index_depth = to_call.drop / abs_beta
            if exceedance is not None:
                # Same transformation as the forward panel: ask the base-
                # horizon run about a proportionally shallower fall.
                scale = math.sqrt(h / base_horizon_days)
                probability = round(exceedance(index_depth / scale), 6)
            frequency, windows = historical_frequency(index_closes, h, index_depth)
            if frequency is not None:
                frequency = round(frequency, 6)
        by_horizon.append(
            MarginHorizon(
                horizon_days=h,
                hit_call_probability=probability,
                historical_frequency=frequency,
                historical_windows=windows,
                interest=round(interest, 2),
                interest_pct_equity=(
                    round(interest / equity, 6) if equity > 0 else None
                ),
                breakeven_return=(
                    round(interest / stock_value, 6) if stock_value > 0 else None
                ),
            )
        )

    scenarios: list[MarginScenario] = []
    for drop in SCENARIO_DROPS:
        a = stock_value * (1.0 - drop) + cash
        e = a - inp.debt
        r = e / a if a > 0 else 0.0
        top_up = (
            0.0 if inp.external else max(0.0, inp.debt / (1.0 - inp.call_ratio) - a)
        )
        scenarios.append(
            MarginScenario(
                drop=drop,
                assets=round(a, 2),
                equity=round(e, 2),
                margin_ratio=round(r, 6),
                status=_status(r, e, inp),
                top_up=round(top_up, 2),
            )
        )

    # Realised risk on equity: the money at risk is measured on the part of
    # the book that was measured, and the reader's cushion is their equity.
    def on_equity(fraction: float) -> float | None:
        if equity <= 0:
            return None
        return round(fraction * measured_value / equity, 6)

    return MarginRisk(
        assets=round(assets, 2),
        equity=round(equity, 2),
        debt=inp.debt,
        rate=inp.rate,
        call_ratio=inp.call_ratio,
        force_ratio=inp.force_ratio,
        external=inp.external,
        leverage=round(leverage, 4) if leverage is not None else None,
        margin_ratio=round(ratio, 6),
        status=status,
        warnings=warnings,
        distance_to_call=to_call,
        distance_to_force=to_force,
        idle_cash_cost_per_year=round(idle, 2) if idle is not None else None,
        equity_var_95=on_equity(var_95),
        equity_expected_shortfall_95=on_equity(expected_shortfall_95),
        equity_max_drawdown=on_equity(max_drawdown),
        by_horizon=by_horizon,
        scenarios=scenarios,
    )

