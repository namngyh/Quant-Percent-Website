"use client";

import { useState } from "react";
import useSWRInfinite from "swr/infinite";
import { Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { SkeletonLoader } from "@/components/states/skeleton-loader";
import { useArticle } from "@/components/articles/article-context";
import { AuthorAvatar } from "@/components/articles/author-avatar";
import { ApiError, apiFetch, apiRequest } from "@/lib/api/fetcher";
import {
  COMMENT_MAX_WORDS,
  countWords,
  type ArticleComment,
  type CommentList,
} from "@/lib/api/articles";
import { useAuth } from "@/lib/auth/auth-context";
import { isVerifiedMember } from "@/lib/auth/verified";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Key = readonly [string, string];

function CommentForm({ onPosted }: { onPosted: () => Promise<void> }) {
  const t = useTranslations("articles.comment");
  const tNav = useTranslations("auth.nav");
  const { article, adjustComments } = useArticle();
  const { user, status } = useAuth();
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const words = countWords(body);
  const over = words > COMMENT_MAX_WORDS;

  if (status === "loading") return <SkeletonLoader rows={2} />;

  if (!user) {
    return (
      <p className="rounded-lg border border-border bg-surface px-4 py-4 text-sm text-ink">
        {t("signIn")}{" "}
        <Link
          href={`/login?next=/articles/${article.slug}`}
          className="font-medium text-brand-strong underline underline-offset-2"
        >
          {tNav("signIn")}
        </Link>
      </p>
    );
  }

  if (!isVerifiedMember(user)) {
    return (
      <p className="rounded-lg border border-border bg-surface px-4 py-4 text-sm text-ink">
        {t("verify")}{" "}
        <Link
          href="/account"
          className="font-medium text-brand-strong underline underline-offset-2"
        >
          {t("verifyAction")}
        </Link>
      </p>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (words === 0 || over || sending) return;
    setSending(true);
    setFailed(null);
    try {
      await apiRequest<ArticleComment>(
        `/api/v1/articles/${article.slug}/comments`,
        { method: "POST", body: JSON.stringify({ body }) }
      );
      setBody("");
      adjustComments(1);
      await onPosted();
    } catch (error) {
      setFailed(
        error instanceof ApiError && error.status === 429
          ? t("rateLimited")
          : t("error")
      );
    } finally {
      setSending(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2">
      <label htmlFor="comment-body" className="sr-only">
        {t("placeholder")}
      </label>
      <Textarea
        id="comment-body"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder={t("placeholder")}
        maxLength={1000}
        aria-invalid={over || undefined}
        aria-describedby="comment-words"
        className="min-h-24"
      />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p
          id="comment-words"
          aria-live="polite"
          className={cn("figure text-[12px]", over ? "text-negative" : "text-dim")}
        >
          {over
            ? t("tooLong", { max: COMMENT_MAX_WORDS })
            : t("words", { count: words, max: COMMENT_MAX_WORDS })}
        </p>
        <Button type="submit" size="sm" disabled={words === 0 || over || sending}>
          {sending ? t("sending") : t("submit")}
        </Button>
      </div>
      {failed && (
        <p role="alert" className="text-sm text-negative">
          {failed}
        </p>
      )}
    </form>
  );
}

/** Newest first, thirty at a time. Comments are plain text: line breaks are
 *  kept, nothing else is interpreted. */
export function CommentSection({ className }: { className?: string }) {
  const t = useTranslations("articles.comment");
  const tList = useTranslations("articles");
  const locale = useLocale();
  const { article, adjustComments } = useArticle();
  const { user, status } = useAuth();
  const [failed, setFailed] = useState<string | null>(null);

  // The viewer is part of the key: `can_delete` in each row depends on who is
  // asking, so signing in or out has to fetch the list again. Nothing is asked
  // until the session is known, which saves fetching it twice on every visit.
  const viewer = user?.id ?? "anonymous";
  const getKey = (index: number, previous: CommentList | null): Key | null => {
    if (status === "loading") return null;
    if (previous && index * previous.page_size >= previous.total) return null;
    return [
      `/api/v1/articles/${article.slug}/comments?page=${index + 1}`,
      viewer,
    ] as const;
  };

  const { data, size, setSize, mutate, isLoading, isValidating, error } =
    useSWRInfinite<CommentList, unknown, typeof getKey>(
      getKey,
      ([path]: Key) => apiFetch<CommentList>(path),
      { revalidateOnFocus: false, revalidateFirstPage: false }
    );

  const comments = data?.flatMap((page) => page.items) ?? [];
  const total = data?.[0]?.total ?? article.comment_count;
  const more = data ? comments.length < total : false;

  const remove = async (id: string) => {
    if (!window.confirm(t("deleteConfirm"))) return;
    setFailed(null);
    try {
      await apiRequest(`/api/v1/articles/${article.slug}/comments/${id}`, {
        method: "DELETE",
      });
      adjustComments(-1);
      await mutate();
    } catch {
      setFailed(t("deleteError"));
    }
  };

  return (
    <section id="comments" className={cn("scroll-mt-24", className)}>
      <h2 className="title-md">
        {t("title")}{" "}
        <span className="figure text-dim">({article.comment_count})</span>
      </h2>

      <div className="mt-6">
        <CommentForm onPosted={async () => void (await mutate())} />
      </div>

      {failed && (
        <p role="alert" className="mt-4 text-sm text-negative">
          {failed}
        </p>
      )}

      <div className="mt-8">
        {isLoading || (status === "loading" && !data) ? (
          <SkeletonLoader rows={3} />
        ) : error ? (
          <p className="text-sm text-negative">{tList("loadError")}</p>
        ) : comments.length === 0 ? (
          <p className="text-sm text-dim">{t("empty")}</p>
        ) : (
          <ul className="divide-y divide-border">
            {comments.map((c) => (
              <li key={c.id} className="flex gap-3 py-5">
                <AuthorAvatar name={c.author.name} src={c.author.avatar_url} size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <span className="text-sm font-semibold text-ink">
                      {c.author.name}
                    </span>
                    {c.author.id === article.author.id && (
                      <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[11px] font-medium text-brand-strong">
                        {tList("authorTag")}
                      </span>
                    )}
                    <time
                      dateTime={c.created_at}
                      className="figure text-[12px] text-dim"
                    >
                      {fmtDateTime(c.created_at, locale)}
                    </time>
                    {c.can_delete && (
                      <button
                        type="button"
                        onClick={() => void remove(c.id)}
                        className="ml-auto inline-flex items-center gap-1 rounded-full px-2 py-1 text-[12px] text-dim hover:bg-surface-2 hover:text-negative"
                      >
                        <Trash2 className="size-3.5" aria-hidden="true" />
                        {t("delete")}
                      </button>
                    )}
                  </div>
                  <p className="mt-1.5 whitespace-pre-line break-words text-[15px] leading-relaxed text-ink">
                    {c.body}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}

        {more && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-4"
            disabled={isValidating}
            onClick={() => void setSize(size + 1)}
          >
            {t("more")}
          </Button>
        )}
      </div>
    </section>
  );
}
