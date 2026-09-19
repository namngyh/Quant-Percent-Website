"use client";

import { useEffect, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { ImagePlus, Lock } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SkeletonLoader } from "@/components/states/skeleton-loader";
import { ArticleMarkdown } from "@/components/articles/article-markdown";
import { ApiError, apiRequest, useApi } from "@/lib/api/fetcher";
import {
  BODY_MAX,
  BODY_MIN,
  IMAGE_MAX_BYTES,
  SUMMARY_MAX,
  TITLE_MAX,
  TITLE_MIN,
  type ArticleDetail,
  type ArticlePayload,
} from "@/lib/api/articles";
import { useAuth } from "@/lib/auth/auth-context";
import { isAuthor } from "@/lib/auth/verified";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];

/* Syntax examples. Code rather than copy: the braces in LaTeX would be read
   as ICU placeholders if they lived in the message files. */
const HELP: { key: string; code: string }[] = [
  { key: "helpHeading", code: "## Tiêu đề mục" },
  { key: "helpEmphasis", code: "**đậm**, *nghiêng*, [liên kết](https://…)" },
  { key: "helpMath", code: "$\\sigma^2 = \\frac{1}{n}\\sum_i (x_i-\\bar x)^2$" },
  { key: "helpBlockMath", code: "$$\nR_t = \\ln\\frac{P_t}{P_{t-1}}\n$$" },
  { key: "helpTable", code: "| Mô hình | Sharpe |\n|---|---:|\n| MSDP | 1.42 |" },
  { key: "helpImage", code: "![Chú thích](url-ảnh)" },
  {
    key: "helpChart",
    code: '```chart\n{\n  "xAxis": { "type": "category", "data": ["2024", "2025"] },\n  "yAxis": { "type": "value" },\n  "series": [{ "type": "line", "name": "VN30", "data": [1250, 1340] }]\n}\n```',
  },
];

function EditorGate() {
  const t = useTranslations("articles.editor");
  return (
    <section className="flex flex-col items-center rounded-lg border border-border bg-surface px-6 py-16 text-center shadow-sm">
      <span className="flex size-12 items-center justify-center rounded-full border border-border bg-background">
        <Lock className="size-5" aria-hidden="true" />
      </span>
      <h2 className="title-md mt-6">{t("gateTitle")}</h2>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-ink">{t("gateText")}</p>
      <Button asChild className="mt-8">
        <Link href="/account">{t("gateAction")}</Link>
      </Button>
    </section>
  );
}

/**
 * Write or edit an article. Markdown on the left of a tab, the rendered result
 * on the other — rendered by the very component the article page uses, so
 * what the preview shows is what readers get.
 */
export function ArticleEditor({ slug }: { slug?: string }) {
  const { user, status } = useAuth();
  const author = isAuthor(user);
  const { data, error } = useApi<ArticleDetail>(
    slug && author ? `/api/v1/articles/${slug}` : null
  );

  if (status === "loading" || (slug && author && !data && !error)) {
    return <SkeletonLoader rows={8} />;
  }
  if (!author) return <EditorGate />;
  if (slug && (error || !data?.can_edit)) {
    return <NotOwner />;
  }
  return <EditorForm slug={slug} initial={data} />;
}

function NotOwner() {
  const t = useTranslations("articles.editor");
  return (
    <p className="rounded-lg border border-border bg-surface p-6 text-sm text-ink">
      {t("notOwner")}
    </p>
  );
}

