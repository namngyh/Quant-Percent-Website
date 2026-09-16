import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { DisclosureBanner } from "@/components/layout/disclosure-banner";
import { SystemIntro } from "@/components/performance/system-intro";
import { ModusOverview } from "@/components/performance/modus-overview";
import { ModusCharts } from "@/components/performance/modus-charts";
import { Sealed } from "@/components/sealed";

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

/**
 * Model Modus over 2024-2026, and nothing else.
 *
 * The page used to carry three evaluation runs of the same system across
 * different periods. Two of them answered questions a reader had not asked —
 * a single 2024 test year, and a 50-seed cost study over 2025-2026 — and
 * putting them beside the headline result made it ambiguous which number was
 * "the" result. Modus is the site's flagship system, so this page now states
 * one period and shows it properly.
 */
export default async function PerformancePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("performance");
  const seal = await getTranslations("seal");

  return (
    <main>
      <DisclosureBanner variant="legal" />
      <div className="page-head">
        <div className="container-qp relative py-14 desk:py-20">
          <h1 className="title-lg">{t("title")}</h1>
          <p className="mt-5 max-w-3xl text-lg leading-relaxed text-dim">
            {t("description")}
          </p>
          <p className="mt-5 max-w-3xl rounded-lg border border-signal/25 bg-signal-soft/60 px-4 py-3 text-sm text-signal-strong">
            {t("restatementNote")}
          </p>
        </div>
      </div>
      <div className="container-qp py-12 desk:py-16">
        {/* The whole report is sealed while Modus is re-examined. The head
            above still says what the page is and why it is closed, so a
            reader is never looking at dimmed charts without the reason. */}
        <Sealed title={seal("title")} note={seal("modus")} sticky>
          <SystemIntro systemSlug="model-modus" />

          <ModusOverview />

          <ModusCharts />
        </Sealed>
      </div>
    </main>
  );
}
