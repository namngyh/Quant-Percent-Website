import { z } from "zod";

/**
 * Public API schemas (spec §18). These define the exact shape the real
 * FastAPI backend will serve later. The mock route handlers validate
 * against them so the swap is transparent.
 */

export const RegimeSchema = z.enum([
  "bullish",
  "bullish_transition",
  "bearish",
  "bearish_transition",
  "sideways",
  "turbulent",
]);
export type Regime = z.infer<typeof RegimeSchema>;

export const RiskStateSchema = z.enum(["low", "moderate", "elevated", "high"]);
export type RiskState = z.infer<typeof RiskStateSchema>;

export const PublicSignalSchema = z.enum([
  "bullish",
  "neutral",
  "defensive",
  "high_risk",
  "low_conviction",
]);
export type PublicSignal = z.infer<typeof PublicSignalSchema>;

/** Freshness metadata required on every public payload (spec §20). */
export const FreshnessSchema = z.object({
  data_as_of: z.string(),
  generated_at: z.string(),
  source_status: z.enum(["ok", "delayed", "unavailable"]),
  is_stale: z.boolean(),
  delay_minutes: z.number(),
});
export type Freshness = z.infer<typeof FreshnessSchema>;

export const QuoteSchema = FreshnessSchema.extend({
  symbol: z.string(),
  name: z.string(),
  price: z.number(),
  change: z.number(),
  change_percent: z.number(),
  volume: z.number(),
  currency: z.string(),
});
export type Quote = z.infer<typeof QuoteSchema>;

export const OhlcvBarSchema = z.object({
  time: z.string(), // ISO date
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number(),
});
export type OhlcvBar = z.infer<typeof OhlcvBarSchema>;

export const HistorySchema = FreshnessSchema.extend({
  symbol: z.string(),
  timeframe: z.string(),
  bars: z.array(OhlcvBarSchema),
});
export type History = z.infer<typeof HistorySchema>;

/** One public forecast record (spec §18 example). */
export const ForecastRecordSchema = FreshnessSchema.extend({
  model_id: z.string(),
  model_name: z.string(),
  model_version: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  horizon: z.number(),
  horizon_unit: z.literal("trading_days"),
  forecast_value: z.number(),
  forecast_return: z.number(),
  probability_up: z.number(),
  probability_down: z.number(),
  volatility: z.number(),
  interval_level: z.number(),
  interval_lower: z.number(),
  interval_upper: z.number(),
  // A purely distributional model makes no regime call and assigns no risk
  // grade; those arrive as null instead of an invented value.
  regime: RegimeSchema.nullable().default(null),
  regime_probability: z.number().nullable().default(null),
  risk_score: z.number().nullable().default(null),
  risk_state: RiskStateSchema.nullable().default(null),
  status: z.enum(["active", "paper_trading", "experimental", "archived"]),
});
export type ForecastRecord = z.infer<typeof ForecastRecordSchema>;

/** Historical forecast vs realized value, for coverage/error review. */
export const ForecastHistoryPointSchema = z.object({
  forecast_at: z.string(),
  horizon: z.number(),
  predicted: z.number(),
  interval_lower: z.number(),
  interval_upper: z.number(),
  actual: z.number(),
  error_percent: z.number(),
  in_interval: z.boolean(),
});
export type ForecastHistoryPoint = z.infer<typeof ForecastHistoryPointSchema>;

export const ForecastHistorySchema = FreshnessSchema.extend({
  model_id: z.string(),
  symbol: z.string(),
  interval_level: z.number(),
  coverage: z.number(),
  points: z.array(ForecastHistoryPointSchema),
});
export type ForecastHistory = z.infer<typeof ForecastHistorySchema>;

/**
 * Quotes come from the ingestion feed and are always present. Every field
 * below them is produced by the model pipeline and is null until a run has
 * written to `quant.market_state` — a reading the model never produced must
 * arrive as null, not as a neutral-looking default.
 */
