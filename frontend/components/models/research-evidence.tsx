"use client";

import Image from "next/image";
import { ShieldCheck } from "lucide-react";
import type { EChartsCoreOption } from "echarts/core";
import { EChart, CHART } from "@/components/charts/echart";
import { cn } from "@/lib/utils";
import { DynamicNetwork } from "@/components/models/dynamic-network";
import { ForecastFan } from "@/components/models/forecast-fan";
import { NetworkClusters } from "@/components/models/network-clusters";
import { NetworkRanking } from "@/components/models/network-ranking";
import { RiskProfile } from "@/components/models/risk-profile";
import type {
  ModelResearchProfile,
  ResearchBand,
  ResearchChart,
  ResearchLocale,
} from "@/config/model-research";

/** A dashed horizontal reference at `value`, labelled with the target itself. */
function targetLine(
  value: number,
  suffix: string,
  color: string,
  locale: ResearchLocale,
) {
  return {
    silent: true,
    symbol: "none",
    label: {
      formatter: `${value.toLocaleString(locale)}${suffix}`,
      color,
      fontFamily: CHART.mono,
      fontSize: 11,
      position: "insideEndTop" as const,
    },
    lineStyle: { color, type: "dashed" as const, width: 1.5, opacity: 0.7 },
    data: [{ yAxis: value }],
  };
}

/**
 * A shaded range, built as the pair of stacked lines ECharts needs.
 *
 * The lower boundary is drawn invisibly and the visible series carries only
 * the distance up to the upper boundary, so the fill starts where the range
 * starts rather than at the axis. Both are marked `silent` — the tooltip
 * reports the boundaries from the named series above them, and a second set
 * of entries for the same numbers reads as duplicate data.
 */
function bandSeries(band: ResearchBand, index: number, locale: ResearchLocale) {
  const stack = `band-${index}`;
  const base = {
    type: "line" as const,
    stack,
    smooth: false,
    symbol: "none" as const,
    silent: true,
    lineStyle: { width: 0 },
    emphasis: { disabled: true },
  };
  return [
    { ...base, name: `${stack}-lower`, data: band.lower, areaStyle: { opacity: 0 } },
    {
      ...base,
      name: band.name[locale],
      data: band.upper.map((v, i) => Number((v - band.lower[i]).toFixed(4))),
      areaStyle: { color: band.color, opacity: band.opacity ?? 0.18 },
    },
  ];
}

