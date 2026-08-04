"use client";

import Image from "next/image";
import { ArrowUpRight, GitCommit, ShieldCheck } from "lucide-react";
import type { EChartsCoreOption } from "echarts/core";
import { EChart, CHART } from "@/components/charts/echart";
import { DynamicNetwork } from "@/components/models/dynamic-network";
import type {
  ModelResearchProfile,
  ResearchChart,
  ResearchLocale,
} from "@/config/model-research";

function chartOption(chart: ResearchChart, locale: ResearchLocale): EChartsCoreOption {
  const suffix = chart.valueSuffix ?? "";

  return {
    animationDuration: 450,
    legend: { show: false },
    grid: { left: 8, right: 14, top: 12, bottom: 8, containLabel: true },
    xAxis: {
      type: "category",
      data: chart.categories,
      axisLine: { lineStyle: { color: CHART.border } },
      axisTick: { show: false },
      axisLabel: { color: CHART.dim, margin: 12 },
    },
    yAxis: {
      type: "value",
      min: chart.minimum,
      max: chart.maximum,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: CHART.border } },
      axisLabel: {
        color: CHART.dim,
        formatter: `{value}${suffix}`,
      },
    },
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: unknown) =>
        typeof value === "number" ? `${value.toLocaleString(locale)}${suffix}` : String(value),
    },
    series: chart.series.map((series, index) => ({
      name: series.name[locale],
      type: series.type ?? "line",
      data: series.data,
      stack: series.stack,
      smooth: false,
      symbol: "circle",
      symbolSize: 7,
      showSymbol: series.type !== "line" || series.data.length <= 12,
      lineStyle: { width: 2.5, color: series.color },
      itemStyle: {
        color: series.color,
        borderColor: "#ffffff",
        borderWidth: series.type === "line" ? 2 : 0,
        borderRadius: series.type === "bar" ? [4, 4, 0, 0] : 0,
      },
      emphasis: { focus: "series" },
      ...(index === 0 && chart.baseline !== undefined
        ? {
            markLine: {
              silent: true,
              symbol: "none",
              label: {
                formatter: `${chart.baseline}${suffix}`,
                color: CHART.dim,
                position: "insideEndTop",
              },
              lineStyle: { color: CHART.faint, type: "dashed", width: 1 },
              data: [{ yAxis: chart.baseline }],
            },
          }
        : {}),
    })),
  };
}

function EvidenceChart({
  chart,
  locale,
}: {
  chart: ResearchChart;
  locale: ResearchLocale;
}) {
  return (
    <figure className="min-w-0 overflow-hidden rounded-lg border border-border bg-background p-5 shadow-sm sm:p-6">
      <figcaption>
        <h3 className="text-base font-semibold">{chart.title[locale]}</h3>
        <p className="mt-2 text-sm leading-relaxed text-dim">{chart.note[locale]}</p>
      </figcaption>
      <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2" aria-hidden="true">
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
        className="mt-2 h-72 sm:h-80"
      />
    </figure>
  );
}

export function ResearchEvidence({
  profile,
  locale,
}: {
  profile: ModelResearchProfile;
  locale: ResearchLocale;
}) {
  const sourceCommit = profile.sourceCommit.slice(0, 8);

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
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="figure text-xs uppercase tracking-[0.08em] text-brand">
              {locale === "vi" ? "Số liệu kiểm tra" : "Test results"}
            </p>
            <h2 id="research-metrics" className="title-md mt-2">
              {locale === "vi" ? "Mô hình đã được kiểm tra ra sao?" : "How was the model tested?"}
            </h2>
          </div>
          <a
            href={profile.repoUrl}
            target="_blank"
            rel="noreferrer"
            className="arrow-link inline-flex min-h-10 items-center gap-2 rounded-full border border-border px-4 text-sm font-medium text-brand hover:border-brand hover:bg-brand-soft"
          >
            {locale === "vi" ? "Xem dữ liệu và mã nguồn" : "View data and source code"}
            <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
          </a>
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

        <div className="mt-8 grid gap-6 desk:grid-cols-2">
          {profile.charts.map((chart) => (
            <EvidenceChart key={chart.id} chart={chart} locale={locale} />
          ))}
        </div>
      </section>

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

      <section className="border-t border-border pt-6" aria-label={locale === "vi" ? "Nguồn và cách đối chiếu" : "Sources and verification"}>
        <div className="flex flex-wrap gap-x-6 gap-y-3 text-xs text-dim">
          <span className="inline-flex items-center gap-2">
            <GitCommit className="h-4 w-4" aria-hidden="true" />
            commit {sourceCommit}
          </span>
          <span>{locale === "vi" ? "Kết quả cập nhật" : "Results updated"}: {profile.artifactDate}</span>
          {profile.runId && <span>run {profile.runId}</span>}
        </div>
        <p className="mt-3 max-w-4xl text-xs leading-relaxed text-dim">
          {profile.provenance[locale]}
        </p>
      </section>
    </>
  );
}