export const MarketOverviewSchema = FreshnessSchema.extend({
  quotes: z.array(QuoteSchema),
  regime: RegimeSchema.nullable().default(null),
  regime_probability: z.number().nullable().default(null),
  probability_up: z.number().nullable().default(null),
  probability_down: z.number().nullable().default(null),
  volatility: z.number().nullable().default(null),
  risk_state: RiskStateSchema.nullable().default(null),
  risk_score: z.number().nullable().default(null),
  model_consensus: z.number().nullable().default(null),
  public_signal: PublicSignalSchema.nullable().default(null),
});
export type MarketOverview = z.infer<typeof MarketOverviewSchema>;

export const StockRowSchema = z.object({
  ticker: z.string(),
  price: z.number(),
  change_percent: z.number(),
  regime: RegimeSchema,
  probability_up: z.number(),
  volatility: z.number(),
  risk_state: RiskStateSchema,
  rank: z.number(),
});
export type StockRow = z.infer<typeof StockRowSchema>;

export const ConstituentsSchema = FreshnessSchema.extend({
  rows: z.array(StockRowSchema),
});
export type Constituents = z.infer<typeof ConstituentsSchema>;

export const RiskDashboardSchema = FreshnessSchema.extend({
  current_drawdown: z.number(),
  rolling_drawdown_60d: z.number(),
  volatility: z.number(),
  var_95: z.number().nullable(),
  es_95: z.number().nullable(),
  downside_probability: z.number(),
  risk_state: RiskStateSchema,
  mc_drawdown_distribution: z.array(
    z.object({ bucket: z.number(), probability: z.number() })
  ),
  mc_paths: z.number(),
  stress_scenarios: z.array(
    z.object({ id: z.string(), impact_percent: z.number() })
  ),
});
export type RiskDashboard = z.infer<typeof RiskDashboardSchema>;

/**
 * One trade in the equity curve. The research runs record profit per
 * closed trade without a timestamp, so the series is indexed by trade
 * number rather than by date.
 */
export const EquityPointSchema = z.object({
  trade: z.number(),
  equity: z.number(),
  equity_pct: z.number(),
  drawdown: z.number(),
  drawdown_pct: z.number(),
});
export type EquityPoint = z.infer<typeof EquityPointSchema>;

export const ResultTypeSchema = z.enum([
  "backtest",
  "out_of_sample",
  "walk_forward",
  "paper_trading",
  "live",
]);

/** One year of an anchored walk-forward run. */
export const WalkForwardFoldSchema = z.object({
  fold: z.number(),
  train_from: z.number(),
  train_to: z.number(),
  test_year: z.number(),
  net_points: z.number(),
  net_pct: z.number(),
  trades: z.number(),
  long: z.number(),
  short: z.number(),
  win_rate: z.number(),
  payoff: z.number(),
  max_drawdown_points: z.number(),
  partial_year: z.boolean(),
  /** Index return over the same dates. Null when no index data covers them. */
  benchmark_pct: z.number().nullable().optional(),
  benchmark_symbol: z.string().nullable().optional(),
});
export type WalkForwardFold = z.infer<typeof WalkForwardFoldSchema>;

export const PerformanceSeriesSchema = FreshnessSchema.extend({
  strategy_slug: z.string(),
  result_type: ResultTypeSchema,
  /** False when the run only exported per-fold aggregates (no trade series). */
  has_trade_series: z.boolean(),
  points: z.array(EquityPointSchema),
  return_distribution: z.array(
    z.object({ bucket: z.number(), count: z.number() })
  ),
  folds: z.array(WalkForwardFoldSchema).nullable(),
  /** Share of exits by reason, in percent. */
  exit_reasons: z
    .array(z.object({ id: z.string(), share: z.number() }))
    .nullable(),
  /** Set when the curve belongs to one representative seed of many. */
  series_note: z
    .object({ seed: z.number(), of_seeds: z.number() })
    .nullable(),
});
export type PerformanceSeries = z.infer<typeof PerformanceSeriesSchema>;

