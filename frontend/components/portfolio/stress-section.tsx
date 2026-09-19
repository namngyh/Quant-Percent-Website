"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { EChart, CHART } from "@/components/charts/echart";
import { InfoTip } from "@/components/info-tip";
import type { PortfolioAnalysis, StressReport } from "@/lib/api/types";
import { fmtNumber, fmtPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * "If it happened again": the book replayed through past falls.
 *
 * Nothing is modelled. Each row is the same holdings at today's weights on
 * the prices of that period. With a loan, the same fall is also shown on
 * equity, and against the warning threshold: a crisis that would have
 * reached it is marked. The liquidity line says how long the book takes to
 * sell, which is what forced selling runs into.
 */

const CRISIS_ORDER = ["gfc_2008", "y2018", "covid_2020", "y2022"];

export function StressSection({
  stress: s,
  data,
}: {
  stress: StressReport;
  data: PortfolioAnalysis;
}) {
  const t = useTranslations("portfolio.stress");
  const locale = useLocale();
  const m = data.margin;
  const onEquity = m !== null && m.equity > 0;
  const leverageFactor = onEquity ? data.measured_value / m.equity : 1;
  const callDrop =
    m && !m.external && m.distance_to_call ? m.distance_to_call.drop : null;

  const crises = useMemo(
    () =>
      [...s.crises].sort(
        (a, b) => CRISIS_ORDER.indexOf(a.key) - CRISIS_ORDER.indexOf(b.key),
      ),
    [s.crises],
  );

  const option = useMemo<EChartsCoreOption>(() => {
    const labels = crises.map((c) => t(`crisis.${c.key}`));
    const book = crises.map((c) => +(c.max_drawdown * 100).toFixed(1));
    const index = crises.map((c) => +(c.index_max_drawdown * 100).toFixed(1));
    const equity = onEquity
      ? crises.map((c) => +(Math.max(c.max_drawdown * leverageFactor, -1) * 100).toFixed(1))
      : null;
    const fmt = (v: number) => fmtPercent(v / 100, locale, 1);
    const bar = (name: string, values: number[], color: string, labelColor: string) => ({
      name,
      type: "bar",
      data: values,
      barWidth: onEquity ? "22%" : "30%",
      itemStyle: { color, borderRadius: [0, 4, 4, 0] },
      label: {
        show: true,
        position: "right",
        distance: 6,
        color: labelColor,
        fontFamily: CHART.mono,
        fontSize: 11,
        formatter: (p: { value: number }) => fmt(p.value),
      },
    });
    return {
      animationDuration: 450,
      legend: { show: false },
      grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) => (typeof v === "number" ? fmt(v) : "—"),
      },
      xAxis: {
        type: "value",
        max: 0,
        inverse: false,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: CHART.surface } },
        axisLabel: { color: CHART.dim, formatter: "{value}%" },
      },
      yAxis: {
        type: "category",
        data: labels,
        inverse: true,
        axisLine: { lineStyle: { color: CHART.border } },
        axisTick: { show: false },
        axisLabel: { color: CHART.ink, fontSize: 12 },
      },
      series: [
        bar(t("legendIndex"), index, CHART.lightgray, CHART.dim),
        bar(t("legendBook"), book, CHART.brand, CHART.ink),
        ...(equity ? [bar(t("legendEquity"), equity, CHART.negative, CHART.negative)] : []),
      ],
    };
  }, [crises, onEquity, leverageFactor, locale, t]);

  const liq = s.liquidity;
  const noDiv = s.no_diversification_volatility;

  return (
    <section aria-labelledby="pf-stress">
      <h2 id="pf-stress" className="title-md inline-flex items-center gap-2">
        {t("heading")}
        <InfoTip
          wide
          text={[
            t("lead"),
            t("coverageNote"),
            onEquity ? t("equityNote") : "",
            t("liquidityNote", { share: fmtPercent(liq.participation, locale, 0) }),
          ].filter(Boolean)}
        />
      </h2>

      {crises.length > 0 ? (
        <>
          <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-xs text-dim" aria-hidden="true">
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: CHART.lightgray }} />
              {t("legendIndex")}
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: CHART.brand }} />
              {t("legendBook")}
            </span>
            {onEquity && (
              <span className="inline-flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: CHART.negative }} />
                {t("legendEquity")}
              </span>
            )}
          </div>
          <EChart
            option={option}
            ariaLabel={t("heading")}
            className={cn("mt-2", crises.length > 2 ? "h-72" : "h-52")}
          />

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[40rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  {[
                    "colCrisis",
                    "colBook",
                    ...(onEquity ? ["colEquity"] : []),
                    "colIndex",
                    "colCorr",
                    ...(callDrop !== null ? ["colCall"] : []),
                    "colCovered",
                  ].map((key) => (
                    <th
                      key={key}
                      scope="col"
                      className={cn(
                        "py-2.5 pr-4 text-xs font-medium uppercase tracking-[0.06em] text-dim",
                        key !== "colCrisis" && key !== "colCall" && key !== "colCovered" && "text-right",
                      )}
                    >
                      {t(key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {crises.map((c) => {
                  const reaches = callDrop !== null && Math.abs(c.max_drawdown) >= callDrop;
                  const equityFall = Math.max(c.max_drawdown * leverageFactor, -1);
                  return (
                    <tr key={c.key} className="border-b border-border/70">
                      <th scope="row" className="py-3 pr-4 text-left font-medium">
                        {t(`crisis.${c.key}`)}
                        <span className="block text-xs font-normal text-dim">
                          {t("sessions", { n: c.sessions })}
                        </span>
                      </th>
                      <td className="figure py-3 pr-4 text-right">
                        {fmtPercent(c.max_drawdown, locale, 1)}
                      </td>
                      {onEquity && (
                        <td
                          className={cn(
                            "figure py-3 pr-4 text-right",
                            equityFall <= -1 ? "text-negative" : "",
                          )}
                        >
                          {equityFall <= -1 ? t("wipedOut") : fmtPercent(equityFall, locale, 1)}
                        </td>
                      )}
                      <td className="figure py-3 pr-4 text-right text-dim">
                        {fmtPercent(c.index_max_drawdown, locale, 1)}
                      </td>
                      <td className="figure py-3 pr-4 text-right">
                        {fmtNumber(c.average_correlation, locale)}
                      </td>
                      {callDrop !== null && (
                        <td className={cn("py-3 pr-4", reaches ? "text-negative" : "text-dim")}>
                          {reaches ? t("reachesCall") : t("staysAbove")}
                        </td>
                      )}
                      <td className="py-3 pr-4 text-xs text-dim">
                        {c.covered_weight >= 0.999
                          ? t("coveredAll")
                          : t("coveredPart", {
                              share: fmtPercent(c.covered_weight, locale, 0),
                              symbols: c.covered.join(", "),
                            })}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p className="mt-5 max-w-3xl text-sm leading-relaxed text-dim">{t("noCrises")}</p>
      )}

      <dl className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2">
        <div className="bg-background p-5">
          <dt className="text-xs text-dim">{t("noDiv")}</dt>
          <dd className="figure mt-2 text-xl font-semibold">{fmtPercent(noDiv, locale, 1)}</dd>
          <p className="mt-2 text-xs leading-relaxed text-dim">
            {t("noDivNote", { now: fmtPercent(data.volatility, locale, 1) })}
          </p>
        </div>
        <div className="bg-background p-5">
          <dt className="text-xs text-dim">{t("liquidity")}</dt>
          <dd
            className={cn(
              "figure mt-2 text-xl font-semibold",
              liq.slow.length > 0 && "text-caution",
            )}
          >
            {liq.book_days === null
              ? "—"
              : liq.book_days < 0.5
                ? t("underHalfDay")
                : t("days", { n: fmtNumber(liq.book_days, locale, { maximumFractionDigits: 1 }) })}
          </dd>
          <p className="mt-2 text-xs leading-relaxed text-dim">
            {liq.slow.length > 0
              ? t("liquiditySlow", {
                  symbols: liq.slow.join(", "),
                  share: fmtPercent(liq.slow_weight, locale, 0),
                  days: fmtNumber(liq.slow_days, locale),
                })
              : t("liquidityFine", {
                  share: fmtPercent(liq.participation, locale, 0),
                  amount: liq.slowest_symbol
                    ? `${liq.slowest_symbol}`
                    : "",
                })}
          </p>
        </div>
      </dl>
    </section>
  );
}
