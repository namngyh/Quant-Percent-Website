import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ArticleEditor } from "@/components/articles/article-editor";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "articles.editor" });
  return { title: t("newTitle"), robots: { index: false, follow: false } };
}

export default async function NewArticlePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("articles.editor");

  return (
    <main className="container-qp py-10 desk:py-14">
      <div className="mx-auto max-w-[50rem]">
        <h1 className="title-lg">{t("newTitle")}</h1>
        <div className="mt-10">
          <ArticleEditor />
        </div>
      </div>
    </main>
  );
}
