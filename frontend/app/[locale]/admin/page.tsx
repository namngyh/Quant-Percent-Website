import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { AdminView } from "@/components/admin/admin-view";
import { localeAlternates } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.admin" });
  return {
    title: t("title"),
    description: t("description"),
    alternates: localeAlternates(locale, "/admin"),
    robots: { index: false, follow: true },
  };
}

export default async function AdminPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("admin");

  return (
    <main className="container-qp section-pad">
      <h1 className="title-lg">{t("title")}</h1>
      <p className="mt-4 max-w-2xl text-ink">{t("description")}</p>
      <div className="mt-12">
        <AdminView />
      </div>
    </main>
  );
}
