"use client";

import { Lock } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/auth-context";

/** Counts of previewable vs members-only models, shown to signed-out visitors. */
export function LockedBanner({
  preview,
  locked,
}: {
  preview: number;
  locked: number;
}) {
  const t = useTranslations("models.locked");
  const tAuth = useTranslations("auth.nav");
  const { status } = useAuth();

  if (locked === 0 || status !== "anonymous") return null;

  return (
    <div className="mt-10 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-border bg-surface px-5 py-4 shadow-sm">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <Lock className="mt-0.5 size-4 shrink-0 text-dim" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm font-medium">{t("bannerTitle", { preview })}</p>
          <p className="mt-1 text-[13px] text-dim">{t("bannerText", { locked })}</p>
        </div>
      </div>
      <Button asChild size="sm">
        <Link href="/login?next=/models">{tAuth("signIn")}</Link>
      </Button>
    </div>
  );
}
