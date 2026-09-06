"use client";

import { MailCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { ResendVerification } from "@/components/auth/resend-verification";
import { useAuth } from "@/lib/auth/auth-context";

/**
 * Shown to a member who is signed in but has not confirmed their address.
 *
 * Deliberately not the sign-in panel: telling somebody who already has a
 * session to sign in is advice they cannot act on.
 */
export function VerifyEmailGate({ compact = false }: { compact?: boolean }) {
  const t = useTranslations("auth.verify");
  const { user } = useAuth();

  if (compact) {
    return (
      <div className="flex flex-col items-center gap-3 text-center">
        <span className="flex size-11 items-center justify-center rounded-full border border-border bg-background">
          <MailCheck className="size-4" aria-hidden="true" />
        </span>
        <p className="text-sm font-medium">{t("gateBadge")}</p>
        <p className="max-w-[15rem] text-xs text-dim">{t("gateCardHint")}</p>
      </div>
    );
  }

  return (
    <section className="flex flex-col items-center rounded-lg border border-border bg-surface px-6 py-16 text-center shadow-sm">
      <span className="flex size-12 items-center justify-center rounded-full border border-border bg-background">
        <MailCheck className="size-5" aria-hidden="true" />
      </span>
      <h2 className="title-md mt-6">{t("gateTitle")}</h2>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-ink">
        {t("gateText", { email: user?.email ?? "" })}
      </p>
      <ResendVerification className="mt-8" />
    </section>
  );
}
