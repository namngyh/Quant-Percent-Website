import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { Suspense } from "react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { DisclosureBanner } from "@/components/layout/disclosure-banner";
import { usesDatabaseApi } from "@/lib/models/catalogue";
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
      <DisclosureBanner variant={usesDatabaseApi() ? "legal" : "mock"} />
      <div className="page-head">
        <div className="container-qp relative py-14 desk:py-20">
          <h1 className="title-lg">{t("title")}</h1>
          <p className="mt-5 max-w-2xl text-lg leading-relaxed text-dim">
            {t("description")}
          </p>
        </div>
      </div>
      <div className="container-qp py-12 desk:py-16">
        <Suspense fallback={<SkeletonLoader rows={8} />}>
          <MarketTabs />
        </Suspense>
      </div>
    </main>
  );
}
