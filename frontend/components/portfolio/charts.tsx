"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { EChart, CHART } from "@/components/charts/echart";
import { useSpanLabel } from "@/components/portfolio/span";
import type {
  CrisisScenario,
  MarginRisk,
  PortfolioAnalysis,
  ReturnHistogram,
} from "@/lib/api/types";
import { fmtNumber, fmtPercent, fmtVnd } from "@/lib/format";
import { sectorLabel } from "@/lib/sectors";
import { cn } from "@/lib/utils";

/**
 * The charts that replaced a run of horizontal bars. Each answers its
 * question in the shape that fits it: a share of a whole is a ring, a
 * distribution is a histogram, a fall through time is a line, a balance
 * sheet is two stacked columns, a position against thresholds is a gauge.
 */

const SECTOR_COLORS = [
  CHART.brand,
  "#158f66",
  CHART.signal,
  "#8a4fbd",
  "#3f7d8c",
  "#c0433a",
  "#8a5a44",
  "#5b6b7a",
];

/** Sector weights as a ring; the count of sectors sits in the hole. */
export function SectorDonut({ data }: { data: PortfolioAnalysis }) {
  const t = useTranslations("portfolio.result");
  const locale = useLocale();
  const rows = useMemo(
    () =>
      Object.entries(data.concentration.sector_weights)
        .sort((a, b) => b[1] - a[1])
        .map(([key, w], i) => ({
          name: sectorLabel(key, locale) ?? key,
          value: +(w * 100).toFixed(1),
          itemStyle: { color: SECTOR_COLORS[i % SECTOR_COLORS.length] },
        })),
    [data.concentration.sector_weights, locale],
  );
  const option = useMemo<EChartsCoreOption>(
    () => ({
      animationDuration: 500,
      tooltip: {
        trigger: "item",
        valueFormatter: (v: unknown) =>
          typeof v === "number" ? fmtPercent(v / 100, locale, 1) : "—",
      },
      legend: {
        orient: "vertical",
        right: 0,
        top: "middle",
        icon: "circle",
        itemWidth: 8,
        itemHeight: 8,
        textStyle: { color: CHART.ink, fontSize: 12 },
        formatter: (name: string) => {
          const r = rows.find((x) => x.name === name);
          return r ? `${name}  ${fmtPercent(r.value / 100, locale, 0)}` : name;
        },
      },
      series: [
        {
          type: "pie",
          radius: ["58%", "82%"],
          center: ["32%", "50%"],
          avoidLabelOverlap: true,
          label: { show: false },
          emphasis: { scale: true, scaleSize: 4 },
          itemStyle: { borderColor: "#ffffff", borderWidth: 2 },
          data: rows,
        },
      ],
      graphic: [
        {
          type: "text",
          left: "32%",
          top: "middle",
          style: {
            text: `${rows.length}\n${t("sectorsWord")}`,
            textAlign: "center",
            fill: CHART.ink,
            fontSize: 13,
            fontFamily: CHART.mono,
            lineHeight: 16,
          },
          z: 10,
          silent: true,
        },
      ],
    }),
    [rows, locale, t],
  );
  if (rows.length === 0) return <p className="text-sm text-dim">{t("sectorMissing")}</p>;
  return <EChart option={option} ariaLabel={t("sectorChartTitle")} className="h-[22rem]" />;
}

