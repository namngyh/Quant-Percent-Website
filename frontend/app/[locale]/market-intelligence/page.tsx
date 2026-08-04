import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { Suspense } from "react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { DisclosureBanner } from "@/components/layout/disclosure-banner";
import { MarketTabs } from "@/components/market/market-tabs";
import { SkeletonLoader } from "@/components/states/skeleton-loader";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.market" });
  return { title: t("title"), description: t("description"), alternates: localeAlternates(locale, "/market-intelligence") };
}

export default async function MarketIntelligencePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("market");

  return (
    <main>
      <DisclosureBanner variant="mock" />
      <div className="container-qp py-12 desk:py-16">
        <h1 className="title-lg">{t("title")}</h1>
        <p className="mt-4 max-w-2xl text-ink">{t("description")}</p>
        <div className="mt-10">
          <Suspense fallback={<SkeletonLoader rows={8} />}>
            <MarketTabs />
          </Suspense>
        </div>
      </div>
    </main>
  );
}
