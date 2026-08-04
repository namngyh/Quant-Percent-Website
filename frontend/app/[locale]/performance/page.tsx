import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { getPublishedStrategies } from "@/lib/strategies/catalogue";
import { Link } from "@/i18n/navigation";
import { DisclosureBanner } from "@/components/layout/disclosure-banner";
import { SystemIntro } from "@/components/performance/system-intro";
import { fmtDate, fmtNumber, fmtPercent, fmtSignedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.performance" });
  return {
    title: t("title"),
    description: t("description"),
    alternates: localeAlternates(locale, "/performance"),
  };
}

/** Performance reports list with one clearly labeled result type each. */
export default async function PerformancePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const l = locale as "vi" | "en";
  const t = await getTranslations("performance");
  const tc = await getTranslations("common");
  const strategies = await getPublishedStrategies();

  return (
    <main>
      <DisclosureBanner variant="legal" />
      <div className="container-qp py-12 desk:py-16">
        <h1 className="title-lg">{t("title")}</h1>
        <p className="mt-4 max-w-2xl text-ink">{t("description")}</p>
        <p className="mt-3 max-w-2xl text-sm text-dim">{t("labelNote")}</p>
        <p className="mt-3 max-w-2xl border-l-2 border-signal pl-4 text-sm text-dim">
          {t("restatementNote")}
        </p>

        <SystemIntro systemSlug="model-modus" />

        <h2 className="mt-14 text-sm font-semibold uppercase tracking-[0.08em] text-dim">
          {t("reportsHeading")}
        </h2>

        <div className="mt-5 grid gap-5 desk:grid-cols-3">
          {strategies.map((s) => {
            const h = s.headline;
            return (
              <article
                key={s.slug}
                className="qp-panel-interactive flex flex-col p-6 hover:border-brand"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <h2 className="text-lg font-semibold leading-tight">
                    {s.name[l]}
                  </h2>
                  <span className="rounded-full border border-signal/35 bg-signal-soft px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-signal-strong">
                    {tc(`resultType.${s.resultType}`)}
                  </span>
                </div>

                <p className="mt-3 flex-1 text-sm leading-relaxed text-ink">
                  {s.summary[l]}
                </p>

                <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-border pt-4">
                  {h.totalReturn !== null && (
                    <div>
                      <dt className="text-[11px] uppercase tracking-[0.06em] text-dim">
                        {t("detail.metricNames.totalReturn")}
                      </dt>
                      <dd
                        className={cn(
                          "figure mt-1 text-xl",
                          h.totalReturn < 0 ? "text-negative" : "text-positive"
                        )}
                      >
                        {fmtSignedPercent(h.totalReturn, locale, 1)}
                      </dd>
                    </div>
                  )}
                  {(h.maxDrawdown ?? h.maxDrawdownPoints) !== null && (
                    <div>
                      <dt className="text-[11px] uppercase tracking-[0.06em] text-dim">
                        {t(
                          h.maxDrawdown !== null
                            ? "detail.metricNames.maxDrawdown"
                            : "detail.metricNames.maxDrawdownPoints"
                        )}
                      </dt>
                      <dd className="figure mt-1 text-xl">
                        {h.maxDrawdown !== null
                          ? fmtPercent(h.maxDrawdown, locale)
                          : `${fmtNumber(h.maxDrawdownPoints as number, locale)} ${t("detail.pointsUnit")}`}
                      </dd>
                    </div>
                  )}
                </dl>

                <dl className="mt-4 space-y-2 text-[13px]">
                  <div className="flex justify-between gap-4">
                    <dt className="text-dim">{t("strategyCard.period")}</dt>
                    <dd className="figure">
                      {fmtDate(s.periodStart, locale)} –{" "}
                      {fmtDate(s.periodEnd, locale)}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-dim">{t("strategyCard.asset")}</dt>
                    <dd className="figure">{s.asset}</dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-dim">
                      {t("detail.metricNames.trades")}
                    </dt>
                    <dd className="figure">
                      {h.trades !== null
                        ? fmtNumber(h.trades, locale, {
                            maximumFractionDigits: 1,
                          })
                        : l === "vi"
                          ? "Chưa có"
                          : "Not available"}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-dim">{t("strategyCard.seeds")}</dt>
                    <dd className="figure">{s.seedNote[l]}</dd>
                  </div>
                </dl>

                <Link
                  href={`/performance/${s.slug}`}
                  className="arrow-link mt-5 inline-flex items-center gap-2 text-[13px] font-medium text-brand underline-offset-4 hover:text-brand-strong hover:underline"
                >
                  {tc("viewDetails")} <span aria-hidden="true" data-arrow>→</span>
                </Link>
              </article>
            );
          })}
        </div>
      </div>
    </main>
  );
}
