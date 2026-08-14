"use client";

import { useLocale, useTranslations } from "next-intl";
import { useApi } from "@/lib/api/fetcher";
import { FEATURED_STRATEGY } from "@/config/strategies";
import type { PerformanceSeries, StrategyMetrics } from "@/lib/api/types";
import { fmtNumber, fmtPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * The report in plain language, above the tables.
 *
 * The figures further down this page are complete but they are not an answer:
 * a reader who does not already know what a payoff ratio is cannot tell from
 * them whether this system is any good or what holding it would feel like.
 * Three things decide that, and none of them is the headline return.
 *
 * 1. **Which years count.** The model was closed before 2024. 2024 was then
 *    used to settle the entry and exit settings, so it is not evidence — only
 *    2025 and 2026 are. Showing the split visually is the difference between
 *    a reader trusting the right number and trusting the wrong one.
 * 2. **It loses more often than it wins.** Around three trades in five lose.
 *    That reads as failure unless the size difference is put next to it, so
 *    the two averages are drawn to scale rather than listed.
 * 3. **What the bad stretch looks like.** A run of losses in a row is the
 *    thing that makes people abandon a system. It is stated up front instead
 *    of being left in a table as `maxConsecutiveLosses`.
 *
 * Everything here is read from the same endpoint as the tables below; nothing
 * is restated by hand.
 */

/** The year used to settle inference settings, from the report's split note.
 *  Not evidence of anything — it is reported so it can be discounted. */
const VALIDATION_YEAR = 2024;

export function ModusPlain() {
  const t = useTranslations("performance.plain");
  const locale = useLocale();

  const metrics = useApi<StrategyMetrics>(
    `/api/v1/strategies/${FEATURED_STRATEGY}/metrics`,
  );
  const series = useApi<PerformanceSeries>(
    `/api/v1/strategies/${FEATURED_STRATEGY}/performance`,
  );

  const m = metrics.data?.metrics ?? null;
  const folds = series.data?.folds ?? [];
  if (!m) return null;

  const avgWin = m.avgWin ?? 0;
  const avgLoss = Math.abs(m.avgLoss ?? 0);
  const widest = Math.max(avgWin, avgLoss) || 1;
  const winRate = m.winRate ?? 0;

  const test = folds.filter((f) => f.test_year !== VALIDATION_YEAR);
  const testPoints = test.reduce((sum, f) => sum + f.net_points, 0);
  const testTrades = test.reduce((sum, f) => sum + f.trades, 0);

  return (
    <section aria-labelledby="modus-plain" className="mt-14">
      <h2 id="modus-plain" className="title-md">
        {t("heading")}
      </h2>
      <p className="mt-3 max-w-3xl leading-relaxed text-dim">{t("lead")}</p>

      <div className="mt-8 grid gap-6 desk:grid-cols-3">
        {/* 1. Which years are evidence. */}
        <article className="qp-panel p-6">
          <h3 className="text-base font-semibold">{t("splitTitle")}</h3>

          <ol className="mt-5 space-y-3">
            {[
              { key: "train", label: "2018–2023", tone: "muted" },
              {
                key: "tune",
                label: String(VALIDATION_YEAR),
                tone: "caution",
              },
              {
                key: "test",
                label: test.map((f) => f.test_year).join("–") || "2025–2026",
                tone: "brand",
              },
            ].map((row) => (
              <li key={row.key} className="flex items-start gap-3">
                <span
                  aria-hidden="true"
                  className={cn(
                    "mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full",
                    row.tone === "brand" && "bg-brand",
                    row.tone === "caution" && "bg-caution",
                    row.tone === "muted" && "bg-lightgray",
                  )}
                />
                <span className="min-w-0">
                  <span className="figure block text-sm font-semibold">
                    {row.label}
                  </span>
                  <span className="mt-0.5 block text-sm leading-relaxed text-dim">
                    {t(`split.${row.key}` as never)}
                  </span>
                </span>
              </li>
            ))}
          </ol>

          {test.length > 0 && (
            <p className="mt-5 border-t border-border pt-4 text-sm leading-relaxed text-ink">
              {t("splitResult", {
                years: test.map((f) => f.test_year).join(", "),
                points: fmtNumber(testPoints, locale, {
                  maximumFractionDigits: 1,
                  signDisplay: "always",
                }),
                trades: fmtNumber(testTrades, locale),
              })}
            </p>
          )}
        </article>

        {/* 2. Loses more often than it wins, and why that is still fine. */}
        <article className="qp-panel p-6">
          <h3 className="text-base font-semibold">{t("asymmetryTitle")}</h3>
          <p className="figure mt-4 text-4xl font-semibold text-ink">
            {fmtPercent(winRate, locale)}
          </p>
          <p className="mt-1 text-sm text-dim">{t("winRateLabel")}</p>

          {/* Drawn to scale: the point is that the green bar is far longer,
              and a number pair alone does not land that. */}
          <dl className="mt-6 space-y-4" aria-hidden="true">
            {[
              { key: "win", value: avgWin, className: "bg-positive" },
              { key: "loss", value: avgLoss, className: "bg-negative" },
            ].map((bar) => (
              <div key={bar.key}>
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="text-sm text-dim">{t(`bar.${bar.key}` as never)}</dt>
                  <dd className="figure text-sm font-semibold">
                    {bar.key === "loss" ? "−" : "+"}
                    {fmtNumber(bar.value, locale, { maximumFractionDigits: 1 })}
                  </dd>
                </div>
                <div className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full bg-surface">
                  <div
                    className={cn("h-full rounded-full", bar.className)}
                    style={{ width: `${(bar.value / widest) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </dl>

          <p className="mt-5 border-t border-border pt-4 text-sm leading-relaxed text-ink">
            {t("asymmetryNote", {
              payoff: fmtNumber(m.payoff ?? 0, locale, {
                maximumFractionDigits: 1,
              }),
            })}
          </p>
        </article>

        {/* 3. What the bad stretch looks like. */}
        <article className="qp-panel p-6">
          <h3 className="text-base font-semibold">{t("painTitle")}</h3>

          <dl className="mt-4 space-y-5">
            <div>
              <dt className="text-sm text-dim">{t("streakLabel")}</dt>
              <dd className="figure mt-1 text-4xl font-semibold text-ink">
                {fmtNumber(m.maxConsecutiveLosses ?? 0, locale)}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-dim">{t("drawdownLabel")}</dt>
              <dd className="figure mt-1 text-4xl font-semibold text-negative">
                {fmtPercent(m.maxDrawdown ?? 0, locale)}
              </dd>
            </div>
          </dl>

          <p className="mt-5 border-t border-border pt-4 text-sm leading-relaxed text-ink">
            {t("painNote")}
          </p>
        </article>
      </div>

      <p className="mt-6 max-w-4xl text-xs leading-relaxed text-dim">
        {t("caveat")}
      </p>
    </section>
  );
}
