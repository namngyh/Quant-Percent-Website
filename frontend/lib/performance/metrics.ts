/** How each performance metric should be rendered. */
export type MetricFormat = "percent" | "points" | "ratio" | "count";

export const METRIC_FORMAT: Record<string, MetricFormat> = {
  totalReturn: "percent",
  annualizedReturn: "percent",
  maxDrawdown: "percent",
  winRate: "percent",
  exposure: "percent",
  pctMonths: "percent",
  wrLong: "percent",
  wrShort: "percent",
  benchmarkReturn: "percent",
  netPoints: "points",
  maxDrawdownPoints: "points",
  expectancy: "points",
  avgWin: "points",
  avgLoss: "points",
  longPnl: "points",
  shortPnl: "points",
  sharpe: "ratio",
  sortino: "ratio",
  calmar: "ratio",
  profitFactor: "ratio",
  payoff: "ratio",
  ulcer: "ratio",
  upi: "ratio",
  equityR2: "ratio",
  trades: "count",
  maxConsecutiveLosses: "count",
};

/**
 * The four figures a reader looks for first, shown large above everything
 * else: what it made, the worst it fell, how often it was right, and how much
 * evidence there is. Everything else is detail behind these.
 */
export const HEADLINE_METRICS = [
  "totalReturn",
  "maxDrawdown",
  "winRate",
  "trades",
] as const;

/**
 * The remaining metrics, grouped by the question they answer rather than by
 * data type. A flat list of twenty-six ratios reads as noise to anyone who is
 * not a quant; grouped under plain headings it reads as a report.
 *
 * `titleKey` resolves under `performance.detail.metricGroups`.
 */
export const METRIC_GROUPS: { titleKey: string; metrics: string[] }[] = [
  {
    titleKey: "returns",
    metrics: ["annualizedReturn", "netPoints", "benchmarkReturn", "pctMonths"],
  },
  {
    titleKey: "risk",
    metrics: [
      "maxDrawdownPoints",
      "ulcer",
      "maxConsecutiveLosses",
      "equityR2",
    ],
  },
  {
    titleKey: "tradeQuality",
    metrics: ["profitFactor", "payoff", "expectancy", "avgWin", "avgLoss"],
  },
  {
    titleKey: "riskAdjusted",
    metrics: ["sharpe", "sortino", "calmar", "upi"],
  },
  {
    titleKey: "breakdown",
    metrics: ["wrLong", "wrShort", "longPnl", "shortPnl", "exposure"],
  },
];

/** Display order: percentage headline first, then points, then ratios. */
export const METRIC_ORDER = [
  "totalReturn",
  "annualizedReturn",
  "maxDrawdown",
  "winRate",
  "profitFactor",
  "payoff",
  "sharpe",
  "sortino",
  "calmar",
  "ulcer",
  "upi",
  "expectancy",
  "netPoints",
  "maxDrawdownPoints",
  "avgWin",
  "avgLoss",
  "longPnl",
  "shortPnl",
  "wrLong",
  "wrShort",
  "exposure",
  "pctMonths",
  "equityR2",
  "trades",
  "maxConsecutiveLosses",
  "benchmarkReturn",
] as const;
