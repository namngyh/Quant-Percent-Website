import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { StatusPanels } from "@/components/status/status-panels";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.status" });
  return { title: t("title"), description: t("description"), alternates: localeAlternates(locale, "/system-status") };
}

export default async function SystemStatusPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("status");

  return (
    <main className="container-qp py-12 desk:py-16">
      <h1 className="title-lg">{t("title")}</h1>
      <p className="mt-4 max-w-2xl text-ink">{t("description")}</p>
      <div className="mt-10 max-w-3xl">
        <StatusPanels />
      </div>
    </main>
  );
}