function chartOption(chart: ResearchChart, locale: ResearchLocale): EChartsCoreOption {
  const suffix = chart.valueSuffix ?? "";
  const stacked = chart.series.some((s) => s.stack);
  const barCount = chart.series.filter((s) => (s.type ?? "line") === "bar").length;
  const bands = (chart.bands ?? []).flatMap((b, i) => bandSeries(b, i, locale));

  return {
    animationDuration: 450,
    // EvidenceChart renders the legend as HTML above the canvas, so the
    // built-in one would be a second copy of the same swatches.
    legend: { show: false },
    // Headroom at the top for the value labels printed above the tallest mark.
    grid: {
      left: 8,
      right: 16,
      top: 22,
      bottom: chart.xAxisLabel ? 26 : 8,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: chart.categories,
      // A band chart runs edge to edge; the default gap leaves a strip of
      // blank plot at each end that reads as missing data.
      boundaryGap: bands.length === 0,
      name: chart.xAxisLabel?.[locale],
      nameLocation: "middle" as const,
      nameGap: 34,
      nameTextStyle: { color: CHART.dim, fontSize: 11 },
      axisLine: { lineStyle: { color: CHART.border } },
      axisTick: { show: false },
      axisLabel: {
        color: CHART.dim,
        margin: 12,
        interval: chart.categoryLabelInterval ?? "auto",
      },
    },
    yAxis: {
      type: "value",
      min: chart.minimum,
      max: chart.maximum,
      axisLine: { show: false },
      axisTick: { show: false },
      // Grid lines recede behind the data rather than competing with it.
      splitLine: { lineStyle: { color: CHART.surface } },
      axisLabel: {
        color: CHART.dim,
        formatter: `{value}${suffix}`,
      },
    },
    tooltip: {
      trigger: "axis",
      // The invisible lower boundary of a band carries no meaning on its own
      // and its stacked partner reports a width, not a level. Both are left
      // out; the named series above them answer the question.
      formatter: (params: unknown) => {
        const rows = (Array.isArray(params) ? params : [params]) as {
          axisValue?: string;
          seriesName?: string;
          value?: unknown;
          color?: string;
        }[];
        const shown = rows.filter(
          (r) => r.seriesName && !/^band-\d+-lower$/.test(r.seriesName),
        );
        if (shown.length === 0) return "";
        const head = shown[0].axisValue ?? "";
        const body = shown
          .map((r) => {
            const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${r.color};margin-right:6px"></span>`;
            const v =
              typeof r.value === "number"
                ? `${r.value.toLocaleString(locale)}${suffix}`
                : String(r.value ?? "");
            return `${dot}${r.seriesName}: <b>${v}</b>`;
          })
          .join("<br/>");
        return `${head}<br/>${body}`;
      },
    },
    series: [
      ...bands,
      ...chart.series.map((series, index) => {
      const type = series.type ?? "line";
      const isBar = type === "bar";
      // Labels are worth printing on a handful of marks. A dozen of them
      // stamped along a trend line turns the line into a wall of digits, and
      // the tooltip already answers "what is this point worth".
      //
      // The count that matters is marks on the canvas, not points in this
      // series: six categories against two series is twelve numbers competing
      // for the same strip of chart. `hideOverlap` cannot rescue that — it
      // resolves collisions within a series, so labels from neighbouring
      // series still print on top of each other. Stacked bars are exempt;
      // their labels sit inside their own segment and cannot collide.
      const marks = isBar ? series.data.length * barCount : series.data.length;
      const labelled = stacked || marks <= 8;
      return {
        name: series.name[locale],
        type,
        // Bars that run below zero need their label under the bar; ECharts
        // reads "top" literally and would park it on the zero line.
        data:
          isBar && !stacked
            ? series.data.map((value) =>
                value < 0 ? { value, label: { position: "bottom" as const } } : value,
              )
            : series.data,
        stack: series.stack,
        smooth: false,
        symbol: "circle",
        symbolSize: 8,
        showSymbol: type !== "line" || series.data.length <= 12,
        lineStyle: { width: 2, color: series.color },
        // Slim bars with room between the groups. Thick blocks read as filler
        // and crowd out the numbers printed on them — but stacked series share
        // one column instead of standing side by side, so the count must not
        // narrow them: at 15% the segment labels no longer fit inside.
        ...(isBar
          ? {
              barWidth: stacked
                ? "26%"
                : barCount > 3
                  ? "15%"
                  : barCount > 1
                    ? "26%"
                    : "34%",
              barGap: !stacked && barCount > 3 ? "12%" : "24%",
            }
          : {}),
        itemStyle: {
          color: series.color,
          // A white edge separates stacked segments and keeps overlapping
          // line markers legible against neighbouring marks.
          borderColor: "#ffffff",
          borderWidth: isBar ? (stacked ? 2 : 0) : 2,
          borderRadius: isBar && !stacked ? [4, 4, 0, 0] : 0,
        },
        label: {
          show: labelled,
          position: stacked ? "inside" : "top",
          distance: 6,
          color: stacked ? "#ffffff" : CHART.ink,
          fontFamily: CHART.mono,
          fontSize: 11,
          formatter: (p: { value: number }) =>
            `${p.value.toLocaleString(locale)}${suffix}`,
        },
        // Where bars are narrow and values are small, neighbouring labels
        // collide. Dropping the ones that would overlap keeps the rest
        // readable; the tooltip still reports every value.
        labelLayout: { hideOverlap: true },
        emphasis: { focus: "series" },
        // A target line belongs to the series it judges; a shared baseline is
        // drawn once, on the first series, so it is not stamped repeatedly.
        ...(series.target !== undefined
          ? {
              markLine: targetLine(series.target, suffix, series.color, locale),
            }
          : index === 0 && chart.baseline !== undefined
            ? {
                markLine: targetLine(chart.baseline, suffix, CHART.faint, locale),
              }
            : {}),
        };
      }),
    ],
  };
}

