"""Portfolio analytics.

The whole module works on one principle: every number returned is either
measured from price history this database holds, or it is omitted. There is no
assumed return, no assumed correlation, no filler value. A position whose
history is too short to measure is reported in `unpriced` instead of being
given a plausible-looking number.

Risk contribution is the part worth reading closely. A position's share of
portfolio risk is not its share of the money — it is
    w_i * (Sigma w)_i / (w' Sigma w)
which accounts for how the position moves with everything else. A stock that
is 25% of the money but moves with the rest of the book can easily be 45% of
the risk, and that gap is the single most useful thing this endpoint reports.

Covariance uses Ledoit-Wolf shrinkage towards a constant-correlation target.
With ~250 observations and 10-30 names the sample covariance is badly
conditioned, and the inverse it feeds is worse; shrinkage is the standard fix
and it is applied here rather than left as a refinement.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.freshness import build_freshness
from app.schemas.common import RiskState
from app.schemas.portfolio import (
    Concentration,
    DrawdownBucket,
    ForwardRisk,
    Holding,
    PortfolioAnalysis,
    PortfolioRequest,
    PositionRisk,
)

TRADING_DAYS = 252
BENCHMARK = "VNINDEX"

# HOSE quotes stocks in thousands of dong, and the feed stores them that way:
# VIC closes at 218.8, meaning 218,800 VND. A reader entering a cost basis of
# 120000 and cash of 50000000 is working in dong, so prices are converted to
# dong before anything is added to anything else. Without this the profit
# figure comes out near -100% on any portfolio that has a cost basis at all.
PRICE_UNIT_VND = 1_000

# A position needs enough observations for its volatility and its correlation
# with the rest of the book to mean anything. Sixty sessions is about a
# quarter; below that the estimate is noise dressed as a number.
MIN_OBSERVATIONS = 60

# The RARF-FHE Monte-Carlo run simulates a fixed 20-session path
# (`models/rarf-fhe/configs/default.yaml`, `simulation.horizon`). That length is
# not carried on `quant.risk_metrics`, so it is pinned here: every number the
# run publishes — VaR, expected shortfall, the drawdown curve — describes 20
# sessions and nothing else. If the run's config changes, this changes with it.
MC_BASE_HORIZON_DAYS = 20

# Drawdown levels the forward panel reports, as falls in this portfolio.
#
# Fixed rather than derived from beta. When the thresholds move with the book,
# every portfolio produces the same curve at slightly different x-labels and
# the panel cannot be read — which is exactly the failure this replaces. Fixing
# the axis puts the variation where a reader can see it: in the probabilities.
#
# The grid runs to 30% because the shallow end saturates over a long horizon: a
# 3% fall sometime in a year is near certain, so a 3-10% grid draws a flat line
# just under 100% and says nothing. Out to 30% the curve keeps a readable
# spread at every horizon the form offers.
DRAWDOWN_THRESHOLDS = (0.03, 0.05, 0.07, 0.10, 0.15, 0.20, 0.30)

# A beta this small means the book barely tracks the index, and dividing by it
# would turn rounding noise into a lookup thousands of percent deep.
MIN_BETA_FOR_SCALING = 0.05


async def _load_closes(
    session: AsyncSession, symbols: list[str], lookback: int
) -> dict[str, dict[date, float]]:
    """Daily closes per symbol, most recent `lookback` sessions."""
    if not symbols:
        return {}
    rows = (
        await session.execute(
            text(
                """
                SELECT symbol, trading_date, close
                FROM (
                    SELECT symbol, trading_date, close,
                           row_number() OVER (
                               PARTITION BY symbol ORDER BY trading_date DESC
                           ) AS rn
                    FROM api.v_history_1d
                    WHERE symbol = ANY(:symbols)
                ) ranked
                WHERE rn <= :lookback
                ORDER BY symbol, trading_date
                """
            ),
            {"symbols": symbols, "lookback": lookback},
        )
    ).mappings().all()

    out: dict[str, dict[date, float]] = {}
    for r in rows:
        close = r["close"]
        if close is None or float(close) <= 0:
            continue
        out.setdefault(r["symbol"], {})[r["trading_date"]] = float(close)
    return out


async def _load_sectors(
    session: AsyncSession, symbols: list[str]
) -> dict[str, str]:
    rows = (
        await session.execute(
            text(
                "SELECT symbol, sector FROM web.symbols "
                "WHERE symbol = ANY(:symbols) AND sector IS NOT NULL"
            ),
            {"symbols": symbols},
        )
    ).mappings().all()
    return {r["symbol"]: r["sector"] for r in rows}


def _aligned_returns(
    closes: dict[str, dict[date, float]], symbols: list[str]
) -> tuple[list[date], np.ndarray]:
    """Log returns on the dates every symbol traded.

    Intersecting rather than forward-filling: a filled price produces a
    zero return, which drags measured volatility down and correlation up.
    Both errors flatter the portfolio, so neither is acceptable here.
    """
    if not symbols:
        return [], np.empty((0, 0))
    common = set(closes[symbols[0]])
    for s in symbols[1:]:
        common &= set(closes[s])
    dates = sorted(common)
    if len(dates) < 2:
        return dates, np.empty((0, len(symbols)))

    prices = np.array([[closes[s][d] for s in symbols] for d in dates])
    returns = np.diff(np.log(prices), axis=0)
    return dates[1:], returns


def _ledoit_wolf(returns: np.ndarray) -> np.ndarray:
    """Sample covariance shrunk towards a constant-correlation target.

    Ledoit and Wolf (2004), including the `rho` term. Dropping rho — the
    usual shortcut — inflates the shrinkage intensity, and on real VN daily
    returns it saturates at 1.0: every correlation collapses onto the mean
    and the matrix loses exactly the structure this endpoint exists to find.
    A basket of names that all move together has to stay distinguishable
    from a basket that does not.

    Returns the sample covariance unchanged when there is one asset, too few
    rows, or a target that already matches the sample.
    """
    n_obs, n_assets = returns.shape
    if n_assets < 2 or n_obs < 3:
        return np.cov(returns, rowvar=False, ddof=1).reshape(n_assets, n_assets)

    # 1/n throughout, so the sample matrix, pi, rho and gamma are all on the
    # same footing; the estimator is defined that way.
    centred = returns - returns.mean(axis=0)
    sample = centred.T @ centred / n_obs
    var = np.diag(sample)
    std = np.sqrt(var)
    outer_std = np.outer(std, std)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.where(outer_std > 0, sample / outer_std, 0.0)
    off = ~np.eye(n_assets, dtype=bool)
    mean_corr = float(corr[off].mean())

    target = mean_corr * outer_std
    np.fill_diagonal(target, var)

    gamma = float(((target - sample) ** 2).sum())
    if gamma <= 0:
        return sample

    squared = centred**2
    # pi_ij = Var of the sample second moment.
    pi_matrix = (squared.T @ squared) / n_obs - sample**2
    pi = float(pi_matrix.sum())

    # theta_ii_ij = Cov(sample_ii, sample_ij), and its transpose for jj.
    cubed_cross = (centred**3).T @ centred / n_obs
    theta_ii = cubed_cross - var[:, None] * sample
    theta_jj = cubed_cross.T - var[None, :] * sample

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(outer_std > 0, std[None, :] / std[:, None], 0.0)
    cross = 0.5 * mean_corr * (ratio * theta_ii + (1.0 / np.where(ratio == 0, np.inf, ratio)) * theta_jj)
    rho = float(np.trace(pi_matrix) + cross[off].sum())

    intensity = max(0.0, min(1.0, (pi - rho) / gamma / n_obs))
    return intensity * target + (1.0 - intensity) * sample


def _max_drawdown(series: np.ndarray) -> float:
    """Largest peak-to-trough fall of a cumulative return path."""
    if series.size == 0:
        return 0.0
    equity = np.exp(np.cumsum(series))
    peak = np.maximum.accumulate(equity)
    return float((equity / peak - 1.0).min())


def _risk_state(volatility: float, drawdown: float) -> RiskState:
    """Grade a portfolio the same way /market/risk grades the index."""
    if volatility >= 0.35 or drawdown <= -0.25:
        return RiskState.high
    if volatility >= 0.25 or drawdown <= -0.15:
        return RiskState.elevated
    if volatility >= 0.15 or drawdown <= -0.08:
        return RiskState.moderate
    return RiskState.low


def _exceedance_at(curve: list[tuple[float, float]], depth: float) -> float:
    """Probability the index run gives a drawdown of at least `depth`.

    `curve` is the published (depth, probability) pairs with depth positive and
    ascending. It is anchored at (0, 1) before interpolating: a fall of at
    least nothing is certain, and without that anchor a long horizon — which
    pulls the lookup depth towards zero — has nothing on its left to
    interpolate against.

    Interpolation is linear in log-probability, which is how a tail decays.
    Interpolating the probability itself would overstate the middle of every
    segment. Past the deepest published point the last segment's slope is
    carried forward rather than the curve being cut off, because a high-beta
    book over a short horizon legitimately lands out there.
    """
    if depth <= 0:
        return 1.0
    if not curve:
        return 0.0

    points = [(0.0, 1.0), *curve]
    floor = 1e-9

    for (d_a, p_a), (d_b, p_b) in zip(points, points[1:], strict=False):
        if depth <= d_b:
            span = d_b - d_a
            if span <= 0:
                return max(0.0, min(1.0, p_b))
            t = (depth - d_a) / span
            log_p = math.log(max(p_a, floor)) + t * (
                math.log(max(p_b, floor)) - math.log(max(p_a, floor))
            )
            return max(0.0, min(1.0, math.exp(log_p)))

    # Beyond the deepest point: extend the final segment's decay.
    (d_a, p_a), (d_b, p_b) = points[-2], points[-1]
    span = d_b - d_a
    if span <= 0 or p_b <= 0:
        return 0.0
    slope = (math.log(max(p_b, floor)) - math.log(max(p_a, floor))) / span
    extended = math.exp(math.log(max(p_b, floor)) + slope * (depth - d_b))
    return max(0.0, min(1.0, extended))


async def _forward_risk(
    session: AsyncSession, beta: float | None, horizon_days: int
) -> ForwardRisk | None:
    """Map the published VN-Index Monte-Carlo run onto this portfolio.

    Two transformations, both stated on the response rather than folded in
    silently:

    * **Beta.** The book takes beta times the index's move, so a fall of `x`
      here corresponds to a fall of `x / beta` there.
    * **Square-root-of-time.** The run simulates a fixed 20 sessions. For a
      driftless diffusion the maximum drawdown over `t` sessions has the same
      distribution as the 20-session drawdown scaled by `sqrt(t / 20)`, so a
      63-session question is answered by asking the run about a proportionally
      shallower fall. It is a first-order approximation — it carries no drift
      and no volatility clustering — which is why the page names it.

    Together: P(this book falls >= x over t) = P(index falls >= x / beta /
    sqrt(t / 20) over 20). The thresholds stay fixed and the probabilities
    move, so two portfolios, or one portfolio over two horizons, can be read
    against the same axis.

    Returns None when no run is loaded, or when the book tracks the index too
    weakly for beta scaling to carry any meaning.
    """
    if beta is None or abs(beta) < MIN_BETA_FOR_SCALING:
        return None

    # These views hold the VN-Index run only and are keyed by timestamp;
    # there is no symbol column to filter on.
    row = (
        await session.execute(
            text(
                """
                SELECT ts, var_95, es_95, mc_paths
                FROM api.v_risk_metrics
                ORDER BY ts DESC
                LIMIT 1
                """
            )
        )
    ).mappings().first()
    if row is None or row["var_95"] is None:
        return None

    buckets = (
        await session.execute(
            text(
                """
                SELECT bucket, probability
                FROM api.v_risk_distribution
                WHERE ts = :ts
                ORDER BY bucket DESC
                """
            ),
            {"ts": row["ts"]},
        )
    ).mappings().all()

    # Published as negative drawdowns; the curve works in positive depths.
    curve = sorted(
        {
            abs(float(b["bucket"])): float(b["probability"]) for b in buckets
        }.items()
    )

    time_scale = math.sqrt(horizon_days / MC_BASE_HORIZON_DAYS)
    abs_beta = abs(beta)

    origin = row["ts"]
    return ForwardRisk(
        source_model="rarf-fhe",
        forecast_origin=origin.date() if hasattr(origin, "date") else origin,
        horizon_days=horizon_days,
        base_horizon_days=MC_BASE_HORIZON_DAYS,
        horizon_scale=round(time_scale, 4),
        paths=int(row["mc_paths"] or 0),
        portfolio_beta=round(beta, 4),
        var_95=round(float(row["var_95"]) * beta * time_scale, 6),
        expected_shortfall_95=round(
            float(row["es_95"]) * beta * time_scale, 6
        ),
        drawdown_probabilities=[
            DrawdownBucket(
                threshold=-depth,
                probability=round(
                    _exceedance_at(curve, depth / abs_beta / time_scale), 6
                ),
            )
            for depth in DRAWDOWN_THRESHOLDS
        ],
    )


async def analyze(
    session: AsyncSession, request: PortfolioRequest
) -> PortfolioAnalysis:
    symbols = [h.symbol for h in request.holdings]
    by_symbol: dict[str, Holding] = {h.symbol: h for h in request.holdings}

    closes = await _load_closes(
        session, symbols + [BENCHMARK], request.lookback_days
    )
    sectors = await _load_sectors(session, symbols)

    priced = [
        s
        for s in symbols
        if len(closes.get(s, {})) >= MIN_OBSERVATIONS
    ]
    unpriced = [s for s in symbols if s not in priced]

    if not priced:
        raise ValueError("no holding has enough price history to analyse")

    dates, returns = _aligned_returns(closes, priced)
    n_obs = returns.shape[0]
    if n_obs < MIN_OBSERVATIONS:
        raise ValueError(
            "the holdings do not share enough common trading days to analyse"
        )

    # Returns are unit-free, so only the levels need converting.
    last_price = {
        s: closes[s][max(closes[s])] * PRICE_UNIT_VND for s in priced
    }
    values = np.array(
        [by_symbol[s].quantity * last_price[s] for s in priced]
    )
    invested = float(values.sum())
    total_value = invested + request.cash
    weights = values / invested if invested > 0 else np.zeros_like(values)

    cov = _ledoit_wolf(returns)
    # Portfolio variance uses invested weights: cash has no variance, and
    # including it would understate the risk of the part that is at risk.
    port_var = float(weights @ cov @ weights)
    port_vol_daily = math.sqrt(max(port_var, 0.0))
    volatility = port_vol_daily * math.sqrt(TRADING_DAYS)

    port_returns = returns @ weights
    downside = port_returns[port_returns < 0]
    downside_deviation = (
        float(downside.std(ddof=1)) * math.sqrt(TRADING_DAYS)
        if downside.size > 1
        else 0.0
    )

    # Historical simulation rather than a normal assumption: the left tail of
    # a Vietnamese equity book is fatter than a normal distribution allows.
    var_95 = float(np.percentile(port_returns, 5))
    tail = port_returns[port_returns <= var_95]
    es_95 = float(tail.mean()) if tail.size else var_95

    max_dd = _max_drawdown(port_returns)

    # Beta against the index over the same dates.
    beta: float | None = None
    bench_closes = closes.get(BENCHMARK, {})
    if len(bench_closes) >= MIN_OBSERVATIONS:
        bench_on_dates = [bench_closes.get(d) for d in [dates[0], *dates]]
        if all(p is not None for p in bench_on_dates):
            bench = np.array(bench_on_dates, dtype=float)
            bench_ret = np.diff(np.log(bench))
            if bench_ret.shape[0] == port_returns.shape[0]:
                bench_var = float(bench_ret.var(ddof=1))
                if bench_var > 0:
                    beta = float(
                        np.cov(port_returns, bench_ret, ddof=1)[0, 1] / bench_var
                    )

    # Risk contribution: weight times marginal contribution, normalised.
    marginal = cov @ weights
    contributions = weights * marginal
    total_contribution = float(contributions.sum())
    if total_contribution > 0:
        risk_shares = contributions / total_contribution
    else:
        risk_shares = np.zeros_like(contributions)

    asset_vol = np.sqrt(np.diag(cov)) * math.sqrt(TRADING_DAYS)

    # Per-asset beta, for the stress page and for explaining a position.
    asset_betas: dict[str, float | None] = {s: None for s in priced}
    if beta is not None:
        bench_ret_full = np.diff(
            np.log(np.array([bench_closes[d] for d in [dates[0], *dates]]))
        )
        bench_var = float(bench_ret_full.var(ddof=1))
        for i, s in enumerate(priced):
            if bench_var > 0:
                asset_betas[s] = round(
                    float(
                        np.cov(returns[:, i], bench_ret_full, ddof=1)[0, 1]
                        / bench_var
                    ),
                    4,
                )

    positions: list[PositionRisk] = []
    total_cost = 0.0
    has_cost = True
    for i, s in enumerate(priced):
        h = by_symbol[s]
        value = float(values[i])
        cost = h.cost_basis * h.quantity if h.cost_basis is not None else None
        if cost is None:
            has_cost = False
        else:
            total_cost += cost
        positions.append(
            PositionRisk(
                symbol=s,
                quantity=h.quantity,
                price=last_price[s],
                market_value=round(value, 2),
                weight=round(float(weights[i]), 6),
                cost_basis=h.cost_basis,
                profit=round(value - cost, 2) if cost is not None else None,
                profit_percent=(
                    round((value - cost) / cost, 6)
                    if cost not in (None, 0)
                    else None
                ),
                volatility=round(float(asset_vol[i]), 6),
                beta=asset_betas[s],
                risk_contribution=round(float(risk_shares[i]), 6),
                sector=sectors.get(s),
                observations=len(closes[s]),
            )
        )

    positions.sort(key=lambda p: p.risk_contribution, reverse=True)

    concentration = _concentration(priced, weights, cov, sectors)

    # The analysis is only as current as the last session every holding
    # traded, so that date is what the payload reports.
    last_session = (
        datetime.combine(max(dates), time(0, 0), tzinfo=UTC) if dates else None
    )

    return PortfolioAnalysis(
        **build_freshness(last_session).model_dump(),
        total_value=round(total_value, 2),
        invested_value=round(invested, 2),
        cash=request.cash,
        cash_weight=round(request.cash / total_value, 6) if total_value else 0.0,
        total_cost=round(total_cost, 2) if has_cost else None,
        profit=round(invested - total_cost, 2) if has_cost else None,
        profit_percent=(
            round((invested - total_cost) / total_cost, 6)
            if has_cost and total_cost
            else None
        ),
        lookback_days=request.lookback_days,
        observations=n_obs,
        volatility=round(volatility, 6),
        downside_deviation=round(downside_deviation, 6),
        max_drawdown=round(max_dd, 6),
        beta=round(beta, 4) if beta is not None else None,
        var_95=round(var_95, 6),
        expected_shortfall_95=round(es_95, 6),
        risk_state=_risk_state(volatility, max_dd),
        positions=positions,
        concentration=concentration,
        forward=await _forward_risk(session, beta, request.horizon_days),
        unpriced=unpriced,
    )


def _concentration(
    symbols: list[str],
    weights: np.ndarray,
    cov: np.ndarray,
    sectors: dict[str, str],
) -> Concentration:
    ordered = np.sort(weights)[::-1]
    hhi = float((weights**2).sum())

    std = np.sqrt(np.diag(cov))
    outer = np.outer(std, std)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.where(outer > 0, cov / outer, 0.0)
    off = ~np.eye(len(symbols), dtype=bool)
    avg_corr = float(corr[off].mean()) if off.any() else 0.0

    max_pair: list[str] | None = None
    max_corr: float | None = None
    if off.any():
        masked = np.where(off, corr, -np.inf)
        idx = int(np.argmax(masked))
        i, j = divmod(idx, len(symbols))
        max_corr = round(float(corr[i, j]), 4)
        max_pair = sorted([symbols[i], symbols[j]])

    # Effective bets: how many independent positions the book really holds.
    # Ten names with an average correlation of 0.7 behave like far fewer, and
    # this is the number that says so.
    if len(symbols) > 1 and avg_corr > -1:
        denom = 1.0 + (len(symbols) - 1) * max(avg_corr, 0.0)
        effective_bets = len(symbols) / denom if denom > 0 else float(len(symbols))
    else:
        effective_bets = float(len(symbols))

    sector_weights: dict[str, float] = {}
    for s, w in zip(symbols, weights, strict=False):
        key = sectors.get(s) or "Unclassified"
        sector_weights[key] = round(sector_weights.get(key, 0.0) + float(w), 6)

    return Concentration(
        positions=len(symbols),
        largest_weight=round(float(ordered[0]), 6) if ordered.size else 0.0,
        top_three_weight=round(float(ordered[:3].sum()), 6),
        herfindahl=round(hhi, 6),
        effective_assets=round(1.0 / hhi, 4) if hhi > 0 else 0.0,
        effective_bets=round(effective_bets, 4),
        average_correlation=round(avg_corr, 4),
        max_pair_correlation=max_corr,
        max_pair=max_pair,
        sector_weights=dict(
            sorted(sector_weights.items(), key=lambda kv: kv[1], reverse=True)
        ),
    )
