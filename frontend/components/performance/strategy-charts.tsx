"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { useApi } from "@/lib/api/fetcher";
import type {
  PerformanceSeries,
  Simulation,
  StrategyMetrics,
} from "@/lib/api/types";
import { CHART, EChart } from "@/components/charts/echart";
import { DataState } from "@/components/states/data-state";
import { DataFreshnessLabel } from "@/components/states/data-freshness-label";
import { InfoTip } from "@/components/info-tip";
import {
  HEADLINE_METRICS,
  METRIC_FORMAT,
  METRIC_GROUPS,
} from "@/lib/performance/metrics";
import { fmtNumber, fmtPercent, fmtSignedPercent } from "@/lib/format";
import { useIsMobile } from "@/lib/use-is-mobile";
import { cn } from "@/lib/utils";

function Panel({
  title,
  tip,
  note,
  children,
}: {
  title: string;
  tip?: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="qp-panel p-5">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        {title} {tip && <InfoTip text={tip} />}
      </h3>
      {note && <p className="mt-1 text-xs leading-relaxed text-dim">{note}</p>}
      {children}
    </div>
  );
}

/** Real research output. No generated series appear on this page. */
export function StrategyCharts({ slug }: { slug: string }) {
  const t = useTranslations("performance.detail");
  const g = useTranslations("glossary");
  const locale = useLocale();
  const isMobile = useIsMobile();

  const series = useApi<PerformanceSeries>(
    `/api/v1/strategies/${slug}/performance`
  );
  const metrics = useApi<StrategyMetrics>(`/api/v1/strategies/${slug}/metrics`);
  const sim = useApi<Simulation>(`/api/v1/strategies/${slug}/simulations`);

  const points = useMemo(() => series.data?.points ?? [], [series.data]);
  const folds = series.data?.folds ?? null;
  const exitReasons = series.data?.exit_reasons ?? null;

  const tradeAxis = useMemo(
    () => points.map((p) => String(p.trade)),
    [points]
  );

  const equityOption = useMemo<EChartsCoreOption>(
    () => ({
      xAxis: {
        type: "category",
        data: tradeAxis,
        name: t("tradeAxis"),
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { color: CHART.dim, fontSize: 12 },
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: { color: CHART.dim, interval: isMobile ? 29 : 19 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          color: CHART.dim,
          formatter: (v: number) => fmtPercent(v, locale, 0),
        },
        splitLine: { lineStyle: { color: CHART.surface } },
      },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) => fmtPercent(Number(v), locale),
      },
      series: [
        {
          name: t("equityCurve"),
          type: "line",
          data: points.map((p) => p.equity_pct),
          showSymbol: false,
          lineStyle: { color: CHART.brand, width: 2 },
          itemStyle: { color: CHART.brand },
        },
      ],
    }),
    [points, tradeAxis, t, locale, isMobile]
  );

  const drawdownOption = useMemo<EChartsCoreOption>(
    () => ({
      xAxis: {
        type: "category",
        data: tradeAxis,
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: { color: CHART.dim, interval: isMobile ? 29 : 19 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          color: CHART.dim,
          formatter: (v: number) => fmtPercent(v, locale, 0),
        },
        splitLine: { lineStyle: { color: CHART.surface } },
      },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) => fmtPercent(Number(v), locale),
      },
      series: [
        {
          name: t("drawdown"),
          type: "line",
          data: points.map((p) => p.drawdown_pct),
          showSymbol: false,
          lineStyle: { color: CHART.negative, width: 1.2 },
          itemStyle: { color: CHART.negative },
          areaStyle: { color: CHART.negative, opacity: 0.12 },
        },
      ],
    }),
    [points, tradeAxis, t, locale, isMobile]
  );

  const distributionOption = useMemo<EChartsCoreOption>(() => {
    const dist = series.data?.return_distribution ?? [];
    return {
      xAxis: {
        type: "category",
        data: dist.map((d) => fmtNumber(d.bucket, locale)),
        name: t("pointsAxis"),
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { color: CHART.dim, fontSize: 12 },
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: { color: CHART.dim },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: CHART.dim },
        splitLine: { lineStyle: { color: CHART.surface } },
      },
      series: [
        {
          name: t("returnDistribution"),
          type: "bar",
          barWidth: "70%",
          data: dist.map((d) => ({
            value: d.count,
            itemStyle: {
              color: d.bucket >= 0 ? CHART.positive : CHART.negative,
            },
          })),
        },
      ],
    };
  }, [series.data, locale, t]);

  const foldOption = useMemo<EChartsCoreOption>(
    () => ({
      xAxis: {
        type: "category",
        data: (folds ?? []).map((f) => String(f.test_year)),
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: { color: CHART.dim },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          color: CHART.dim,
          formatter: (v: number) => fmtPercent(v, locale, 0),
        },
        splitLine: { lineStyle: { color: CHART.surface } },
      },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) => fmtSignedPercent(Number(v), locale, 1),
      },
      series: [
        {
          name: t("foldNet"),
          type: "bar",
          data: (folds ?? []).map((f) => ({
            value: f.net_pct,
            itemStyle: {
              color: f.net_pct >= 0 ? CHART.brand : CHART.negative,
            },
          })),
          barWidth: "45%",
        },
      ],
    }),
    [folds, locale, t]
  );

  const seedOption = useMemo<EChartsCoreOption>(() => {
    const dist = sim.data?.seed_distribution ?? [];
    return {
      xAxis: {
        type: "category",
        data: dist.map((d) => fmtNumber(d.bucket, locale)),
        name: t("pointsAxis"),
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { color: CHART.dim, fontSize: 12 },
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: { color: CHART.dim },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: CHART.dim },
        splitLine: { lineStyle: { color: CHART.surface } },
      },
      tooltip: { trigger: "axis" },
      series: [
        {
          name: t("seedDistribution"),
          type: "bar",
          data: dist.map((d) => d.count),
          barWidth: "70%",
          itemStyle: { color: CHART.signal },
        },
      ],
    };
  }, [sim.data, locale, t]);

  const costOption = useMemo<EChartsCoreOption>(() => {
    const scenarios = sim.data?.cost_stress.scenarios ?? [];
    return {
      xAxis: {
        type: "category",
        data: scenarios.map((s) => fmtNumber(s.cost_points, locale)),
        name: t("costAxis"),
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { color: CHART.dim, fontSize: 12 },
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: { color: CHART.dim },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { color: CHART.dim },
        splitLine: { lineStyle: { color: CHART.surface } },
      },
      tooltip: { trigger: "axis" },
      series: [
        {
          name: t("costStress"),
          type: "line",
          data: scenarios.map((s) => s.profit_mean),
          symbolSize: 6,
          lineStyle: { color: CHART.signal, width: 2 },
          itemStyle: { color: CHART.signal },
        },
      ],
    };
  }, [sim.data, locale, t]);

  const m = metrics.data?.metrics;
  const cis = metrics.data?.confidence_intervals ?? null;

  const metricTips: Record<string, string> = {
    sharpe: g("sharpe"),
    sortino: g("sortino"),
    maxDrawdown: g("drawdown"),
    maxDrawdownPoints: g("drawdown"),
    calmar: g("calmar"),
    winRate: g("winRate"),
    profitFactor: g("profitFactor"),
    exposure: g("exposure"),
  };

  const formatMetric = (key: string, value: number) => {
    switch (METRIC_FORMAT[key]) {
      case "percent":
        return fmtPercent(value, locale);
      case "points":
        return `${fmtNumber(value, locale)} ${t("pointsUnit")}`;
      case "count":
        return fmtNumber(value, locale, { maximumFractionDigits: 1 });
      default:
        return fmtNumber(value, locale);
    }
  };

  return (
    <DataState
      loading={series.isLoading || metrics.isLoading}
      error={series.error || metrics.error}
      onRetry={() => {
        series.mutate();
        metrics.mutate();
      }}
      skeletonRows={10}
    >
      {series.data && (
        <div className="space-y-6">
          {/* Metrics include only values the run actually produced.
              Twenty-six tiles in one flat grid read as noise to anyone who is
              not a quant, so the four headline figures come first and the
              rest sit behind one disclosure, grouped by what they answer. */}
          {m && (
            <div className="space-y-5">
              <div>
                <h3 className="text-sm font-medium">
                  {t("metricGroups.headline")}
                </h3>
                <p className="mt-1 text-xs leading-relaxed text-dim">
                  {t("metricGroups.headlineNote")}
                </p>
                <div className="mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm desk:grid-cols-4">
                  {HEADLINE_METRICS.filter(
                    (k) => m[k as keyof typeof m] != null
                  ).map((k) => (
                    <div key={k} className="bg-background p-5">
                      <p className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.06em] text-dim">
                        {t(`metricNames.${k}`)}
                        {metricTips[k] && <InfoTip text={metricTips[k]} />}
                      </p>
                      <p className="figure mt-2 text-2xl font-medium">
                        {formatMetric(k, m[k as keyof typeof m] as number)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <details className="group qp-panel p-5">
                <summary className="cursor-pointer list-none text-sm font-medium text-brand hover:text-brand-strong">
                  <span className="group-open:hidden">
                    {t("metricGroups.showDetail")}
                  </span>
                  <span className="hidden group-open:inline">
                    {t("metricGroups.hideDetail")}
                  </span>
                </summary>
                <div className="mt-5 space-y-6">
                  {METRIC_GROUPS.map((group) => {
                    const available = group.metrics.filter(
                      (k) => m[k as keyof typeof m] != null
                    );
                    if (available.length === 0) return null;
                    return (
                      <div key={group.titleKey}>
                        <h4 className="text-[13px] font-medium">
                          {t(`metricGroups.${group.titleKey}`)}
                        </h4>
                        <p className="mt-1 text-xs leading-relaxed text-dim">
                          {t(`metricGroups.${group.titleKey}Note`)}
                        </p>
                        <div className="mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3 desk:grid-cols-5">
                          {available.map((k) => (
                            <div key={k} className="bg-background p-4">
                              <p className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.06em] text-dim">
                                {t(`metricNames.${k}`)}
                                {metricTips[k] && (
                                  <InfoTip text={metricTips[k]} />
                                )}
                              </p>
                              <p className="figure mt-1.5 text-lg font-medium">
                                {formatMetric(
                                  k,
                                  m[k as keyof typeof m] as number
                                )}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </details>
            </div>
          )}

          {/* Walk-forward: per-fold results, never blended into one curve */}
          {folds && folds.length > 0 && (
            <Panel title={t("foldTitle")} note={t("foldNote")}>
              <EChart
                option={foldOption}
                ariaLabel={t("foldTitle")}
                className="mt-3 h-[26rem]"
              />
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[640px] text-[13px]">
                  <thead>
                    <tr className="border-b border-border bg-surface text-left">
                      <th scope="col" className="px-3 py-2.5 font-medium text-dim">
                        {t("foldTrain")}
                      </th>
                      <th scope="col" className="px-3 py-2.5 font-medium text-dim">
                        {t("foldTest")}
                      </th>
                      <th scope="col" className="px-3 py-2.5 text-right font-medium text-dim">
                        {t("metricNames.totalReturn")}
                      </th>
                      <th scope="col" className="px-3 py-2.5 text-right font-medium text-dim">
                        {t("metricNames.trades")}
                      </th>
                      <th scope="col" className="px-3 py-2.5 text-right font-medium text-dim">
                        {t("metricNames.winRate")}
                      </th>
                      <th scope="col" className="px-3 py-2.5 text-right font-medium text-dim">
                        {t("metricNames.maxDrawdownPoints")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {folds.map((f) => (
                      <tr key={f.fold} className="border-b border-border last:border-0">
                        <td className="figure px-3 py-2.5">
                          {f.train_from}–{f.train_to}
                        </td>
                        <td className="figure px-3 py-2.5">
                          {f.test_year}
                          {f.partial_year && (
                            <span className="ml-2 rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-[0.06em] text-dim">
                              {t("partialYear")}
                            </span>
                          )}
                        </td>
                        <td
                          className={cn(
                            "figure px-3 py-2.5 text-right",
                            f.net_pct < 0 && "text-negative"
                          )}
                        >
                          {fmtSignedPercent(f.net_pct, locale, 1)}
                        </td>
                        <td className="figure px-3 py-2.5 text-right">{f.trades}</td>
                        <td className="figure px-3 py-2.5 text-right">
                          {fmtPercent(f.win_rate / 100, locale)}
                        </td>
                        <td className="figure px-3 py-2.5 text-right">
                          {fmtNumber(f.max_drawdown_points, locale)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}

          {/* Trade-indexed equity and drawdown */}
          {series.data.has_trade_series && points.length > 0 && (
            <>
              <Panel
                title={t("equityCurve")}
                note={
                  series.data.series_note
                    ? t("seriesNote", {
                        seed: series.data.series_note.seed,
                        total: series.data.series_note.of_seeds,
                      })
                    : t("tradeIndexNote")
                }
              >
                <EChart
                  option={equityOption}
                  ariaLabel={t("equityCurve")}
                  className="mt-3 h-[26rem]"
                />
              </Panel>

              <Panel title={t("drawdown")} tip={g("drawdown")}>
                <EChart
                  option={drawdownOption}
                  ariaLabel={t("drawdown")}
                  className="mt-3 h-96"
                />
              </Panel>

              <Panel title={t("returnDistribution")}>
                <EChart
                  option={distributionOption}
                  ariaLabel={t("returnDistribution")}
                  className="mt-3 h-[26rem]"
                />
              </Panel>
            </>
          )}

          {/* Validation run: real exit-reason breakdown */}
          {exitReasons && exitReasons.length > 0 && (
            <Panel title={t("exitReasonsTitle")} note={t("exitReasonsNote")}>
              <ul className="mt-4 space-y-2.5">
                {exitReasons.map((r) => (
                  <li
                    key={r.id}
                    className="grid grid-cols-[1fr_auto] items-center gap-4 desk:grid-cols-[220px_1fr_auto]"
                  >
                    <span className="text-[13px]">
                      {t(`exitReasons.${r.id}`)}
                    </span>
                    <span aria-hidden="true" className="hidden h-2 bg-surface desk:block">
                      <span
                        className="block h-full bg-ink"
                        style={{ width: `${r.share}%` }}
                      />
                    </span>
                    <span className="figure text-[13px]">
                      {fmtPercent(r.share / 100, locale)}
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {/* Multi-seed run: seed distribution, bootstrap, cost sensitivity */}
          {sim.data && (
            <>
              <Panel
                title={t("seedDistribution")}
                note={t("seedDistributionNote", {
                  seeds: sim.data.n_seeds,
                  positive: fmtPercent(sim.data.pct_positive / 100, locale, 0),
                  long: sim.data.long_bias_seeds,
                  short: sim.data.short_bias_seeds,
                })}
              >
                <EChart
                  option={seedOption}
                  ariaLabel={t("seedDistribution")}
                  className="mt-3 h-[26rem]"
                />
                <dl className="mt-4 grid grid-cols-2 gap-4 border-t border-border pt-4 desk:grid-cols-4">
                  {[
                    { k: "profitMean", v: sim.data.profit.mean },
                    { k: "profitMedian", v: sim.data.profit.median },
                    { k: "profitMin", v: sim.data.profit.min },
                    { k: "profitMax", v: sim.data.profit.max },
                  ].map((row) => (
                    <div key={row.k}>
                      <dt className="text-[11px] uppercase tracking-[0.06em] text-dim">
                        {t(`seedStats.${row.k}`)}
                      </dt>
                      <dd className="figure mt-1 text-lg">
                        {fmtNumber(row.v, locale)} {t("pointsUnit")}
                      </dd>
                    </div>
                  ))}
                </dl>
              </Panel>

              <Panel
                title={t("bootstrapTitle")}
                tip={g("bootstrap")}
                note={t("bootstrapNote", {
                  n: fmtNumber(sim.data.bootstrap.n, locale),
                })}
              >
                <dl className="mt-4 grid grid-cols-2 gap-4 desk:grid-cols-4">
                  <div>
                    <dt className="text-[11px] uppercase tracking-[0.06em] text-dim">
                      {t("bootstrapMedian")}
                    </dt>
                    <dd className="figure mt-1 text-lg">
                      {fmtNumber(sim.data.bootstrap.final_median, locale)}{" "}
                      {t("pointsUnit")}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] uppercase tracking-[0.06em] text-dim">
                      {t("bootstrapVar")}
                    </dt>
                    <dd className="figure mt-1 text-lg">
                      {fmtNumber(sim.data.bootstrap.var5, locale)}{" "}
                      {t("pointsUnit")}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] uppercase tracking-[0.06em] text-dim">
                      {t("bootstrapPayoff")}
                    </dt>
                    <dd className="figure mt-1 text-lg">
                      {fmtNumber(sim.data.bootstrap.payoff_mean, locale)}{" "}
                      <span className="text-xs text-dim">
                        ({fmtNumber(sim.data.bootstrap.payoff_ci90[0], locale)}–
                        {fmtNumber(sim.data.bootstrap.payoff_ci90[1], locale)})
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] uppercase tracking-[0.06em] text-dim">
                      {t("bootstrapProb")}
                    </dt>
                    <dd className="figure mt-1 text-lg">
                      {fmtPercent(sim.data.bootstrap.prob_payoff_gt1, locale, 0)}
                    </dd>
                  </div>
                </dl>
              </Panel>

              <Panel
                title={t("costStress")}
                note={t("costStressNote", {
                  fee: fmtNumber(sim.data.cost_stress.fee_tax_points, locale),
                  slippage: fmtNumber(
                    sim.data.cost_stress.slippage_points,
                    locale
                  ),
                })}
              >
                <EChart
                  option={costOption}
                  ariaLabel={t("costStress")}
                  className="mt-3 h-[26rem]"
                />
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full min-w-[560px] text-[13px]">
                    <thead>
                      <tr className="border-b border-border bg-surface text-left">
                        <th scope="col" className="px-3 py-2.5 font-medium text-dim">
                          {t("costPerTrade")}
                        </th>
                        <th scope="col" className="px-3 py-2.5 text-right font-medium text-dim">
                          {t("seedStats.profitMean")}
                        </th>
                        <th scope="col" className="px-3 py-2.5 text-right font-medium text-dim">
                          {t("ci95")}
                        </th>
                        <th scope="col" className="px-3 py-2.5 text-right font-medium text-dim">
                          {t("metricNames.payoff")}
                        </th>
                        <th scope="col" className="px-3 py-2.5 text-right font-medium text-dim">
                          {t("pctPositive")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {sim.data.cost_stress.scenarios.map((s) => (
                        <tr
                          key={s.cost_points}
                          className="border-b border-border last:border-0"
                        >
                          <td className="figure px-3 py-2.5">
                            {fmtNumber(s.cost_points, locale)} {t("pointsUnit")}
                          </td>
                          <td className="figure px-3 py-2.5 text-right">
                            {fmtNumber(s.profit_mean, locale)}
                          </td>
                          <td className="figure px-3 py-2.5 text-right text-dim">
                            {fmtNumber(s.ci95[0], locale)}–
                            {fmtNumber(s.ci95[1], locale)}
                          </td>
                          <td className="figure px-3 py-2.5 text-right">
                            {fmtNumber(s.payoff_mean, locale)}
                          </td>
                          <td className="figure px-3 py-2.5 text-right">
                            {fmtPercent(s.pct_positive / 100, locale, 0)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </>
          )}

          {/* Confidence intervals over seeds */}
          {cis && cis.length > 0 && (
            <Panel title={t("ciTitle")} note={t("ciNote")}>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[520px] text-[13px]">
                  <thead>
                    <tr className="border-b border-border bg-surface text-left">
                      <th scope="col" className="px-3 py-2.5 font-medium text-dim">
                        {t("metricColumn")}
                      </th>
                      <th scope="col" className="px-3 py-2.5 text-right font-medium text-dim">
                        {t("meanColumn")}
                      </th>
                      <th scope="col" className="px-3 py-2.5 text-right font-medium text-dim">
                        {t("ci95")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {cis.map((row) => (
                      <tr key={row.metric} className="border-b border-border last:border-0">
                        <td className="px-3 py-2.5">
                          {t(`metricNames.${row.metric}`)}
                        </td>
                        <td className="figure px-3 py-2.5 text-right">
                          {formatMetric(row.metric, row.mean)}
                        </td>
                        <td className="figure px-3 py-2.5 text-right text-dim">
                          {formatMetric(row.metric, row.ci95_lo)} –{" "}
                          {formatMetric(row.metric, row.ci95_hi)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}

          <DataFreshnessLabel freshness={series.data} illustrative={false} />
        </div>
      )}
    </DataState>
  );
}
