"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { CHART, EChart } from "@/components/charts/echart";
import { DataState } from "@/components/states/data-state";
import { MetricCounter } from "@/components/home/metric-counter";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";
import { useApi } from "@/lib/api/fetcher";
import { useMediaQuery } from "@/lib/use-media-query";
import { FEATURED_STRATEGY } from "@/config/strategies";
import type { PerformanceSeries, StrategyMetrics } from "@/lib/api/types";
import { fmtNumber, fmtPercent } from "@/lib/format";

/**
 * Model Modus against VN-Index, as cumulative growth.
 *
 * Over 2024 to 2026-08-03 Modus finished ahead on return (+135.2% against
 * +55.8%) and well ahead on risk: its deepest fall inside a year was -8.9%
 * where the index fell -18.1%. Both claims are checkable against a public
 * index, which is the point — a reader can verify them in an afternoon.
 *
 * 2024 is the weakest of the three and the one the model was tuned on, so it
 * is the least flattering and the least trustworthy at the same time. It
 * stays in the line rather than being trimmed out.
 */

/** Deepest fall of VN-Index over the same window (2024-01-02 to 2026-08-03),
 *  measured from the running peak of daily closes. Computed once from the
 *  price series rather than recomputed in the browser on every page view. */
const BENCHMARK_MAX_DRAWDOWN = -0.1811;

/** The feed's symbol is VNINDEX; readers know it as VN-Index. */
const BENCHMARK_LABELS: Record<string, string> = { VNINDEX: "VN-Index" };

/**
 * Chart colours for the dark panel this section now sits on.
 *
 * `CHART.brand` is the accent at its light-ground lightness and disappears
 * against `--accent-deep`; `accent` here is the same hue lifted to read on
 * dark, matching `--accent-lift` in the stylesheet. These are duplicated as
 * literals because ECharts paints to a canvas and cannot resolve `var()`.
 */
const DARK = {
  /* The panel the plot is drawn on — lighter than the section, so the chart
   * has a surface of its own. `bg` is what the point markers are ringed in,
   * so it has to be the panel colour and not the section's. */
  bg: "#17304c",
  panel: "#1e3d5e",
  line: "rgba(255,255,255,0.16)",
  dim: "rgba(255,255,255,0.58)",
  /* Brighter than the section's `--accent-lift`. That value is tuned for text
   * on `--accent-deep`; a 4px line has far less ink than a letterform and was
   * losing against the panel. */
  accent: "#9cc6ec",
  area: "rgba(156,198,236,0.2)",
};

