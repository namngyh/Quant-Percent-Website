"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { EChart, CHART } from "@/components/charts/echart";
import { InfoTip } from "@/components/info-tip";
import type { PortfolioOutlook } from "@/lib/api/types";
import { fmtPercent } from "@/lib/format";

/**
 * Causa's calibrated return interval, laid over this book.
 *
 * Three horizons, one band each: the range the model puts 90% of outcomes
 * in, scaled to the portfolio by beta and — when there is a loan — onto
 * equity by leverage. Two reference lines sit on the same axis: the return
 * that pays the interest, and the fall that reaches the warning threshold.
 * No median is drawn: the model's own report says its point forecast has
 * not beaten a baseline, and a line down the middle would read as one.
 */

export function PortfolioOutlookSection({
  outlook: o,
  hasLoan,
}: {
  outlook: PortfolioOutlook;
  hasLoan: boolean;
}) {
  const t = useTranslations("portfolio.outlook");
  const locale = useLocale();
  const onEquity = hasLoan && o.horizons.every((h) => h.equity_lower !== null);

  const option = useMemo<EChartsCoreOption>(() => {
    const labels = o.horizons.map((h) => t("sessions", { n: h.horizon_days }));
    const lo = o.horizons.map(
      (h) => +(((onEquity ? h.equity_lower : h.portfolio_lower) ?? 0) * 100).toFixed(1),
    );
    const hi = o.horizons.map(
      (h) => +(((onEquity ? h.equity_upper : h.portfolio_upper) ?? 0) * 100).toFixed(1),
    );
    const breakeven = o.horizons.map((h) =>
      h.breakeven_return === null ? null : +(h.breakeven_return * 100).toFixed(2),
    );
    const fmt = (v: number) => fmtPercent(v / 100, locale, 1);
    return {
      animationDuration: 450,
      legend: { show: false },
      grid: { left: 8, right: 20, top: 28, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        formatter: (params: { dataIndex: number }[]) => {
          const i = params[0]?.dataIndex ?? 0;
          const h = o.horizons[i];
          const rows = [
            `<b>${labels[i]}</b>`,
            `${t("band", { level: fmtPercent(o.interval_level, locale, 0) })}: ${fmt(lo[i])} … ${fmt(hi[i])}`,
            `${t("index")}: ${fmtPercent(h.index_lower, locale, 1)} … ${fmtPercent(h.index_upper, locale, 1)}`,
          ];
          if (breakeven[i] !== null)
            rows.push(`${t("breakeven")}: +${fmt(breakeven[i] as number)}`);
          return rows.join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        boundaryGap: true,
        axisLine: { lineStyle: { color: CHART.border } },
        axisTick: { show: false },
        axisLabel: { color: CHART.dim, margin: 12 },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: CHART.surface } },
        axisLabel: { color: CHART.dim, formatter: "{value}%" },
      },
      series: [
        // Floating box from lower to upper. A candlestick with no wick,
        // because stacked bars split at zero and the lower bound is negative.
        {
          type: "candlestick",
          data: hi.map((h, i) => [lo[i], h, lo[i], h]),
          barWidth: "38%",
          itemStyle: {
            color: CHART.brandSoft,
            color0: CHART.brandSoft,
            borderColor: CHART.brand,
            borderColor0: CHART.brand,
            borderWidth: 1.5,
          },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { width: 1.5 },
            label: { fontFamily: CHART.mono, fontSize: 11, position: "insideEndTop" },
            data: [
              {
                yAxis: 0,
                lineStyle: { color: CHART.faint, type: "solid" },
                label: { show: false },
              },
              ...(o.call_drop !== null && onEquity
                ? [
                    {
                      // The call line is a fall in the stocks; on the equity
                      // axis it is scaled by the same leverage as the band.
                      yAxis: +(
                        o.call_drop *
                        ((o.horizons[0].equity_lower ?? 1) / (o.horizons[0].portfolio_lower || 1)) *
                        100
                      ).toFixed(1),
                      lineStyle: { color: CHART.negative, type: "dashed" },
                      label: { formatter: t("callLine"), color: CHART.negative },
                    },
                  ]
                : o.call_drop !== null
                  ? [
                      {
                        yAxis: +(o.call_drop * 100).toFixed(1),
                        lineStyle: { color: CHART.negative, type: "dashed" },
                        label: { formatter: t("callLine"), color: CHART.negative },
                      },
                    ]
                  : []),
            ],
          },
        },
        // Upper / lower edge labels.
        {
          type: "scatter",
          data: hi,
          symbolSize: 0,
          silent: true,
          label: {
            show: true,
            position: "top",
            distance: 8,
            color: CHART.ink,
            fontFamily: CHART.mono,
            fontSize: 11,
            formatter: (p: { value: number }) => `+${fmt(p.value)}`,
          },
        },
        {
          type: "scatter",
          data: lo,
          symbolSize: 0,
          silent: true,
          label: {
            show: true,
            position: "bottom",
            distance: 8,
            color: CHART.negative,
            fontFamily: CHART.mono,
            fontSize: 11,
            formatter: (p: { value: number }) => fmt(p.value),
          },
        },
        ...(breakeven.some((b) => b !== null)
          ? [
              {
                type: "line",
                data: breakeven,
                symbol: "diamond",
                symbolSize: 8,
                lineStyle: { color: CHART.signal, width: 1.5, type: "dotted" },
                itemStyle: { color: CHART.signal },
                label: { show: false },
              },
            ]
          : []),
      ],
    };
  }, [o, onEquity, locale, t]);

  return (
    <section aria-labelledby="pf-outlook">
      <h2 id="pf-outlook" className="inline-flex items-center gap-2 text-lg font-semibold">
        {t("heading")}
        <InfoTip
          wide
          text={[
            t("lead", { level: fmtPercent(o.interval_level, locale, 0), beta: o.portfolio_beta }),
            t("source"),
            t("caveat"),
          ]}
        />
      </h2>
      <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-xs text-dim" aria-hidden="true">
        <span className="inline-flex items-center gap-2">
          <span
            className="h-3 w-4 rounded-sm border border-brand"
            style={{ backgroundColor: CHART.brandSoft }}
          />
          {onEquity ? t("legendEquity") : t("legendStocks")}
        </span>
        {hasLoan && (
          <span className="inline-flex items-center gap-2">
            <span className="w-5 border-t-2 border-dotted" style={{ borderColor: CHART.signal }} />
            {t("breakeven")}
          </span>
        )}
        {o.call_drop !== null && (
          <span className="inline-flex items-center gap-2">
            <span className="w-5 border-t-2 border-dashed border-negative" />
            {t("callLine")}
          </span>
        )}
      </div>
      <EChart option={option} ariaLabel={t("heading")} className="mt-2 h-64" />
    </section>
  );
}

