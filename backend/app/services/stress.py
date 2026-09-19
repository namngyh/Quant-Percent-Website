"""Bad-day measurements: crises replayed, liquidity, and a risk budget.

Everything here is measured, not modelled, and the one parameter is named.

* **Crisis replay.** The covariance the page uses is estimated on the last
  year, and correlations rise in a sell-off — the very moment the figure
  matters. Rather than push them up by some chosen amount, the book is
  re-measured on the actual sessions of past falls: the same holdings, the
  same weights, the prices of 2008, 2018, 2020 and 2022. What happened is
  the estimate. A holding not yet listed then is left out and the page says
  how much of the book the replay covers.

* **No-diversification bound.** With every correlation at one, portfolio
  volatility is the weighted sum of the holdings' own — an identity, not a
  scenario. It is the ceiling on what correlation can do.

* **Liquidity.** Days to sell a position at a share of its average daily
  volume. The share is the one parameter in this module; it is a constant
  here, stated on the page, because there is no data to estimate it from.

* **VaR check.** The 95% one-day VaR is compared with what the book then
  did, out of sample: at each session the VaR is estimated from the prior
  half-year only, and a breach is a return below it. Around one session in
  twenty is the expected rate.

* **Risk budget.** The reader's own limit — a loss they would not accept —
  set against the realised and replayed falls above and, where the index
  run allows, against the probability of reaching it within the horizon.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.portfolio import (
    CrisisScenario,
    LiquiditySummary,
    RiskBudget,
    RiskBudgetInput,
    StressReport,
    VarCheck,
)

TRADING_DAYS = 252

# Peak-to-trough windows of the four largest VN-Index falls in the data.
# Fixed dates rather than detected: the reader should recognise them.
CRISES: tuple[tuple[str, date, date], ...] = (
    ("gfc_2008", date(2008, 1, 2), date(2009, 2, 24)),
    ("y2018", date(2018, 4, 9), date(2018, 7, 11)),
    ("covid_2020", date(2020, 1, 22), date(2020, 3, 31)),
    ("y2022", date(2022, 4, 4), date(2022, 11, 16)),
)
# A replay needs enough sessions to say anything, and enough of the book.
MIN_CRISIS_SESSIONS = 20
MIN_CRISIS_COVERAGE = 0.5

# Share of a stock's average daily volume one seller can take without
# moving the price much. The one parameter in this module.
PARTICIPATION = 0.20
ADV_SESSIONS = 20
# Above this many sessions to exit, a position is called slow to sell.
SLOW_DAYS = 5.0

# VaR check: estimate on this many prior sessions, test on the next.
VAR_CHECK_WINDOW = 126


# ---------------------------------------------------------------------------
# Crisis replay
# ---------------------------------------------------------------------------


async def _load_window(
    session: AsyncSession, symbols: list[str], start: date, end: date
) -> dict[str, dict[date, float]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT symbol, trading_date, close
                FROM api.v_history_1d
                WHERE symbol = ANY(:symbols)
                  AND trading_date BETWEEN :start AND :end
                  AND close > 0
                ORDER BY symbol, trading_date
                """
            ),
            {"symbols": symbols, "start": start, "end": end},
        )
    ).mappings().all()
    out: dict[str, dict[date, float]] = {}
    for r in rows:
        out.setdefault(r["symbol"], {})[r["trading_date"]] = float(r["close"])
    return out


