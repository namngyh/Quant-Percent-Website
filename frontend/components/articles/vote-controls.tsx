"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowBigDown, ArrowBigUp, MessageSquare, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import {
  useArticle,
  type VoteNotice,
  type VoteSpot,
} from "@/components/articles/article-context";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";

/** What went wrong, with the one link that fixes it when there is one. */
function Notice({ kind, className }: { kind: VoteNotice; className?: string }) {
  const t = useTranslations("articles.vote");
  const tNav = useTranslations("auth.nav");
  const { article, dismissNotice } = useArticle();

  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-3 rounded-lg border border-border bg-background px-3.5 py-3 text-[13px] leading-snug text-ink shadow-[var(--shadow-sm)]",
        className
      )}
    >
      <div className="min-w-0 flex-1">
        <p>{t(kind)}</p>
        {kind === "signIn" && (
          <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-medium">
            <Link
              href={`/login?next=/articles/${article.slug}`}
              className="text-brand-strong underline underline-offset-2"
            >
              {tNav("signIn")}
            </Link>
            <Link
              href={`/register?next=/articles/${article.slug}`}
              className="text-brand-strong underline underline-offset-2"
            >
              {tNav("signUp")}
            </Link>
          </p>
        )}
        {kind === "verify" && (
          <Link
            href="/account"
            className="mt-2 inline-block font-medium text-brand-strong underline underline-offset-2"
          >
            {t("verifyAction")}
          </Link>
        )}
      </div>
      <button
        type="button"
        onClick={dismissNotice}
        aria-label={t("dismiss")}
        className="-m-1 rounded-full p-1 text-dim hover:bg-surface-2 hover:text-ink"
      >
        <X className="size-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}

function useSpot(spot: VoteSpot) {
  const ctx = useArticle();
  const { article } = ctx;
  return {
    ...ctx,
    up: article.my_vote === 1,
    down: article.my_vote === -1,
    noticeHere: ctx.notice?.at === spot ? ctx.notice.kind : null,
    press: (target: 1 | -1) => void ctx.vote(target, spot),
  };
}

/**
 * Desktop: a narrow column that stays beside the text while it scrolls.
 * Research articles are long, and a control that is only at the top or the
 * bottom is out of reach for almost all of the time somebody spends reading.
 */
export function VoteRail() {
  const t = useTranslations("articles.vote");
  const { article, busy, up, down, noticeHere, press } = useSpot("rail");

  return (
    <div className="relative flex flex-col items-center gap-1">
      <button
        type="button"
        onClick={() => press(1)}
        disabled={busy}
        aria-pressed={up}
        aria-label={t("upAria")}
        title={t("up")}
        className={cn(
          "flex size-11 items-center justify-center rounded-full border transition-colors",
          up
            ? "border-positive bg-positive/10 text-positive"
            : "border-border bg-background text-dim hover:border-positive hover:text-positive"
        )}
      >
        <ArrowBigUp className={cn("size-6", up && "fill-current")} aria-hidden="true" />
      </button>
      <span
        className={cn(
          "figure py-1 text-[17px] font-semibold tabular-nums",
          up ? "text-positive" : down ? "text-negative" : "text-ink"
        )}
        aria-label={t("tally", { up: article.upvotes, down: article.downvotes })}
      >
        {article.score}
      </span>
      <button
        type="button"
        onClick={() => press(-1)}
        disabled={busy}
        aria-pressed={down}
        aria-label={t("downAria")}
        title={t("down")}
        className={cn(
          "flex size-11 items-center justify-center rounded-full border transition-colors",
          down
            ? "border-negative bg-negative/10 text-negative"
            : "border-border bg-background text-dim hover:border-negative hover:text-negative"
        )}
      >
        <ArrowBigDown className={cn("size-6", down && "fill-current")} aria-hidden="true" />
      </button>
      <a
        href="#comments"
        className="mt-4 flex flex-col items-center gap-1 rounded-lg px-2 py-1.5 text-dim transition-colors hover:text-brand-strong"
        aria-label={t("toComments")}
      >
        <MessageSquare className="size-5" aria-hidden="true" />
        <span className="figure text-[12px]">{article.comment_count}</span>
      </a>
      {noticeHere && (
        <Notice kind={noticeHere} className="absolute left-full top-0 z-10 ml-3 w-64" />
      )}
    </div>
  );
}

/**
 * The end of the article: the moment the reader has an opinion. Big, labelled
 * buttons rather than bare arrows, because here there is room to say what a
 * vote means.
 */
