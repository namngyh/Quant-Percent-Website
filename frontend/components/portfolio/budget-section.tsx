"use client";

import { useLocale, useTranslations } from "next-intl";
import { InfoTip } from "@/components/info-tip";
import { StatTable } from "@/components/portfolio/stat-table";
import { useSpanLabel } from "@/components/portfolio/span";
import { CHART } from "@/components/charts/echart";
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

function BudgetAxis({ budget: b, data }: { budget: RiskBudget; data: PortfolioAnalysis }) {
  const t = useTranslations("portfolio.budget");
  const tc = useTranslations("portfolio.stress.crisis");
  const locale = useLocale();
  const spanLabel = useSpanLabel();
  const factor =
    b.basis === "equity" && data.margin && data.margin.equity > 0
      ? data.measured_value / data.margin.equity
      : 1;
  const crises = (data.stress?.crises ?? []).map((c) => ({
    key: c.key,
    loss: Math.min(1, Math.abs(c.max_drawdown) * factor),
  }));
  const top = Math.min(
    1,
    Math.max(b.max_loss_pct, b.realised_max_loss, ...crises.map((c) => c.loss)) * 1.15,
  );
  const x = (v: number) => `${Math.min(100, (v / top) * 100)}%`;
  const over = b.realised_max_loss > b.max_loss_pct;
  return (
    <div className="mt-5 rounded-lg border border-border bg-background p-4 shadow-sm">
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-dim" aria-hidden="true">
        <span className="inline-flex items-center gap-2">
          <span className="h-2.5 w-4 rounded-sm" style={{ backgroundColor: over ? CHART.negative : CHART.brand }} />
          {t("axisRealised", { span: spanLabel(data.observations) })}
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="h-3 w-0.5 bg-ink" />
          {t("axisLimit")}
        </span>
        {crises.length > 0 && (
          <span className="inline-flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full border-2 border-signal bg-background" />
            {t("axisCrises")}
          </span>
        )}
      </div>
      <div className="relative mt-3 h-8">
        <div className="absolute inset-x-0 top-1 h-4 overflow-hidden rounded-sm bg-surface">
          <div
            className="h-full rounded-sm"
            style={{ width: x(b.realised_max_loss), backgroundColor: over ? CHART.negative : CHART.brand }}
          />
        </div>
        <div className="absolute inset-y-0 w-0.5 bg-ink" style={{ left: x(b.max_loss_pct) }} />
        {crises.map((c) => (
          <span
            key={c.key}
            title={`${tc(c.key)}: ${fmtPercent(c.loss, locale, 0)}`}
            className={cn(
              "absolute top-1.5 h-3 w-3 -translate-x-1/2 rounded-full border-2 bg-background",
              c.loss > b.max_loss_pct ? "border-negative" : "border-signal",
            )}
            style={{ left: x(c.loss) }}
          />
        ))}
      </div>
      <div className="relative mt-1 h-10 text-xs">
        <span className="absolute -translate-x-1/2 whitespace-nowrap text-ink" style={{ left: x(b.max_loss_pct) }}>
          <span className="figure font-medium">{fmtPercent(b.max_loss_pct, locale, 0)}</span> {t("axisLimitShort")}
        </span>
        <span className="absolute right-0 top-5 text-dim">{fmtPercent(top, locale, 0)}</span>
        <span className="absolute left-0 top-5 text-dim">0%</span>
      </div>
      <p className="mt-1 text-xs text-dim">
        {crises.length > 0
          ? crises
              .map((c) => `${tc(c.key)} ${fmtPercent(c.loss, locale, 0)}`)
              .join(" · ")
          : ""}
      </p>
    </div>
  );
}

export function BudgetSection({
  budget: b,
  data,
}: {
  budget: RiskBudget;
  data: PortfolioAnalysis;
}) {
  const t = useTranslations("portfolio.budget");
  const th = useTranslations("portfolio.form.horizons");
  const locale = useLocale();

  return (
    <section aria-labelledby="pf-budget">
      <h2 id="pf-budget" className="inline-flex items-center gap-2 text-lg font-semibold">
        {t("heading")}
        <InfoTip
          wide
          text={[
            t("lead", { basis: t(`basis.${b.basis}`) }),
            t("probabilityNote"),
          ]}
        />
      </h2>


      {/* One axis, in the basis the limit was set on: the realised fall as a
          bar, the limit as a line, each replayed crisis as a dot. Whether a
          dot sits left or right of the line is the whole message. */}
      <BudgetAxis budget={b} data={data} />

      <StatTable
        className="mt-5"
        rows={[
          {
            label: t("limit"),
            value: `${fmtVnd(b.limit_amount, locale)} đ`,
            note: t("limitNote", {
              pct: fmtPercent(b.max_loss_pct, locale, 0),
              basis: t(`basis.${b.basis}`),
              drop: fmtPercent(b.drop_to_limit, locale, 1),
            }),
          },
          {
            label: t("probability", { horizon: th(HORIZON_KEY[b.horizon_days] ?? "m3") }),
            value: b.hit_probability === null ? "—" : fmtPercent(b.hit_probability, locale, 0),
            note:
              b.hit_probability === null
                ? t("probabilityNone")
                : b.historical_frequency === null
                  ? t("probabilityModelOnly")
                  : t("probabilityWithHistory", {
                      history: fmtPercent(b.historical_frequency, locale, 0),
                    }),
          },
        ]}
      />
    </section>
  );
}
