"use client";

import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { ApiError, useApi } from "@/lib/api/fetcher";
import type { RiskDashboard } from "@/lib/api/types";
import { CHART, EChart } from "@/components/charts/echart";
import { InfoTip } from "@/components/info-tip";
import { fmtPercent } from "@/lib/format";

/**
 * Drawdown exceedance curve plus the loss measures behind it.
 *
 * The Monte-Carlo model's output is a probability attached to each depth of
 * fall, which a bar chart of unrelated buckets does not convey. Plotted as a
 * curve — "how likely is a fall of at least this much" — the shape is the
 * answer, and the steepness between two thresholds is readable directly.
 *
 * Hidden when no risk run has been published, rather than shown empty.
 */

const COPY = {
  vi: {
    title: "Khả năng sụt giảm ở các mức",
    lead: "Đường cong cho biết xác suất chỉ số giảm ít nhất tới từng mức, theo mô phỏng của mô hình. Ví dụ điểm ở mức 5% cho biết khả năng xảy ra một đợt giảm từ 5% trở lên.",
    xAxis: "Mức giảm",
    yAxis: "Khả năng xảy ra",
    curve: "Khả năng giảm ít nhất tới mức này",
    paths: "kịch bản mô phỏng",
    var95: "Ngưỡng lỗ 95% (VaR)",
    var95Tip:
      "Trong 95 trên 100 kịch bản, mức lỗ không vượt quá con số này. Không phải mức lỗ tối đa.",
    es95: "Lỗ trung bình khi vượt ngưỡng",
    es95Tip: "Mức lỗ trung bình trong 5% kịch bản xấu nhất.",
    drawdown: "Đang giảm từ đỉnh",
    vol: "Biến động",
    state: "Trạng thái rủi ro",
  },
  en: {
    title: "Likelihood of a fall of each size",
    lead: "The curve gives the probability that the index falls at least as far as each level, across the model's simulations. The point at 5%, for example, is the chance of a fall of 5% or more.",
    xAxis: "Size of fall",
    yAxis: "Probability",
    curve: "Chance of falling at least this far",
    paths: "simulated paths",
    var95: "95% loss threshold (VaR)",
    var95Tip:
      "In 95 of 100 simulated paths the loss stays inside this figure. Not a worst case.",
    es95: "Average loss beyond the threshold",
    es95Tip: "Mean loss across the worst 5% of paths.",
    drawdown: "Current fall from peak",
    vol: "Volatility",
    state: "Risk state",
  },
} as const;

export function RiskProfile({ locale }: { locale: "vi" | "en" }) {
  const t = COPY[locale];
  const { data, error } = useApi<RiskDashboard>("/api/v1/market/risk");

  const buckets = useMemo(
    () =>
      [...(data?.mc_drawdown_distribution ?? [])].sort(
        (a, b) => Math.abs(a.bucket) - Math.abs(b.bucket)
      ),
    [data]
  );

  const option = useMemo<EChartsCoreOption>(
    () => ({
      grid: { left: 8, right: 22, top: 30, bottom: 44, containLabel: true },
      xAxis: {
        type: "category",
        data: buckets.map((b) => fmtPercent(Math.abs(b.bucket), locale, 0)),
        name: t.xAxis,
        nameLocation: "middle",
        nameGap: 30,
        nameTextStyle: { color: CHART.dim, fontSize: 12 },
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: { color: CHART.dim },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        // No axis name: it sits at the top-left, which is where the series
        // label also lands, and the two overlapped into unreadable text. The
        // percentage ticks and the section heading already say what this is.
        min: 0,
        max: 1,
        axisLabel: {
          color: CHART.dim,
          formatter: (v: number) => fmtPercent(v, locale, 0),
        },
        splitLine: { lineStyle: { color: CHART.surface } },
      },
      // One series needs no legend box — the heading names it.
      legend: { show: false },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) => fmtPercent(Number(v), locale),
      },
      series: [
        {
          name: t.curve,
          type: "line",
          data: buckets.map((b) => b.probability),
          smooth: 0.25,
          symbolSize: 9,
          lineStyle: { color: CHART.negative, width: 2 },
          itemStyle: {
            color: CHART.negative,
            borderColor: "#ffffff",
            borderWidth: 2,
          },
          areaStyle: { color: CHART.negative, opacity: 0.1 },
          label: {
            show: true,
            position: "top",
            distance: 10,
            color: CHART.ink,
            fontFamily: CHART.mono,
            fontSize: 11,
            formatter: (p: { value: number }) =>
              fmtPercent(p.value, locale, 0),
          },
        },
      ],
    }),
    [buckets, t, locale]
  );

  if (error instanceof ApiError && error.status === 503) return null;
  if (!data || buckets.length === 0) return null;

  const tiles = [
    {
      label: t.var95,
      tip: t.var95Tip,
      value: data.var_95 === null ? "—" : fmtPercent(data.var_95, locale),
    },
    {
      label: t.es95,
      tip: t.es95Tip,
      value: data.es_95 === null ? "—" : fmtPercent(data.es_95, locale),
    },
    {
      label: t.drawdown,
      value: fmtPercent(data.current_drawdown, locale),
    },
    { label: t.vol, value: fmtPercent(data.volatility, locale) },
  ];

  return (
    <section className="mt-14">
      <h2 className="title-md">{t.title}</h2>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-ink">{t.lead}</p>

      <div className="qp-panel mt-6 p-5">
        <EChart option={option} ariaLabel={t.title} className="h-96" />
        <p className="figure mt-2 text-right text-xs text-dim">
          {data.mc_paths.toLocaleString(locale)} {t.paths}
        </p>

        <div className="mt-5 grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2 desk:grid-cols-4">
          {tiles.map((tile) => (
            <div key={tile.label} className="bg-background p-4">
              <p className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.06em] text-dim">
                {tile.label}
                {tile.tip && <InfoTip text={tile.tip} />}
              </p>
              <p className="figure mt-2 text-xl font-medium">{tile.value}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
