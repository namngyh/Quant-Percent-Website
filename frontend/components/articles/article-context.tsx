"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { ApiError, apiRequest, useApi } from "@/lib/api/fetcher";
import type { ArticleDetail, Vote, VoteResult } from "@/lib/api/articles";
import { useAuth } from "@/lib/auth/auth-context";
import { isVerifiedMember } from "@/lib/auth/verified";

export type VoteSpot = "rail" | "block" | "bar";
export type VoteNotice = "signIn" | "verify" | "own" | "error" | "rateLimited";

interface ArticleContextValue {
  article: ArticleDetail;
  busy: boolean;
  notice: { kind: VoteNotice; at: VoteSpot } | null;
  dismissNotice: () => void;
  vote: (target: Vote, at: VoteSpot) => Promise<void>;
  adjustComments: (delta: number) => void;
}

const ArticleContext = createContext<ArticleContextValue | null>(null);

export function useArticle() {
  const value = useContext(ArticleContext);
  if (!value) throw new Error("useArticle outside ArticleProvider");
  return value;
}

/** Counts after moving from the current vote to `next` (0 = no vote). */
function withVote(article: ArticleDetail, next: Vote | 0): ArticleDetail {
  let { upvotes, downvotes } = article;
  if (article.my_vote === 1) upvotes -= 1;
  if (article.my_vote === -1) downvotes -= 1;
  if (next === 1) upvotes += 1;
  if (next === -1) downvotes += 1;
  return {
    ...article,
    upvotes,
    downvotes,
    score: upvotes - downvotes,
    my_vote: next === 0 ? null : next,
  };
}

/**
 * One source of truth for the vote controls on the article page.
 *
 * The page puts a vote control in three places — beside the text, at the end
 * of it, and in a bar on phones — and all three must show the same count and
 * the same pressed state, so they read it from here rather than each keeping
 * their own.
 *
 * `initial` is the anonymous copy rendered on the server. Once the browser
 * knows somebody is signed in it asks again, because only that request
 * carries the cookie that says what this reader already voted.
 */
export function ArticleProvider({
  initial,
  children,
}: {
  initial: ArticleDetail;
  children: React.ReactNode;
}) {
  const { user, status } = useAuth();
  const key =
    status === "authenticated" ? `/api/v1/articles/${initial.slug}` : null;
  const { data, mutate } = useApi<ArticleDetail>(key);

  // Local copy for signed-out readers, whose SWR key is null and so cannot be
  // written through mutate.
  const [local, setLocal] = useState<ArticleDetail>(initial);
  const article = data ?? local;

  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<ArticleContextValue["notice"]>(null);

  const write = useCallback(
    async (next: ArticleDetail) => {
      setLocal(next);
      if (key) await mutate(next, { revalidate: false });
    },
    [key, mutate]
  );

  const vote = useCallback(
    async (target: Vote, at: VoteSpot) => {
      if (status === "loading" || busy) return;
      if (!user) return setNotice({ kind: "signIn", at });
      if (!isVerifiedMember(user)) return setNotice({ kind: "verify", at });
      if (user.id && user.id === article.author.id) {
        return setNotice({ kind: "own", at });
      }

      const before = article;
      // Pressing the vote you already cast takes it back.
      const value: Vote | 0 = before.my_vote === target ? 0 : target;
      const optimistic = withVote(before, value);

      setNotice(null);
      setBusy(true);
      await write(optimistic);
      try {
        const result = await apiRequest<VoteResult>(
          `/api/v1/articles/${before.slug}/vote`,
          { method: "PUT", body: JSON.stringify({ value }) }
        );
        await write({ ...optimistic, ...result });
      } catch (error) {
        await write(before);
        const code =
          error instanceof ApiError
            ? (error.payload as { detail?: { error?: string } } | undefined)
                ?.detail?.error
            : undefined;
        setNotice({
          kind:
            error instanceof ApiError && error.status === 429
              ? "rateLimited"
              : code === "cannot_vote_own"
                ? "own"
                : code === "email_not_verified"
                  ? "verify"
                  : error instanceof ApiError && error.status === 401
                    ? "signIn"
                    : "error",
          at,
        });
      } finally {
        setBusy(false);
      }
    },
    [article, busy, status, user, write]
  );

  const adjustComments = useCallback(
    (delta: number) => {
      void write({
        ...article,
        comment_count: Math.max(0, article.comment_count + delta),
      });
    },
    [article, write]
  );

  return (
    <ArticleContext.Provider
      value={{
        article,
        busy,
        notice,
        dismissNotice: () => setNotice(null),
        vote,
        adjustComments,
      }}
    >
      {children}
    </ArticleContext.Provider>
  );
}