function EvidenceChart({
  chart,
  locale,
  className,
}: {
  chart: ResearchChart;
  locale: ResearchLocale;
  className?: string;
}) {
  return (
    <figure
      className={cn(
        "min-w-0 overflow-hidden rounded-lg border border-border bg-background p-5 shadow-sm sm:p-6",
        className,
      )}
    >
      <figcaption>
        <h3 className="text-base font-semibold">{chart.title[locale]}</h3>
        <p className="mt-2 text-sm leading-relaxed text-dim">{chart.note[locale]}</p>
      </figcaption>
      <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2" aria-hidden="true">
        {(chart.bands ?? []).map((band) => (
          <span
            key={band.name[locale]}
            className="inline-flex items-center gap-2 text-xs text-dim"
          >
            {/* A square reads as an area; the round swatches mark lines. */}
            <span
              className="h-2.5 w-3.5 rounded-[2px]"
              style={{
                backgroundColor: band.color,
                opacity: (band.opacity ?? 0.18) + 0.22,
              }}
            />
            {band.name[locale]}
          </span>
        ))}
        {chart.series.map((series) => (
          <span
            key={series.name[locale]}
            className="inline-flex items-center gap-2 text-xs text-dim"
          >
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: series.color }}
            />
            {series.name[locale]}
          </span>
        ))}
      </div>
      <EChart
        option={chartOption(chart, locale)}
        ariaLabel={`${chart.title[locale]}. ${chart.note[locale]}`}
        className="mt-2 h-96 sm:h-[26rem]"
      />
    </figure>
  );
}

/**
 * Only the network model ships a per-stock research export, so the ranking
 * table and cluster charts key off the same marker the relationship map uses.
 */
const NETWORK_VISUAL = "/research/dynamic-graph-network.png";

/** The Monte-Carlo model owns the market-wide risk run. */
const RISK_MODEL = "rarf-fhe";

/**
 * Which index each research model forecasts.
 *
 * `dynamic-graph` is deliberately absent. It describes market structure and
 * publishes no forecast, so there is no distribution for the fan chart to
 * draw and the block is skipped entirely rather than rendering empty.
 */
const FORECAST_SYMBOL: Record<string, string> = {
  "raemf-mc": "VNINDEX",
  "rarf-fhe": "VNINDEX",
  msdp: "VNINDEX",
};

