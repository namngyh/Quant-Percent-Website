"use client";

import { useLocale, useTranslations } from "next-intl";
import { InfoTip } from "@/components/info-tip";
import type { PortfolioAnalysis, RiskBudget } from "@/lib/api/types";
import { fmtPercent, fmtVnd } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * The reader's own limit against what the book has done.
 *
 * Four plain answers: how much money the limit is; whether the book's own
 * deepest fall over the last year stayed inside it; which past crises would
 * have broken it; and — when the index run can be scaled to the book — how
 * likely it is to be reached within the chosen horizon. No sentence about
 * what to change.
 */

const HORIZON_KEY: Record<number, string> = { 21: "m1", 63: "m3", 126: "m6", 252: "y1" };

export function BudgetSection({
  budget: b,
  data,
}: {
  budget: RiskBudget;
  data: PortfolioAnalysis;
}) {
  const t = useTranslations("portfolio.budget");
  const th = useTranslations("portfolio.form.horizons");
  const tc = useTranslations("portfolio.stress.crisis");
  const locale = useLocale();
  const crisesTotal = data.stress?.crises.length ?? 0;
  const over = !b.realised_within || b.crisis_breaches.length > 0;

  return (
    <section aria-labelledby="pf-budget">
      <h2 id="pf-budget" className="title-md inline-flex items-center gap-2">
        {t("heading")}
        <InfoTip
          wide
          text={[
            t("lead", { basis: t(`basis.${b.basis}`) }),
            t("probabilityNote"),
          ]}
        />
      </h2>

      <p
        className={cn(
          "mt-5 max-w-4xl border-l-4 px-5 py-4 leading-relaxed text-ink",
          over ? "border-caution bg-caution-soft" : "border-positive bg-surface",
        )}
      >
        {t(over ? "summaryOver" : "summaryWithin", {
          limit: fmtPercent(b.max_loss_pct, locale, 0),
          basis: t(`basis.${b.basis}`),
          amount: `${fmtVnd(b.limit_amount, locale)} đ`,
          realised: fmtPercent(b.realised_max_loss, locale, 1),
          breaches: b.crisis_breaches.length,
          total: crisesTotal,
        })}
      </p>

      <dl className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4">
        <div className="bg-background p-5">
          <dt className="text-xs text-dim">{t("limit")}</dt>
          <dd className="figure mt-2 text-xl font-semibold">{fmtVnd(b.limit_amount, locale)} đ</dd>
          <p className="mt-2 text-xs leading-relaxed text-dim">
            {t("limitNote", {
              pct: fmtPercent(b.max_loss_pct, locale, 0),
              basis: t(`basis.${b.basis}`),
              drop: fmtPercent(b.drop_to_limit, locale, 1),
            })}
          </p>
        </div>
        <div className="bg-background p-5">
          <dt className="text-xs text-dim">{t("realised")}</dt>
          <dd
            className={cn(
              "figure mt-2 text-xl font-semibold",
              b.realised_within ? "text-positive" : "text-negative",
            )}
          >
            −{fmtPercent(b.realised_max_loss, locale, 1)}
          </dd>
          <p className="mt-2 text-xs leading-relaxed text-dim">
            {t(b.realised_within ? "realisedWithin" : "realisedOver", {
              days: data.observations,
            })}
          </p>
        </div>
        <div className="bg-background p-5">
          <dt className="text-xs text-dim">{t("crises")}</dt>
          <dd
            className={cn(
              "figure mt-2 text-xl font-semibold",
              b.crisis_breaches.length > 0 ? "text-negative" : "text-positive",
            )}
          >
            {b.crisis_breaches.length}/{crisesTotal}
          </dd>
          <p className="mt-2 text-xs leading-relaxed text-dim">
            {b.crisis_breaches.length > 0
              ? t("crisesOver", {
                  list: b.crisis_breaches.map((k) => tc(k)).join(", "),
                })
              : t("crisesWithin")}
          </p>
        </div>
        <div className="bg-background p-5">
          <dt className="text-xs text-dim">
            {t("probability", { horizon: th(HORIZON_KEY[b.horizon_days] ?? "m3") })}
          </dt>
          <dd className="figure mt-2 text-xl font-semibold">
            {b.hit_probability === null ? "—" : fmtPercent(b.hit_probability, locale, 0)}
          </dd>
          <p className="mt-2 text-xs leading-relaxed text-dim">
            {b.hit_probability === null
              ? t("probabilityNone")
              : b.historical_frequency === null
                ? t("probabilityModelOnly")
                : t("probabilityWithHistory", {
                    history: fmtPercent(b.historical_frequency, locale, 0),
                  })}
          </p>
        </div>
      </dl>
    </section>
  );
}
