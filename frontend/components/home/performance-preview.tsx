"use client";

import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useApi } from "@/lib/api/fetcher";
import type { PerformanceSeries, StrategyMetrics } from "@/lib/api/types";
import { FEATURED_STRATEGY } from "@/config/strategies";
import { DataState } from "@/components/states/data-state";
import { DataFreshnessLabel } from "@/components/states/data-freshness-label";
import { Button } from "@/components/ui/button";
import { fmtNumber, fmtPercent, fmtSignedPercent } from "@/lib/format";

/** Home performance preview with a clearly labeled result type. */
export function PerformancePreview() {
  const t = useTranslations("home.performance");
  const tp = useTranslations("performance");
  const tc = useTranslations("common");
  const locale = useLocale();
  const metrics = useApi<StrategyMetrics>(
    `/api/v1/strategies/${FEATURED_STRATEGY}/metrics`
  );
  // The per-year breakdown sits beside the headline so a visitor sees the
  // losing year here rather than having to open the report to find it.
  const series = useApi<PerformanceSeries>(
    `/api/v1/strategies/${FEATURED_STRATEGY}/performance`
  );
  const folds = series.data?.folds ?? [];

  const m = metrics.data?.metrics;

  const figures = m
    ? [
        { key: "totalReturn", value: m.totalReturn, format: "signedPercent" },
        { key: "annualizedReturn", value: m.annualizedReturn, format: "percent" },
        { key: "maxDrawdown", value: m.maxDrawdown, format: "percent" },
        { key: "sharpe", value: m.sharpe, format: "ratio" },
        { key: "profitFactor", value: m.profitFactor, format: "ratio" },
        { key: "trades", value: m.trades, format: "ratio" },
      ].filter((f) => f.value !== null)
    : [];

  return (
    <section className="border-t border-border">
      <div className="container-qp section-pad">
        <div className="grid gap-12 desk:grid-cols-[1fr_1.4fr]">
          <div>
            <p className="eyebrow">{t("eyebrow")}</p>
            <h2 className="title-lg mt-4">{t("title")}</h2>
            <p className="mt-5 max-w-md text-ink">{t("description")}</p>
            <Button asChild variant="outline" className="mt-8">
              <Link href="/performance">{t("cta")}</Link>
            </Button>
          </div>

          <DataState
            loading={metrics.isLoading}
            error={metrics.error}
            onRetry={() => metrics.mutate()}
            skeletonRows={6}
          >
            {m && metrics.data && (
              <div className="rounded-lg border border-brand/30 bg-brand-soft/20 p-6 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm font-medium">
                    Model Modus · VN30F1M · 2024–2026
                  </p>
                  <span className="rounded-full border border-signal/35 bg-signal-soft px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-signal-strong">
                    {tc("resultType.walk_forward")}
                  </span>
                </div>

                <dl className="mt-6 grid grid-cols-2 gap-5 desk:grid-cols-3">
                  {figures.map((f) => (
                    <div key={f.key}>
                      <dt className="text-[11px] uppercase tracking-[0.06em] text-dim">
                        {tp(`detail.metricNames.${f.key}`)}
                      </dt>
                      <dd className="figure mt-1.5 text-2xl text-brand-strong">
                        {f.format === "signedPercent"
                          ? fmtSignedPercent(f.value as number, locale, 1)
                          : f.format === "percent"
                            ? fmtPercent(f.value as number, locale)
                            : fmtNumber(f.value as number, locale)}
                      </dd>
                    </div>
                  ))}
                </dl>

                {folds.length > 0 && (
                  <div className="mt-6 border-t border-border pt-5">
                    <p className="text-[11px] uppercase tracking-[0.06em] text-dim">
                      {t("byYear")}
                    </p>
                    <ul className="mt-3 flex flex-wrap gap-x-8 gap-y-3">
                      {folds.map((f) => (
                        <li key={f.fold}>
                          <span className="figure text-xs text-dim">
                            {f.test_year}
                            {f.partial_year ? "*" : ""}
                          </span>
                          <span
                            className={
                              f.net_points < 0
                                ? "figure ml-2 text-sm font-semibold text-negative"
                                : "figure ml-2 text-sm font-semibold text-positive"
                            }
                          >
                            {fmtNumber(f.net_points, locale, {
                              maximumFractionDigits: 0,
                              signDisplay: "always",
                            })}
                          </span>
                        </li>
                      ))}
                    </ul>
                    {folds.some((f) => f.partial_year) && (
                      <p className="mt-2 text-xs text-dim">{t("partialNote")}</p>
                    )}
                  </div>
                )}

                <p className="mt-5 border-t border-border pt-4 text-xs leading-relaxed text-dim">
                  {tp("labelNote")}
                </p>
                <DataFreshnessLabel
                  freshness={metrics.data}
                  illustrative={false}
                />
              </div>
            )}
          </DataState>
        </div>
      </div>
    </section>
  );
}
