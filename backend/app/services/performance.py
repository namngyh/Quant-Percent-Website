from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.freshness import build_freshness
from app.db.models import (
    ReportBucket,
    ReportEquityPoint,
    ReportExitReason,
    ReportFold,
    ReportMetric,
    ReportSimulation,
    Strategy,
)
from app.schemas.performance import (
    Bootstrap,
    ConfidenceInterval,
    CostStress,
    DistributionBucket,
    EquityPoint,
    ExitReason,
    Metrics,
    PerformanceSeries,
    ProfitStats,
    SeriesNote,
    Simulation,
    StrategyDetail,
    StrategyHeadline,
    StrategyList,
    StrategyMetrics,
    StrategySummary,
    WalkForwardFold,
)

# Reports are finished research runs: the data does not go stale the way
# a market feed does, so freshness is pinned to the evaluation window.
_REPORT_STALE_MINUTES = 10 * 365 * 24 * 60


def _report_freshness(strategy: Strategy):
    return build_freshness(
        strategy.data_as_of,
        strategy.generated_at,
        delay_minutes=0,
        stale_after_minutes=_REPORT_STALE_MINUTES,
    )


async def get_strategy(session: AsyncSession, slug: str) -> Strategy | None:
    return await session.scalar(
        select(Strategy).where(Strategy.slug == slug, Strategy.published.is_(True))
    )


async def list_strategies(session: AsyncSession) -> StrategyList:
    strategies = (
        await session.scalars(
            select(Strategy)
            .where(Strategy.published.is_(True))
            .order_by(Strategy.sort_order, Strategy.slug)
        )
    ).all()

    summaries: list[StrategySummary] = []
    for s in strategies:
        metrics = await _metric_map(session, s.slug)
        summaries.append(_strategy_summary(s, metrics))

    newest = max((s.data_as_of for s in strategies), default=None)
    freshness = build_freshness(
        newest, delay_minutes=0, stale_after_minutes=_REPORT_STALE_MINUTES
    )
    return StrategyList(**freshness.model_dump(), strategies=summaries)


def _strategy_summary(
    strategy: Strategy, metrics: dict[str, float]
) -> StrategySummary:
    return StrategySummary(
        slug=strategy.slug,
        name=strategy.name,
        summary=strategy.summary,
        system_slug=strategy.system_slug,
        result_type=strategy.result_type,
        asset=strategy.asset,
        timeframe=strategy.timeframe,
        benchmark=strategy.benchmark,
        period_start=strategy.period_start.isoformat(),
        period_end=strategy.period_end.isoformat(),
        fees_note=strategy.fees_note,
        slippage_note=strategy.slippage_note,
        split_note=strategy.split_note,
        seed_note=strategy.seed_note,
        model_version=strategy.model_version,
        code_version=strategy.code_version,
        headline=StrategyHeadline(
            totalReturn=metrics.get("totalReturn"),
            netPoints=metrics.get("netPoints"),
            maxDrawdown=metrics.get("maxDrawdown"),
            maxDrawdownPoints=metrics.get("maxDrawdownPoints"),
            trades=metrics.get("trades"),
            winRate=metrics.get("winRate"),
        ),
    )


async def get_detail(
    session: AsyncSession, strategy: Strategy
) -> StrategyDetail:
    summary = _strategy_summary(
        strategy, await _metric_map(session, strategy.slug)
    )
    return StrategyDetail(
        **summary.model_dump(),
        caveats=strategy.caveats,
        provenance=strategy.provenance,
    )


async def _metric_map(session: AsyncSession, slug: str) -> dict[str, float]:
    rows = (
        await session.scalars(
            select(ReportMetric).where(ReportMetric.strategy_slug == slug)
        )
    ).all()
    return {r.metric: r.value for r in rows}


# VN-Index: the benchmark Vietnamese investors actually quote and can verify.
#
# VN30F1M is technically written on VN30, so VN30 is the closer underlying.
# VN-Index is the index a reader will check the claim against, which is what
# makes the comparison useful to them. The basis note on the page says the
# two instruments differ.
BENCHMARK_SYMBOL = "VNINDEX"


async def _benchmark_by_year(
    session: AsyncSession, folds, period_end
) -> dict[int, float]:
    """Index return over exactly the dates each fold was tested on.

    Bounded by the fold's own year and by the report's end date, so a partial
    final year is compared against the same partial period rather than against
    a full calendar year it never traded.
    """
    if not folds:
        return {}

    out: dict[int, float] = {}
    for f in folds:
        row = (
            await session.execute(
                text(
                    """
                    SELECT (array_agg(close ORDER BY trading_date))[1] AS first_close,
                           (array_agg(close ORDER BY trading_date DESC))[1] AS last_close
                    FROM api.v_history_1d
                    WHERE symbol = :symbol
                      AND trading_date >= make_date(:yr, 1, 1)
                      AND trading_date <= LEAST(
                            make_date(:yr, 12, 31), CAST(:period_end AS date)
                          )
                    """
                ),
                {
                    "symbol": BENCHMARK_SYMBOL,
                    "yr": f.test_year,
                    "period_end": period_end,
                },
            )
        ).mappings().first()
        if row and row["first_close"] and float(row["first_close"]) > 0:
            out[f.test_year] = round(
                float(row["last_close"]) / float(row["first_close"]) - 1.0, 6
            )
    return out


