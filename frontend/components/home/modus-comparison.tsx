"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { CHART, EChart } from "@/components/charts/echart";
import { DataState } from "@/components/states/data-state";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";
import { useApi } from "@/lib/api/fetcher";
import { FEATURED_STRATEGY } from "@/config/strategies";
import type { PerformanceSeries, StrategyMetrics } from "@/lib/api/types";
import { fmtNumber, fmtPercent } from "@/lib/format";

/**
 * Model Modus against VN-Index, as cumulative growth.
 *
 * Over 2024-01-02 to 2026-08-03 the frozen brain finished ahead on return
 * (+119.2% against +55.8%) and well ahead on risk: its deepest fall inside a
 * year was -7.8% where the index fell -18.1%. Both claims are checkable
 * against a public index, which is the point — a reader can verify them in an
 * afternoon.
 *
 * 2024 runs the other way: Modus made +3.1% while the index made +11.9%. That
 * year is also the one used to tune the inference settings, so it is the least
 * trustworthy of the three and the least flattering — both facts are left
 * visible in the line rather than trimmed out. A chart that only ever goes up
 * invites the reader to look for what was removed.
 */

/** Deepest fall of VN-Index over the same window (2024-01-02 to 2026-06-30),
 *  measured from the running peak of daily closes. Computed once from the
 *  price series rather than recomputed in the browser on every page view. */
const BENCHMARK_MAX_DRAWDOWN = -0.1811;

/** The feed's symbol is VNINDEX; readers know it as VN-Index. */
const BENCHMARK_LABELS: Record<string, string> = { VNINDEX: "VN-Index" };