export function ResearchEvidence({
  profile,
  locale,
}: {
  profile: ModelResearchProfile;
  locale: ResearchLocale;
}) {
  // Absent means the model publishes no forecast, not "default to the index".
  const forecastSymbol = FORECAST_SYMBOL[profile.slug];

  return (
    <>
      <section aria-labelledby="research-verdict">
        <div className="border-l-4 border-signal bg-signal-soft px-5 py-6 sm:px-7">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-signal-dark">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            {profile.verdict.eyebrow[locale]}
          </div>
          <h2 id="research-verdict" className="mt-3 max-w-4xl text-2xl font-semibold leading-tight">
            {profile.verdict.title[locale]}
          </h2>
          <p className="mt-4 max-w-4xl leading-relaxed text-ink">
            {profile.verdict.body[locale]}
          </p>
        </div>
      </section>

      <section aria-labelledby="research-metrics">
        {/* No link to the model repository. The methodology below is what is
            published; the implementation is not. */}
        <div>
          <p className="figure text-xs uppercase tracking-[0.08em] text-brand">
            {locale === "vi" ? "Số liệu kiểm tra" : "Test results"}
          </p>
          <h2 id="research-metrics" className="title-md mt-2">
            {locale === "vi"
              ? "Mô hình đã được kiểm tra ra sao?"
              : "How was the model tested?"}
          </h2>
        </div>

        <dl className="mt-7 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4">
          {profile.metrics.map((metric) => (
            <div key={metric.label[locale]} className="bg-background p-5">
              <dt className="text-xs text-dim">{metric.label[locale]}</dt>
              <dd className="figure mt-2 text-xl font-semibold">{metric.value[locale]}</dd>
              <p className="mt-2 text-xs leading-relaxed text-dim">{metric.note[locale]}</p>
            </div>
          ))}
        </dl>

        <div
          className={cn(
            "mt-8 grid gap-6",
            // A single chart spans the row; two or more share it.
            profile.charts.length > 1 && "desk:grid-cols-2",
          )}
        >
          {profile.charts.map((chart, i) => (
            <EvidenceChart
              key={chart.id}
              chart={chart}
              locale={locale}
              // An odd count leaves the last chart beside an empty half-row,
              // which reads as a panel that failed to load. It takes the
              // width instead.
              className={cn(
                profile.charts.length % 2 === 1 &&
                  i === profile.charts.length - 1 &&
                  "desk:col-span-2",
              )}
            />
          ))}
        </div>
      </section>

      {/* Each model gets the view that matches what it publishes. The network
          model ranks stocks; the forecasting models publish a distribution,
          and each block removes itself when its model publishes nothing. */}
      {profile.visual?.src === NETWORK_VISUAL && (
        <>
          <NetworkRanking locale={locale} asOf={profile.artifactDate} />
          <NetworkClusters locale={locale} />
        </>
      )}
      {forecastSymbol && (
        <ForecastFan
          slug={profile.slug}
          symbol={forecastSymbol}
          locale={locale}
        />
      )}
      {profile.slug === RISK_MODEL && <RiskProfile locale={locale} />}

      {profile.visual && (
        <section aria-labelledby="research-visual">
          <h2 id="research-visual" className="title-md">
            {locale === "vi" ? "Bản đồ liên kết mới nhất" : "Latest relationship map"}
          </h2>
          <figure className="mt-6 overflow-hidden rounded-lg border border-border bg-background shadow-sm">
            {profile.visual.src === "/research/dynamic-graph-network.png" ? (
              <DynamicNetwork locale={locale} />
            ) : (
              <div className="relative aspect-[16/9] w-full bg-surface">
                <Image
                  src={profile.visual.src}
                  alt={profile.visual.alt[locale]}
                  fill
                  sizes="(max-width: 960px) 100vw, 1200px"
                  className="object-contain"
                />
              </div>
            )}
            <figcaption className="border-t border-border px-5 py-4 text-sm leading-relaxed text-dim">
              {profile.visual.caption[locale]}
            </figcaption>
          </figure>
        </section>
      )}

      <section className="grid gap-10 desk:grid-cols-[1.15fr_0.85fr]" aria-labelledby="research-method">
        <div>
          <h2 id="research-method" className="title-md">
            {locale === "vi" ? "Mô hình hoạt động như thế nào?" : "How does the model work?"}
          </h2>
          <ol className="mt-6 space-y-5">
            {profile.method[locale].map((item, index) => (
              <li key={item} className="grid grid-cols-[2rem_1fr] gap-3">
                <span className="figure flex h-8 w-8 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand">
                  {index + 1}
                </span>
                <p className="pt-1 text-sm leading-relaxed text-ink">{item}</p>
              </li>
            ))}
          </ol>
        </div>
        <div>
          <h2 className="title-md">
            {locale === "vi" ? "Điều cần lưu ý" : "What should readers keep in mind?"}
          </h2>
          <ul className="mt-6 space-y-4">
            {profile.findings[locale].map((item) => (
              <li key={item} className="flex gap-3 text-sm leading-relaxed text-ink">
                <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-signal" aria-hidden="true" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Provenance without internals. The date tells a reader how current the
          figures are, which is the part that concerns them. Commit hashes and
          internal run identifiers are build detail and are not published. */}
      <section
        className="border-t border-border pt-6"
        aria-label={locale === "vi" ? "Nguồn số liệu" : "Data provenance"}
      >
        <div className="flex flex-wrap gap-x-6 gap-y-3 text-xs text-dim">
          <span className="inline-flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            {locale === "vi" ? "Kết quả cập nhật" : "Results updated"}:{" "}
            {profile.artifactDate}
          </span>
        </div>
        <p className="mt-3 max-w-4xl text-xs leading-relaxed text-dim">
          {profile.provenance[locale]}
        </p>
      </section>
    </>
  );
}
