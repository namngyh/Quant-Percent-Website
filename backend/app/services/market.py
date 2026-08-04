from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.freshness import build_freshness
from app.schemas.market import (
    Constituents,
    History,
    MarketOverview,
    McBucket,
    OhlcvBar,
    Quote,
    RiskDashboard,
    StockRow,
    StressScenario,
)

# Everything below reads the vetted `api` views, never the ingestion
# tables directly (spec §21) — the API role has no rights on them anyway.

INDEX_SYMBOLS = ("VNINDEX", "VN30", "VN30F1M")


async def get_quote(session: AsyncSession, symbol: str) -> Quote | None:
    row = (
        await session.execute(
            text(
                """
                SELECT symbol, name, price, change, change_percent,
                       volume, currency, data_as_of
                FROM api.v_quote
                WHERE symbol = :symbol
                """
            ),
            {"symbol": symbol.upper()},
        )
    ).mappings().first()
    # A symbol can be registered in web.symbols before any bar has been
    # ingested for it; that is "no data yet", not an error.
    if row is None or row["price"] is None:
        return None

    freshness = build_freshness(row["data_as_of"])
    return Quote(
        **freshness.model_dump(),
        symbol=row["symbol"],
        name=row["name"],
        price=float(row["price"]),
        change=float(row["change"] or 0),
        change_percent=float(row["change_percent"] or 0),
        volume=int(row["volume"] or 0),
        currency=row["currency"],
    )


async def get_history(
    session: AsyncSession, symbol: str, count: int
) -> History:
    rows = (
        await session.execute(
            text(
                """
                SELECT trading_date, open, high, low, close, volume
                FROM api.v_history_1d
                WHERE symbol = :symbol
                ORDER BY trading_date DESC
                LIMIT :count
                """
            ),
            {"symbol": symbol.upper(), "count": count},
        )
    ).mappings().all()

    bars = [
        OhlcvBar(
            time=r["trading_date"],
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=int(r["volume"] or 0),
        )
        for r in reversed(rows)
    ]
    last_ts = (
        datetime.combine(bars[-1].time, datetime.min.time(), tzinfo=UTC)
        if bars
        else None
    )
    freshness = build_freshness(
        last_ts,
        # A daily series is expected to be a session old
        stale_after_minutes=4 * 24 * 60,
    )
    return History(
        **freshness.model_dump(),
        symbol=symbol.upper(),
        timeframe="1D",
        bars=bars,
    )


async def get_overview(session: AsyncSession) -> MarketOverview:
    quotes: list[Quote] = []
    for symbol in INDEX_SYMBOLS:
        quote = await get_quote(session, symbol)
        if quote is not None:
            quotes.append(quote)

    state = (
        await session.execute(
            text(
                """
                SELECT ts, regime, regime_probability, probability_up,
                       probability_down, volatility, risk_state, risk_score,
                       model_consensus, public_signal, generated_at
                FROM api.v_market_state
                ORDER BY ts DESC
                LIMIT 1
                """
            )
        )
    ).mappings().first()

    if state is None:
        # No model output yet: report the quotes we have and say so,
        # rather than inventing a market state
        freshness = build_freshness(
            max((q.data_as_of for q in quotes), default=None)
        )
        return MarketOverview(
            **freshness.model_dump(),
            quotes=quotes,
            regime="sideways",
            regime_probability=0.0,
            probability_up=0.0,
            probability_down=0.0,
            volatility=0.0,
            risk_state="moderate",
            risk_score=0,
            model_consensus=0.0,
            public_signal="low_conviction",
        )

    freshness = build_freshness(state["ts"], state["generated_at"])
    return MarketOverview(
        **freshness.model_dump(),
        quotes=quotes,
        regime=state["regime"],
        regime_probability=float(state["regime_probability"]),
        probability_up=float(state["probability_up"]),
        probability_down=float(state["probability_down"]),
        volatility=float(state["volatility"]),
        risk_state=state["risk_state"],
        risk_score=int(state["risk_score"]),
        model_consensus=float(state["model_consensus"]),
        public_signal=state["public_signal"],
    )


async def get_constituents(session: AsyncSession) -> Constituents:
    rows = (
        await session.execute(
            text(
                """
                SELECT ticker, price, change_percent, regime, probability_up,
                       volatility, risk_state, rank, ts
                FROM api.v_vn30_constituents
                ORDER BY ticker
                """
            )
        )
    ).mappings().all()

    freshness = build_freshness(max((r["ts"] for r in rows), default=None))
    return Constituents(
        **freshness.model_dump(),
        rows=[
            StockRow(
                ticker=r["ticker"],
                price=float(r["price"] or 0),
                change_percent=float(r["change_percent"] or 0),
                regime=r["regime"],
                probability_up=float(r["probability_up"]),
                volatility=float(r["volatility"]),
                risk_state=r["risk_state"],
                rank=int(r["rank"]),
            )
            for r in rows
        ],
    )


async def get_risk(session: AsyncSession) -> RiskDashboard | None:
    row = (
        await session.execute(
            text(
                """
                SELECT ts, current_drawdown, rolling_drawdown_60d, volatility,
                       var_95, es_95, downside_probability, risk_state,
                       mc_paths, generated_at
                FROM api.v_risk_metrics
                ORDER BY ts DESC
                LIMIT 1
                """
            )
        )
    ).mappings().first()
    if row is None:
        return None

    buckets = (
        await session.execute(
            text(
                """
                SELECT bucket, probability FROM api.v_risk_distribution
                WHERE ts = :ts ORDER BY bucket DESC
                """
            ),
            {"ts": row["ts"]},
        )
    ).mappings().all()

    scenarios = (
        await session.execute(
            text(
                """
                SELECT scenario_id, impact_percent FROM api.v_risk_scenarios
                WHERE ts = :ts ORDER BY impact_percent
                """
            ),
            {"ts": row["ts"]},
        )
    ).mappings().all()

    freshness = build_freshness(row["ts"], row["generated_at"])
    return RiskDashboard(
        **freshness.model_dump(),
        current_drawdown=float(row["current_drawdown"]),
        rolling_drawdown_60d=float(row["rolling_drawdown_60d"]),
        volatility=float(row["volatility"]),
        var_95=float(row["var_95"]) if row["var_95"] is not None else None,
        es_95=float(row["es_95"]) if row["es_95"] is not None else None,
        downside_probability=float(row["downside_probability"]),
        risk_state=row["risk_state"],
        mc_drawdown_distribution=[
            McBucket(bucket=float(b["bucket"]), probability=float(b["probability"]))
            for b in buckets
        ],
        mc_paths=int(row["mc_paths"]),
        stress_scenarios=[
            StressScenario(
                id=s["scenario_id"], impact_percent=float(s["impact_percent"])
            )
            for s in scenarios
        ],
    )


async def last_trading_day(session: AsyncSession) -> date | None:
    """Uses the trading calendar so holidays are not mistaken for sessions."""
    row = (
        await session.execute(
            text(
                """
                SELECT trading_date FROM web.trading_calendar
                WHERE is_trading_day AND trading_date <= :today
                ORDER BY trading_date DESC LIMIT 1
                """
            ),
            {"today": datetime.now(UTC).date()},
        )
    ).first()
    return row[0] if row else None


def delayed_cutoff() -> datetime:
    """Publication delay we are allowed to show data with."""
    return datetime.now(UTC) - timedelta(
        minutes=settings.market_delay_minutes
    )
