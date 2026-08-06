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
      <div className="container-qp py-12 desk:py-16">
        <p className="figure text-xs uppercase tracking-[0.08em] text-brand">
          {t("eyebrow")}
        </p>
        <h1 className="title-lg mt-2">{t("title")}</h1>
        <p className="mt-4 max-w-3xl leading-relaxed text-ink">
          {t("description")}
        </p>
        <p className="mt-4 max-w-3xl border-l-2 border-signal pl-4 text-sm leading-relaxed text-dim">
          {t("scopeNote")}
        </p>

        <div className="mt-10">
          <PortfolioWorkspace />
        </div>
      </div>
    </main>
  );
}
