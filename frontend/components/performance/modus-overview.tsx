"use client";

import { useTranslations, useLocale } from "next-intl";
import { useApi } from "@/lib/api/fetcher";
import { DataState } from "@/components/states/data-state";
import type { StrategyMetrics, PerformanceSeries } from "@/lib/api/types";
import { fmtNumber, fmtPercent, fmtSignedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";
import { FEATURED_STRATEGY } from "@/config/strategies";

/**
 * The 2024-2026 result for Model Modus, in one block.
 *
 * The page used to show three equal cards, one per evaluation run. That put a
 * single test year, a two-and-a-half year walk-forward and a 50-seed cost
 * study side by side as if they were three comparable products, and it left
 * the reader to work out which one actually covers 2024-2026. Worse, the
 * headline +68.3% hid the fact that the 2026 fold is negative — that only
 * appeared if you opened the detail page.
 *
 * This component leads with the run that spans the whole period, breaks it
 * down by year so a losing year cannot hide inside a total, and then lists
 * every metric the report carries.
 */

/** The only run covering 2024 through 2026. */
const WALK_FORWARD = FEATURED_STRATEGY;

/** Assumed starting capital the research project quotes returns against. */
const NOTIONAL_POINTS = 1000;

type Metrics = StrategyMetrics["metrics"];
type MetricKey = keyof Metrics;

/** The ten figures a reader can actually judge the system by.
 *
 * The table previously carried all twenty-four the report exports. Long-only
 * and short-only breakdowns, Ulcer, UPI, equity R-squared and the rest are
 * detail that few readers can act on, and their volume pushed the headline
 * risk measures out of view. */
const TABLE_KEYS: MetricKey[] = [
  "totalReturn",
  "annualizedReturn",
  "maxDrawdown",
  "sharpe",
  "sortino",
  "calmar",
  "profitFactor",
  "winRate",
  "payoff",
  "trades",
];

/** Metrics that are a share of something, so they render as percentages. */
const PERCENT_KEYS = new Set<MetricKey>([
  "totalReturn",
  "annualizedReturn",
  "maxDrawdown",
  "winRate",
  "exposure",
  "pctMonths",
  "wrLong",
  "wrShort",
]);

/** Metrics measured in index points rather than as a ratio or a share. */
const POINT_KEYS = new Set<MetricKey>([
  "netPoints",
  "maxDrawdownPoints",
  "expectancy",
  "avgWin",
  "avgLoss",
  "longPnl",
  "shortPnl",
]);

function formatMetric(
  key: MetricKey,
  value: number | null,
  locale: string,
  pointsUnit: string,
) {
  if (value === null || value === undefined) return null;
  if (PERCENT_KEYS.has(key)) {
    return key === "totalReturn" || key === "annualizedReturn"
      ? fmtSignedPercent(value, locale, 1)
      : fmtPercent(value, locale);
  }
  if (POINT_KEYS.has(key)) {
    return `${fmtNumber(value, locale, { maximumFractionDigits: 2 })} ${pointsUnit}`;
  }
  return fmtNumber(value, locale, { maximumFractionDigits: 2 });
}

export function ModusOverview() {
  const locale = useLocale();
  const t = useTranslations("performance");
  const tc = useTranslations("common");

  const metrics = useApi<StrategyMetrics>(
    `/api/v1/strategies/${WALK_FORWARD}/metrics`,
  );
  const series = useApi<PerformanceSeries>(
    `/api/v1/strategies/${WALK_FORWARD}/performance`,
  );

  const m = metrics.data?.metrics ?? null;
  const folds = series.data?.folds ?? null;
  const pointsUnit = t("detail.pointsUnit");
  const names = (key: string) => t(`detail.metricNames.${key}` as never);

  return (
    <section aria-labelledby="modus-2024-2026" className="mt-14">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="figure text-xs uppercase tracking-[0.08em] text-brand">
            {t("overview.eyebrow")}
          </p>
          <h2 id="modus-2024-2026" className="title-md mt-2">
            {t("overview.heading")}
          </h2>
        </div>
        <span className="rounded-full border border-signal/35 bg-signal-soft px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-signal-strong">
          {tc("resultType.out_of_sample")}
        </span>
      </div>

      <p className="mt-4 max-w-3xl leading-relaxed text-ink">
        {t("overview.lead")}
      </p>

      <DataState
        loading={metrics.isLoading}
        error={metrics.error}
        empty={!metrics.isLoading && !m}
        className="mt-7"
      >
        {m && (
          <>
          <dl className="mt-7 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4">
            {(
              [
                ["totalReturn", "overview.totalReturnNote"],
                ["annualizedReturn", "overview.annualNote"],
                ["maxDrawdown", "overview.drawdownNote"],
                ["trades", "overview.tradesNote"],
              ] as const
            ).map(([key, noteKey]) => {
              const value = m[key] as number | null;
              const text = formatMetric(key, value, locale, pointsUnit);
              if (text === null) return null;

              // The two percentages on this row are not on the same base.
              // Return is points over the 1,000-point notional; drawdown is
              // measured against the equity peak at the time, which was well
              // above 1,000 by then. Dividing one by the other gives a
              // flattering ratio, so the drawdown note states its own base
              // and gives the like-for-like figure alongside.
              const note =
                key === "maxDrawdown" && m.maxDrawdownPoints !== null
                  ? t("overview.drawdownNote", {
                      points: `${fmtNumber(m.maxDrawdownPoints, locale, { maximumFractionDigits: 1 })} ${pointsUnit}`,
                      onNotional: fmtPercent(
                        m.maxDrawdownPoints / NOTIONAL_POINTS,
                        locale,
                      ),
                    })
                  : t(noteKey);

              return (
                <div key={key} className="bg-background p-5">
                  <dt className="text-xs text-dim">{names(key)}</dt>
                  <dd
                    className={cn(
                      "figure mt-2 text-xl font-semibold",
                      key === "totalReturn" &&
                        (value as number) < 0 &&
                        "text-negative",
                      key === "totalReturn" &&
                        (value as number) >= 0 &&
                        "text-positive",
                    )}
                  >
                    {text}
                  </dd>
                  <p className="mt-2 text-xs leading-relaxed text-dim">{note}</p>
                </div>
              );
            })}
          </dl>

          {folds && folds.length > 0 && (
            <div className="mt-8">
              <h3 className="text-base font-semibold">{t("overview.byYear")}</h3>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-dim">
                {t("overview.byYearNote")}
              </p>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[42rem] border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th scope="col" className="py-2.5 pr-4 text-xs font-medium uppercase tracking-[0.06em] text-dim">
                        {t("detail.foldTest")}
                      </th>
                      <th scope="col" className="py-2.5 pr-4 text-xs font-medium uppercase tracking-[0.06em] text-dim">
                        {t("detail.foldTrain")}
                      </th>
                      <th scope="col" className="py-2.5 pr-4 text-right text-xs font-medium uppercase tracking-[0.06em] text-dim">
                        {t("detail.foldNet")}
                      </th>
                      <th scope="col" className="py-2.5 pr-4 text-right text-xs font-medium uppercase tracking-[0.06em] text-dim">
                        {names("trades")}
                      </th>
                      <th scope="col" className="py-2.5 pr-4 text-right text-xs font-medium uppercase tracking-[0.06em] text-dim">
                        {names("winRate")}
                      </th>
                      <th scope="col" className="py-2.5 pr-4 text-right text-xs font-medium uppercase tracking-[0.06em] text-dim">
                        {names("payoff")}
                      </th>
                      <th scope="col" className="py-2.5 text-right text-xs font-medium uppercase tracking-[0.06em] text-dim">
                        {names("maxDrawdownPoints")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {folds.map((f) => (
                      <tr key={f.fold} className="border-b border-border/70">
                        <th scope="row" className="figure py-3 pr-4 text-left font-normal">
                          {f.test_year}
                          {f.partial_year && (
                            <span className="ml-2 rounded border border-caution/40 bg-caution-soft px-1.5 py-0.5 text-[10px] uppercase tracking-[0.06em] text-caution">
                              {t("detail.partialYear")}
                            </span>
                          )}
                        </th>
                        <td className="figure py-3 pr-4 text-dim">
                          {f.train_from}–{f.train_to}
                        </td>
                        <td
                          className={cn(
                            "figure py-3 pr-4 text-right",
                            f.net_points < 0 ? "text-negative" : "text-positive",
                          )}
                        >
                          {fmtNumber(f.net_points, locale, {
                            maximumFractionDigits: 1,
                            signDisplay: "always",
                          })}{" "}
                          {pointsUnit}
                        </td>
                        <td className="figure py-3 pr-4 text-right">
                          {fmtNumber(f.trades, locale)}
                        </td>
                        <td className="figure py-3 pr-4 text-right">
                          {fmtPercent(f.win_rate / 100, locale)}
                        </td>
                        <td className="figure py-3 pr-4 text-right">
                          {fmtNumber(f.payoff, locale, { maximumFractionDigits: 2 })}
                        </td>
                        <td className="figure py-3 text-right">
                          {fmtNumber(f.max_drawdown_points, locale, {
                            maximumFractionDigits: 1,
                          })}{" "}
                          {pointsUnit}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* One table rather than five expandable groups. A reader
              comparing this system with another wants every figure in one
              place to scan down, not a disclosure widget to open first. */}
          <div className="mt-10">
            <h3 className="text-base font-semibold">{t("overview.tableHeading")}</h3>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-dim">
              {t("overview.tableNote")}
            </p>

            {/* Two columns of five rather than one long table. Ten rows in a
                single column runs past the fold on a laptop and reads as a
                data dump; paired columns keep the whole set in one view. */}
            <dl className="mt-5 grid gap-x-12 gap-y-0 sm:grid-cols-2">
              {TABLE_KEYS.map((key) => {
                const text = formatMetric(
                  key,
                  m[key] as number | null,
                  locale,
                  pointsUnit,
                );
                // A metric the run did not export is left out rather than
                // shown as a dash the reader has to interpret.
                if (text === null) return null;
                return (
                  <div
                    key={key}
                    className="flex items-baseline justify-between gap-6 border-b border-border py-3.5"
                  >
                    <dt className="min-w-0">
                      <span className="block text-sm font-medium">
                        {names(key)}
                      </span>
                      <span className="mt-0.5 block text-xs leading-snug text-dim">
                        {t(`overview.meaning.${key}` as never)}
                      </span>
                    </dt>
                    <dd className="figure shrink-0 text-lg font-semibold">
                      {text}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </div>
          </>
        )}
      </DataState>
    </section>
  );
}
