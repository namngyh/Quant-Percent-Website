"use client";

import { useMemo, useState } from "react";
import { useTranslations, useLocale } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { EChart, CHART } from "@/components/charts/echart";
import type { PortfolioAnalysis } from "@/lib/api/types";
import { fmtNumber, fmtPercent, fmtSignedPercent } from "@/lib/format";
import { sectorLabel } from "@/lib/sectors";
import { cn } from "@/lib/utils";

/**
 * Every number on this panel is measured from the price history of the
 * holdings that were entered. None of it comes from a fitted model, with the
 * single exception of the forward block, which is labelled with the model and
 * run date it came from.
 *
 * The panel that matters most is risk contribution. A reader already knows
 * what share of their money is in each name; what they cannot see is that a
 * quarter of the money can be most of the risk. That gap is stated in words,
 * not left for them to spot in a table.
 */

function fmtVnd(value: number, locale: string) {
  // Millions and billions, because 563.240.000 does not read at a glance.
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) {
    return `${fmtNumber(value / 1_000_000_000, locale, { maximumFractionDigits: 2 })} tỷ`;
  }
  if (abs >= 1_000_000) {
    return `${fmtNumber(value / 1_000_000, locale, { maximumFractionDigits: 1 })} tr`;
  }
  return fmtNumber(value, locale, { maximumFractionDigits: 0 });
}

function Tile({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note: string;
  tone?: "positive" | "negative" | "caution";
}) {
  return (
    <div className="bg-background p-5">
      <dt className="text-xs text-dim">{label}</dt>
      <dd
        className={cn(
          "figure mt-2 text-xl font-semibold",
          tone === "positive" && "text-positive",
          tone === "negative" && "text-negative",
          tone === "caution" && "text-caution",
        )}
      >
        {value}
      </dd>
      <p className="mt-2 text-xs leading-relaxed text-dim">{note}</p>
    </div>
  );
}

