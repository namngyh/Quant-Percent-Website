import validationJson from "@/config/performance/validation-2024.json";
import walkForwardJson from "@/config/performance/walk-forward.json";
import multiseedJson from "@/config/performance/multiseed-test.json";
import { getStrategy, type StrategyConfig } from "@/config/strategies";
import type {
  EquityPoint,
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
 * project's `results/` directory (see each JSON's `provenance` block).
 *
 * Percentages follow the research project's own convention: a notional
 * of NOTIONAL_POINTS index points, drawdown against the running equity
 * peak. Verified to reproduce the published net_pct and max_dd_pct.
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
    netPoints: full.net_profit ?? null,
    maxDrawdownPoints: full.max_dd ?? null,
    expectancy: full.expectancy ?? null,
    avgWin: full.avg_win ?? null,
    avgLoss: full.avg_loss ?? null,
    longPnl: full.long_pnl ?? null,
    shortPnl: full.short_pnl ?? null,
    sharpe: full.sharpe ?? null,
    sortino: full.sortino ?? null,
    calmar: full.calmar ?? null,
    profitFactor: full.profit_factor ?? null,
    payoff: full.payoff ?? null,
    ulcer: full.ulcer ?? null,
    upi: full.upi ?? null,
    equityR2: full.equity_r2 ?? null,
    trades: full.total_trades ?? null,
    maxConsecutiveLosses: full.max_cons_l ?? null,
    // No benchmark series was exported with any of these runs
    benchmarkReturn: null,
  };
}

/** Source metric key → the key used for labels in messages. */
const CI_METRICS: [string, string][] = [
  ["net_profit", "netPoints"],
  ["rr", "payoff"],
  ["profit_factor", "profitFactor"],
  ["sharpe", "sharpe"],
  ["sortino", "sortino"],
  ["calmar", "calmar"],
  ["max_dd", "maxDrawdownPoints"],
  ["win_rate", "winRate"],
  ["upi", "upi"],
  ["total_trades", "trades"],
];

/** Metrics stored in percent units that must be shown as fractions. */
const CI_PERCENT_KEYS = new Set(["winRate"]);

export function getSeries(slug: string): SeriesBody | null {
  const strategy = getStrategy(slug);
  if (!strategy) return null;

  const base = {
    strategy_slug: slug,
    result_type: strategy.resultType,
  };

  if (strategy.dataset === "validation") {
    return {
      ...base,
      has_trade_series: true,
      points: validationJson.equity as EquityPoint[],
      return_distribution: validationJson.distribution,
      folds: null,
      exit_reasons: validationJson.exit_reasons,
      series_note: null,
    };
  }

  if (strategy.dataset === "walkForward") {
    const folds: WalkForwardFold[] = walkForwardJson.folds.map((f) => ({
      ...f,
      net_pct: Math.round((f.net_points / NOTIONAL_POINTS) * 10000) / 10000,
    }));
    return {
      ...base,
      // The walk-forward run exported per-fold aggregates only
      has_trade_series: false,
      points: [],
      return_distribution: [],
      folds,
      exit_reasons: null,
      series_note: null,
    };
  }

  const median = multiseedJson.median_seed;
  return {
    ...base,
    has_trade_series: true,
    points: median.equity as EquityPoint[],
    return_distribution: median.distribution,
    folds: null,
    exit_reasons: null,
    series_note: { seed: median.seed, of_seeds: multiseedJson.n_seeds },
  };
}

export function getMetrics(slug: string): MetricsBody | null {
  const strategy = getStrategy(slug);
  if (!strategy) return null;

  if (strategy.dataset === "validation") {
    return {
      strategy_slug: slug,
      metrics: metricsFromFull(
        validationJson.full as FullStats,
        validationJson.tier3.all as FullStats
      ),
      confidence_intervals: null,
    };
  }

  if (strategy.dataset === "walkForward") {
    return {
      strategy_slug: slug,
      metrics: metricsFromFull(
        walkForwardJson.full as FullStats,
        walkForwardJson.tier3.all as FullStats
      ),
      confidence_intervals: null,
    };
  }

  // Multi-seed: means over 50 seeds. Percentage drawdown is peak-relative
  // and was not exported per seed, so it stays null rather than being
  // approximated from the mean in points.
  const ci = multiseedJson.ci95 as Record<
    string,
    { mean: number; ci95_lo: number; ci95_hi: number }
  >;
  const mean = (key: string) => ci[key]?.mean ?? null;

  return {
    strategy_slug: slug,
    metrics: {
      totalReturn: onNotional(mean("net_profit")),
      annualizedReturn: onNotional(mean("annual_ret")),
      maxDrawdown: null,
      winRate: pct(mean("win_rate")),
      exposure: pct(mean("exposure")),
      pctMonths: pct(mean("pct_months")),
      wrLong: pct(mean("wr_long")),
      wrShort: pct(mean("wr_short")),
      netPoints: mean("net_profit"),
      maxDrawdownPoints: mean("max_dd"),
      expectancy: mean("expectancy"),
      avgWin: mean("avg_win"),
      avgLoss: mean("avg_loss"),
      longPnl: mean("long_pnl"),
      shortPnl: mean("short_pnl"),
      sharpe: mean("sharpe"),
      sortino: mean("sortino"),
      calmar: mean("calmar"),
      profitFactor: mean("profit_factor"),
      payoff: mean("rr"),
      ulcer: mean("ulcer"),
      upi: mean("upi"),
      equityR2: mean("equity_r2"),
      trades: mean("total_trades"),
      maxConsecutiveLosses: mean("max_cons_l"),
      benchmarkReturn: null,
    },
    confidence_intervals: CI_METRICS.filter(([src]) => ci[src]).map(
      ([src, key]) => {
        const scale = CI_PERCENT_KEYS.has(key) ? 100 : 1;
        return {
          metric: key,
          mean: ci[src].mean / scale,
          ci95_lo: ci[src].ci95_lo / scale,
          ci95_hi: ci[src].ci95_hi / scale,
        };
      }
    ),
  };
}

/** Only the multi-seed run produced a distribution over seeds. */
export function getSimulation(slug: string): SimulationBody | null {
  const strategy = getStrategy(slug);
  if (!strategy || strategy.dataset !== "multiseed") return null;

  return {
    strategy_slug: slug,
    n_seeds: multiseedJson.n_seeds,
    pct_positive: multiseedJson.pct_positive,
    long_bias_seeds: multiseedJson.long_bias_seeds,
    short_bias_seeds: multiseedJson.short_bias_seeds,
    seed_distribution: multiseedJson.seed_distribution,
    profit: multiseedJson.profit,
    bootstrap: multiseedJson.bootstrap,
    cost_stress: multiseedJson.cost_stress,
  };
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
  if (strategy.dataset === "validation") return validationJson.provenance;
  if (strategy.dataset === "walkForward") return walkForwardJson.provenance;
  return multiseedJson.provenance;
}

export { NOTIONAL_POINTS };