def replay(
    closes: dict[str, dict[date, float]],
    symbols: list[str],
    weights: np.ndarray,
    index_closes: dict[date, float],
) -> tuple[dict[str, float], list[str], int] | None:
    """Re-measure the book on one window's prices.

    Returns (figures, covered symbols, sessions) or None when too little of
    the book traded through the window. Weights of the covered holdings are
    renormalised so the figures describe a full book of what was listed.
    """
    covered = [s for s in symbols if len(closes.get(s, {})) >= MIN_CRISIS_SESSIONS]
    if not covered:
        return None
    idx = [symbols.index(s) for s in covered]
    w = weights[idx]
    if w.sum() <= 0:
        return None
    w = w / w.sum()

    common = set(closes[covered[0]])
    for s in covered[1:]:
        common &= set(closes[s])
    dates = sorted(common)
    if len(dates) < MIN_CRISIS_SESSIONS:
        return None
    prices = np.array([[closes[s][d] for s in covered] for d in dates])
    rets = np.diff(np.log(prices), axis=0)
    port = rets @ w

    # Anchored at the starting value, so a fall on the first session of the
    # window is a drawdown from the peak the book entered it with.
    equity = np.exp(np.concatenate([[0.0], np.cumsum(port)]))
    peak = np.maximum.accumulate(equity)
    max_dd = float((equity / peak - 1.0).min())
    total = float(equity[-1] - 1.0)
    vol = float(port.std(ddof=1)) * math.sqrt(TRADING_DAYS)
    var_95 = float(np.percentile(port, 5))
    tail = port[port <= var_95]
    es_95 = float(tail.mean()) if tail.size else var_95

    corr = np.corrcoef(rets, rowvar=False) if len(covered) > 1 else np.ones((1, 1))
    off = ~np.eye(len(covered), dtype=bool)
    avg_corr = float(corr[off].mean()) if off.any() else 1.0

    # The index over the same dates, for the reader to compare against.
    idx_dates = [d for d in dates if d in index_closes]
    if len(idx_dates) >= 2:
        ip = np.array([index_closes[d] for d in idx_dates])
        ipeak = np.maximum.accumulate(ip)
        index_dd = float((ip / ipeak - 1.0).min())
    else:
        index_dd = 0.0

    return (
        {
            "total_return": round(total, 6),
            "max_drawdown": round(max_dd, 6),
            "volatility": round(vol, 6),
            "var_95": round(var_95, 6),
            "expected_shortfall_95": round(es_95, 6),
            "average_correlation": round(avg_corr, 4),
            "index_max_drawdown": round(index_dd, 6),
        },
        covered,
        int(port.size),
    )


async def crisis_scenarios(
    session: AsyncSession,
    symbols: list[str],
    weights: np.ndarray,
) -> list[CrisisScenario]:
    out: list[CrisisScenario] = []
    for key, start, end in CRISES:
        closes = await _load_window(session, [*symbols, "VNINDEX"], start, end)
        index_closes = closes.pop("VNINDEX", {})
        result = replay(closes, symbols, weights, index_closes)
        if result is None:
            continue
        figures, covered, sessions = result
        covered_weight = float(weights[[symbols.index(s) for s in covered]].sum())
        if covered_weight < MIN_CRISIS_COVERAGE:
            continue
        out.append(
            CrisisScenario(
                key=key,
                start=start,
                end=end,
                sessions=sessions,
                covered=covered,
                covered_weight=round(covered_weight, 6),
                **figures,
            )
        )
    return out


def no_diversification(weights: np.ndarray, asset_vol: np.ndarray) -> float:
    """Portfolio volatility if every correlation were one."""
    return float((weights * asset_vol).sum())


# ---------------------------------------------------------------------------
# Liquidity
# ---------------------------------------------------------------------------


async def average_volumes(
    session: AsyncSession, symbols: list[str]
) -> dict[str, float]:
    """Mean volume over each symbol's last `ADV_SESSIONS` sessions."""
    rows = (
        await session.execute(
            text(
                """
                SELECT symbol, avg(volume) AS adv
                FROM (
                    SELECT symbol, volume,
                           row_number() OVER (
                               PARTITION BY symbol ORDER BY trading_date DESC
                           ) AS rn
                    FROM api.v_history_1d
                    WHERE symbol = ANY(:symbols) AND volume IS NOT NULL
                ) ranked
                WHERE rn <= :n
                GROUP BY symbol
                """
            ),
            {"symbols": symbols, "n": ADV_SESSIONS},
        )
    ).mappings().all()
    return {r["symbol"]: float(r["adv"]) for r in rows if r["adv"]}


def days_to_sell(quantity: float, adv: float | None) -> float | None:
    if adv is None or adv <= 0:
        return None
    return round(quantity / (PARTICIPATION * adv), 2)