/** The book's own daily returns; the worst 5% in red, VaR and ES as lines. */
export function ReturnHistogramChart({ histogram: h }: { histogram: ReturnHistogram }) {
  const t = useTranslations("portfolio.result");
  const locale = useLocale();
  const spanLabel = useSpanLabel();
  const option = useMemo<EChartsCoreOption>(() => {
    const mids = h.bins.map((b) => (b.lower + b.upper) / 2);
    const labels = mids.map((m) => fmtPercent(m, locale, 1));
    return {
      animationDuration: 500,
      grid: { left: 8, right: 12, top: 28, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis",
        formatter: (params: { dataIndex: number; value: number }[]) => {
          const i = params[0]?.dataIndex ?? 0;
          const b = h.bins[i];
          return `${fmtPercent(b.lower, locale, 1)} … ${fmtPercent(b.upper, locale, 1)}<br/>${t("histSessions", { n: b.count })}`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: CHART.border } },
        axisTick: { show: false },
        axisLabel: { color: CHART.dim, fontFamily: CHART.mono, fontSize: 10, interval: 3 },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: CHART.surface } },
        axisLabel: { color: CHART.dim, fontSize: 10 },
      },
      series: [
        {
          type: "bar",
          barCategoryGap: "12%",
          data: h.bins.map((b) => ({
            value: b.count,
            itemStyle: {
              color: b.upper <= h.var_95 ? CHART.negative : CHART.brandSoft,
              borderColor: b.upper <= h.var_95 ? CHART.negative : CHART.brand,
              borderWidth: 1,
            },
          })),
          markLine: {
            silent: true,
            symbol: "none",
            label: { fontFamily: CHART.mono, fontSize: 11, position: "insideEndTop" },
            data: [
              {
                xAxis: labels[nearest(mids, h.var_95)],
                lineStyle: { color: CHART.negative, width: 1.5, type: "dashed" },
                label: {
                  formatter: `${t("histVar")} ${fmtPercent(h.var_95, locale, 1)}`,
                  color: CHART.negative,
                },
              },
              {
                xAxis: labels[nearest(mids, h.expected_shortfall_95)],
                lineStyle: { color: CHART.negative, width: 1, type: "dotted" },
                label: {
                  formatter: `${t("histEs")} ${fmtPercent(h.expected_shortfall_95, locale, 1)}`,
                  color: CHART.negative,
                  position: "insideEndBottom",
                },
              },
            ],
          },
        },
      ],
    };
  }, [h, locale, t]);
  const title = t("histTitle", { span: spanLabel(h.observations) });
  return (
    <figure className="min-w-0">
      <figcaption className="text-sm font-medium">{title}</figcaption>
      <EChart option={option} ariaLabel={title} className="h-56" />
      <p className="mt-1 text-xs text-dim">{t("histNote")}</p>
    </figure>
  );
}

function nearest(values: number[], target: number): number {
  let best = 0;
  for (let i = 1; i < values.length; i++) {
    if (Math.abs(values[i] - target) < Math.abs(values[best] - target)) best = i;
  }
  return best;
}

const CRISIS_COLORS: Record<string, string> = {
  gfc_2008: CHART.negative,
  y2018: CHART.signal,
  covid_2020: CHART.brand,
  y2022: "#158f66",
};

/** How the book fell through each past crisis, session by session. */
export const CRISIS_COLOR = (key: string): string => CRISIS_COLORS[key] ?? CHART.dim;

/**
 * The book replayed through past falls, one line per crisis the reader has
 * switched on. Series carry stable ids and the chart updates with
 * `replaceMerge`, so switching a crisis on draws only that line in, left to
 * right, and leaves the others where they are.
 */