export function ModusComparison() {
  const t = useTranslations("home.comparison");
  const locale = useLocale();
  const narrow = useMediaQuery("(max-width: 640px)");

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
        width: strong ? 4 : 2,
        color,
        type: strong ? ("solid" as const) : ("dashed" as const),
      },
      // The point rings are the section's own background, so a marker reads as
      // a hole punched through the line rather than as a dot sitting on it.
      itemStyle: { color, borderColor: DARK.bg, borderWidth: 2 },
      ...(strong ? { areaStyle: { color: DARK.area } } : {}),
      label: {
        show: true,
        // Modus above its line, the index below its own. Both sat above, and
        // because both curves rise steeply to the right a centred label always
        // had the next segment of some line running through it. Sending the
        // lower series downward puts each label in the empty space beside its
        // own curve instead.
        position: strong ? ("top" as const) : ("bottom" as const),
        distance: 12,
        color: strong ? "#ffffff" : "rgba(255,255,255,0.72)",
        fontFamily: CHART.mono,
        fontSize: narrow ? (strong ? 12 : 10) : strong ? 14 : 12,
        fontWeight: strong ? 600 : 400,
        formatter: (p: { value: number }) =>
          p.value === 0 ? "" : `${p.value > 0 ? "+" : ""}${p.value.toFixed(1)}%`,
      },
      // Point labels are centred on their point, so the last one on the right
      // overhangs the plot and the two lines' labels collide wherever the
      // curves converge. On a phone that produced a clipped "%" on the final
      // figure and overlapping glyphs at every crossing. ECharts resolves the
      // collisions itself once told to; the overhang is handled by the grid's
      // right inset below.
      labelLayout: { hideOverlap: true },
      z: strong ? 3 : 2,
    });

    return {
      animationDuration: 700,
      legend: { show: false },
      // `containLabel` reserves room for axis labels but not for series point
      // labels, so the right inset is what keeps the final "+135.2%" inside
      // the canvas. It needs to be roughly half that label's width, which is
      // wider relative to the plot on a phone than on a desktop.
      grid: {
        left: 8,
        right: narrow ? 42 : 30,
        top: narrow ? 46 : 40,
        bottom: 8,
        containLabel: true,
      },
      tooltip: {
        trigger: "axis",
        // The shared base style gives the tooltip a white card, which on this
        // section would be the only bright rectangle on a dark panel.
        backgroundColor: DARK.panel,
        borderColor: DARK.line,
        textStyle: { color: "#ffffff", fontFamily: CHART.mono, fontSize: 12 },
        axisPointer: { lineStyle: { color: DARK.line, width: 1 } },
        extraCssText: "box-shadow:0 12px 34px rgba(0,0,0,0.45);",
        valueFormatter: (v: unknown) =>
          typeof v === "number" ? fmtPercent(v / 100, locale) : String(v),
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: labels,
        axisLine: { lineStyle: { color: DARK.line } },
        axisTick: { show: false },
        // At 14px the four category labels did not fit across a phone and
        // ECharts silently dropped the last one — the chart ran to 2026 with
        // no 2026 on the axis. Smaller type fits all four; `interval: 0`
        // makes the dropping impossible rather than merely unlikely, and
        // `hideOverlap` is the safety net if a longer label ever appears.
        axisLabel: {
          color: "#ffffff",
          fontFamily: CHART.mono,
          fontSize: narrow ? 11 : 14,
          margin: narrow ? 10 : 16,
          interval: 0,
          hideOverlap: true,
        },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: DARK.line } },
        axisLabel: { color: DARK.dim, formatter: "{value}%" },
      },
      series: [
        line(benchmark, index, DARK.dim, false),
        line("Model Modus", modus, DARK.accent, true),
      ],
    };
  }, [folds, locale, benchmark, t, narrow]);

  const drawdownRatio =
    m?.maxDrawdown != null && m.maxDrawdown !== 0
      ? Math.abs(BENCHMARK_MAX_DRAWDOWN / m.maxDrawdown)
      : null;

  // Three claims, each one a number the report already carries. Each carries
  // its raw value and its formatter separately so the figure can be counted
  // up — the formatter is applied to every intermediate frame, which is what
  // keeps "-8,9%" reading correctly in Vietnamese all the way through.
  const strengths = m
    ? [
        {
          key: "drawdown",
          raw: m.maxDrawdown ?? 0,
          format: (v: number) => fmtPercent(v, locale),
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
          raw: m.exposure ?? 0,
          format: (v: number) => fmtPercent(v, locale),
          note: t("exposureNote"),
        },
        // Payoff rather than Sharpe. The two years are scored separately and
        // never chained, so there is no report-level Sharpe to quote — and for
        // a reader deciding whether to keep reading, "each winner is 2.5x each
        // loser" lands where "Sharpe 2.8" does not.
        {
          key: "payoff",
          raw: m.payoff ?? 0,
          format: (v: number) =>
            `${fmtNumber(v, locale, { maximumFractionDigits: 1 })}×`,
          note: t("payoffNote", { winRate: fmtPercent(m.winRate ?? 0, locale) }),
        },
      ]
    : [];

  return (
    /*
      The one dark section on the site. This is the flagship claim, so it is
      the one that gets the contrast — and a single dark band is what gives the
      homepage a floor to measure its white sections against.
    */
    /*
      Two sections, not one, because the chart panel is meant to straddle the
      seam between them: it hangs out of the bottom of the dark band and lands
      on the white one, which is the only thing on the page that occupies two
      surfaces at once.

      Notably NOT `overflow-hidden` on the dark section — that was there for the
      grid texture, and it would have clipped the overhanging panel flat against
      the section edge. The texture is `inset: 0` and never overflows anyway.
    */
    <>
    <section className="on-dark relative">
      <div aria-hidden="true" className="grid-dark" />
      <div aria-hidden="true" className="numeral-clip">
        <span className="section-numeral">01</span>
      </div>
      {/*
        The `min-h` is a floor, not a layout. The white section below is pulled
        up by a fixed 112/144px, so anything that makes this section shorter
        than the headline plus that overhang gets the headline painted over.
        `DataState` below reserves the panel's own height, which is what
        normally holds this open; the floor is the guard for whatever renders
        here next. A `padding-bottom` would do the same job and must not be
        used — see the note on the panel.
      */}
      <div className="container-qp relative min-h-[34rem] pt-20 desk:min-h-[44rem] desk:pt-32">
        {/* The four-sentence paragraph that stood here restated the chart in
            prose — same period, same comparison, same conclusion — and the
            chart is the version a reader can check. */}
        <div className="max-w-3xl">
          <p className="eyebrow">
            <span className="tick text-accent-lift/70">01</span>
            {t("eyebrow")}
          </p>
          <h2 className="title-lg mt-5 text-white">{t("title")}</h2>
        </div>

        {/*
          `reserve` is the panel's own height, to the pixel: p-5/p-7, the
          legend row, its `mt-5`, and the canvas. The series is fetched on the
          client with no server fallback, so loading — and error, permanently,
          if the API has no report to give — used to shrink this section from
          923px to ~400px and let the white overhang cut through the headline.
          Holding the space means the seam is where it was measured to be
          whether or not the data arrives, and nothing shifts when it does.

          `tone` because the notices default to a near-white card that cannot
          be seen at all against the section.
        */}
        <DataState
          loading={series.isLoading}
          error={series.error}
          empty={!series.isLoading && folds.length === 0}
          className="mt-10"
          reserve="min-h-[29rem] sm:min-h-[36rem]"
          tone="dark"
        >
          {/*
            The plot sits on its own panel, a step lighter than the section.

            It was drawn straight onto the section for a while, on the argument
            that the section is already a surface and boxing the chart inside it
            would be a rectangle inside a rectangle. That was wrong in practice:
            the section carries a measurement grid, so the chart's own gridlines
            landed on top of a second set at a different pitch, and the plot had
            no ground to separate it from the texture. An opaque panel both
            gives the chart a surface and hides the decorative grid behind it.
          */}
          {/*
            `z-10` is what puts the panel over the white section that is pulled
            up beneath it. The pull itself lives on that section as an explicit
            negative top margin, not here as a negative bottom margin: a bottom
            margin on this element collapses out through the container and the
            section, so the overhang would silently disappear the day anyone
            gave the dark section a `padding-bottom` or a border.
          */}
          <div className="relative z-10 mt-12 rounded-xl border border-white/10 bg-[#17304c] p-5 shadow-[0_28px_70px_-26px_rgb(0_0_0_/_0.75)] sm:p-7">
            <div className="flex flex-wrap gap-x-8 gap-y-2" aria-hidden="true">
              <span className="inline-flex items-center gap-2.5 text-sm font-medium text-white">
                <span
                  className="h-1 w-6 rounded-full"
                  style={{ backgroundColor: DARK.accent }}
                />
                Model Modus
              </span>
              <span className="inline-flex items-center gap-2.5 text-sm text-white/55">
                <span
                  className="h-1 w-6 rounded-full"
                  style={{ backgroundColor: DARK.dim }}
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
        </DataState>
      </div>
    </section>

    {/*
      The white half, pulled up under the dark one so the chart panel spans the
      seam. Two things here are load bearing:

        * `relative`. The dark section is positioned (it hosts the grid texture
          and the numeral), and a positioned element paints above a static one
          regardless of document order — so while this section was static the
          dark band was drawn on top of it and covered the entire overhang. It
          only has to be positioned too; document order then decides, and the
          panel's own `z-10` keeps it above both.
        * The top padding clears the overhang. It is `pt` minus `mt` of real
          space above the figures, so reducing either one lands the chart on
          top of them.

      The pull is a fixed distance measured against a section that is as tall
      as the panel, which only holds because the panel's height is reserved on
      the `DataState` above for the states where there is no panel. These two
      numbers are one decision: changing this `-mt`, that `reserve`, or the
      chart's own height without the others puts the white edge back through
      the headline.
    */}
    <section className="relative -mt-28 bg-background desk:-mt-36">
      <div className="container-qp pb-20 pt-40 desk:pb-32 desk:pt-52">
        {/* Three figures, unboxed and run large. They used to sit in a
            bordered grid of equal cells, which gave them the weight of table
            rows; at this size, separated by a hairline each, the row reads as
            three statements rather than as a table. */}
        {strengths.length > 0 && (
          <dl className="grid gap-x-10 gap-y-12 sm:grid-cols-3">
            {strengths.map((s) => (
              <div key={s.key} className="border-t border-border pt-7">
                <dd className="figure text-[clamp(48px,6.5vw,86px)] font-medium leading-none tracking-[-0.035em] text-accent">
                  <MetricCounter value={s.raw} format={s.format} />
                </dd>
                <dt className="mt-5 text-sm font-medium text-foreground">
                  {t(`${s.key}Label`)}
                </dt>
                <p className="mt-2 text-sm leading-relaxed text-dim">
                  {s.note}
                </p>
              </div>
            ))}
          </dl>
        )}

        {/* Kept, and kept short. It is the one line that stops the chart
            being read as like for like — a leveraged futures system against
            an unleveraged index. */}
        <p className="mt-12 max-w-3xl text-xs leading-relaxed text-dim">
          {t("basisNote", { benchmark })}
        </p>

        <Button asChild variant="outline" className="mt-10">
          <Link href="/performance">{t("cta")}</Link>
        </Button>
      </div>
    </section>
    </>
  );
}
