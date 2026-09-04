"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";

/**
 * What a visitor sees when a page fails to render.
 *
 * Without this file Next.js falls back to its own screen: black text on white,
 * in English, with no header, no logo, an empty <title>, and a ten-digit error
 * id as the only other content. That is what the site served on a 500 — a
 * backend restart, a database under load, the VPN dropping — and none of it is
 * hypothetical on a one-vCPU host.
 *
 * This renders inside `[locale]/layout.tsx`, so the header, the footer and the
 * language switcher are all still there and a reader is never stranded. It is a
 * Client Component because `reset` is a callback and error boundaries in the
 * App Router are client-side by definition.
 *
 * The message says the one thing a visitor most needs to know — that nothing of
 * theirs was lost — because the portfolio tool takes holdings as input and "the
 * page crashed" is a reasonable moment to wonder whether they were kept. They
 * are not; the tool stores nothing, and saying so here costs a sentence.
 *
 * `digest` is the server-side hash of the real error. The stack itself is
 * deliberately never shown: it would leak paths and query shapes to anyone who
 * can trigger a 500. The digest is safe to print and is the only thing that
 * lets a report be matched to a server log.
 */
export default function LocaleError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("error");

  useEffect(() => {
    // The browser console is the only sink available here. A real error
    // reporter would be wired in at this point.
    console.error(error);
  }, [error]);

  return (
    <main className="container-qp section-pad">
      <div className="mx-auto max-w-xl text-center">
        <p className="figure text-6xl text-lightgray" aria-hidden="true">
          500
        </p>
        <h1 className="title-md mt-6">{t("title")}</h1>
        <p className="mt-4 leading-relaxed text-dim">{t("description")}</p>

        <div className="mt-9 flex flex-wrap justify-center gap-3">
          <Button onClick={reset}>{t("retry")}</Button>
          <Button asChild variant="outline">
            <Link href="/">{t("backHome")}</Link>
          </Button>
        </div>

        {error.digest && (
          <p className="figure mt-8 text-xs text-dim">
            {t("reference")}: {error.digest}
          </p>
        )}
      </div>
    </main>
  );
}
