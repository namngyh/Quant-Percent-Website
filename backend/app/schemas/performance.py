from __future__ import annotations

from app.schemas.common import ApiModel, Freshness, ResultType


class EquityPoint(ApiModel):
    trade: int
    equity: float
    equity_pct: float
    drawdown: float
    drawdown_pct: float


class DistributionBucket(ApiModel):
    bucket: float
    count: int


class WalkForwardFold(ApiModel):
    fold: int
    train_from: int
    train_to: int
    test_year: int
    net_points: float
    net_pct: float
    trades: int
    long: int
    short: int
    win_rate: float
    payoff: float
    max_drawdown_points: float
    partial_year: bool


class ExitReason(ApiModel):
    id: str
    share: float


class SeriesNote(ApiModel):
    seed: int
    of_seeds: int


class PerformanceSeries(Freshness):
    strategy_slug: str
    result_type: ResultType
    has_trade_series: bool
    points: list[EquityPoint]
    return_distribution: list[DistributionBucket]
    folds: list[WalkForwardFold] | None
    exit_reasons: list[ExitReason] | None
    series_note: SeriesNote | None


class Metrics(ApiModel):
    """Missing metrics stay null — never zero-filled (spec §10.4)."""

    totalReturn: float | None = None
    annualizedReturn: float | None = None
    maxDrawdown: float | None = None
    winRate: float | None = None
    exposure: float | None = None
    pctMonths: float | None = None
    wrLong: float | None = None
    wrShort: float | None = None
    netPoints: float | None = None
    maxDrawdownPoints: float | None = None
    expectancy: float | None = None
    avgWin: float | None = None
    avgLoss: float | None = None
    longPnl: float | None = None
    shortPnl: float | None = None
    sharpe: float | None = None
    sortino: float | None = None
    calmar: float | None = None
    profitFactor: float | None = None
    payoff: float | None = None
    ulcer: float | None = None
    upi: float | None = None
    equityR2: float | None = None
    trades: float | None = None
    maxConsecutiveLosses: float | None = None
    benchmarkReturn: float | None = None


class ConfidenceInterval(ApiModel):
    metric: str
    mean: float
    ci95_lo: float
    ci95_hi: float


class StrategyMetrics(Freshness):
    strategy_slug: str
    metrics: Metrics
    confidence_intervals: list[ConfidenceInterval] | None


class ProfitStats(ApiModel):
    mean: float
    median: float
    std: float
    min: float
    max: float


class Bootstrap(ApiModel):
    n: int
    final_median: float
    final_mean: float
    var5: float
    payoff_mean: float
    payoff_ci90: list[float]
    prob_payoff_gt1: float


class CostScenario(ApiModel):
    cost_points: float
    profit_mean: float
    profit_min: float
    ci95: list[float]
    pct_positive: float
    payoff_mean: float
    win_rate: float
    max_drawdown_points: float


class CostStress(ApiModel):
    fee_tax_points: float
    slippage_points: float
    scenarios: list[CostScenario]


class Simulation(Freshness):
    strategy_slug: str
    n_seeds: int
    pct_positive: float
    long_bias_seeds: int
    short_bias_seeds: int
    seed_distribution: list[DistributionBucket]
    profit: ProfitStats
    bootstrap: Bootstrap
    cost_stress: CostStress


class StrategyHeadline(ApiModel):
    totalReturn: float | None
    netPoints: float | None
    maxDrawdown: float | None
    maxDrawdownPoints: float | None
    trades: float | None
    winRate: float | None


class LocalizedText(ApiModel):
    vi: str
    en: str


class LocalizedList(ApiModel):
    vi: list[str]
    en: list[str]


class StrategySummary(ApiModel):
    slug: str
    name: LocalizedText
    summary: LocalizedText
    system_slug: str
    result_type: ResultType
    asset: str
    timeframe: str
    benchmark: LocalizedText
    period_start: str
    period_end: str
    fees_note: LocalizedText
    slippage_note: LocalizedText
    split_note: LocalizedText
    seed_note: LocalizedText
    model_version: str
    code_version: str
    headline: StrategyHeadline


class StrategyDetail(StrategySummary):
    caveats: LocalizedList
    provenance: dict


class StrategyList(Freshness):
    strategies: list[StrategySummary]