export function PortfolioResult({ data }: { data: PortfolioAnalysis }) {
  const t = useTranslations("portfolio.result");
  const [glossaryOpen, setGlossaryOpen] = useState(false);
  const locale = useLocale();
  const c = data.concentration;

  // The position whose risk share most exceeds its money share. This is the
  // sentence a reader takes away, so it is computed rather than left implicit.
  const standout = useMemo(() => {
    if (data.positions.length === 0) return null;
    return data.positions.reduce((worst, p) =>
      p.risk_contribution - p.weight > worst.risk_contribution - worst.weight
        ? p
        : worst,
    );
  }, [data.positions]);

  const riskOption = useMemo<EChartsCoreOption>(() => {
    const symbols = data.positions.map((p) => p.symbol);
    return {
      animationDuration: 400,
      legend: { show: false },
      grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) =>
          typeof v === "number" ? fmtPercent(v / 100, locale) : String(v),
      },
      xAxis: {
        type: "category",
        data: symbols,
        axisLine: { lineStyle: { color: CHART.border } },
        axisTick: { show: false },
        axisLabel: { color: CHART.dim, margin: 12, fontFamily: CHART.mono },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: CHART.surface } },
        axisLabel: { color: CHART.dim, formatter: "{value}%" },
      },
      series: [
        {
          name: t("weightSeries"),
          type: "bar",
          data: data.positions.map((p) => +(p.weight * 100).toFixed(2)),
          barWidth: "26%",
          barGap: "24%",
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
          labelLayout: { hideOverlap: true },
        },
        {
          name: t("riskSeries"),
          type: "bar",
          data: data.positions.map((p) => +(p.risk_contribution * 100).toFixed(2)),
          barWidth: "26%",
          itemStyle: { color: CHART.brand, borderRadius: [4, 4, 0, 0] },
          label: {
            show: true,
            position: "top",
            distance: 5,
            color: CHART.ink,
            fontFamily: CHART.mono,
            fontSize: 11,
            formatter: (p: { value: number }) => `${p.value}%`,
          },
          labelLayout: { hideOverlap: true },
        },
      ],
    };
  }, [data.positions, locale, t]);

  const forward = data.forward;

  /** Probability of exceeding each decline level, as a falling curve. */
  const exceedanceOption = useMemo<EChartsCoreOption>(() => {
    const buckets = forward?.drawdown_probabilities ?? [];
    return {
      animationDuration: 450,
      legend: { show: false },
      grid: { left: 8, right: 20, top: 28, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) =>
          typeof v === "number" ? fmtPercent(v / 100, locale) : String(v),
      },
      xAxis: {
        type: "category",
        data: buckets.map((b) => fmtPercent(Math.abs(b.threshold), locale)),
        axisLine: { lineStyle: { color: CHART.border } },
        axisTick: { show: false },
        axisLabel: { color: CHART.dim, fontFamily: CHART.mono, margin: 12 },
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
          data: buckets.map((b) => +(b.probability * 100).toFixed(1)),
          smooth: false,
          symbol: "circle",
          symbolSize: 9,
          lineStyle: { width: 2.5, color: CHART.negative },
          itemStyle: {
            color: CHART.negative,
            borderColor: "#ffffff",
            borderWidth: 2,
          },
          areaStyle: { color: "rgba(169, 59, 50, 0.10)" },
          label: {
            show: true,
            position: "top",
            distance: 8,
            color: CHART.ink,
            fontFamily: CHART.mono,
            fontSize: 11,
            formatter: (p: { value: number }) => `${p.value}%`,
          },
          // A coin-flip line: above it the decline is more likely than not.
          markLine: {
            silent: true,
            symbol: "none",
            label: {
              formatter: "50%",
              color: CHART.dim,
              fontFamily: CHART.mono,
              fontSize: 11,
              position: "insideEndTop",
            },
            lineStyle: { color: CHART.faint, type: "dashed", width: 1.5 },
            data: [{ yAxis: 50 }],
          },
        },
      ],
    };
  }, [forward, locale]);

  /** The same thresholds expressed as money, next to the portfolio's value. */
  const lossScaleOption = useMemo<EChartsCoreOption>(() => {
    const buckets = forward?.drawdown_probabilities ?? [];
    return {
      animationDuration: 450,
      legend: { show: false },
      grid: { left: 8, right: 24, top: 28, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) =>
          typeof v === "number"
            ? `${fmtVnd(v, locale)} đ`
            : String(v),
      },
      xAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: CHART.surface } },
        axisLabel: {
          color: CHART.dim,
          formatter: (v: number) => fmtVnd(v, locale),
        },
      },
      yAxis: {
        type: "category",
        data: buckets.map((b) => fmtPercent(Math.abs(b.threshold), locale)),
        axisLine: { lineStyle: { color: CHART.border } },
        axisTick: { show: false },
        axisLabel: { color: CHART.dim, fontFamily: CHART.mono },
      },
      series: [
        {
          type: "bar",
          barWidth: "48%",
          data: buckets.map((b) =>
            Math.round(Math.abs(b.threshold) * data.invested_value),
          ),
          itemStyle: {
            color: CHART.signal,
            borderRadius: [0, 4, 4, 0] as const,
          },
          label: {
            show: true,
            position: "right",
            distance: 8,
            color: CHART.ink,
            fontFamily: CHART.mono,
            fontSize: 11,
            formatter: (p: { value: number }) => `${fmtVnd(p.value, locale)} đ`,
          },
        },
      ],
    };
  }, [forward, locale, data.invested_value]);

  return (
    <div className="mt-10 space-y-12">
      {data.unpriced.length > 0 && (
        <p
          role="alert"
          className="border-l-4 border-caution bg-caution-soft px-5 py-4 text-sm leading-relaxed text-ink"
        >
          {t("unpriced", {
            symbols: data.unpriced.join(", "),
            count: data.unpriced.length,
          })}
        </p>
      )}

      {/* 1. What is it worth, and is it up or down. */}
      <section aria-labelledby="pf-overview">
        <h2 id="pf-overview" className="title-md">
          {t("overviewHeading")}
        </h2>
        <dl className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4">
          <Tile
            label={t("totalValue")}
            value={`${fmtVnd(data.total_value, locale)} đ`}
            note={t("totalValueNote", {
              invested: `${fmtVnd(data.invested_value, locale)} đ`,
              cash: `${fmtVnd(data.cash, locale)} đ`,
            })}
          />
          <Tile
            label={t("profit")}
            value={
              data.profit_percent === null
                ? t("noCostBasis")
                : fmtSignedPercent(data.profit_percent, locale, 1)
            }
            note={
              data.profit === null
                ? t("noCostBasisNote")
                : t("profitNote", { amount: `${fmtVnd(data.profit, locale)} đ` })
            }
            tone={
              data.profit_percent === null
                ? undefined
                : data.profit_percent >= 0
                  ? "positive"
                  : "negative"
            }
          />
          <Tile
            label={t("riskLevel")}
            value={t(`riskState.${data.risk_state}`)}
            note={t("riskLevelNote", {
              vol: fmtPercent(data.volatility, locale),
            })}
            tone={
              data.risk_state === "high" || data.risk_state === "elevated"
                ? "caution"
                : undefined
            }
          />
          <Tile
            label={t("beta")}
            value={data.beta === null ? t("notAvailable") : fmtNumber(data.beta, locale)}
            note={
              data.beta === null
                ? t("betaMissing")
                : data.beta >= 1
                  ? t("betaAbove", { pct: fmtPercent(data.beta - 1, locale) })
                  : t("betaBelow", { pct: fmtPercent(1 - data.beta, locale) })
            }
          />
        </dl>

        {standout && standout.risk_contribution - standout.weight > 0.05 && (
          <p className="mt-6 max-w-4xl border-l-4 border-signal bg-signal-soft px-5 py-4 leading-relaxed text-ink">
            {t("standout", {
              symbol: standout.symbol,
              weight: fmtPercent(standout.weight, locale),
              risk: fmtPercent(standout.risk_contribution, locale),
              vol: fmtPercent(standout.volatility, locale),
            })}
          </p>
        )}
      </section>

      {/* 2. Where the risk actually sits. */}
      <section aria-labelledby="pf-risk-contribution">
        <h2 id="pf-risk-contribution" className="title-md">
          {t("contributionHeading")}
        </h2>
        <p className="mt-3 max-w-3xl leading-relaxed text-dim">
          {t("contributionLead")}
        </p>

        <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2" aria-hidden="true">
          <span className="inline-flex items-center gap-2 text-xs text-dim">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: CHART.lightgray }}
            />
            {t("weightSeries")}
          </span>
          <span className="inline-flex items-center gap-2 text-xs text-dim">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: CHART.brand }}
            />
            {t("riskSeries")}
          </span>
        </div>

        <EChart
          option={riskOption}
          ariaLabel={t("contributionHeading")}
          className="mt-2 h-80"
        />

        <div className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[46rem] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                {[
                  "colSymbol",
                  "colSector",
                  "colPrice",
                  "colValue",
                  "colWeight",
                  "colRisk",
                  "colVol",
                  "colBeta",
                  "colProfit",
                ].map((key, i) => (
                  <th
                    key={key}
                    scope="col"
                    className={cn(
                      "py-2.5 pr-4 text-xs font-medium uppercase tracking-[0.06em] text-dim",
                      i >= 2 && "text-right",
                    )}
                  >
                    {t(key)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.positions.map((p) => (
                <tr key={p.symbol} className="border-b border-border/70">
                  <th scope="row" className="figure py-3 pr-4 text-left font-medium">
                    {p.symbol}
                  </th>
                  <td className="py-3 pr-4 text-dim">
                    {sectorLabel(p.sector, locale) ?? "—"}
                  </td>
                  <td className="figure py-3 pr-4 text-right">
                    {fmtNumber(p.price, locale, { maximumFractionDigits: 0 })}
                  </td>
                  <td className="figure py-3 pr-4 text-right">
                    {fmtVnd(p.market_value, locale)}
                  </td>
                  <td className="figure py-3 pr-4 text-right">
                    {fmtPercent(p.weight, locale)}
                  </td>
                  <td
                    className={cn(
                      "figure py-3 pr-4 text-right",
                      p.risk_contribution > p.weight * 1.3 && "text-caution",
                    )}
                  >
                    {fmtPercent(p.risk_contribution, locale)}
                  </td>
                  <td className="figure py-3 pr-4 text-right">
                    {fmtPercent(p.volatility, locale)}
                  </td>
                  <td className="figure py-3 pr-4 text-right">
                    {p.beta === null ? "—" : fmtNumber(p.beta, locale)}
                  </td>
                  <td
                    className={cn(
                      "figure py-3 pr-4 text-right",
                      p.profit_percent !== null &&
                        (p.profit_percent >= 0 ? "text-positive" : "text-negative"),
                    )}
                  >
                    {p.profit_percent === null
                      ? "—"
                      : fmtSignedPercent(p.profit_percent, locale, 1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 3. Diversification by risk, not by headcount. */}
      <section aria-labelledby="pf-diversification">
        <h2 id="pf-diversification" className="title-md">
          {t("diversificationHeading")}
        </h2>
        <p className="mt-3 max-w-3xl leading-relaxed text-dim">
          {t("diversificationLead", {
            positions: c.positions,
            bets: fmtNumber(c.effective_bets, locale, {
              maximumFractionDigits: 1,
            }),
          })}
        </p>

        <dl className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4">
          <Tile
            label={t("positions")}
            value={fmtNumber(c.positions, locale)}
            note={t("positionsNote", {
              largest: fmtPercent(c.largest_weight, locale),
            })}
          />
          <Tile
            label={t("effectiveBets")}
            value={fmtNumber(c.effective_bets, locale, {
              maximumFractionDigits: 1,
            })}
            note={t("effectiveBetsNote")}
            tone={c.effective_bets < c.positions / 2 ? "caution" : undefined}
          />
          <Tile
            label={t("avgCorrelation")}
            value={fmtNumber(c.average_correlation, locale)}
            note={t("avgCorrelationNote")}
          />
          <Tile
            label={t("topSector")}
            value={
              Object.keys(c.sector_weights)[0]
                ? `${fmtPercent(Object.values(c.sector_weights)[0], locale)}`
                : t("notAvailable")
            }
            note={
              Object.keys(c.sector_weights)[0]
                ? t("topSectorNote", {
                    sector:
                      sectorLabel(Object.keys(c.sector_weights)[0], locale) ??
                      "",
                  })
                : t("sectorMissing")
            }
          />
        </dl>

        {c.max_pair && c.max_pair_correlation !== null && (
          <p className="mt-5 max-w-4xl text-sm leading-relaxed text-dim">
            {t("closestPair", {
              a: c.max_pair[0],
              b: c.max_pair[1],
              value: fmtNumber(c.max_pair_correlation, locale),
            })}
          </p>
        )}
      </section>

      {/* 4. Loss measured on this book's own history. */}
      <section aria-labelledby="pf-loss">
        <h2 id="pf-loss" className="title-md">
          {t("lossHeading")}
        </h2>
        <p className="mt-3 max-w-3xl leading-relaxed text-dim">
          {t("lossLead", {
            days: data.observations,
            months: Math.round(data.observations / 21),
          })}
        </p>
        <dl className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4">
          <Tile
            label={t("var95")}
            value={fmtPercent(data.var_95, locale)}
            note={t("var95Note", {
              amount: `${fmtVnd(Math.abs(data.var_95 * data.invested_value), locale)} đ`,
            })}
            tone="caution"
          />
          <Tile
            label={t("es95")}
            value={fmtPercent(data.expected_shortfall_95, locale)}
            note={t("es95Note", {
              amount: `${fmtVnd(Math.abs(data.expected_shortfall_95 * data.invested_value), locale)} đ`,
            })}
            tone="caution"
          />
          <Tile
            label={t("maxDrawdown")}
            value={fmtPercent(data.max_drawdown, locale)}
            note={t("maxDrawdownNote")}
          />
          <Tile
            label={t("downside")}
            value={fmtPercent(data.downside_deviation, locale)}
            note={t("downsideNote")}
          />
        </dl>
      </section>

      {/* Each term defined against this portfolio's own numbers. A generic
          definition of "VaR" tells a reader what the acronym expands to; the
          version below tells them how much money is at stake in their book,
          which is the question they actually had. */}
      <section aria-labelledby="pf-glossary">
        <button
          type="button"
          onClick={() => setGlossaryOpen((v) => !v)}
          aria-expanded={glossaryOpen}
          className="flex w-full items-center justify-between gap-4 rounded-lg border border-border bg-surface/60 px-5 py-4 text-left transition-colors hover:border-brand"
        >
          <span>
            <span id="pf-glossary" className="block font-semibold">
              {t("glossaryHeading")}
            </span>
            <span className="mt-1 block text-sm text-dim">
              {t("glossaryLead")}
            </span>
          </span>
          <span aria-hidden="true" className="figure shrink-0 text-brand">
            {glossaryOpen ? "−" : "+"}
          </span>
        </button>

        {glossaryOpen && (
          <dl className="mt-5 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2">
            {[
              {
                term: t("var95"),
                body: t("explain.var95", {
                  pct: fmtPercent(Math.abs(data.var_95), locale),
                  amount: `${fmtVnd(Math.abs(data.var_95 * data.invested_value), locale)} đ`,
                }),
              },
              {
                term: t("es95"),
                body: t("explain.es95", {
                  pct: fmtPercent(Math.abs(data.expected_shortfall_95), locale),
                  amount: `${fmtVnd(Math.abs(data.expected_shortfall_95 * data.invested_value), locale)} đ`,
                }),
              },
              {
                term: t("maxDrawdown"),
                body: t("explain.maxDrawdown", {
                  pct: fmtPercent(Math.abs(data.max_drawdown), locale),
                  amount: `${fmtVnd(Math.abs(data.max_drawdown * data.invested_value), locale)} đ`,
                }),
              },
              {
                term: t("downside"),
                body: t("explain.downside", {
                  pct: fmtPercent(data.downside_deviation, locale),
                  total: fmtPercent(data.volatility, locale),
                }),
              },
              {
                term: t("riskSeries"),
                body: t("explain.riskContribution"),
              },
              {
                term: t("effectiveBets"),
                body: t("explain.effectiveBets", {
                  positions: c.positions,
                  bets: fmtNumber(c.effective_bets, locale, {
                    maximumFractionDigits: 1,
                  }),
                }),
              },
              {
                term: t("beta"),
                body:
                  data.beta === null
                    ? t("explain.betaMissing")
                    : t("explain.beta", {
                        beta: fmtNumber(data.beta, locale),
                        move: fmtPercent(Math.abs(data.beta) * 0.1, locale),
                      }),
              },
              {
                term: t("avgCorrelation"),
                body: t("explain.correlation", {
                  value: fmtNumber(c.average_correlation, locale),
                }),
              },
            ].map((item) => (
              <div key={item.term} className="bg-background p-5">
                <dt className="font-medium">{item.term}</dt>
                <dd className="mt-2 text-sm leading-relaxed text-dim">
                  {item.body}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      {/* 5. The only forward-looking block, and it says where it came from. */}
      {data.forward && (
        <section aria-labelledby="pf-forward">
          <h2 id="pf-forward" className="title-md">
            {t("forwardHeading")}
          </h2>
          <p className="mt-3 max-w-3xl leading-relaxed text-dim">
            {t("forwardLead", {
              beta: fmtNumber(data.forward.portfolio_beta, locale),
              paths: fmtNumber(data.forward.paths, locale),
              origin: data.forward.forecast_origin,
              baseDays: data.forward.base_horizon_days,
              horizonDays: data.forward.horizon_days,
            })}
          </p>
          <div className="mt-7 grid gap-6 desk:grid-cols-2">
            <figure className="min-w-0 overflow-hidden rounded-lg border border-border bg-background p-5 shadow-sm">
              <figcaption>
                <h3 className="text-base font-semibold">
                  {t("exceedanceTitle")}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-dim">
                  {t("exceedanceNote")}
                </p>
              </figcaption>
              <EChart
                option={exceedanceOption}
                ariaLabel={t("exceedanceTitle")}
                className="mt-4 h-72"
              />
            </figure>

            <figure className="min-w-0 overflow-hidden rounded-lg border border-border bg-background p-5 shadow-sm">
              <figcaption>
                <h3 className="text-base font-semibold">
                  {t("lossScaleTitle")}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-dim">
                  {t("lossScaleNote")}
                </p>
              </figcaption>
              <EChart
                option={lossScaleOption}
                ariaLabel={t("lossScaleTitle")}
                className="mt-4 h-72"
              />
            </figure>
          </div>

          <div className="mt-6 overflow-x-auto">
            <table className="w-full min-w-[28rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th scope="col" className="py-2.5 pr-4 text-xs font-medium uppercase tracking-[0.06em] text-dim">
                    {t("colDecline")}
                  </th>
                  <th scope="col" className="py-2.5 text-right text-xs font-medium uppercase tracking-[0.06em] text-dim">
                    {t("colChance")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.forward.drawdown_probabilities.map((b) => (
                  <tr key={b.threshold} className="border-b border-border/70">
                    <th scope="row" className="figure py-3 pr-4 text-left font-normal">
                      {t("declineRow", {
                        pct: fmtPercent(Math.abs(b.threshold), locale),
                        amount: `${fmtVnd(Math.abs(b.threshold) * data.invested_value, locale)} đ`,
                      })}
                    </th>
                    <td className="figure py-3 text-right">
                      {fmtPercent(b.probability, locale)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-5 max-w-4xl text-xs leading-relaxed text-dim">
            {t("forwardCaveat", {
              baseDays: data.forward.base_horizon_days,
            })}
          </p>
        </section>
      )}

      <section
        className="border-t border-border pt-6"
        aria-label={t("provenanceLabel")}
      >
        <p className="max-w-4xl text-xs leading-relaxed text-dim">
          {t("provenance", {
            days: data.observations,
            lookback: data.lookback_days,
            asOf: data.data_as_of.slice(0, 10),
          })}
        </p>
      </section>
    </div>
  );
}
