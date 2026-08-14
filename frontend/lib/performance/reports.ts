import frozenBrainJson from "@/config/performance/frozen-brain.json";
import { getStrategy, type StrategyConfig } from "@/config/strategies";
import type {
  Freshness,
  PerformanceSeries,
  Simulation,
  StrategyMetrics,
  WalkForwardFold,
} from "@/lib/api/types";

/** The route handlers add the freshness block, so getters omit it. */
type Body<T> = Omit<T, keyof Freshness>;
export type SeriesBody = Body<PerformanceSeries>;
export type MetricsBody = Body<StrategyMetrics>;
export type SimulationBody = Body<Simulation>;

/**
 * Real research results extracted from the Model-Modus project. Nothing
 * here is generated. Every number traces back to a file in that
 * project's `results/` directory (see the JSON's `provenance` block).
 *
 * One report is published: a brain frozen after 2023, scored on 2024
 * (validation), 2025 and 2026 (test). The run exported per-year aggregates
 * only — no per-trade series — so there is no equity curve and no return
 * distribution to show. That is reported through `has_trade_series: false`
 * rather than by drawing a curve interpolated from yearly totals, which would
 * be an invented picture of trades that are not in the data.
 *
 * Percentages follow the research project's own convention: a notional
 * of NOTIONAL_POINTS index points.
 */

const NOTIONAL_POINTS = 1000;

/** Metrics arrive in percent units from the source files. */
const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? null : v / 100;

/** Points converted to a return on notional. */
const onNotional = (v: number | null | undefined) =>
  v === null || v === undefined ? null : v / NOTIONAL_POINTS;

type FullStats = Record<string, number>;

function metricsFromFull(full: FullStats, tier3All?: FullStats) {
  const or = (v: number | undefined) => (v === undefined ? null : v);
  return {
    totalReturn: tier3All
      ? pct(tier3All.net_pct)
      : onNotional(full.net_profit),
    annualizedReturn: tier3All ? pct(tier3All.car) : onNotional(full.annual_ret),
    maxDrawdown: tier3All ? pct(tier3All.max_dd_pct) : null,
    winRate: pct(full.win_rate),
    exposure: pct(full.exposure),
    pctMonths: pct(full.pct_months),
    wrLong: pct(full.wr_long),
    wrShort: pct(full.wr_short),
    netPoints: or(full.net_profit),
    maxDrawdownPoints: or(full.max_dd),
    expectancy: or(full.expectancy),
    avgWin: or(full.avg_win),
    avgLoss: or(full.avg_loss),
    longPnl: or(full.long_pnl),
    shortPnl: or(full.short_pnl),
    // Risk-adjusted ratios are not combinable across separately scored years,
    // so the frozen-brain report omits them at the report level and carries
    // them per year instead. `or` keeps them null rather than undefined.
    sharpe: or(full.sharpe),
    sortino: or(full.sortino),
    calmar: or(full.calmar),
    profitFactor: or(full.profit_factor),
    payoff: or(full.payoff),
    ulcer: or(full.ulcer),
    upi: or(full.upi),
    equityR2: or(full.equity_r2),
    trades: or(full.total_trades),
    maxConsecutiveLosses: or(full.max_cons_l),
    // The benchmark is computed per test year from the price database, not
    // carried in the report file.
    benchmarkReturn: null,
  };
}

export function getSeries(slug: string): SeriesBody | null {
  const strategy = getStrategy(slug);
  if (!strategy) return null;

  const folds: WalkForwardFold[] = frozenBrainJson.folds.map((f) => ({
    ...f,
    net_pct: Math.round((f.net_points / NOTIONAL_POINTS) * 10000) / 10000,
  }));

  return {
    strategy_slug: slug,
    result_type: strategy.resultType,
    has_trade_series: false,
    points: [],
    return_distribution: [],
    folds,
    exit_reasons: frozenBrainJson.exit_reasons,
    series_note: null,
  };
}

export function getMetrics(slug: string): MetricsBody | null {
  const strategy = getStrategy(slug);
  if (!strategy) return null;

  return {
    strategy_slug: slug,
    metrics: metricsFromFull(
      frozenBrainJson.full as FullStats,
      frozenBrainJson.tier3.all as FullStats
    ),
    confidence_intervals: null,
  };
}

/** Only a multi-seed run produces a distribution over seeds, and none is
 *  published at the moment. The route still exists and returns 404 through
 *  this null, so it starts working again the day such a report is added. */
export function getSimulation(): SimulationBody | null {
  return null;
}

/** Compact figures for the report cards on /performance. */
export function getHeadline(strategy: StrategyConfig) {
  const metrics = getMetrics(strategy.slug)?.metrics;
  return {
    totalReturn: metrics?.totalReturn ?? null,
    netPoints: metrics?.netPoints ?? null,
    maxDrawdown: metrics?.maxDrawdown ?? null,
    maxDrawdownPoints: metrics?.maxDrawdownPoints ?? null,
    trades: metrics?.trades ?? null,
    winRate: metrics?.winRate ?? null,
  };
}

/** Provenance block for the dataset behind a report. */
export function getProvenance(slug: string) {
  const strategy = getStrategy(slug);
  if (!strategy) return null;
  return frozenBrainJson.provenance;
}