function EditorForm({
  slug,
  initial,
}: {
  slug?: string;
  initial?: ArticleDetail;
}) {
  const t = useTranslations("articles.editor");
  const router = useRouter();
  const [tab, setTab] = useState<"write" | "preview">("write");
  const [state, setState] = useState<"idle" | "saving" | "error" | "rate_limited">("idle");
  const [imageState, setImageState] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [saved, setSaved] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const {
    register,
    handleSubmit,
    control,
    setValue,
    getValues,
    formState: { errors, isDirty },
  } = useForm<ArticlePayload>({
    defaultValues: {
      title: initial?.title ?? "",
      summary: initial?.summary ?? "",
      body: initial?.body ?? "",
    },
  });

  const body = useWatch({ control, name: "body" });
  const bodyField = register("body", {
    validate: (v) => {
      const len = v.trim().length;
      if (len < BODY_MIN) return t("bodyLength", { min: BODY_MIN });
      if (len > BODY_MAX) return t("bodyTooLong", { max: BODY_MAX });
      return true;
    },
  });

  // A long article is an hour of somebody's work; closing the tab by accident
  // should at least ask first.
  useEffect(() => {
    if (!isDirty || saved) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [isDirty, saved]);

  const insertAtCursor = (snippet: string) => {
    const el = bodyRef.current;
    const current = getValues("body");
    const start = el?.selectionStart ?? current.length;
    const end = el?.selectionEnd ?? current.length;
    const next = `${current.slice(0, start)}${snippet}${current.slice(end)}`;
    setValue("body", next, { shouldDirty: true });
    requestAnimationFrame(() => {
      if (!el) return;
      el.focus();
      el.selectionStart = el.selectionEnd = start + snippet.length;
    });
  };

  const upload = async (file: File) => {
    setImageState(null);
    if (!IMAGE_TYPES.includes(file.type)) return setImageState(t("imageUnsupported"));
    if (file.size > IMAGE_MAX_BYTES) return setImageState(t("imageTooLarge"));
    setUploading(true);
    try {
      const result = await apiRequest<{ id: string; url: string }>(
        "/api/v1/articles/images",
        { method: "POST", body: file, headers: { "Content-Type": file.type } }
      );
      const alt = file.name.replace(/\.[^.]+$/, "").replace(/[[\]]/g, "");
      setTab("write");
      insertAtCursor(`\n![${alt}](${API_BASE}${result.url})\n`);
    } catch (error) {
      setImageState(
        error instanceof ApiError && error.status === 413
          ? t("imageTooLarge")
          : error instanceof ApiError && error.status === 415
            ? t("imageUnsupported")
            : t("imageError")
      );
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onSubmit = async (values: ArticlePayload) => {
    setState("saving");
    const payload = {
      title: values.title.trim(),
      summary: values.summary.trim(),
      body: values.body,
    };
    try {
      const result = await apiRequest<{ slug: string }>(
        slug ? `/api/v1/articles/${slug}` : "/api/v1/articles",
        { method: slug ? "PATCH" : "POST", body: JSON.stringify(payload) }
      );
      setSaved(true);
      router.push(`/articles/${result.slug}`);
      router.refresh();
    } catch (error) {
      setState(error instanceof ApiError && error.status === 429 ? "rate_limited" : "error");
    }
  };

  const err = (msg?: string) =>
    msg ? <p className="mt-1.5 text-xs text-negative">{msg}</p> : null;

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-7" noValidate>
      <div>
        <Label htmlFor="article-title">{t("fieldTitle")}</Label>
        <Input
          id="article-title"
          className="mt-2 rounded-lg text-[17px] font-medium"
          maxLength={TITLE_MAX}
          aria-invalid={errors.title ? true : undefined}
          {...register("title", {
            validate: (v) => {
              const len = v.trim().length;
              return (len >= TITLE_MIN && len <= TITLE_MAX) ||
                t("titleLength", { min: TITLE_MIN, max: TITLE_MAX });
            },
          })}
        />
        {err(errors.title?.message)}
      </div>

      <div>
        <Label htmlFor="article-summary">{t("fieldSummary")}</Label>
        <p className="mt-1 text-xs text-dim">{t("summaryHint")}</p>
        <Textarea
          id="article-summary"
          className="mt-2 min-h-20"
          maxLength={SUMMARY_MAX}
          aria-invalid={errors.summary ? true : undefined}
          {...register("summary", {
            validate: (v) =>
              v.trim().length <= SUMMARY_MAX || t("summaryLength", { max: SUMMARY_MAX }),
          })}
        />
        {err(errors.summary?.message)}
      </div>

      <div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <Label htmlFor="article-body">{t("fieldBody")}</Label>
          <div className="flex items-center gap-2">
            <div role="tablist" aria-label={t("fieldBody")} className="flex rounded-full border border-border p-0.5">
              {(["write", "preview"] as const).map((key) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={tab === key}
                  onClick={() => setTab(key)}
                  className={cn(
                    "rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors",
                    tab === key ? "bg-brand text-white" : "text-dim hover:text-ink"
                  )}
                >
                  {t(key)}
                </button>
              ))}
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
            >
              <ImagePlus aria-hidden="true" />
              {uploading ? t("uploading") : t("insertImage")}
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept={IMAGE_TYPES.join(",")}
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void upload(file);
              }}
            />
          </div>
        </div>
        {imageState && (
          <p role="alert" className="mt-2 text-xs text-negative">
            {imageState}
          </p>
        )}

        <div className={cn("mt-3", tab !== "write" && "hidden")}>
          <Textarea
            id="article-body"
            className="min-h-[28rem] font-mono text-[14px] leading-relaxed"
            aria-invalid={errors.body ? true : undefined}
            {...bodyField}
            ref={(el) => {
              bodyField.ref(el);
              bodyRef.current = el;
            }}
          />
        </div>
        {tab === "preview" && (
          <div className="mt-3 min-h-[28rem] rounded-lg border border-border bg-background px-5 py-6 sm:px-8">
            {body.trim() ? (
              <ArticleMarkdown source={body} />
            ) : (
              <p className="text-sm text-dim">{t("previewEmpty")}</p>
            )}
          </div>
        )}
        <div className="mt-1.5 flex justify-between gap-3">
          {err(errors.body?.message) ?? <span />}
          <span className="figure text-[12px] text-dim">
            {t("chars", { count: body.length })}
          </span>
        </div>

        <details className="mt-4 rounded-lg border border-border bg-surface px-4 py-3 text-sm">
          <summary className="cursor-pointer font-medium text-ink">{t("helpTitle")}</summary>
          <dl className="mt-3 space-y-3">
            {HELP.map((item) => (
              <div key={item.key} className="grid gap-1 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-4">
                <dt className="text-dim">{t(item.key)}</dt>
                <dd>
                  <pre className="overflow-x-auto whitespace-pre rounded-md bg-background px-3 py-2 font-mono text-[12px] text-ink">
                    {item.code}
                  </pre>
                </dd>
              </div>
            ))}
          </dl>
        </details>
      </div>

      {(state === "error" || state === "rate_limited") && (
        <p role="alert" className="text-sm text-negative">
          {state === "rate_limited" ? t("rateLimited") : t("error")}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-border pt-6">
        <Button type="submit" disabled={state === "saving" || uploading}>
          {state === "saving" ? t("saving") : slug ? t("save") : t("publish")}
        </Button>
        <Button asChild variant="ghost">
          <Link href={slug ? `/articles/${slug}` : "/articles"}>{t("cancel")}</Link>
        </Button>
        {isDirty && state !== "saving" && (
          <span className="text-[13px] text-dim">{t("unsaved")}</span>
        )}
      </div>
    </form>
  );
}
