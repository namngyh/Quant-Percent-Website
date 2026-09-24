import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ArrowLeft, Clock } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { ArticleActions } from "@/components/articles/article-actions";
import { ArticleProvider } from "@/components/articles/article-context";
import { ArticleMarkdown } from "@/components/articles/article-markdown";
import { AuthorAvatar } from "@/components/articles/author-avatar";
import { CommentSection } from "@/components/articles/comment-section";
import { VoteBar, VoteBlock, VoteRail } from "@/components/articles/vote-controls";
import { RoleBadge } from "@/components/admin/role-badge";
import { articlesAvailable, fetchArticle, readingMinutes } from "@/lib/api/articles";
import { fmtDateTime } from "@/lib/format";
import { localeAlternates } from "@/lib/seo";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}): Promise<Metadata> {
  const { locale, slug } = await params;
  const article = articlesAvailable() ? await fetchArticle(slug) : null;
  if (!article) return {};
  return {
    title: article.title,
    description: article.summary ?? undefined,
    alternates: localeAlternates(locale, `/articles/${slug}`),
    openGraph: {
      type: "article",
      title: article.title,
      description: article.summary ?? undefined,
      publishedTime: article.created_at,
      modifiedTime: article.updated_at,
      authors: [article.author.name],
    },
  };
}

/*
 * Layout, top to bottom: title, author, time, then the text. Voting sits in
 * three places that share one state (see ArticleProvider):
 *
 *   desktop  a column beside the text that stays in view while it scrolls
 *   end      a labelled block right after the last paragraph
 *   phone    a bar on the bottom edge, until the end block takes over
 */
export default async function ArticlePage({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  setRequestLocale(locale);
  const article = articlesAvailable() ? await fetchArticle(slug) : null;
  if (!article) notFound();
  const t = await getTranslations("articles");

  // Saves within the first minute are the author fixing a typo after
  // publishing, not an edit worth announcing to readers.
  const edited =
    new Date(article.updated_at).getTime() - new Date(article.created_at).getTime() > 60_000;

  return (
    <main className="pb-20 desk:pb-0">
      <ArticleProvider initial={article}>
        <article className="container-qp py-10 desk:py-14">
          <div className="mx-auto grid max-w-[50rem] desk:max-w-[56rem] desk:grid-cols-[3.5rem_minmax(0,1fr)] desk:gap-x-10">
            <header className="desk:col-start-2">
              <Link
                href="/articles"
                className="inline-flex items-center gap-1.5 text-[13px] font-medium text-dim hover:text-brand-strong"
              >
                <ArrowLeft className="size-4" aria-hidden="true" />
                {t("back")}
              </Link>

              <h1 className="title-lg mt-6 break-words">{article.title}</h1>
              {article.summary && (
                <p className="mt-4 text-lg leading-relaxed text-dim">{article.summary}</p>
              )}

              <div className="mt-7 flex flex-wrap items-center justify-between gap-4 border-y border-border py-4">
                <div className="flex items-center gap-3">
                  <AuthorAvatar name={article.author.name} src={article.author.avatar_url} />
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 text-[15px] font-semibold text-ink">
                      <span>{article.author.name}</span>
                      {article.author.role !== "user" && <RoleBadge role={article.author.role} />}
                    </p>
                    <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[13px] text-dim">
                      <time dateTime={article.created_at} className="figure">
                        {fmtDateTime(article.created_at, locale)}
                      </time>
                      {edited && (
                        <>
                          <span aria-hidden="true">·</span>
                          <span>
                            {t("edited", { date: fmtDateTime(article.updated_at, locale) })}
                          </span>
                        </>
                      )}
                      <span aria-hidden="true">·</span>
                      <span className="inline-flex items-center gap-1">
                        <Clock className="size-3.5" aria-hidden="true" />
                        {t("readingTime", { minutes: readingMinutes(article.body) })}
                      </span>
                    </p>
                  </div>
                </div>
                <ArticleActions />
              </div>
            </header>

            <aside className="row-start-2 hidden pt-10 desk:block" aria-label={t("vote.label")}>
              <div className="sticky top-24">
                <VoteRail />
              </div>
            </aside>

            <div className="min-w-0 pt-10 desk:col-start-2 desk:row-start-2">
              <ArticleMarkdown source={article.body} />
              <VoteBlock className="mt-14" />
              <CommentSection className="mt-14" />
            </div>
          </div>
        </article>
        <VoteBar />
      </ArticleProvider>
    </main>
  );
}