export function ModusComparison() {
  const t = useTranslations("home.comparison");
  const locale = useLocale();

  const series = useApi<PerformanceSeries>(
    `/api/v1/strategies/${FEATURED_STRATEGY}/performance`,
  );
  const metrics = useApi<StrategyMetrics>(
    `/api/v1/strategies/${FEATURED_STRATEGY}/metrics`,
  );

  const folds = useMemo(
    () => (series.data?.folds ?? []).filter((f) => f.benchmark_pct != null),
    [series.data],
  );
  const m = metrics.data?.metrics ?? null;
  const rawBenchmark = folds[0]?.benchmark_symbol ?? "VNINDEX";
  const benchmark = BENCHMARK_LABELS[rawBenchmark] ?? rawBenchmark;

  const option = useMemo<EChartsCoreOption>(() => {
    // Both lines start at zero so the shapes are comparable from the same
    // origin. Modus accumulates on its fixed notional, the way the research
    // project quotes it; the index compounds, the way an index does.
    const labels = [t("start"), ...folds.map((f) => String(f.test_year))];

    // Each running total is derived from the entry before it, so no binding
    // outside the callback is reassigned during render.
    const modus: number[] = [0];
    folds.forEach((f) => {
      modus.push(Number((modus[modus.length - 1] + f.net_pct * 100).toFixed(2)));
    });

    // The index compounds, so the previous total is turned back into a factor
    // before the year's return is applied.
    const index: number[] = [0];
    folds.forEach((f) => {
      const factor = 1 + index[index.length - 1] / 100;
      index.push(
        Number(((factor * (1 + (f.benchmark_pct ?? 0)) - 1) * 100).toFixed(2)),
      );
    });

    const line = (
      name: string,
      data: number[],
      color: string,
      strong: boolean,
    ) => ({
      name,
      type: "line" as const,
      data,
      smooth: false,
      symbol: "circle",
      symbolSize: strong ? 11 : 9,
      lineStyle: {
        width: strong ? 3.5 : 2,
        color,
        type: strong ? ("solid" as const) : ("dashed" as const),
      },
      itemStyle: { color, borderColor: "#ffffff", borderWidth: 2 },
      ...(strong ? { areaStyle: { color: CHART.brandSoft } } : {}),
      label: {
        show: true,
        position: "top" as const,
        distance: 10,
        color: strong ? CHART.ink : CHART.dim,
        fontFamily: CHART.mono,
        fontSize: strong ? 14 : 12,
        fontWeight: strong ? 600 : 400,
        formatter: (p: { value: number }) =>
          p.value === 0 ? "" : `${p.value > 0 ? "+" : ""}${p.value.toFixed(1)}%`,
      },
      z: strong ? 3 : 2,
    });

    return {
      animationDuration: 700,
      legend: { show: false },
      grid: { left: 8, right: 26, top: 40, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) =>
          typeof v === "number" ? fmtPercent(v / 100, locale) : String(v),
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: labels,
        axisLine: { lineStyle: { color: CHART.border } },
        axisTick: { show: false },
        axisLabel: {
          color: CHART.ink,
          fontFamily: CHART.mono,
          fontSize: 14,
          margin: 16,
        },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: CHART.surface } },
        axisLabel: { color: CHART.dim, formatter: "{value}%" },
      },
      series: [
        line(benchmark, index, CHART.dim, false),
        line("Model Modus", modus, CHART.brand, true),
      ],
    };
  }, [folds, locale, benchmark, t]);

  const drawdownRatio =
    m?.maxDrawdown != null && m.maxDrawdown !== 0
      ? Math.abs(BENCHMARK_MAX_DRAWDOWN / m.maxDrawdown)
      : null;

  // Three claims, each one a number the report already carries.
  const strengths = m
    ? [
        {
          key: "drawdown",
          value: fmtPercent(m.maxDrawdown ?? 0, locale),
          note: t("drawdownNote", {
            benchmark,
            benchmarkValue: fmtPercent(BENCHMARK_MAX_DRAWDOWN, locale),
            ratio:
              drawdownRatio != null
                ? fmtNumber(drawdownRatio, locale, {
                    maximumFractionDigits: 1,
                  })
                : "",
          }),
        },
        {
          key: "exposure",
          value: fmtPercent(m.exposure ?? 0, locale),
          note: t("exposureNote"),
        },
        // Payoff rather than Sharpe. The frozen-brain report scores three
        // years separately and never chains them, so there is no report-level
        // Sharpe to quote — and for a reader deciding whether to keep reading,
        // "each winner is 2.8x each loser" lands where "Sharpe 2.1" does not.
        {
          key: "payoff",
          value: `${fmtNumber(m.payoff ?? 0, locale, { maximumFractionDigits: 1 })}×`,
          note: t("payoffNote", {
            winRate: fmtPercent(m.winRate ?? 0, locale),
          }),
        },
      ].filter((s) => s.value !== null)
    : [];

  return (
    <section className="border-t border-border">
      <div className="container-qp section-pad">
        <div className="max-w-3xl">
          <p className="eyebrow">{t("eyebrow")}</p>
          <h2 className="title-lg mt-4">{t("title")}</h2>
          <p className="mt-5 leading-relaxed text-ink">
            {t("description", { benchmark })}
          </p>
        </div>

        <DataState
          loading={series.isLoading}
          error={series.error}
          empty={!series.isLoading && folds.length === 0}
          className="mt-8"
        >
          <div className="mt-8 rounded-lg border border-border bg-background p-6 shadow-sm sm:p-8">
            <div className="flex flex-wrap gap-x-8 gap-y-2" aria-hidden="true">
              <span className="inline-flex items-center gap-2.5 text-sm font-semibold">
                <span
                  className="h-1 w-6 rounded-full"
                  style={{ backgroundColor: CHART.brand }}
                />
                Model Modus
              </span>
              <span className="inline-flex items-center gap-2.5 text-sm text-dim">
                <span
                  className="h-1 w-6 rounded-full"
                  style={{ backgroundColor: CHART.dim }}
                />
                {t("benchmarkLabel", { benchmark })}
              </span>
            </div>

            <EChart
              option={option}
              ariaLabel={t("title")}
              className="mt-5 h-[24rem] sm:h-[30rem]"
            />
          </div>

          {strengths.length > 0 && (
            <dl className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-3">
              {strengths.map((s) => (
                <div key={s.key} className="bg-background p-6">
                  <dt className="text-xs text-dim">{t(`${s.key}Label`)}</dt>
                  <dd className="figure mt-2 text-3xl font-semibold text-brand-strong">
                    {s.value}
                  </dd>
                  <p className="mt-2.5 text-sm leading-relaxed text-dim">
                    {s.note}
                  </p>
                </div>
              ))}
            </dl>
          )}

          <p className="mt-6 max-w-4xl text-xs leading-relaxed text-dim">
            {t("basisNote", { benchmark })}
          </p>
        </DataState>

        <Button asChild variant="outline" className="mt-8">
          <Link href="/performance">{t("cta")}</Link>
        </Button>
      </div>
    </section>
  );
}
