import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { AlertTriangle } from "lucide-react";
import { getPublishedStrategy } from "@/lib/strategies/catalogue";
import { DisclosureBanner } from "@/components/layout/disclosure-banner";
import { StrategyCharts } from "@/components/performance/strategy-charts";
import { fmtDate } from "@/lib/format";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}): Promise<Metadata> {
  const { locale, slug } = await params;
  const s = await getPublishedStrategy(slug);
  if (!s) return {};
  const l = locale as "vi" | "en";
  return { title: s.name[l], description: s.summary[l] };
}

/** Performance report (§10.2 mandatory info + §10.3 charts + §10.4 metrics). */
export default async function StrategyPage({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  setRequestLocale(locale);
  const s = await getPublishedStrategy(slug);
  if (!s) notFound();
  const l = locale as "vi" | "en";
  const t = await getTranslations("performance");
  const tc = await getTranslations("common");
  const provenance = s.provenance;

  const info: { label: string; value: string }[] = [
    {
      label: t("detail.period"),
      value: `${fmtDate(s.periodStart, locale)} – ${fmtDate(s.periodEnd, locale)}`,
    },
    { label: t("detail.asset"), value: s.asset },
    { label: t("detail.timeframe"), value: s.timeframe },
    { label: t("detail.benchmark"), value: s.benchmark[l] },
    { label: t("detail.fees"), value: s.feesNote[l] },
    { label: t("detail.slippage"), value: s.slippageNote[l] },
    { label: t("detail.split"), value: s.splitNote[l] },
    { label: t("detail.status"), value: tc(`resultType.${s.resultType}`) },
    { label: t("detail.seeds"), value: s.seedNote[l] },
    { label: t("detail.modelVersion"), value: s.modelVersion },
    // The internal code-version tag is build detail, and the note above the
    // report already states which order-fill method produced these figures.
    {
      label: t("detail.source"),
      value: provenance?.source_project ?? (l === "vi" ? "Chưa có dữ liệu" : "Not available"),
    },
  ];

  return (
    <main>
      <DisclosureBanner variant="legal" />
      <div className="container-qp py-12 desk:py-16">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="title-lg">{s.name[l]}</h1>
            <p className="mt-4 max-w-2xl text-ink">{s.summary[l]}</p>
          </div>
          <span className="border border-foreground px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]">
            {tc(`resultType.${s.resultType}`)}
          </span>
        </div>

        {/* Scope and limitations, before any number is shown */}
        <section className="mt-10 rounded-lg border border-border bg-surface p-6 shadow-sm">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <AlertTriangle className="size-4 text-dim" aria-hidden="true" />
            {t("detail.caveatsTitle")}
          </h2>
          <ul className="mt-4 space-y-2.5">
            {s.caveats[l].map((c) => (
              <li key={c} className="flex gap-3 text-[13px] leading-relaxed text-ink">
                <span aria-hidden="true" className="text-signal-strong">
                  •
                </span>
                {c}
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-10">
          <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-dim">
            {t("detail.reportInfo")}
          </h2>
          <dl className="mt-4 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4">
            {info.map((row) => (
              <div key={row.label} className="bg-background p-4">
                <dt className="text-[11px] uppercase tracking-[0.06em] text-dim">
                  {row.label}
                </dt>
                <dd className="mt-1.5 text-[13px] font-medium leading-snug">
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 max-w-2xl text-sm text-dim">{t("labelNote")}</p>
        </section>

        <section className="mt-10">
          <StrategyCharts slug={s.slug} />
        </section>
      </div>
    </main>
  );
}
