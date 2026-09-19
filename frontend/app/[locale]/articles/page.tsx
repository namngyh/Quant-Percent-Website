import type { Metadata } from "next";
import { ArrowBigUp, ChevronLeft, ChevronRight, MessageSquare, Search } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { WriteButton } from "@/components/articles/article-actions";
import { AuthorAvatar } from "@/components/articles/author-avatar";
import {
  ARTICLE_SORTS,
  articlesAvailable,
  fetchArticleList,
  type ArticleSort,
  type ArticleSummary,
} from "@/lib/api/articles";
import { fmtDate } from "@/lib/format";
import { localeAlternates } from "@/lib/seo";
import { cn } from "@/lib/utils";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.articles" });
  return {
    title: t("title"),
    description: t("description"),
    alternates: localeAlternates(locale, "/articles"),
  };
}

export const dynamic = "force-dynamic";

interface Query {
  sort?: string;
  q?: string;
  page?: string;
}

function hrefFor(current: { sort: ArticleSort; q: string }, patch: { sort?: ArticleSort; page?: number }) {
  const params = new URLSearchParams();
  const sort = patch.sort ?? current.sort;
  if (sort !== "new") params.set("sort", sort);
  if (current.q) params.set("q", current.q);
  if (patch.page && patch.page > 1) params.set("page", String(patch.page));
  const qs = params.toString();
  return qs ? `/articles?${qs}` : "/articles";
}

function Chip({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      className={cn(
        "rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition-colors",
        active
          ? "border-brand bg-brand text-white"
          : "border-border text-dim hover:border-brand hover:text-brand"
      )}
    >
      {children}
    </Link>
  );
}

