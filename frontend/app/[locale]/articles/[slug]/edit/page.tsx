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
  return { title: t("editTitle"), robots: { index: false, follow: false } };
}

export default async function EditArticlePage({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("articles.editor");

  return (
    <main className="container-qp py-10 desk:py-14">
      <div className="mx-auto max-w-[50rem]">
        <h1 className="title-lg">{t("editTitle")}</h1>
        <div className="mt-10">
          {/* Loaded in the browser: whether this reader may edit depends on
              their session, which the server render never sees. */}
          <ArticleEditor slug={slug} />
        </div>
      </div>
    </main>
  );
}