export function VoteBlock({ className }: { className?: string }) {
  const t = useTranslations("articles.vote");
  const { article, busy, up, down, noticeHere, press } = useSpot("block");
  const cast = article.my_vote !== null;

  return (
    <section
      id="article-end"
      aria-label={t("question")}
      className={cn(
        "rounded-xl border border-border bg-surface px-5 py-6 text-center sm:px-8",
        className
      )}
    >
      <p className="text-[17px] font-semibold text-ink">{t("question")}</p>
      <div className="mt-5 flex flex-wrap justify-center gap-3">
        <button
          type="button"
          onClick={() => press(1)}
          disabled={busy}
          aria-pressed={up}
          className={cn(
            "inline-flex min-w-40 items-center justify-center gap-2 rounded-full border px-5 py-3 text-[15px] font-medium transition-colors",
            up
              ? "border-positive bg-positive text-white"
              : "border-border bg-background text-ink hover:border-positive hover:text-positive"
          )}
        >
          <ArrowBigUp className={cn("size-5", up && "fill-current")} aria-hidden="true" />
          {t("up")}
          <span className="figure tabular-nums opacity-80">{article.upvotes}</span>
        </button>
        <button
          type="button"
          onClick={() => press(-1)}
          disabled={busy}
          aria-pressed={down}
          className={cn(
            "inline-flex min-w-40 items-center justify-center gap-2 rounded-full border px-5 py-3 text-[15px] font-medium transition-colors",
            down
              ? "border-negative bg-negative text-white"
              : "border-border bg-background text-ink hover:border-negative hover:text-negative"
          )}
        >
          <ArrowBigDown className={cn("size-5", down && "fill-current")} aria-hidden="true" />
          {t("down")}
          <span className="figure tabular-nums opacity-80">{article.downvotes}</span>
        </button>
      </div>
      {cast && !noticeHere && (
        <p role="status" className="mt-4 text-[13px] text-dim">
          {t("thanks")}
        </p>
      )}
      {noticeHere && (
        <Notice kind={noticeHere} className="mx-auto mt-5 max-w-sm text-left" />
      )}
    </section>
  );
}

/**
 * Phones: a bar along the bottom edge, where a thumb already rests. It gives
 * way once the end-of-article block scrolls into view — that block does the
 * same job with more room, and the bar would otherwise sit on the footer.
 *
 * Portalled to <body>. `main` keeps the transform its entrance animation ends
 * on, and a transformed ancestor becomes the containing block for `fixed`
 * descendants — inside it, the bar sat at the bottom of the article instead
 * of the bottom of the screen.
 */
export function VoteBar() {
  const t = useTranslations("articles.vote");
  const tc = useTranslations("articles");
  const { article, busy, up, down, noticeHere, press } = useSpot("bar");
  const [reachedEnd, setReachedEnd] = useState(false);
  const hydrated = useHydrated();

  useEffect(() => {
    const end = document.getElementById("article-end");
    if (!end) return;
    const io = new IntersectionObserver(([entry]) => {
      // Past it counts too: scrolling on into the comments keeps the bar away.
      setReachedEnd(entry.isIntersecting || entry.boundingClientRect.top < 0);
    });
    io.observe(end);
    return () => io.disconnect();
  }, []);

  if (!hydrated) return null;

  return createPortal(
    <div
      className={cn(
        "fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background/95 backdrop-blur-md transition-transform duration-300 desk:hidden",
        reachedEnd && !noticeHere ? "translate-y-full" : "translate-y-0"
      )}
      // inert, not aria-hidden: off-screen buttons must leave the tab order too.
      inert={reachedEnd && !noticeHere}
    >
      {noticeHere && (
        <div className="container-qp pt-3">
          <Notice kind={noticeHere} />
        </div>
      )}
      <div className="container-qp flex h-14 items-center justify-between gap-3 pb-[env(safe-area-inset-bottom)]">
        <div className="flex items-center gap-1 rounded-full border border-border bg-surface p-1">
          <button
            type="button"
            onClick={() => press(1)}
            disabled={busy}
            aria-pressed={up}
            aria-label={t("upAria")}
            className={cn(
              "flex size-10 items-center justify-center rounded-full transition-colors",
              up ? "bg-positive text-white" : "text-dim active:bg-surface-2"
            )}
          >
            <ArrowBigUp className={cn("size-5", up && "fill-current")} aria-hidden="true" />
          </button>
          <span
            className={cn(
              "figure min-w-8 text-center text-[15px] font-semibold tabular-nums",
              up ? "text-positive" : down ? "text-negative" : "text-ink"
            )}
          >
            {article.score}
          </span>
          <button
            type="button"
            onClick={() => press(-1)}
            disabled={busy}
            aria-pressed={down}
            aria-label={t("downAria")}
            className={cn(
              "flex size-10 items-center justify-center rounded-full transition-colors",
              down ? "bg-negative text-white" : "text-dim active:bg-surface-2"
            )}
          >
            <ArrowBigDown className={cn("size-5", down && "fill-current")} aria-hidden="true" />
          </button>
        </div>
        <a
          href="#comments"
          className="inline-flex items-center gap-2 rounded-full border border-border px-4 py-2.5 text-[14px] font-medium text-ink"
        >
          <MessageSquare className="size-4" aria-hidden="true" />
          {tc("commentCount", { count: article.comment_count })}
        </a>
      </div>
    </div>,
    document.body
  );
}