async def get_series(
    session: AsyncSession, strategy: Strategy
) -> PerformanceSeries:
    points = (
        await session.scalars(
            select(ReportEquityPoint)
            .where(ReportEquityPoint.strategy_slug == strategy.slug)
            .order_by(ReportEquityPoint.trade)
        )
    ).all()

    buckets = (
        await session.scalars(
            select(ReportBucket)
            .where(
                ReportBucket.strategy_slug == strategy.slug,
                ReportBucket.kind == "return_distribution",
            )
            .order_by(ReportBucket.bucket)
        )
    ).all()

    fold_rows = (
        await session.scalars(
            select(ReportFold)
            .where(ReportFold.strategy_slug == strategy.slug)
            .order_by(ReportFold.fold)
        )
    ).all()

    benchmarks = await _benchmark_by_year(
        session, fold_rows, strategy.period_end
    )

    exit_rows = (
        await session.scalars(
            select(ReportExitReason)
            .where(ReportExitReason.strategy_slug == strategy.slug)
            .order_by(ReportExitReason.share.desc())
        )
    ).all()

    simulation = await session.scalar(
        select(ReportSimulation).where(
            ReportSimulation.strategy_slug == strategy.slug
        )
    )
    series_note = (
        SeriesNote(seed=simulation.median_seed, of_seeds=simulation.n_seeds)
        if simulation is not None and simulation.median_seed is not None
        else None
    )

    return PerformanceSeries(
        **_report_freshness(strategy).model_dump(),
        strategy_slug=strategy.slug,
        result_type=strategy.result_type,
        has_trade_series=bool(points),
        points=[
            EquityPoint(
                trade=p.trade,
                equity=p.equity,
                equity_pct=p.equity_pct,
                drawdown=p.drawdown,
                drawdown_pct=p.drawdown_pct,
            )
            for p in points
        ],
        return_distribution=[
            DistributionBucket(bucket=b.bucket, count=b.count) for b in buckets
        ],
        folds=(
            [
                WalkForwardFold(
                    fold=f.fold,
                    train_from=f.train_from,
                    train_to=f.train_to,
                    test_year=f.test_year,
                    net_points=f.net_points,
                    net_pct=f.net_pct,
                    trades=f.trades,
                    long=f.long_trades,
                    short=f.short_trades,
                    win_rate=f.win_rate,
                    payoff=f.payoff,
                    max_drawdown_points=f.max_drawdown_points,
                    partial_year=f.partial_year,
                    benchmark_pct=benchmarks.get(f.test_year),
                    benchmark_symbol=BENCHMARK_SYMBOL if f.test_year in benchmarks else None,
                )
                for f in fold_rows
            ]
            if fold_rows
            else None
        ),
        exit_reasons=(
            [ExitReason(id=r.reason, share=r.share) for r in exit_rows]
            if exit_rows
            else None
        ),
        series_note=series_note,
    )


async def get_metrics(
    session: AsyncSession, strategy: Strategy
) -> StrategyMetrics:
    rows = (
        await session.scalars(
            select(ReportMetric).where(ReportMetric.strategy_slug == strategy.slug)
        )
    ).all()

    values = {r.metric: r.value for r in rows}
    cis = [
        ConfidenceInterval(
            metric=r.metric, mean=r.value, ci95_lo=r.ci95_lo, ci95_hi=r.ci95_hi
        )
        for r in rows
        if r.in_confidence_table and r.ci95_lo is not None and r.ci95_hi is not None
    ]

    return StrategyMetrics(
        **_report_freshness(strategy).model_dump(),
        strategy_slug=strategy.slug,
        metrics=Metrics(**values),
        confidence_intervals=cis or None,
    )


async def get_simulation(
    session: AsyncSession, strategy: Strategy
) -> Simulation | None:
    row = await session.scalar(
        select(ReportSimulation).where(
            ReportSimulation.strategy_slug == strategy.slug
        )
    )
    if row is None:
        return None

    buckets = (
        await session.scalars(
            select(ReportBucket)
            .where(
                ReportBucket.strategy_slug == strategy.slug,
                ReportBucket.kind == "seed_distribution",
            )
            .order_by(ReportBucket.bucket)
        )
    ).all()

    return Simulation(
        **_report_freshness(strategy).model_dump(),
        strategy_slug=strategy.slug,
        n_seeds=row.n_seeds,
        pct_positive=row.pct_positive,
        long_bias_seeds=row.long_bias_seeds,
        short_bias_seeds=row.short_bias_seeds,
        seed_distribution=[
            DistributionBucket(bucket=b.bucket, count=b.count) for b in buckets
        ],
        profit=ProfitStats(**row.profit),
        bootstrap=Bootstrap(**row.bootstrap),
        cost_stress=CostStress(**row.cost_stress),
    )
