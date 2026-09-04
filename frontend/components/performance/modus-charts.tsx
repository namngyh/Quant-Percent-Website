"use client";

import { useMemo } from "react";
import { useTranslations, useLocale } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { CHART, EChart } from "@/components/charts/echart";
import { DataState } from "@/components/states/data-state";
import { useApi } from "@/lib/api/fetcher";
import type { PerformanceSeries } from "@/lib/api/types";
import { fmtNumber } from "@/lib/format";
import { FEATURED_STRATEGY } from "@/config/strategies";

/**
 * The 2024-2026 result, drawn from what that run actually recorded.
 *
 * The walk-forward run reports `has_trade_series: false`: it stored a summary
 * per test year and no per-trade sequence. An equity curve therefore cannot be
 * drawn for this period. Borrowing the curve from the 2024-only validation run
 * or the 2025-2026 seed study would put a line on the page that does not
 * belong to the period named above it, so these charts show the yearly record
 * instead — which is the granularity the data has.
 */

const WALK_FORWARD = FEATURED_STRATEGY;

function Panel({
  title,
  note,
  children,
}: {
  title: string;
  note: string;
  children: React.ReactNode;
}) {
  return (
    <figure className="min-w-0 overflow-hidden rounded-lg border border-border bg-background p-5 shadow-sm sm:p-6">
      <figcaption>
        <h3 className="text-base font-semibold">{title}</h3>
        <p className="mt-2 text-sm leading-relaxed text-dim">{note}</p>
      </figcaption>
      {children}
    </figure>
  );
}

