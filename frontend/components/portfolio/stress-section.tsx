"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { InfoTip } from "@/components/info-tip";
import type { StatRow } from "@/components/portfolio/stat-table";
import { CRISIS_COLOR, CrisisPaths } from "@/components/portfolio/charts";
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
  const callDrop = m && !m.external && m.distance_to_call ? m.distance_to_call.drop : null;

  const crises = useMemo(
    () => [...s.crises].sort((a, b) => CRISIS_ORDER.indexOf(a.key) - CRISIS_ORDER.indexOf(b.key)),
    [s.crises],
  );

  // Nothing is drawn until the reader picks a crisis; each pick draws that
  // one line in and leaves the others alone.
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const shown = crises.filter((c) => selected.has(c.key));

  return (
    <section aria-labelledby="pf-stress">
      <h2 id="pf-stress" className="inline-flex items-center gap-2 text-lg font-semibold">
        {t("heading")}
        <InfoTip
          wide
          text={[t("lead"), t("coverageNote"), onEquity ? t("equityNote") : ""].filter(Boolean)}
        />
      </h2>

      {crises.length > 0 ? (
        <>
          <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label={t("pickLabel")}>
            {crises.map((c) => {
              const on = selected.has(c.key);
              const color = CRISIS_COLOR(c.key);
              return (
                <button
                  key={c.key}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggle(c.key)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors",
                    on
                      ? "border-transparent text-white"
                      : "border-border bg-background text-ink hover:border-ink/40",
                  )}
                  style={on ? { backgroundColor: color } : undefined}
                >
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: on ? "white" : color }}
                    aria-hidden="true"
                  />
                  {t(`crisis.${c.key}`)}
                </button>
              );
            })}
          </div>

          <div className="relative mt-3">
            <CrisisPaths crises={crises} selected={selected} callDrop={callDrop} />
            {shown.length === 0 && (
              <p className="pointer-events-none absolute inset-0 flex items-center justify-center px-6 text-center text-sm text-dim">
                {t("pickHint")}
              </p>
            )}
          </div>

          {shown.length > 0 && (
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
                          key !== "colCrisis" &&
                            key !== "colCall" &&
                            key !== "colCovered" &&
                            "text-right",
                        )}
                      >
                        {t(key)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((c) => {
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
          )}
        </>
      ) : (
        <p className="mt-5 max-w-3xl text-sm leading-relaxed text-dim">{t("noCrises")}</p>
      )}
    </section>
  );
}

/**
 * The two stress numbers that read as loss measurements rather than crisis
 * replays: what the book's volatility would be with no diversification, and
 * how long it takes to sell. They sit in the loss panel next to VaR.
 */
export function useStressRows(
  s: StressReport | null,
  data: PortfolioAnalysis,
): { rows: StatRow[]; liquidityTip: string } | null {
  const t = useTranslations("portfolio.stress");
  const locale = useLocale();
  if (!s) return null;
  const liq = s.liquidity;
  const noDiv = s.no_diversification_volatility;
  return {
    liquidityTip: t("liquidityNote", {
      share: fmtPercent(liq.participation, locale, 0),
    }),
    rows: [
      {
        label: t("noDiv"),
        value: fmtPercent(noDiv, locale, 1),
        note: t("noDivNote", { now: fmtPercent(data.volatility, locale, 1) }),
      },
      {
        label: t("liquidity"),
        value:
          liq.book_days === null
            ? "—"
            : liq.book_days < 1
              ? t("underOneDay")
              : t("days", {
                  n: fmtNumber(liq.book_days, locale, {
                    maximumFractionDigits: 0,
                  }),
                }),
        note:
          liq.slow.length > 0
            ? t("liquiditySlow", {
                symbols: liq.slow.join(", "),
                share: fmtPercent(liq.slow_weight, locale, 0),
                days: fmtNumber(liq.slowest_days ?? liq.slow_days, locale, {
                  maximumFractionDigits: 0,
                }),
              })
            : t("liquidityFine"),
        tone: liq.slow.length > 0 ? ("caution" as const) : undefined,
      },
    ],
  };
}