export function CrisisPaths({
  crises,
  selected,
  callDrop,
}: {
  crises: CrisisScenario[];
  selected: ReadonlySet<string>;
  callDrop: number | null;
}) {
  const t = useTranslations("portfolio.stress");
  const locale = useLocale();
  const option = useMemo<EChartsCoreOption>(() => {
    // The axis spans every crisis, selected or not, so it never jumps.
    const longest = Math.max(...crises.map((c) => c.sessions), 1);
    const series = crises.filter((c) => selected.has(c.key)).map((c) => {
      const n = c.path.length;
      // Thinned paths are evenly spaced across the window's sessions.
      const step = n > 1 ? c.sessions / (n - 1) : 0;
      return {
        id: c.key,
        name: t(`crisis.${c.key}`),
        type: "line",
        showSymbol: false,
        smooth: 0.15,
        animationDuration: 1600,
        animationEasing: "linear",
        lineStyle: { width: 2.2, color: CRISIS_COLORS[c.key] ?? CHART.dim },
        itemStyle: { color: CRISIS_COLORS[c.key] ?? CHART.dim },
        data: c.path.map((v, i) => [+(i * step).toFixed(1), +(v * 100).toFixed(2)]),
        endLabel: {
          show: true,
          formatter: t(`crisis.${c.key}`),
          color: CRISIS_COLORS[c.key] ?? CHART.dim,
          fontSize: 11,
          offset: [4, 0],
        },
        labelLayout: { moveOverlap: "shiftY" },
      };
    });
    // Ticks every quarter (63 sessions); round the axis up to a whole one so
    // the last tick does not collide with the end.
    const QUARTER = 63;
    const axisMax = Math.ceil(longest / QUARTER) * QUARTER;
    return {
      animationDuration: 700,
      legend: { show: false },
      grid: { left: 8, right: 120, top: 16, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) => (typeof v === "number" ? fmtPercent(v / 100, locale, 1) : "—"),
      },
      xAxis: {
        type: "value",
        max: axisMax,
        interval: QUARTER,
        axisLine: { lineStyle: { color: CHART.border } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: {
          color: CHART.dim,
          formatter: (v: number) => (v === 0 ? "" : t("monthsAxis", { n: Math.round(v / 21) })),
        },
      },
      yAxis: {
        type: "value",
        max: 5,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: CHART.surface } },
        axisLabel: { color: CHART.dim, formatter: "{value}%" },
      },
      series: [
        ...series,
        ...(callDrop !== null
          ? [
              {
                id: "call",
                type: "line",
                data: [],
                markLine: {
                  silent: true,
                  symbol: "none",
                  lineStyle: { color: CHART.negative, type: "dashed", width: 1.5 },
                  label: {
                    formatter: t("reachesCallLine"),
                    color: CHART.negative,
                    fontSize: 11,
                    position: "insideStartBottom",
                  },
                  data: [{ yAxis: -callDrop * 100 }],
                },
              },
            ]
          : []),
      ],
    };
  }, [crises, selected, callDrop, locale, t]);
  return (
    <EChart option={option} ariaLabel={t("heading")} className="h-80" replaceMerge={REPLACE_SERIES} />
  );
}

const REPLACE_SERIES: "series"[] = ["series"];

/** Assets and funding as two stacked columns — the balance sheet. */
export function BalanceColumns({ margin: m, data }: { margin: MarginRisk; data: PortfolioAnalysis }) {
  const t = useTranslations("portfolio.margin");
  const locale = useLocale();
  const option = useMemo<EChartsCoreOption>(() => {
    const seg = (name: string, values: (number | null)[], color: string, textColor: string) => ({
      name,
      type: "bar",
      stack: "bs",
      barWidth: "56%",
      data: values,
      itemStyle: { color, borderColor: "#ffffff", borderWidth: 1 },
      label: {
        show: true,
        position: "inside",
        color: textColor,
        fontFamily: CHART.mono,
        fontSize: 11,
        formatter: (p: { value: number; seriesName: string }) =>
          p.value > 0 && p.value / m.assets >= 0.08
            ? `${p.seriesName}\n${fmtVnd(p.value, locale)}`
            : "",
      },
    });
    return {
      animationDuration: 500,
      legend: {
        bottom: 0,
        icon: "circle",
        itemWidth: 8,
        itemHeight: 8,
        textStyle: { color: CHART.dim, fontSize: 11 },
      },
      grid: { left: 8, right: 8, top: 8, bottom: 28, containLabel: true },
      tooltip: {
        trigger: "item",
        valueFormatter: (v: unknown) => (typeof v === "number" ? `${fmtVnd(v, locale)} đ` : "—"),
      },
      xAxis: {
        type: "category",
        data: [t("assets"), t("funding")],
        axisLine: { lineStyle: { color: CHART.border } },
        axisTick: { show: false },
        axisLabel: { color: CHART.ink, fontSize: 12 },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: CHART.surface } },
        axisLabel: { color: CHART.dim, fontSize: 10, formatter: (v: number) => fmtVnd(v, locale) },
      },
      series: [
        seg(t("stocks"), [data.invested_value, null], CHART.brand, "#ffffff"),
        seg(t("cash"), [data.cash, null], CHART.brandSoft, CHART.brandDark),
        seg(t("equity"), [null, Math.max(m.equity, 0)], "#158f66", "#ffffff"),
        seg(t("debt"), [null, m.debt], CHART.signal, "#ffffff"),
      ],
    };
  }, [m, data, locale, t]);
  return <EChart option={option} ariaLabel={t("assets")} className="h-64" />;
}

