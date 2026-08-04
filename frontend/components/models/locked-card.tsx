"use client";

import { Lock } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useAuth } from "@/lib/auth/auth-context";

/**
 * Wraps a server-rendered ModelCard. Members-only models are blurred
 * behind a lock until the visitor signs in; clicking goes to /login and
 * returns to the model afterwards.
 */
export function LockedCard({
  locked,
  slug,
  children,
}: {
  locked: boolean;
  slug: string;
  children: React.ReactNode;
}) {
  const t = useTranslations("models.locked");
  const { status } = useAuth();

  // While the stored session is being read, show the card as-is so
  // signed-in visitors never see a flash of the locked state.
  if (!locked || status !== "anonymous") return <>{children}</>;

  return (
    <div className="relative h-full">
      <div
        aria-hidden="true"
        className="pointer-events-none h-full select-none opacity-55 blur-[3px] [&>article]:h-full"
      >
        {children}
      </div>

      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-background/40 p-6 text-center">
        <span className="flex size-11 items-center justify-center rounded-full border border-border bg-background">
          <Lock className="size-4" aria-hidden="true" />
        </span>
        <p className="text-sm font-medium">{t("badge")}</p>
        <p className="max-w-[15rem] text-xs text-dim">{t("cardHint")}</p>
      </div>

      {/* Whole-card click target */}
      <Link
        href={`/login?next=/models/${slug}`}
        className="absolute inset-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
      >
        <span className="sr-only">{t("cardHint")}</span>
      </Link>
    </div>
  );
}