type Horizon = PortfolioOutlook["horizons"][number];

/**
 * The same interval, market beside book: for each horizon a grey box for
 * VN-Index and a blue one for the portfolio. Wider blue means the book
 * swings more than the market — beta, as a picture.
 */
export function OutlookVsIndexSection({ outlook: o }: { outlook: PortfolioOutlook }) {
  const t = useTranslations("portfolio.outlook");
  const locale = useLocale();

  const option = useMemo<EChartsCoreOption>(() => {
    const labels = o.horizons.map((h) => t("sessions", { n: h.horizon_days }));
    const pct = (v: number) => +(v * 100).toFixed(1);
    const fmt = (v: number) => fmtPercent(v / 100, locale, 1);
    const OFFSET = 0.19;
    // Value axis with hand-placed x so the two boxes sit side by side;
    // candlesticks on a category axis would overlap.
    const box = (
      id: string,
      name: string,
      dx: number,
      lo: (h: Horizon) => number,
      hi: (h: Horizon) => number,
      fill: string,
      border: string,
    ) => ({
      id,
      name,
      type: "candlestick",
      barWidth: 30,
      data: o.horizons.map((h, i) => [i + dx, pct(lo(h)), pct(hi(h)), pct(lo(h)), pct(hi(h))]),
      itemStyle: {
        color: fill,
        color0: fill,
        borderColor: border,
        borderColor0: border,
        borderWidth: 1.5,
      },
    });
    const edge = (
      dx: number,
      pick: (h: Horizon) => number,
      position: "top" | "bottom",
      color: string,
      sign: string,
    ) => ({
      type: "scatter",
      data: o.horizons.map((h, i) => [i + dx, pct(pick(h))]),
      symbolSize: 0,
      silent: true,
      label: {
        show: true,
        position,
        distance: 6,
        color,
        fontFamily: CHART.mono,
        fontSize: 10,
        formatter: (p: { value: number[] }) => `${sign}${fmt(p.value[1])}`,
      },
    });
    const all = o.horizons.flatMap((h) => [
      h.index_lower,
      h.index_upper,
      h.portfolio_lower,
      h.portfolio_upper,
    ]);
    const span = Math.ceil((Math.max(...all.map((v) => Math.abs(v))) * 100 + 8) / 10) * 10;
    return {
      animationDuration: 450,
      legend: { show: false },
      grid: { left: 8, right: 12, top: 28, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params: { value: number[] }[]) => {
          const i = Math.round(params[0]?.value[0] ?? 0);
          const h = o.horizons[i];
          if (!h) return "";
          return [
            `<b>${labels[i]}</b>`,
            `${t("index")}: ${fmt(pct(h.index_lower))} … ${fmt(pct(h.index_upper))}`,
            `${t("legendPortfolio")}: ${fmt(pct(h.portfolio_lower))} … ${fmt(pct(h.portfolio_upper))}`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "value",
        min: -0.5,
        max: o.horizons.length - 0.5,
        interval: 0.5,
        axisLine: { lineStyle: { color: CHART.border } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: {
          color: CHART.dim,
          fontFamily: CHART.mono,
          formatter: (v: number) => (Number.isInteger(v) ? (labels[v] ?? "") : ""),
        },
      },
      yAxis: {
        type: "value",
        min: -span,
        max: span,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: CHART.surface } },
        axisLabel: { color: CHART.dim, formatter: "{value}%" },
      },
      series: [
        box(
          "index",
          t("index"),
          -OFFSET,
          (h) => h.index_lower,
          (h) => h.index_upper,
          CHART.surface,
          CHART.dim,
        ),
        box(
          "book",
          t("legendPortfolio"),
          OFFSET,
          (h) => h.portfolio_lower,
          (h) => h.portfolio_upper,
          CHART.brandSoft,
          CHART.brand,
        ),
        edge(-OFFSET, (h) => h.index_upper, "top", CHART.dim, "+"),
        edge(-OFFSET, (h) => h.index_lower, "bottom", CHART.dim, ""),
        edge(OFFSET, (h) => h.portfolio_upper, "top", CHART.ink, "+"),
        edge(OFFSET, (h) => h.portfolio_lower, "bottom", CHART.negative, ""),
        {
          type: "line",
          data: [],
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: CHART.faint, type: "solid", width: 1.5 },
            label: { show: false },
            data: [{ yAxis: 0 }],
          },
        },
      ],
    };
  }, [o, locale, t]);

  return (
    <section aria-labelledby="pf-outlook-index">
      <h2 id="pf-outlook-index" className="inline-flex items-center gap-2 text-lg font-semibold">
        {t("compareHeading")}
        <InfoTip
          wide
          text={[
            t("compareLead", {
              level: fmtPercent(o.interval_level, locale, 0),
              beta: o.portfolio_beta,
            }),
            t("source"),
          ]}
        />
      </h2>
      <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-xs text-dim" aria-hidden="true">
        <span className="inline-flex items-center gap-2">
          <span
            className="h-3 w-4 rounded-sm border"
            style={{ backgroundColor: CHART.surface, borderColor: CHART.dim }}
          />
          {t("index")}
        </span>
        <span className="inline-flex items-center gap-2">
          <span
            className="h-3 w-4 rounded-sm border border-brand"
            style={{ backgroundColor: CHART.brandSoft }}
          />
          {t("legendPortfolio")}
        </span>
      </div>
      <EChart option={option} ariaLabel={t("compareHeading")} className="mt-2 h-64" />
    </section>
  );
}