async function ArticleCard({ article, locale }: { article: ArticleSummary; locale: string }) {
  const t = await getTranslations("articles");
  return (
    <li className="qp-panel-interactive group relative flex gap-4 p-5 sm:gap-5 sm:p-6">
      <div
        className="flex w-12 shrink-0 flex-col items-center rounded-lg bg-surface py-2 text-center"
        aria-label={t("vote.tally", { up: article.upvotes, down: article.downvotes })}
      >
        <ArrowBigUp className="size-5 text-dim" aria-hidden="true" />
        <span
          className={cn(
            "figure text-[15px] font-semibold tabular-nums",
            article.score > 0 ? "text-positive" : article.score < 0 ? "text-negative" : "text-ink"
          )}
        >
          {article.score}
        </span>
      </div>
      <div className="min-w-0 flex-1">
        <h2 className="text-[18px] font-semibold leading-snug text-ink group-hover:text-brand-strong">
          {/* The link's box covers the card, so the whole card is the target
              without nesting interactive elements inside an <a>. */}
          <Link href={`/articles/${article.slug}`} className="after:absolute after:inset-0 after:content-['']">
            {article.title}
          </Link>
        </h2>
        {article.summary && (
          <p className="mt-2 line-clamp-2 text-[14px] leading-relaxed text-dim">{article.summary}</p>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px] text-dim">
          <span className="inline-flex items-center gap-2 font-medium text-ink">
            <AuthorAvatar name={article.author.name} size="sm" />
            {article.author.name}
          </span>
          <span aria-hidden="true">·</span>
          <time dateTime={article.created_at} className="figure">
            {fmtDate(article.created_at, locale)}
          </time>
          <span aria-hidden="true">·</span>
          <span className="inline-flex items-center gap-1.5">
            <MessageSquare className="size-3.5" aria-hidden="true" />
            {t("commentCount", { count: article.comment_count })}
          </span>
        </div>
      </div>
    </li>
  );
}

/** Articles, newest first by default, sortable by votes and by discussion. */
export default async function ArticlesPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Query>;
}) {
  const { locale } = await params;
  const query = await searchParams;
  setRequestLocale(locale);
  const t = await getTranslations("articles");

  const sort: ArticleSort = ARTICLE_SORTS.includes(query.sort as ArticleSort)
    ? (query.sort as ArticleSort)
    : "new";
  const q = (query.q ?? "").trim().slice(0, 100);
  const page = Math.max(1, Number.parseInt(query.page ?? "1", 10) || 1);
  const current = { sort, q };

  const list = articlesAvailable() ? await fetchArticleList({ sort, q, page }) : null;
  const pages = list ? Math.max(1, Math.ceil(list.total / list.page_size)) : 1;

  return (
    <main>
      <div className="page-head">
        <div className="container-qp relative flex flex-wrap items-end justify-between gap-6 py-14 desk:py-20">
          <div>
            <h1 className="title-lg">{t("title")}</h1>
            <p className="mt-5 max-w-2xl text-lg leading-relaxed text-dim">{t("description")}</p>
          </div>
          <WriteButton />
        </div>
      </div>

      <div className="container-qp py-10 desk:py-14">
        <div className="mx-auto max-w-4xl">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <nav aria-label={t("sortLabel")} className="flex flex-wrap gap-2">
              {ARTICLE_SORTS.map((s) => (
                <Chip key={s} href={hrefFor(current, { sort: s })} active={sort === s}>
                  {t(`sort.${s}`)}
                </Chip>
              ))}
            </nav>
            {/* A plain GET form: search works before any script has loaded and
                the result is a URL that can be shared. */}
            <form action={`/${locale}/articles`} method="get" role="search" className="relative sm:w-72">
              {sort !== "new" && <input type="hidden" name="sort" value={sort} />}
              <label htmlFor="article-search" className="sr-only">
                {t("searchPlaceholder")}
              </label>
              <Search
                className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-dim"
                aria-hidden="true"
              />
              <input
                id="article-search"
                name="q"
                type="search"
                defaultValue={q}
                maxLength={100}
                placeholder={t("searchPlaceholder")}
                className="h-11 w-full rounded-full border border-input bg-surface pl-10 pr-4 text-[14px] outline-none transition-colors placeholder:text-dim hover:bg-surface-2 focus-visible:border-brand focus-visible:bg-background focus-visible:ring-4 focus-visible:ring-brand/12"
              />
            </form>
          </div>

          {!list ? (
            <p className="mt-10 rounded-lg border border-border bg-surface p-6 text-sm text-dim">
              {t("unavailable")}
            </p>
          ) : list.items.length === 0 ? (
            <p className="mt-10 rounded-lg border border-border bg-surface p-6 text-sm text-dim">
              {q ? t("emptySearch", { q }) : t("empty")}
            </p>
          ) : (
            <>
              <p className="mt-8 text-[13px] text-dim">{t("resultCount", { total: list.total })}</p>
              <ul className="mt-3 space-y-4">
                {list.items.map((a) => (
                  <ArticleCard key={a.slug} article={a} locale={locale} />
                ))}
              </ul>
            </>
          )}

          {list && pages > 1 && (
            <nav aria-label={t("pagination")} className="mt-10 flex items-center justify-between gap-4">
              {page > 1 ? (
                <Link
                  href={hrefFor(current, { page: page - 1 })}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border px-4 py-2 text-[13px] font-medium text-ink hover:border-brand hover:text-brand"
                >
                  <ChevronLeft className="size-4" aria-hidden="true" />
                  {t("prev")}
                </Link>
              ) : (
                <span />
              )}
              <span className="figure text-[13px] text-dim">{t("pageOf", { page, pages })}</span>
              {page < pages ? (
                <Link
                  href={hrefFor(current, { page: page + 1 })}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border px-4 py-2 text-[13px] font-medium text-ink hover:border-brand hover:text-brand"
                >
                  {t("next")}
                  <ChevronRight className="size-4" aria-hidden="true" />
                </Link>
              ) : (
                <span />
              )}
            </nav>
          )}
        </div>
      </div>
    </main>
  );
}
