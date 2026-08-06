import { getLocale, getTranslations } from "next-intl/server";
import { FEATURED_STRATEGY, strategiesForSystem } from "@/config/strategies";
import { getHeadline } from "@/lib/performance/reports";
import { Link } from "@/i18n/navigation";
import { fmtDate, fmtNumber, fmtSignedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Every published validation run of a model, linked from its page. */
export async function ValidatedPerformance({
  systemSlug,
}: {
  systemSlug: string;
}) {
  // Only the run the performance page publishes. The other two evaluations
  // are internal; listing them here advertised reports a reader cannot open.
  const reports = strategiesForSystem(systemSlug).filter(
    (r) => r.slug === FEATURED_STRATEGY
  );
  if (reports.length === 0) return null;

  const locale = (await getLocale()) as "vi" | "en";
  const t = await getTranslations("models.detail");
  const tp = await getTranslations("performance");
  const tc = await getTranslations("common");

  return (
    <section>
      <h2 className="title-md">{t("validatedPerformance")}</h2>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-dim">
        {t("validatedPerformanceNote")}
      </p>

      <ul className="mt-8 divide-y divide-border overflow-hidden rounded-lg border border-border shadow-sm">
        {reports.map((r) => {
          const h = getHeadline(r);
          return (
            <li key={r.slug}>
              <Link
                href="/performance"
                className="flex flex-wrap items-center justify-between gap-4 p-5 transition-colors hover:bg-surface"
              >
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2.5">
                    <span className="text-[15px] font-medium">{r.name[locale]}</span>
                    <span className="rounded-full border border-border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-dim">
                      {tc(`resultType.${r.resultType}`)}
                    </span>
                  </p>
                  <p className="figure mt-1.5 text-xs text-dim">
                    {fmtDate(r.periodStart, locale)} – {fmtDate(r.periodEnd, locale)}
                    {h.trades !== null && (
                      <>
                        {" · "}
                        {tp("detail.tradesShort", {
                          count: fmtNumber(h.trades, locale, {
                            maximumFractionDigits: 1,
                          }),
                        })}
                      </>
                    )}
                  </p>
                </div>

                <div className="flex items-center gap-6">
                  {h.totalReturn !== null && (
                    <div className="text-right">
                      <p className="text-[10px] uppercase tracking-[0.06em] text-dim">
                        {tp("detail.metricNames.totalReturn")}
                      </p>
                      <p
                        className={cn(
                          "figure mt-0.5 text-lg",
                          h.totalReturn < 0 && "text-negative"
                        )}
                      >
                        {fmtSignedPercent(h.totalReturn, locale, 1)}
                      </p>
                    </div>
                  )}
                  <span aria-hidden="true" className="text-dim">
                    →
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>

      <p className="mt-4 max-w-2xl text-xs leading-relaxed text-dim">
        {tp("labelNote")}
      </p>
    </section>
  );
}