/** The margin ratio as a gauge with the broker's two thresholds. */
export function RatioGauge({ margin: m }: { margin: MarginRisk }) {
  const t = useTranslations("portfolio.margin");
  const locale = useLocale();
  const option = useMemo<EChartsCoreOption>(
    () => ({
      animationDuration: 600,
      series: [
        {
          type: "gauge",
          startAngle: 200,
          endAngle: -20,
          min: 0,
          max: 100,
          radius: "100%",
          center: ["50%", "62%"],
          axisLine: {
            lineStyle: {
              width: 16,
              color: [
                [m.force_ratio, CHART.negative],
                [m.call_ratio, CHART.signal],
                [1, "#9fd0b8"],
              ],
            },
          },
          pointer: { length: "62%", width: 5, itemStyle: { color: CHART.ink } },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          anchor: { show: true, size: 10, itemStyle: { color: CHART.ink } },
          title: { show: false },
          detail: {
            valueAnimation: true,
            offsetCenter: [0, "34%"],
            fontFamily: CHART.mono,
            fontSize: 22,
            fontWeight: 600,
            color: CHART.ink,
            formatter: (v: number) => fmtPercent(v / 100, locale, 1),
          },
          data: [{ value: +(m.margin_ratio * 100).toFixed(1) }],
        },
      ],
    }),
    [m, locale],
  );
  return (
    <div>
      <EChart option={option} ariaLabel={t("ratioTitle")} className="h-52" />
      <div className="-mt-2 flex justify-center gap-4 text-xs text-dim">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: CHART.negative }} />
          {t("forceShort")} {fmtPercent(m.force_ratio, locale, 0)}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: CHART.signal }} />
          {t("callShort")} {fmtPercent(m.call_ratio, locale, 0)}
        </span>
      </div>
    </div>
  );
}

/** Equity left as the stocks fall, against the two thresholds. */
export function ScenarioLine({ margin: m }: { margin: MarginRisk }) {
  const t = useTranslations("portfolio.margin");
  const locale = useLocale();
  const option = useMemo<EChartsCoreOption>(() => {
    const pts = [{ drop: 0, margin_ratio: m.margin_ratio }, ...m.scenarios];
    return {
      animationDuration: 500,
      grid: { left: 8, right: 16, top: 24, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis",
        formatter: (params: { dataIndex: number }[]) => {
          const i = params[0]?.dataIndex ?? 0;
          const p = pts[i];
          const sc = m.scenarios[i - 1];
          return [
            `<b>${t("colDrop")} ${fmtPercent(p.drop, locale, 0)}</b>`,
            `${t("colRatio")}: ${fmtPercent(p.margin_ratio, locale, 1)}`,
            sc ? `${t("colEquity")}: ${fmtVnd(sc.equity, locale)} đ` : "",
            sc && sc.top_up > 0 ? `${t("colTopUp")}: ${fmtVnd(sc.top_up, locale)} đ` : "",
          ]
            .filter(Boolean)
            .join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: pts.map((p) => (p.drop > 0 ? `−${fmtPercent(p.drop, locale, 0)}` : fmtPercent(0, locale, 0))),
        boundaryGap: false,
        axisLine: { lineStyle: { color: CHART.border } },
        axisTick: { show: false },
        axisLabel: { color: CHART.dim, fontFamily: CHART.mono, fontSize: 11 },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: CHART.surface } },
        axisLabel: { color: CHART.dim, formatter: "{value}%" },
      },
      series: [
        {
          type: "line",
          data: pts.map((p) => +(p.margin_ratio * 100).toFixed(1)),
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 2.5, color: CHART.brand },
          itemStyle: {
            color: (p: { dataIndex: number }) => {
              const r = pts[p.dataIndex].margin_ratio;
              return r <= m.force_ratio ? CHART.negative : r <= m.call_ratio ? CHART.signal : CHART.brand;
            },
            borderColor: "#ffffff",
            borderWidth: 2,
          },
          areaStyle: { color: "rgba(58,114,196,0.08)" },
          label: {
            show: true,
            position: "top",
            fontFamily: CHART.mono,
            fontSize: 11,
            color: CHART.ink,
            formatter: (p: { value: number }) => fmtPercent(p.value / 100, locale, 0),
          },
          markLine: {
            silent: true,
            symbol: "none",
            label: { fontFamily: CHART.mono, fontSize: 11, position: "insideEndTop" },
            data: [
              {
                yAxis: +(m.call_ratio * 100).toFixed(1),
                lineStyle: { color: CHART.signal, type: "dashed", width: 1.5 },
                label: {
                  formatter: `${t("callShort")} ${fmtPercent(m.call_ratio, locale, 0)}`,
                  color: CHART.signalDark,
                  position: "insideMiddleTop",
                },
              },
              {
                yAxis: +(m.force_ratio * 100).toFixed(1),
                lineStyle: { color: CHART.negative, type: "dashed", width: 1.5 },
                label: {
                  formatter: `${t("forceShort")} ${fmtPercent(m.force_ratio, locale, 0)}`,
                  color: CHART.negative,
                  position: "insideMiddleBottom",
                },
              },
            ],
          },
        },
      ],
    };
  }, [m, locale, t]);
  return <EChart option={option} ariaLabel={t("scenarioTitle")} className="h-64" />;
}

