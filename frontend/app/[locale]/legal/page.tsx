import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { getTranslations, setRequestLocale } from "next-intl/server";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.legal" });
  return { title: t("title"), description: t("description"), alternates: localeAlternates(locale, "/legal") };
}

export default async function LegalPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("legal");
  const items = t.raw("items") as { title: string; text: string }[];

  return (
    <main className="container-qp section-pad">
      <h1 className="title-lg max-w-3xl">{t("title")}</h1>
      <p className="mt-5 max-w-2xl text-ink">{t("intro")}</p>

      <ol className="mt-14 max-w-3xl space-y-10">
        {items.map((item, i) => (
          <li key={item.title} className="grid grid-cols-[3rem_1fr] gap-4">
            <span className="figure pt-0.5 text-sm text-dim" aria-hidden="true">
              {String(i + 1).padStart(2, "0")}
            </span>
            <div>
              <h2 className="text-lg font-semibold">{item.title}</h2>
              <p className="mt-2 leading-relaxed text-ink">{item.text}</p>
            </div>
          </li>
        ))}
      </ol>

      <p className="mt-16 max-w-3xl border-l-2 border-lightgray pl-4 text-sm text-dim">
        {t("reviewNote")}
      </p>
    </main>
  );
}
