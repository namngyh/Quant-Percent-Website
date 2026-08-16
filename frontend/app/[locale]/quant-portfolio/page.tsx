import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { localeAlternates } from "@/lib/seo";
import { DisclosureBanner } from "@/components/layout/disclosure-banner";
import { PortfolioWorkspace } from "@/components/portfolio/portfolio-workspace";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.portfolio" });
  return {
    title: t("title"),
    description: t("description"),
    alternates: localeAlternates(locale, "/quant-portfolio"),
  };
}

/**
 * Quant Portfolio.
 *
 * This measures a portfolio the reader enters; it does not tell them what to
 * buy or sell. That boundary is deliberate and is stated on the page: giving
 * securities investment advice in Vietnam is a licensed activity, and every
 * other page on this site says plainly that nothing here is a recommendation.
 */
export default async function QuantPortfolioPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("portfolio");

  return (
    <main>
      <DisclosureBanner variant="legal" />
      <div className="page-head">
        <div className="container-qp relative py-14 desk:py-20">
          <p className="eyebrow">{t("eyebrow")}</p>
          <h1 className="title-lg mt-5">{t("title")}</h1>
          <p className="mt-5 max-w-3xl text-lg leading-relaxed text-dim">
            {t("description")}
          </p>
          <p className="mt-5 max-w-3xl rounded-lg border border-signal/25 bg-signal-soft/60 px-4 py-3 text-sm leading-relaxed text-signal-strong">
            {t("scopeNote")}
          </p>
        </div>
      </div>
      <div className="container-qp py-12 desk:py-16">
        <PortfolioWorkspace />
      </div>
    </main>
  );
}