/** Metrics may legitimately be missing: null, never zero-filled. */
export const StrategyMetricsSchema = FreshnessSchema.extend({
  strategy_slug: z.string(),
  metrics: z.object({
    totalReturn: z.number().nullable(),
    annualizedReturn: z.number().nullable(),
    maxDrawdown: z.number().nullable(),
    winRate: z.number().nullable(),
    exposure: z.number().nullable(),
    pctMonths: z.number().nullable(),
    wrLong: z.number().nullable(),
    wrShort: z.number().nullable(),
    netPoints: z.number().nullable(),
    maxDrawdownPoints: z.number().nullable(),
    expectancy: z.number().nullable(),
    avgWin: z.number().nullable(),
    avgLoss: z.number().nullable(),
    longPnl: z.number().nullable(),
    shortPnl: z.number().nullable(),
    sharpe: z.number().nullable(),
    sortino: z.number().nullable(),
    calmar: z.number().nullable(),
    profitFactor: z.number().nullable(),
    payoff: z.number().nullable(),
    ulcer: z.number().nullable(),
    upi: z.number().nullable(),
    equityR2: z.number().nullable(),
    trades: z.number().nullable(),
    maxConsecutiveLosses: z.number().nullable(),
    /** Benchmark series was not exported with these runs. */
    benchmarkReturn: z.number().nullable(),
  }),
  /** 95% confidence interval over seeds, where the run produced one. */
  confidence_intervals: z
    .array(
      z.object({
        metric: z.string(),
        mean: z.number(),
        ci95_lo: z.number(),
        ci95_hi: z.number(),
      })
    )
    .nullable(),
});
export type StrategyMetrics = z.infer<typeof StrategyMetricsSchema>;

/**
 * Distribution of outcomes across initialisation seeds, plus bootstrap
 * confidence intervals and transaction-cost sensitivity. Only produced
 * for runs that were repeated over many seeds.
 */
export const SimulationSchema = FreshnessSchema.extend({
  strategy_slug: z.string(),
  n_seeds: z.number(),
  pct_positive: z.number(),
  long_bias_seeds: z.number(),
  short_bias_seeds: z.number(),
  seed_distribution: z.array(
    z.object({ bucket: z.number(), count: z.number() })
  ),
  profit: z.object({
    mean: z.number(),
    median: z.number(),
    std: z.number(),
    min: z.number(),
    max: z.number(),
  }),
  bootstrap: z.object({
    n: z.number(),
    final_median: z.number(),
    final_mean: z.number(),
    var5: z.number(),
    payoff_mean: z.number(),
    payoff_ci90: z.array(z.number()),
    prob_payoff_gt1: z.number(),
  }),
  cost_stress: z.object({
    fee_tax_points: z.number(),
    slippage_points: z.number(),
    scenarios: z.array(
      z.object({
        cost_points: z.number(),
        profit_mean: z.number(),
        profit_min: z.number(),
        ci95: z.array(z.number()),
        pct_positive: z.number(),
        payoff_mean: z.number(),
        win_rate: z.number(),
        max_drawdown_points: z.number(),
      })
    ),
  }),
});
export type Simulation = z.infer<typeof SimulationSchema>;

export const SystemStatusSchema = z.object({
  generated_at: z.string(),
  services: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      status: z.enum(["operational", "degraded", "down"]),
    })
  ),
});
export type SystemStatus = z.infer<typeof SystemStatusSchema>;

export const DataFreshnessReportSchema = z.object({
  generated_at: z.string(),
  feeds: z.array(
    z.object({
      id: z.string(),
      symbol: z.string(),
      data_as_of: z.string(),
      is_stale: z.boolean(),
      delay_minutes: z.number(),
    })
  ),
});
export type DataFreshnessReport = z.infer<typeof DataFreshnessReportSchema>;

export const ModelStatusReportSchema = z.object({
  generated_at: z.string(),
  models: z.array(
    z.object({
      model_id: z.string(),
      status: z.enum(["active", "paper_trading", "experimental", "archived"]),
      last_run_at: z.string().nullable(),
      healthy: z.boolean(),
    })
  ),
});
export type ModelStatusReport = z.infer<typeof ModelStatusReportSchema>;

/** Contact form payload shared by client form and API route. */
export const ContactPayloadSchema = z.object({
  name: z.string().trim().min(1).max(200),
  email: z.string().trim().email().max(320),
  phone: z.string().trim().max(40).optional().or(z.literal("")),
  organization: z.string().trim().max(200).optional().or(z.literal("")),
  inquiryType: z.enum([
    "investor_interest",
    "research_collaboration",
    "data_partnership",
    "technology_partnership",
    "general",
  ]),
  message: z.string().trim().min(10).max(5000),
  locale: z.enum(["vi", "en"]),
  consent: z.literal(true),
  /** Honeypot must stay empty; bots fill it. */
  website: z.string().max(0).optional().or(z.literal("")),
});
export type ContactPayload = z.infer<typeof ContactPayloadSchema>;

