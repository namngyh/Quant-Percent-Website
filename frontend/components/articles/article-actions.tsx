"use client";

import { useState } from "react";
import { Pencil, PenLine, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { useArticle } from "@/components/articles/article-context";
import { apiRequest } from "@/lib/api/fetcher";
import { useAuth } from "@/lib/auth/auth-context";
import { isAuthor } from "@/lib/auth/verified";

/** Edit and delete, for whoever the server says may. */
export function ArticleActions() {
  const t = useTranslations("articles");
  const router = useRouter();
  const { article } = useArticle();
  const [deleting, setDeleting] = useState(false);
  const [failed, setFailed] = useState(false);

  if (!article.can_edit && !article.can_delete) return null;

  const remove = async () => {
    if (!window.confirm(t("deleteConfirm"))) return;
    setDeleting(true);
    setFailed(false);
    try {
      await apiRequest(`/api/v1/articles/${article.slug}`, { method: "DELETE" });
      router.push("/articles");
      router.refresh();
    } catch {
      setFailed(true);
      setDeleting(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {article.can_edit && (
        <Button asChild size="sm" variant="outline">
          <Link href={`/articles/${article.slug}/edit`}>
            <Pencil aria-hidden="true" />
            {t("edit")}
          </Link>
        </Button>
      )}
      {article.can_delete && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={deleting}
          onClick={() => void remove()}
          className="hover:text-negative"
        >
          <Trash2 aria-hidden="true" />
          {deleting ? t("deleting") : t("delete")}
        </Button>
      )}
      {failed && (
        <p role="alert" className="w-full text-sm text-negative">
          {t("deleteError")}
        </p>
      )}
    </div>
  );
}

/** "Write an article", shown only to accounts that can publish. */
export function WriteButton() {
  const t = useTranslations("articles");
  const { user } = useAuth();
  if (!isAuthor(user)) return null;
  return (
    <Button asChild>
      <Link href="/articles/new">
        <PenLine aria-hidden="true" />
        {t("write")}
      </Link>
    </Button>
  );
}
