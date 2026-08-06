"use client";

import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { ApiError, useApi } from "@/lib/api/fetcher";
import type { ForecastRecord } from "@/lib/api/types";
import { CHART, EChart } from "@/components/charts/echart";
import { fmtPercent, fmtPrice } from "@/lib/format";

/**
 * Forecast range by horizon, for models that publish a distribution.
 *
 * MSDP and RARF-FHE do not forecast a number, they forecast a spread. A row
 * of point estimates hides that entirely; the honest picture is how wide the
 * band gets as the horizon lengthens, anchored at today's index level. The
 * widening itself is the message — a 60-session band four times the width of
 * the 5-session one says more about the model than any single figure.
 *
 * Renders nothing when the model publishes no forecast, so a page for a model
 * that only does research does not carry an empty frame.
 */

const COPY = {
  vi: {
    title: "Phạm vi dự báo theo từng thời hạn",
    lead: "Cột dọc là khoảng dự báo {level}: mô hình cho rằng chỉ số nhiều khả năng nằm trong khoảng này. Chấm giữa là giá trị trung vị. Khoảng càng rộng khi nhìn xa hơn nghĩa là mô hình càng ít chắc chắn.",
    axis: "Số phiên tới",
    now: "Hiện tại",
    band: "Khoảng dự báo",
    median: "Trung vị",
    sessions: "phiên",
    prob: "Khả năng tăng",
    vol: "Biến động dự kiến",
  },
  en: {
    title: "Forecast range by horizon",
    lead: "Each bar is the {level} forecast interval: the model expects the index to land inside it. The dot is the median. A band that widens with the horizon means the model is less certain further out.",
    axis: "Sessions ahead",
    now: "Now",
    band: "Forecast range",
    median: "Median",
    sessions: "sessions",
    prob: "Chance of rising",
    vol: "Expected volatility",
  },
} as const;

export function ForecastFan({
  slug,
  symbol,
  locale,
}: {
  slug: string;
  symbol: string;
  locale: "vi" | "en";
}) {
  const t = COPY[locale];
  const { data, error } = useApi<{ records: ForecastRecord[] }>(
    `/api/v1/models/${slug}/latest?symbol=${symbol}`
  );

  const records = useMemo(
    () => [...(data?.records ?? [])].sort((a, b) => a.horizon - b.horizon),
    [data]
  );

  const option = useMemo<EChartsCoreOption>(() => {
    const horizons = records.map((r) => String(r.horizon));
    // A floating bar needs a base and a height: ECharts stacks a transparent
    // segment under the visible one.
    const base = records.map((r) => r.interval_lower);
    const span = records.map((r) => r.interval_upper - r.interval_lower);
    const median = records.map((r) => r.forecast_value);
    const low = Math.min(...base);
    const high = Math.max(...records.map((r) => r.interval_upper));
    const pad = (high - low) * 0.08;

    return {
      grid: { left: 8, right: 20, top: 34, bottom: 44, containLabel: true },
      xAxis: {
        type: "category",
        data: horizons,
        name: t.axis,
        nameLocation: "middle",
        nameGap: 30,
        nameTextStyle: { color: CHART.dim, fontSize: 12 },
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: { color: CHART.dim },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        min: Math.floor(low - pad),
        max: Math.ceil(high + pad),
        axisLabel: { color: CHART.dim },
        splitLine: { lineStyle: { color: CHART.surface } },
      },
      tooltip: {
        trigger: "axis",
        formatter: (params: { dataIndex: number }[]) => {
          const r = records[params[0].dataIndex];
          if (!r) return "";
          return [
            `<b>${r.horizon} ${t.sessions}</b>`,
            `${t.median}: ${fmtPrice(r.forecast_value, locale)}`,
            `${t.band}: ${fmtPrice(r.interval_lower, locale)} – ${fmtPrice(r.interval_upper, locale)}`,
            `${t.prob}: ${fmtPercent(r.probability_up, locale)}`,
            `${t.vol}: ${fmtPercent(r.volatility, locale)}`,
          ].join("<br/>");
        },
      },
      legend: {
        data: [t.band, t.median],
        top: 0,
        left: 0,
        itemWidth: 16,
        itemHeight: 3,
        icon: "roundRect",
        textStyle: { color: CHART.ink, fontFamily: CHART.mono, fontSize: 12 },
      },
      series: [
        {
          name: "base",
          type: "bar",
          stack: "range",
          silent: true,
          itemStyle: { color: "transparent" },
          data: base,
          barWidth: "42%",
          legendHoverLink: false,
        },
        {
          name: t.band,
          type: "bar",
          stack: "range",
          data: span,
          barWidth: "42%",
          itemStyle: {
            color: CHART.brand,
            opacity: 0.28,
            borderRadius: [4, 4, 4, 4],
          },
        },
        {
          name: t.median,
          type: "scatter",
          data: median,
          symbolSize: 12,
          itemStyle: {
            color: CHART.brand,
            borderColor: "#ffffff",
            borderWidth: 2,
          },
        },
      ],
    };
  }, [records, t, locale]);

  // A model that publishes no forecast returns 404 by design.
  if (error instanceof ApiError && error.status === 404) return null;
  if (records.length === 0) return null;

  const level = fmtPercent(records[0].interval_level, locale, 0);

  return (
    <section className="mt-14">
      <h2 className="title-md">{t.title}</h2>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-ink">
        {t.lead.replace("{level}", level)}
      </p>
      {/* Chart only. The page already opens with per-horizon cards carrying
          the same figures; repeating them here read as padding. What this
          adds is the comparison across horizons, which those cards cannot
          show side by side. Values stay reachable on hover. */}
      <div className="qp-panel mt-6 p-5">
        <EChart option={option} ariaLabel={t.title} className="h-[26rem]" />
      </div>
    </section>
  );
}
