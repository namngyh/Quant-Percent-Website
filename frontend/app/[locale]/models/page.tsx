import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { getTranslations, setRequestLocale } from "next-intl/server";
import {
  getPublishedModels,
  usesDatabaseApi,
} from "@/lib/models/catalogue";
import { DisclosureBanner } from "@/components/layout/disclosure-banner";
import { AllInOne } from "@/components/models/all-in-one";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.models" });
  return { title: t("title"), description: t("description"), alternates: localeAlternates(locale, "/models") };
}

export const dynamic = "force-dynamic";

/**
 * What the four models say about the market, on one page.
 *
 * This used to be a filterable catalogue: twelve cards, six of them locked
 * placeholders, with market and status chips above them. That answered "what
 * models exist" — a question about us. A reader arrives asking what the
 * market is doing, so the page now opens with the answer and each panel
 * links to the model behind it for anyone who wants the other question too.
 *
 * The catalogue still lives at /models/[slug] per model; nothing was
 * removed from the site, only from the path of someone who wanted a number.
 */
export default async function ModelsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("models");
  const catalogue = await getPublishedModels();

  return (
    <main>
      <DisclosureBanner variant={usesDatabaseApi() ? "legal" : "mock"} />
      <div className="page-head">
        <div className="container-qp relative py-10 desk:py-14">
          <h1 className="title-lg">{t("title")}</h1>
          <p className="mt-4 max-w-2xl leading-relaxed text-dim">
            {t("description")}
          </p>
        </div>
      </div>
      <div className="container-qp py-10 desk:py-12">
        <AllInOne
          names={Object.fromEntries(catalogue.map((m) => [m.slug, m.name]))}
        />
      </div>
    </main>
  );
}
