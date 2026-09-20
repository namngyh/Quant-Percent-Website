"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { EChart, CHART } from "@/components/charts/echart";
import type { MarginRisk, MarginStatus, PortfolioAnalysis } from "@/lib/api/types";
import { fmtNumber, fmtPercent, fmtVnd } from "@/lib/format";
import { cn } from "@/lib/utils";
import { InfoTip } from "@/components/info-tip";
import { StatTable } from "@/components/portfolio/stat-table";
import { BalanceColumns, LossDumbbell, RatioGauge, ScenarioLine } from "@/components/portfolio/charts";

/**
 * The portfolio seen from the reader's own money.
 *
 * Everything on this panel is arithmetic on the loan the reader typed and
 * on figures the rest of the page already shows. It says how far the stocks
 * can fall before the broker's thresholds are reached, what the loan costs
 * for each holding period, and how often the index has fallen that far in
 * that long. It does not say whether to borrow less.
 *
 * The one estimate — the probability of reaching the warning threshold —
 * is placed next to the historical frequency of the same fall, so a reader
 * can see the two disagree when they do.
 */

const HORIZON_KEY: Record<number, string> = {
  21: "m1",
  63: "m3",
  126: "m6",
  252: "y1",
};

function statusTone(status: MarginStatus): "negative" | "caution" | undefined {
  if (status === "below_force" || status === "negative_equity") return "negative";
  if (status === "between") return "caution";
  return undefined;
}

/** Past the warning line already: the odds of reaching it are moot. */
const pastThreshold = (status: MarginStatus) =>
  status === "between" || status === "below_force" || status === "negative_equity";