def liquidity_summary(
    symbols: list[str], weights: np.ndarray, days: dict[str, float | None]
) -> LiquiditySummary:
    slow = [s for s in symbols if (days.get(s) or 0) > SLOW_DAYS]
    slow_weight = (
        float(weights[[symbols.index(s) for s in slow]].sum()) if slow else 0.0
    )
    known = [(s, d) for s, d in days.items() if d is not None]
    slowest = max(known, key=lambda x: x[1]) if known else None
    # Sessions to exit the whole book: the slowest position sets it.
    return LiquiditySummary(
        participation=PARTICIPATION,
        slow_days=SLOW_DAYS,
        slow=slow,
        slow_weight=round(slow_weight, 6),
        slowest_symbol=slowest[0] if slowest else None,
        slowest_days=slowest[1] if slowest else None,
        book_days=slowest[1] if slowest else None,
    )


# ---------------------------------------------------------------------------
# VaR check
# ---------------------------------------------------------------------------


def var_check(port_returns: np.ndarray) -> VarCheck | None:
    """Out-of-sample breach rate of the one-day 95% VaR."""
    n = port_returns.size
    if n <= VAR_CHECK_WINDOW + 10:
        return None
    breaches = 0
    tested = 0
    for t in range(VAR_CHECK_WINDOW, n):
        var_t = np.percentile(port_returns[t - VAR_CHECK_WINDOW : t], 5)
        tested += 1
        if port_returns[t] < var_t:
            breaches += 1
    return VarCheck(
        window=VAR_CHECK_WINDOW,
        tested=tested,
        breaches=breaches,
        breach_rate=round(breaches / tested, 6) if tested else 0.0,
        expected_rate=0.05,
    )


# ---------------------------------------------------------------------------
# Risk budget
# ---------------------------------------------------------------------------


def risk_budget(
    inp: RiskBudgetInput,
    *,
    horizon_days: int,
    measured_value: float,
    equity: float | None,
    realised_max_drawdown: float,
    crises: list[CrisisScenario],
    beta: float | None,
    exceedance: Callable[[float], float] | None,
    base_horizon_days: int,
    index_closes: np.ndarray,
    history_frequency: Callable[[np.ndarray, int, float], tuple[float | None, int]],
) -> RiskBudget:
    """The reader's limit against the falls this page measured.

    The limit is a share of the reader's own money — equity when there is a
    loan, the stock value otherwise — and every comparison is made on the
    same basis. `drop` is the fall in the stocks that spends the budget:
    with a loan that is the limit divided by leverage.
    """
    on_equity = equity is not None and equity > 0
    basis = equity if on_equity else measured_value
    limit_amount = inp.max_loss_pct * basis
    # A fall x in the stocks costs x·V of the basis; the budget is spent at
    # x = limit·basis/V.
    drop = (
        min(1.0, inp.max_loss_pct * basis / measured_value)
        if measured_value > 0
        else 1.0
    )

    def on_basis(stock_fraction: float) -> float:
        return stock_fraction * measured_value / basis if basis > 0 else 0.0

    realised = on_basis(abs(realised_max_drawdown))
    crisis_hits = [
        c.key for c in crises if on_basis(abs(c.max_drawdown)) > inp.max_loss_pct
    ]

    probability: float | None = None
    frequency: float | None = None
    if beta is not None and abs(beta) > 0:
        index_depth = drop / abs(beta)
        if exceedance is not None:
            probability = round(
                exceedance(index_depth / math.sqrt(horizon_days / base_horizon_days)), 6
            )
        frequency, _ = history_frequency(index_closes, horizon_days, index_depth)
        if frequency is not None:
            frequency = round(frequency, 6)

    return RiskBudget(
        max_loss_pct=inp.max_loss_pct,
        basis="equity" if on_equity else "portfolio",
        limit_amount=round(limit_amount, 2),
        drop_to_limit=round(drop, 6),
        drop_amount=round(drop * measured_value, 2),
        realised_max_loss=round(realised, 6),
        realised_within=realised <= inp.max_loss_pct,
        crisis_breaches=crisis_hits,
        hit_probability=probability,
        historical_frequency=frequency,
        horizon_days=horizon_days,
    )


__all__ = [
    "StressReport",
    "average_volumes",
    "crisis_scenarios",
    "days_to_sell",
    "liquidity_summary",
    "no_diversification",
    "risk_budget",
    "var_check",
]
