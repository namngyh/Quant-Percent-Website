"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { EChart, CHART } from "@/components/charts/echart";
import type { MarginRisk, MarginStatus, PortfolioAnalysis } from "@/lib/api/types";
import { fmtNumber, fmtPercent, fmtVnd } from "@/lib/format";
import { cn } from "@/lib/utils";
import { InfoTip } from "@/components/info-tip";

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

function Tile({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note: string;
  tone?: "negative" | "caution";
}) {
  return (
    <div className="bg-background p-5">
      <dt className="text-xs text-dim">{label}</dt>
      <dd
        className={cn(
          "figure mt-2 text-xl font-semibold",
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

function statusTone(status: MarginStatus): "negative" | "caution" | undefined {
  if (status === "below_force" || status === "negative_equity") return "negative";
  if (status === "between") return "caution";
  return undefined;
}

/** A horizontal bar split into labelled segments that sum to `total`. */
function SplitBar({
  label,
  total,
  segments,
  locale,
}: {
  label: string;
  total: number;
  segments: { name: string; value: number; className: string }[];
  locale: string;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-medium uppercase tracking-[0.06em] text-dim">
          {label}
        </span>
        <span className="figure text-sm">{fmtVnd(total, locale)} đ</span>
      </div>
      <div className="mt-2 flex h-9 overflow-hidden rounded-md" role="img" aria-label={label}>
        {segments
          .filter((s) => s.value > 0)
          .map((s) => {
            const share = total > 0 ? s.value / total : 0;
            return (
              <div
                key={s.name}
                className={cn("flex items-center justify-center overflow-hidden", s.className)}
                style={{ flex: `${share} 1 0%` }}
                title={`${s.name}: ${fmtVnd(s.value, locale)} đ (${fmtPercent(share, locale, 0)})`}
              >
                {share >= 0.14 && (
                  <span className="figure truncate px-2 text-xs">
                    {s.name} · {fmtPercent(share, locale, 0)}
                  </span>
                )}
              </div>
            );
          })}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-dim">
        {segments.map((s) => (
          <li key={s.name} className="inline-flex items-center gap-2">
            <span className={cn("h-2.5 w-2.5 rounded-sm", s.className)} />
            {s.name}: <span className="figure text-ink">{fmtVnd(s.value, locale)} đ</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Where the margin ratio sits against the broker's two thresholds. */
function RatioBand({
  ratio,
  callRatio,
  forceRatio,
  locale,
  labels,
}: {
  ratio: number;
  callRatio: number;
  forceRatio: number;
  locale: string;
  labels: { you: string; call: string; force: string };
}) {
  // The axis runs 0–100% of assets; the reader's own ratio is a needle.
  const pct = (v: number) => `${Math.min(Math.max(v, 0), 1) * 100}%`;
  return (
    <div>
      <div className="relative h-3 overflow-hidden rounded-full bg-surface">
        <div
          className="absolute inset-y-0 left-0 bg-negative/70"
          style={{ width: pct(forceRatio) }}
        />
        <div
          className="absolute inset-y-0 bg-caution/70"
          style={{ left: pct(forceRatio), width: pct(callRatio - forceRatio) }}
        />
        <div
          className="absolute inset-y-0 bg-positive/50"
          style={{ left: pct(callRatio), right: 0 }}
        />
      </div>
      {/* Three rows: the two thresholds are often 5 points apart, which
          is not enough width for two labels on one line. */}
      <div className="relative mt-1 h-[4.5rem] text-xs">
        {[
          { at: ratio, text: labels.you, strong: true, row: "top-0" },
          { at: callRatio, text: labels.call, strong: false, row: "top-6" },
          { at: forceRatio, text: labels.force, strong: false, row: "top-11" },
        ].map((m) => (
          <div
            key={m.text}
            className={cn(
              "absolute -translate-x-1/2 text-center whitespace-nowrap",
              m.row,
              m.strong ? "text-ink" : "text-dim",
            )}
            style={{ left: pct(m.at) }}
          >
            <div
              className={cn(
                "mx-auto w-px",
                m.strong ? "h-3 bg-ink" : "h-2 bg-dim",
              )}
            />
            <span className="figure">{fmtPercent(m.at, locale, 1)}</span>
            <span className="ml-1">{m.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

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

  return (
    <section aria-labelledby="pf-margin">
      <h2 id="pf-margin" className="title-md inline-flex items-center gap-2">
        {t("heading")}
        <InfoTip
          wide
          text={[
            t("lead"),
            t("caveat.selfReported", { asOf: data.data_as_of.slice(0, 10) }),
            t("caveat.collateral"),
            t("caveat.rollover"),
          ]}
        />
      </h2>

      {m.status !== "above_call" && (
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
          })}
        </p>
      )}

      {/* 1. Where the money is and where it came from, on the same scale. */}
      <div className="mt-7 grid gap-6 rounded-lg border border-border bg-background p-5 shadow-sm desk:grid-cols-2">
        <SplitBar
          label={t("assets")}
          total={m.assets}
          locale={locale}
          segments={[
            { name: t("stocks"), value: stockValue, className: "bg-brand/70 text-white" },
            { name: t("cash"), value: cash, className: "bg-brand-soft text-brand-strong" },
          ]}
        />
        <SplitBar
          label={t("funding")}
          total={m.assets}
          locale={locale}
          segments={[
            {
              name: t("equity"),
              value: Math.max(m.equity, 0),
              className: "bg-positive/60 text-white",
            },
            { name: t("debt"), value: m.debt, className: "bg-signal/70 text-white" },
          ]}
        />
      </div>

      {/* 2. The ratio against the broker's thresholds. */}
      {m.status !== "negative_equity" && (
        <div className="mt-6 rounded-lg border border-border bg-background p-5 shadow-sm">
          <h3 className="inline-flex items-center gap-2 text-base font-semibold">
            {t("ratioTitle")}
            <InfoTip wide text={t("ratioNote")} />
          </h3>
          <div className="mt-4">
            <RatioBand
              ratio={m.margin_ratio}
              callRatio={m.call_ratio}
              forceRatio={m.force_ratio}
              locale={locale}
              labels={{ you: t("you"), call: t("callShort"), force: t("forceShort") }}
            />
          </div>
        </div>
      )}

      {/* 3. The four numbers. */}
      <dl className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4">
        <Tile
          label={t("leverage")}
          value={m.leverage === null ? "—" : `${fmtNumber(m.leverage, locale)}×`}
          note={leverageSentence}
          tone={tone}
        />
        <Tile
          label={t("distanceCall")}
          value={
            m.distance_to_call === null
              ? "—"
              : `−${fmtPercent(m.distance_to_call.drop, locale, 1)}`
          }
          note={
            m.distance_to_call === null || m.distance_to_force === null
              ? t("distanceNone")
              : t("distanceNote", {
                  amount: `${fmtVnd(m.distance_to_call.amount, locale)} đ`,
                  force: fmtPercent(m.distance_to_force.drop, locale, 1),
                })
          }
          tone={tone}
        />
        <Tile
          label={t("interest")}
          value={`${fmtVnd(m.by_horizon[m.by_horizon.length - 1]?.interest ?? 0, locale)} đ`}
          note={
            m.equity > 0
              ? t("interestNote", {
                  pct: fmtPercent(
                    (m.by_horizon[m.by_horizon.length - 1]?.interest_pct_equity ?? 0),
                    locale,
                    1,
                  ),
                  rate: fmtPercent(m.rate, locale, 1),
                })
              : t("interestNoteNoEquity", { rate: fmtPercent(m.rate, locale, 1) })
          }
        />
        <Tile
          label={t("idleCash")}
          value={
            m.idle_cash_cost_per_year === null
              ? "—"
              : `${fmtVnd(m.idle_cash_cost_per_year, locale)} đ`
          }
          note={
            m.idle_cash_cost_per_year === null
              ? t("idleCashNone")
              : t("idleCashNote", {
                  cash: `${fmtVnd(Math.min(cash, m.debt), locale)} đ`,
                })
          }
        />
      </dl>

      {/* The realised fall next to the distance: two numbers a reader can
          hold side by side without any model in between. */}
      {m.distance_to_call !== null && (
        <p className="mt-6 max-w-4xl border-l-4 border-signal bg-signal-soft px-5 py-4 leading-relaxed text-ink">
          {t("realisedVsDistance", {
            days: data.observations,
            drawdown: fmtPercent(Math.abs(data.max_drawdown), locale, 1),
            distance: fmtPercent(m.distance_to_call.drop, locale, 1),
          })}
        </p>
      )}

      {/* 4. The same loan over each holding period. */}
      <div className="mt-8">
        <h3 className="inline-flex items-center gap-2 text-base font-semibold">
          {t("horizonTitle")}
          <InfoTip
            wide
            text={[
              canScale ? t("horizonNote") : t("horizonNoteNoBeta"),
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

        {(canScale || hasHistory) && (
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
                {["colHorizon", "colModel", "colHistory", "colInterest", "colInterestPct", "colBreakeven"].map(
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

      {/* 5. What the account looks like after each fall. */}
      <div className="mt-8">
        <h3 className="inline-flex items-center gap-2 text-base font-semibold">
          {t("scenarioTitle")}
          <InfoTip wide text={t("scenarioNote")} />
        </h3>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[40rem] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                {["colDrop", "colAssets", "colEquity", "colRatio", "colStatus", "colTopUp"].map(
                  (key, i) => (
                    <th
                      key={key}
                      scope="col"
                      className={cn(
                        "py-2.5 pr-4 text-xs font-medium uppercase tracking-[0.06em] text-dim",
                        i >= 1 && i !== 4 && "text-right",
                      )}
                    >
                      {t(key)}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {m.scenarios.map((s) => {
                const st = statusTone(s.status);
                return (
                  <tr key={s.drop} className="border-b border-border/70">
                    <th scope="row" className="figure py-3 pr-4 text-left font-normal">
                      −{fmtPercent(s.drop, locale, 0)}
                    </th>
                    <td className="figure py-3 pr-4 text-right">{fmtVnd(s.assets, locale)}</td>
                    <td
                      className={cn(
                        "figure py-3 pr-4 text-right",
                        s.equity <= 0 && "text-negative",
                      )}
                    >
                      {fmtVnd(s.equity, locale)}
                    </td>
                    <td className="figure py-3 pr-4 text-right">
                      {fmtPercent(s.margin_ratio, locale, 1)}
                    </td>
                    <td
                      className={cn(
                        "py-3 pr-4",
                        st === "caution" && "text-caution",
                        st === "negative" && "text-negative",
                      )}
                    >
                      {t(`statusShort.${s.status}`)}
                    </td>
                    <td className="figure py-3 pr-4 text-right">
                      {s.top_up > 0 ? `${fmtVnd(s.top_up, locale)} đ` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 6. The realised risk figures, on equity instead of on the stocks. */}
      {m.equity > 0 && (
        <div className="mt-8">
          <h3 className="inline-flex items-center gap-2 text-base font-semibold">
            {t("equityRiskTitle")}
            <InfoTip wide text={t("equityRiskNote")} />
          </h3>
          <dl className="mt-4 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-3">
            {[
              { key: "var95", stocks: data.var_95, equity: m.equity_var_95 },
              { key: "es95", stocks: data.expected_shortfall_95, equity: m.equity_expected_shortfall_95 },
              { key: "maxDrawdown", stocks: data.max_drawdown, equity: m.equity_max_drawdown },
            ].map((row) => (
              <div key={row.key} className="bg-background p-5">
                <dt className="text-xs text-dim">{t(`equityMeasures.${row.key}`)}</dt>
                <dd
                  className={cn(
                    "figure mt-2 text-xl font-semibold",
                    row.equity !== null && row.equity <= -1 ? "text-negative" : "text-caution",
                  )}
                >
                  {row.equity === null
                    ? "—"
                    : row.equity <= -1
                      ? t("wipedOut")
                      : fmtPercent(row.equity, locale, 1)}
                </dd>
                <p className="mt-2 text-xs leading-relaxed text-dim">
                  {t("equityVsStocks", { stocks: fmtPercent(row.stocks, locale, 1) })}
                </p>
              </div>
            ))}
          </dl>
        </div>
      )}

    </section>
  );
}
