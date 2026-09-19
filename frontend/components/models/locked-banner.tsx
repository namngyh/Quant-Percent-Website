"use client";

import { Lock } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/auth-context";
import { isVerifiedMember } from "@/lib/auth/verified";

/** Counts of previewable vs members-only models, shown to anyone who cannot
 *  yet open them — signed out, or signed in without a confirmed address. */
export function LockedBanner({
  preview,
  locked,
}: {
  preview: number;
  locked: number;
}) {
  const t = useTranslations("models.locked");
  const tAuth = useTranslations("auth.nav");
  const tVerify = useTranslations("auth.verify");
  const { user, status } = useAuth();

  if (locked === 0 || status === "loading" || isVerifiedMember(user)) {
    return null;
  }

  const unverified = user !== null;

  return (
    <div className="mt-10 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-border bg-surface px-5 py-4 shadow-sm">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <Lock className="mt-0.5 size-4 shrink-0 text-dim" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm font-medium">{t("bannerTitle", { preview })}</p>
          <p className="mt-1 text-[13px] text-dim">
            {unverified
              ? tVerify("bannerText", { locked })
              : t("bannerText", { locked })}
          </p>
        </div>
      </div>
      <Button asChild size="sm">
        <Link href={unverified ? "/account" : "/login?next=/models"}>
          {unverified ? tVerify("bannerAction") : tAuth("signIn")}
        </Link>
      </Button>
    </div>
  );
}
