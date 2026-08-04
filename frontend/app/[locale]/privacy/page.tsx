import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { getTranslations, setRequestLocale } from "next-intl/server";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.privacy" });
  return { title: t("title"), description: t("description"), alternates: localeAlternates(locale, "/privacy") };
}

export default async function PrivacyPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("privacy");
  const sections = t.raw("sections") as { title: string; text: string }[];

  return (
    <main className="container-qp section-pad">
      <h1 className="title-lg max-w-3xl">{t("title")}</h1>
      <p className="mt-5 max-w-2xl text-ink">{t("intro")}</p>

      <div className="mt-14 max-w-3xl space-y-10">
        {sections.map((s) => (
          <section key={s.title}>
            <h2 className="text-lg font-semibold">{s.title}</h2>
            <p className="mt-2 leading-relaxed text-ink">{s.text}</p>
          </section>
        ))}
      </div>
    </main>
  );
}
