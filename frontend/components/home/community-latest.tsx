import { getTranslations } from "next-intl/server";
import { ArrowBigUp, ArrowRight, MessageSquare, PenLine } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Reveal } from "@/components/reveal";
import { AuthorAvatar } from "@/components/articles/author-avatar";
import { articlesAvailable, fetchArticleList, type ArticleList } from "@/lib/api/articles";
import { fmtDate } from "@/lib/format";

/**
 * The three newest articles, so the homepage shows the community is alive
 * rather than describing it.
 *
 * Rendered on the server like the articles page itself. When there is no
 * backend (mock mode) or the request fails, the section still appears with
 * its way in — the community exists either way; only the preview is missing.
 */
export async function CommunityLatest({ locale }: { locale: string }) {
  const t = await getTranslations("home.community");
  const tArticles = await getTranslations("articles");

  let list: ArticleList | null = null;
  if (articlesAvailable()) {
    try {
      list = await fetchArticleList({ sort: "new", page: 1 });
    } catch {
      // A backend hiccup must not take the homepage down with it.
      list = null;
    }
  }
  const items = list?.items.slice(0, 3) ?? [];

  return (
    <section className="relative overflow-hidden border-b border-border bg-background">
      <div aria-hidden="true" className="numeral-clip">
        <span className="section-numeral">02</span>
      </div>
      <div className="container-qp section-pad relative">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-2xl">
            <p className="eyebrow">
              <span className="tick text-accent/60">02</span>
              {t("eyebrow")}
            </p>
            <h2 className="title-lg mt-5">{t("title")}</h2>
            <p className="mt-5 text-lg leading-relaxed text-dim">{t("description")}</p>
          </div>
          <Link
            href="/articles"
            className="arrow-link inline-flex items-center gap-2 text-sm font-medium text-brand underline-offset-4 hover:underline"
          >
            {t("viewAll")} <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>

        {items.length > 0 ? (
          <ul className="mt-12 grid gap-5 desk:grid-cols-3">
            {items.map((article, i) => (
              <li key={article.slug}>
                <Reveal index={i} className="h-full">
                  <article className="qp-panel-interactive group relative flex h-full flex-col p-6">
                    <div className="flex items-center gap-2.5 text-[13px]">
                      <AuthorAvatar
                        name={article.author.name}
                        src={article.author.avatar_url}
                        size="sm"
                      />
                      <span className="min-w-0 truncate font-medium text-ink">
                        {article.author.name}
                      </span>
                      <span aria-hidden="true" className="text-dim">·</span>
                      <time dateTime={article.created_at} className="figure shrink-0 text-dim">
                        {fmtDate(article.created_at, locale)}
                      </time>
                    </div>
                    <h3 className="mt-4 text-[18px] font-semibold leading-snug text-ink group-hover:text-brand-strong">
                      <Link
                        href={`/articles/${article.slug}`}
                        className="after:absolute after:inset-0 after:content-['']"
                      >
                        {article.title}
                      </Link>
                    </h3>
                    {article.summary && (
                      <p className="mt-2 line-clamp-3 flex-1 text-[14px] leading-relaxed text-dim">
                        {article.summary}
                      </p>
                    )}
                    <div className="mt-5 flex items-center gap-4 text-[13px] text-dim">
                      <span
                        className="inline-flex items-center gap-1"
                        aria-label={tArticles("vote.tally", {
                          up: article.upvotes,
                          down: article.downvotes,
                        })}
                      >
                        <ArrowBigUp className="size-4" aria-hidden="true" />
                        <span className="figure tabular-nums">{article.score}</span>
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <MessageSquare className="size-3.5" aria-hidden="true" />
                        {tArticles("commentCount", { count: article.comment_count })}
                      </span>
                    </div>
                  </article>
                </Reveal>
              </li>
            ))}
          </ul>
        ) : (
          list && <p className="mt-12 text-dim">{t("empty")}</p>
        )}

        <div className="mt-10 flex flex-wrap gap-3">
          <Button asChild>
            <Link href="/articles">{t("viewAll")}</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/articles/new">
              <PenLine className="mr-1 size-4" aria-hidden="true" />
              {t("write")}
            </Link>
          </Button>
        </div>
      </div>
    </section>
  );
}