export function ModusCharts() {
  const t = useTranslations("performance.charts");
  const td = useTranslations("performance.detail");
  const locale = useLocale();

  const series = useApi<PerformanceSeries>(
    `/api/v1/strategies/${WALK_FORWARD}/performance`,
  );
  const folds = useMemo(() => series.data?.folds ?? [], [series.data]);
  const years = useMemo(() => folds.map((f) => String(f.test_year)), [folds]);
  const pointsUnit = td("pointsUnit");

  const categoryAxis = {
    type: "category" as const,
    data: years,
    axisLine: { lineStyle: { color: CHART.border } },
    axisTick: { show: false },
    axisLabel: { color: CHART.dim, fontFamily: CHART.mono, margin: 12 },
  };
  const valueAxis = {
    type: "value" as const,
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: CHART.surface } },
    axisLabel: { color: CHART.dim },
  };

  /** Net result per test year, with the losing year plainly red. */
  const yearlyOption = useMemo<EChartsCoreOption>(
    () => ({
      animationDuration: 450,
      grid: { left: 8, right: 18, top: 28, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) =>
          typeof v === "number"
            ? `${fmtNumber(v, locale, { maximumFractionDigits: 1 })} ${pointsUnit}`
            : String(v),
      },
      xAxis: categoryAxis,
      yAxis: valueAxis,
      series: [
        {
          type: "bar",
          barWidth: "38%",
          data: folds.map((f) => ({
            value: f.net_points,
            itemStyle: {
              color: f.net_points < 0 ? CHART.negative : CHART.positive,
              borderRadius:
                f.net_points < 0
                  ? ([0, 0, 4, 4] as const)
                  : ([4, 4, 0, 0] as const),
            },
            label: { position: f.net_points < 0 ? "bottom" : "top" },
          })),
          label: {
            show: true,
            distance: 6,
            color: CHART.ink,
            fontFamily: CHART.mono,
            fontSize: 11,
            formatter: (p: { value: number }) =>
              `${fmtNumber(p.value, locale, { maximumFractionDigits: 1, signDisplay: "always" })}`,
          },
          markLine: {
            silent: true,
            symbol: "none",
            label: { show: false },
            lineStyle: { color: CHART.faint, width: 1 },
            data: [{ yAxis: 0 }],
          },
        },
      ],
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [folds, locale, pointsUnit],
  );

  /** Running total across the three test years. */
  const cumulativeOption = useMemo<EChartsCoreOption>(() => {
    const cumulative: number[] = [];
    folds.forEach((f, i) => {
      cumulative.push((i === 0 ? 0 : cumulative[i - 1]) + f.net_points);
    });
    return {
      animationDuration: 450,
      grid: { left: 8, right: 18, top: 28, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) =>
          typeof v === "number"
            ? `${fmtNumber(v, locale, { maximumFractionDigits: 1 })} ${pointsUnit}`
            : String(v),
      },
      xAxis: categoryAxis,
      yAxis: valueAxis,
      series: [
        {
          type: "line",
          data: cumulative,
          smooth: false,
          symbol: "circle",
          symbolSize: 9,
          lineStyle: { width: 2.5, color: CHART.brand },
          itemStyle: {
            color: CHART.brand,
            borderColor: "#ffffff",
            borderWidth: 2,
          },
          areaStyle: { color: CHART.brandSoft },
          label: {
            show: true,
            position: "top",
            distance: 8,
            color: CHART.ink,
            fontFamily: CHART.mono,
            fontSize: 11,
            formatter: (p: { value: number }) =>
              fmtNumber(p.value, locale, { maximumFractionDigits: 0 }),
          },
        },
      ],
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folds, locale, pointsUnit]);

  /** Win rate against payoff: the trade-off the system runs on. */
  const qualityOption = useMemo<EChartsCoreOption>(
    () => ({
      animationDuration: 450,
      // The swatches are rendered as HTML above the canvas; the built-in
      // legend would be a second copy of the same two labels.
      legend: { show: false },
      grid: { left: 8, right: 18, top: 28, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis" },
      xAxis: categoryAxis,
      yAxis: [
        {
          ...valueAxis,
          max: 60,
          axisLabel: { color: CHART.dim, formatter: "{value}%" },
        },
        {
          ...valueAxis,
          splitLine: { show: false },
          axisLabel: { color: CHART.dim },
        },
      ],
      series: [
        {
          name: td("metricNames.winRate"),
          type: "bar",
          barWidth: "34%",
          yAxisIndex: 0,
          data: folds.map((f) => +f.win_rate.toFixed(1)),
          itemStyle: { color: CHART.lightgray, borderRadius: [4, 4, 0, 0] },
          label: {
            show: true,
            position: "top",
            distance: 5,
            color: CHART.dim,
            fontFamily: CHART.mono,
            fontSize: 11,
            formatter: (p: { value: number }) => `${p.value}%`,
          },
        },
        {
          name: td("metricNames.payoff"),
          type: "line",
          yAxisIndex: 1,
          data: folds.map((f) => f.payoff),
          symbol: "circle",
          symbolSize: 9,
          lineStyle: { width: 2.5, color: CHART.signal },
          itemStyle: {
            color: CHART.signal,
            borderColor: "#ffffff",
            borderWidth: 2,
          },
          label: {
            show: true,
            position: "top",
            distance: 8,
            color: CHART.signalDark,
            fontFamily: CHART.mono,
            fontSize: 11,
          },
        },
      ],
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [folds, td],
  );

  return (
    <section aria-labelledby="modus-charts" className="mt-14">
      <h2 id="modus-charts" className="title-md">
        {t("heading")}
      </h2>
      <p className="mt-3 max-w-3xl leading-relaxed text-dim">{t("lead")}</p>

      <DataState
        loading={series.isLoading}
        error={series.error}
        empty={!series.isLoading && folds.length === 0}
        className="mt-6"
      >
        <div className="mt-6 space-y-6">
          <Panel title={t("cumulativeTitle")} note={t("cumulativeNote")}>
            <EChart
              option={cumulativeOption}
              ariaLabel={t("cumulativeTitle")}
              className="mt-4 h-80"
            />
          </Panel>

          <div className="grid gap-6 desk:grid-cols-2">
            <Panel title={t("yearlyTitle")} note={t("yearlyNote")}>
              <EChart
                option={yearlyOption}
                ariaLabel={t("yearlyTitle")}
                className="mt-4 h-72"
              />
            </Panel>

            <Panel title={t("qualityTitle")} note={t("qualityNote")}>
              <div
                className="mt-4 flex flex-wrap gap-x-5 gap-y-2"
                aria-hidden="true"
              >
                <span className="inline-flex items-center gap-2 text-xs text-dim">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: CHART.lightgray }}
                  />
                  {td("metricNames.winRate")}
                </span>
                <span className="inline-flex items-center gap-2 text-xs text-dim">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: CHART.signal }}
                  />
                  {td("metricNames.payoff")}
                </span>
              </div>
              <EChart
                option={qualityOption}
                ariaLabel={t("qualityTitle")}
                className="mt-1 h-64"
              />
            </Panel>
          </div>
        </div>

        <p className="mt-5 max-w-3xl text-xs leading-relaxed text-dim">
          {t("seriesCaveat", {
            drawdown: folds.length
              ? `${fmtNumber(Math.min(...folds.map((f) => f.max_drawdown_points)), locale, { maximumFractionDigits: 1 })} ${pointsUnit}`
              : "",
          })}
        </p>
      </DataState>
    </section>
  );
}