/* ------------------------------------------------------------------ *
 * Quant Portfolio
 *
 * Money is in dong throughout. Prices from the feed are quoted in
 * thousands, and the backend converts before returning anything here,
 * so nothing on this contract needs to know about that.
 * ------------------------------------------------------------------ */

export const HoldingInputSchema = z.object({
  symbol: z.string().trim().min(1).max(20),
  quantity: z.number().positive(),
  cost_basis: z.number().positive().nullable().optional(),
});
export type HoldingInput = z.infer<typeof HoldingInputSchema>;

export const PortfolioRequestSchema = z.object({
  holdings: z.array(HoldingInputSchema).min(1).max(50),
  cash: z.number().min(0),
  horizon_days: z.number().int().min(21).max(252),
  lookback_days: z.number().int().min(60).max(1000).optional(),
});
export type PortfolioRequestPayload = z.infer<typeof PortfolioRequestSchema>;

export const PositionRiskSchema = z.object({
  symbol: z.string(),
  quantity: z.number(),
  price: z.number(),
  market_value: z.number(),
  weight: z.number(),
  cost_basis: z.number().nullable(),
  profit: z.number().nullable(),
  profit_percent: z.number().nullable(),
  volatility: z.number(),
  beta: z.number().nullable(),
  risk_contribution: z.number(),
  sector: z.string().nullable(),
  observations: z.number(),
});
export type PositionRisk = z.infer<typeof PositionRiskSchema>;

export const ConcentrationSchema = z.object({
  positions: z.number(),
  largest_weight: z.number(),
  top_three_weight: z.number(),
  herfindahl: z.number(),
  effective_assets: z.number(),
  effective_bets: z.number(),
  average_correlation: z.number(),
  max_pair_correlation: z.number().nullable(),
  max_pair: z.array(z.string()).nullable(),
  sector_weights: z.record(z.string(), z.number()),
});
export type Concentration = z.infer<typeof ConcentrationSchema>;

export const ForwardRiskSchema = z.object({
  source_model: z.string(),
  forecast_origin: z.string(),
  horizon_days: z.number(),
  base_horizon_days: z.number(),
  horizon_scale: z.number(),
  paths: z.number(),
  portfolio_beta: z.number(),
  var_95: z.number(),
  expected_shortfall_95: z.number(),
  drawdown_probabilities: z.array(
    z.object({ threshold: z.number(), probability: z.number() })
  ),
});
export type ForwardRisk = z.infer<typeof ForwardRiskSchema>;

export const PortfolioAnalysisSchema = FreshnessSchema.extend({
  total_value: z.number(),
  invested_value: z.number(),
  cash: z.number(),
  cash_weight: z.number(),
  total_cost: z.number().nullable(),
  profit: z.number().nullable(),
  profit_percent: z.number().nullable(),
  lookback_days: z.number(),
  observations: z.number(),
  volatility: z.number(),
  downside_deviation: z.number(),
  max_drawdown: z.number(),
  beta: z.number().nullable(),
  var_95: z.number(),
  expected_shortfall_95: z.number(),
  risk_state: z.enum(["low", "moderate", "elevated", "high"]),
  positions: z.array(PositionRiskSchema),
  concentration: ConcentrationSchema,
  forward: ForwardRiskSchema.nullable(),
  unpriced: z.array(z.string()),
});
export type PortfolioAnalysis = z.infer<typeof PortfolioAnalysisSchema>;

export const TradableSymbolSchema = z.object({
  symbol: z.string(),
  name: z.string(),
  exchange: z.string(),
  sector: z.string().nullable(),
  sessions: z.number(),
});
export type TradableSymbol = z.infer<typeof TradableSymbolSchema>;

export const TradableSymbolsSchema = FreshnessSchema.extend({
  rows: z.array(TradableSymbolSchema),
});
export type TradableSymbols = z.infer<typeof TradableSymbolsSchema>;
