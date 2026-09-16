/**
 * Articles — types and calls. Shapes mirror backend/app/schemas/articles.py.
 *
 * Kept free of "use client" and of hooks so the server pages can import the
 * types and `countWords`; the fetching hooks live beside the components that
 * use them.
 */

export type ArticleSort = "new" | "old" | "top" | "comments";
export const ARTICLE_SORTS: ArticleSort[] = ["new", "top", "comments", "old"];

export type Vote = -1 | 1;

export interface ArticleAuthor {
  id: string;
  name: string;
  role: "user" | "author" | "admin";
}

export interface ArticleSummary {
  slug: string;
  title: string;
  summary: string | null;
  author: ArticleAuthor;
  created_at: string;
  updated_at: string;
  upvotes: number;
  downvotes: number;
  score: number;
  comment_count: number;
}

export interface ArticleList {
  items: ArticleSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface ArticleDetail extends ArticleSummary {
  body: string;
  my_vote: Vote | null;
  can_edit: boolean;
  can_delete: boolean;
  can_vote: boolean;
}

export interface VoteResult {
  upvotes: number;
  downvotes: number;
  score: number;
  my_vote: Vote | null;
}

export interface ArticleComment {
  id: string;
  body: string;
  author: ArticleAuthor;
  created_at: string;
  can_delete: boolean;
}

export interface CommentList {
  items: ArticleComment[];
  total: number;
  page: number;
  page_size: number;
}

export interface ArticlePayload {
  title: string;
  summary: string;
  body: string;
}

export const COMMENT_MAX_WORDS = 100;
export const TITLE_MIN = 5;
export const TITLE_MAX = 200;
export const SUMMARY_MAX = 400;
export const BODY_MIN = 50;
export const BODY_MAX = 100_000;
export const IMAGE_MAX_BYTES = 2 * 1024 * 1024;

/** Whitespace-separated words — the same rule as `count_words` on the server,
 *  so the counter under the box and the API never disagree by one. */
export function countWords(text: string) {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

/** About 220 words a minute, never less than one. Formulas and figures slow
 *  reading down, so this errs short rather than pretending to precision. */
export function readingMinutes(body: string) {
  return Math.max(1, Math.round(countWords(body) / 220));
}

// ------------------------------------------------------------------ server

function apiBase() {
  if (process.env.DATA_MODE !== "api") return null;
  return process.env.API_BASE_URL?.replace(/\/$/, "") || null;
}

/** False when this deployment has no backend to ask (the mock data mode). */
export function articlesAvailable() {
  return apiBase() !== null;
}

async function serverGet<T>(path: string): Promise<T | null> {
  const base = apiBase();
  if (!base) return null;
  const response = await fetch(`${base}${path}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`Backend API ${response.status} for ${path}`);
  }
  return (await response.json()) as T;
}

/**
 * Rendered on the server so the text is in the HTML search engines and link
 * previews read. Anonymous by construction: no cookies are forwarded, so the
 * per-viewer fields (my_vote, can_edit…) come back empty and the page asks
 * again from the browser when there is a session to ask with.
 */
export function fetchArticleList(params: {
  sort: ArticleSort;
  q?: string;
  page: number;
}) {
  const qs = new URLSearchParams({ sort: params.sort, page: String(params.page) });
  if (params.q) qs.set("q", params.q);
  return serverGet<ArticleList>(`/api/v1/articles?${qs}`);
}

export function fetchArticle(slug: string) {
  return serverGet<ArticleDetail>(`/api/v1/articles/${encodeURIComponent(slug)}`);
}