/** Each loss as two joined dots: on the stocks, then on equity. */
export function LossDumbbell({ margin: m, data }: { margin: MarginRisk; data: PortfolioAnalysis }) {
  const t = useTranslations("portfolio.margin");
  const locale = useLocale();
  const rows = [
    { key: "var95", stocks: data.var_95, equity: m.equity_var_95 },
    { key: "es95", stocks: data.expected_shortfall_95, equity: m.equity_expected_shortfall_95 },
    { key: "maxDrawdown", stocks: data.max_drawdown, equity: m.equity_max_drawdown },
  ];
  const top = Math.min(1, Math.max(...rows.map((r) => Math.abs(r.equity ?? r.stocks)), 0.05) * 1.25);
  const x = (v: number) => `${Math.min(100, (Math.abs(v) / top) * 100)}%`;
  return (
    <div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-dim" aria-hidden="true">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: CHART.lightgray }} />
          {t("equityLegendStocks")}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: CHART.negative }} />
          {t("equityLegendEquity")}
        </span>
      </div>
      <ul className="mt-3 space-y-4">
        {rows.map((r) => {
          const eq = r.equity === null ? null : Math.abs(r.equity);
          const wiped = eq !== null && eq >= 1;
          return (
            <li key={r.key}>
              <div className="flex items-baseline justify-between text-sm">
                <span>{t(`equityMeasures.${r.key}`)}</span>
                <span className="figure text-xs text-dim">
                  {fmtVnd(Math.abs(r.stocks) * data.measured_value, locale)} đ
                </span>
              </div>
              <div className="relative mt-1.5 h-5">
                <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" />
                {eq !== null && (
                  <div
                    className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full"
                    style={{ left: x(r.stocks), width: `calc(${x(eq)} - ${x(r.stocks)})`, backgroundColor: CHART.negative }}
                  />
                )}
                <span
                  className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background"
                  style={{ left: x(r.stocks), backgroundColor: CHART.lightgray }}
                  title={fmtPercent(Math.abs(r.stocks), locale, 1)}
                />
                {eq !== null && (
                  <span
                    className={cn(
                      "absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background",
                    )}
                    style={{ left: x(eq), backgroundColor: CHART.negative }}
                    title={fmtPercent(eq, locale, 1)}
                  />
                )}
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-dim">{fmtPercent(Math.abs(r.stocks), locale, 1)}</span>
                <span className={cn("figure", wiped ? "text-negative" : "text-ink")}>
                  {eq === null ? "—" : wiped ? t("wipedOut") : fmtPercent(eq, locale, 1)}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-xs text-dim">
        {t("dumbbellNote", { leverage: m.leverage === null ? "—" : fmtNumber(m.leverage, locale) })}
      </p>
    </div>
  );
}
