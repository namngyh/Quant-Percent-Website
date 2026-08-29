import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { JoinForm } from "@/components/join/join-form";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.join" });
  return {
    title: t("title"),
    description: t("description"),
    alternates: localeAlternates(locale, "/join"),
  };
}

export default async function JoinPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("join");

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
        <JoinForm />
      </div>
    </main>
  );
}