export function MarginSection({
  margin: m,
  data,
}: {
  margin: MarginRisk;
  data: PortfolioAnalysis;
}) {
  const t = useTranslations("portfolio.margin");
  const th = useTranslations("portfolio.form.horizons");
  const locale = useLocale();
  const stockValue = data.invested_value;
  const cash = data.cash;

  const horizonOption = useMemo<EChartsCoreOption>(() => {
    const rows = m.by_horizon;
    const hasModel = rows.some((r) => r.hit_call_probability !== null);
    const pct = (v: number | null) => (v === null ? null : +(v * 100).toFixed(1));
    return {
      animationDuration: 400,
      legend: { show: false },
      grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) =>
          typeof v === "number" ? fmtPercent(v / 100, locale) : "—",
      },
      xAxis: {
        type: "category",
        data: rows.map((r) => th(HORIZON_KEY[r.horizon_days] ?? "m3")),
        axisLine: { lineStyle: { color: CHART.border } },
        axisTick: { show: false },
        axisLabel: { color: CHART.dim, margin: 12 },
      },
      // Auto-scaled: a low-leverage book sits under 10% at every horizon,
      // and a fixed 0–100 axis flattened that into an unreadable line.
      yAxis: {
        type: "value",
        min: 0,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: CHART.surface } },
        axisLabel: { color: CHART.dim, formatter: "{value}%" },
      },
      series: [
        {
          name: t("chart.model"),
          type: "line",
          data: rows.map((r) => pct(r.hit_call_probability)),
          symbol: "circle",
          symbolSize: 9,
          lineStyle: { width: 2.5, color: CHART.negative },
          itemStyle: { color: CHART.negative, borderColor: "#ffffff", borderWidth: 2 },
          label: {
            show: hasModel,
            position: "top",
            distance: 8,
            color: CHART.ink,
            fontFamily: CHART.mono,
            fontSize: 11,
            formatter: (p: { value: number | null }) =>
              p.value === null ? "" : fmtPercent(p.value / 100, locale, 1),
          },
        },
        {
          name: t("chart.history"),
          type: "line",
          data: rows.map((r) => pct(r.historical_frequency)),
          symbol: "diamond",
          symbolSize: 9,
          lineStyle: { width: 2, color: CHART.signal, type: "dashed" },
          itemStyle: { color: CHART.signal, borderColor: "#ffffff", borderWidth: 2 },
          // Labelled only when it is the only series; otherwise the two
          // sets of labels collide and the table below has both anyway.
          label: {
            show: !hasModel,
            position: "top",
            distance: 8,
            color: CHART.signalDark,
            fontFamily: CHART.mono,
            fontSize: 11,
            formatter: (p: { value: number | null }) =>
              p.value === null ? "" : fmtPercent(p.value / 100, locale, 1),
          },
        },
      ],
    };
  }, [m.by_horizon, locale, t, th]);

  const tone = statusTone(m.status);
  const leverageSentence =
    m.leverage === null
      ? t("leverageNone")
      : t("leverageNote", {
          equity: fmtPercent((0.1 * stockValue) / m.equity, locale, 0),
        });

  const canScale = m.by_horizon.some((h) => h.hit_call_probability !== null);
  const hasHistory = m.by_horizon.some((h) => h.historical_frequency !== null);
  const external = m.external;
  const past = pastThreshold(m.status);
  // Probabilities of reaching a line the account is already past, or that
  // an external lender never drew, are not shown — only the interest.
  const showOdds = !external && !past && (canScale || hasHistory);

  return (
    <section aria-labelledby="pf-margin">
      <h2 id="pf-margin" className="inline-flex items-center gap-2 text-lg font-semibold">
        {t("heading")}
        <InfoTip
          wide
          text={[
            t("lead"),
            t("caveat.selfReported"),
            ...(external ? [] : [t("caveat.collateral"), t("caveat.rollover")]),
          ]}
        />
      </h2>

      {m.status !== "above_call" && m.status !== "no_thresholds" && (
        <p
          role="alert"
          className={cn(
            "mt-5 max-w-4xl border-l-4 px-5 py-4 text-sm leading-relaxed text-ink",
            m.status === "between" && "border-caution bg-caution-soft",
            m.status !== "between" && "border-negative bg-surface",
          )}
        >
          {t(`status.${m.status}`, {
            ratio: fmtPercent(m.margin_ratio, locale, 1),
            call: fmtPercent(m.call_ratio, locale, 0),
            force: fmtPercent(m.force_ratio, locale, 0),
            debt: `${fmtVnd(m.debt, locale)} đ`,
            assets: `${fmtVnd(m.assets, locale)} đ`,
          })}
        </p>
      )}

      {/* Plausibility notes on what was typed. The analysis still runs;
          these say where to look again. `already_past_threshold` is
          covered by the status banner above and is not repeated. */}
      {m.warnings.filter((w) => w !== "already_past_threshold").length > 0 && (
        <ul className="mt-5 max-w-4xl space-y-2">
          {m.warnings
            .filter((w) => w !== "already_past_threshold")
            .map((w) => (
              <li
                key={w}
                className="border-l-4 border-caution bg-caution-soft px-5 py-3 text-sm leading-relaxed text-ink"
              >
                {t(`warnings.${w}`, {
                  debt: `${fmtVnd(m.debt, locale)} đ`,
                  stocks: `${fmtVnd(stockValue, locale)} đ`,
                  leverage: m.leverage === null ? "—" : fmtNumber(m.leverage, locale),
                  rate: fmtPercent(m.rate, locale, 1),
                })}
              </li>
            ))}
        </ul>
      )}

      {/* 1+2. The balance sheet as two columns, the ratio as a gauge, and
          the four figures beside them — one row, three ways in. */}
      <div className="mt-6 grid gap-4 desk:grid-cols-12">
        <div className="rounded-lg border border-border bg-background p-4 shadow-sm desk:col-span-4">
          <h3 className="text-sm font-semibold">{t("balanceTitle")}</h3>
          <BalanceColumns margin={m} data={data} />
        </div>
        {m.status !== "negative_equity" && !external && (
          <div className="rounded-lg border border-border bg-background p-4 shadow-sm desk:col-span-3">
            <h3 className="inline-flex items-center gap-2 text-sm font-semibold">
              {t("ratioTitle")}
              <InfoTip wide text={t("ratioNote")} />
            </h3>
            <RatioGauge margin={m} />
          </div>
        )}
        <StatTable
          columns={1}
          className={m.status !== "negative_equity" && !external ? "desk:col-span-5" : "desk:col-span-8"}
          rows={[
          {
            label: t("leverage"),
            value: m.leverage === null ? "—" : `${fmtNumber(m.leverage, locale)}×`,
            note: leverageSentence,
            tone,
          },
          {
            label: t("distanceCall"),
            value:
              m.distance_to_call === null
                ? "—"
                : `−${fmtPercent(m.distance_to_call.drop, locale, 1)}`,
            note: external
              ? t("distanceExternal")
              : m.distance_to_call === null || m.distance_to_force === null
                ? t("distanceNone")
                : t("distanceNote", {
                    amount: `${fmtVnd(m.distance_to_call.amount, locale)} đ`,
                    force: fmtPercent(m.distance_to_force.drop, locale, 1),
                  }),
            tone,
          },
          {
            label: t("interest"),
            value: `${fmtVnd(m.by_horizon[m.by_horizon.length - 1]?.interest ?? 0, locale)} đ`,
            note:
              m.equity > 0
                ? t("interestNote", {
                    pct: fmtPercent(
                      m.by_horizon[m.by_horizon.length - 1]?.interest_pct_equity ?? 0,
                      locale,
                      1,
                    ),
                    rate: fmtPercent(m.rate, locale, 1),
                  })
                : t("interestNoteNoEquity", { rate: fmtPercent(m.rate, locale, 1) }),
          },
          {
            label: t("idleCash"),
            value:
              m.idle_cash_cost_per_year === null
                ? "—"
                : `${fmtVnd(m.idle_cash_cost_per_year, locale)} đ`,
            note:
              m.idle_cash_cost_per_year === null
                ? t("idleCashNone")
                : t("idleCashNote", { cash: `${fmtVnd(Math.min(cash, m.debt), locale)} đ` }),
          },
        ]}
        />
      </div>

      {/* 5+6. Equity as the stocks fall, and each loss on the stocks versus on
          equity — side by side, both about the same thing: leverage. */}
      <div className="mt-6 grid gap-4 desk:grid-cols-12">
        <div className="rounded-lg border border-border bg-background p-4 shadow-sm desk:col-span-7">
          <h3 className="inline-flex items-center gap-2 text-sm font-semibold">
            {t("scenarioTitle")}
            <InfoTip wide text={t("scenarioNote")} />
          </h3>
          {external ? (
            <p className="mt-3 text-sm text-dim">{t("scenarioExternal")}</p>
          ) : (
            <ScenarioLine margin={m} />
          )}
        </div>
        {m.equity > 0 && (
          <div className="rounded-lg border border-border bg-background p-4 shadow-sm desk:col-span-5">
            <h3 className="inline-flex items-center gap-2 text-sm font-semibold">
              {t("equityRiskTitle")}
              <InfoTip wide text={t("equityRiskNote")} />
            </h3>
            <div className="mt-3">
              <LossDumbbell margin={m} data={data} />
            </div>
          </div>
        )}
      </div>


      {/* 4. The same loan over each holding period. */}
      <div className="mt-8">
        <h3 className="inline-flex items-center gap-2 text-base font-semibold">
          {t("horizonTitle")}
          <InfoTip
            wide
            text={[
              external
                ? t("horizonNoteExternal")
                : past
                  ? t("horizonNotePast")
                  : canScale
                    ? t("horizonNote")
                    : t("horizonNoteNoBeta"),
              ...(hasHistory
                ? [
                    t("historyNote", {
                      windows: fmtNumber(m.by_horizon[0]?.historical_windows ?? 0, locale),
                    }),
                  ]
                : []),
              ...(canScale ? [t("caveat.model")] : []),
            ]}
          />
        </h3>

        {showOdds && (
          <>
            <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2" aria-hidden="true">
              <span className="inline-flex items-center gap-2 text-xs text-dim">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: CHART.negative }} />
                {t("chart.model")}
              </span>
              <span className="inline-flex items-center gap-2 text-xs text-dim">
                <span className="h-2.5 w-2.5 rotate-45" style={{ backgroundColor: CHART.signal }} />
                {t("chart.history")}
              </span>
            </div>
            <EChart option={horizonOption} ariaLabel={t("horizonTitle")} className="mt-2 h-64" />
          </>
        )}

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[40rem] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                {(showOdds
                  ? ["colHorizon", "colModel", "colHistory", "colInterest", "colInterestPct", "colBreakeven"]
                  : ["colHorizon", "colInterest", "colInterestPct", "colBreakeven"]
                ).map(
                  (key, i) => (
                    <th
                      key={key}
                      scope="col"
                      className={cn(
                        "py-2.5 pr-4 text-xs font-medium uppercase tracking-[0.06em] text-dim",
                        i >= 1 && "text-right",
                      )}
                    >
                      {t(key)}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {m.by_horizon.map((h) => {
                const selected = h.horizon_days === data.forward?.horizon_days;
                return (
                  <tr
                    key={h.horizon_days}
                    className={cn("border-b border-border/70", selected && "bg-surface/60")}
                  >
                    <th scope="row" className="py-3 pr-4 text-left font-medium">
                      {th(HORIZON_KEY[h.horizon_days] ?? "m3")}
                    </th>
                    {showOdds && (
                      <>
                        <td className="figure py-3 pr-4 text-right">
                          {h.hit_call_probability === null
                            ? "—"
                            : fmtPercent(h.hit_call_probability, locale, 1)}
                        </td>
                        <td className="figure py-3 pr-4 text-right">
                          {h.historical_frequency === null
                            ? "—"
                            : fmtPercent(h.historical_frequency, locale, 1)}
                        </td>
                      </>
                    )}
                    <td className="figure py-3 pr-4 text-right">{fmtVnd(h.interest, locale)}</td>
                    <td className="figure py-3 pr-4 text-right">
                      {h.interest_pct_equity === null
                        ? "—"
                        : fmtPercent(h.interest_pct_equity, locale, 1)}
                    </td>
                    <td className="figure py-3 pr-4 text-right">
                      {h.breakeven_return === null
                        ? "—"
                        : `+${fmtPercent(h.breakeven_return, locale, 1)}`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

    </section>
  );
}
