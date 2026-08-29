import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { FeedbackForm } from "@/components/feedback/feedback-form";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.feedback" });
  return {
    title: t("title"),
    description: t("description"),
    alternates: localeAlternates(locale, "/feedback"),
  };
}

export default async function FeedbackPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("feedback");

  return (
    <main className="container-qp section-pad">
      <div className="grid gap-14 desk:grid-cols-[1fr_1.3fr]">
        <div>
          <h1 className="title-lg">{t("title")}</h1>
          <p className="mt-5 max-w-md text-ink">{t("description")}</p>
          <p className="mt-8 max-w-md border-l-2 border-lightgray pl-4 text-sm text-dim">
            {t("note")}
          </p>
        </div>
        <FeedbackForm />
      </div>
    </main>
  );
}
