"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { SkeletonLoader } from "@/components/states/skeleton-loader";
import { ApiError, apiRequest } from "@/lib/api/fetcher";

type State = "pending" | "success" | "invalid" | "error";

export function VerifyEmailStatus({ token }: { token: string }) {
  const t = useTranslations("auth");
  const [state, setState] = useState<State>("pending");
  const fired = useRef(false);

  useEffect(() => {
    // The token is single use, and React Strict Mode runs effects twice in dev.
    // A ref rather than state because the setter is async: both runs would still
    // read false, spend the token twice, and report failure right after success.
    if (fired.current) return;
    fired.current = true;

    apiRequest<{ success: boolean }>("/api/v1/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ token }),
    })
      .then(() => setState("success"))
      .catch((error) =>
        setState(
          error instanceof ApiError && error.status === 400 ? "invalid" : "error"
        )
      );
  }, [token]);

  if (state === "pending") {
    return (
      <div role="status" aria-label={t("verify.verifying")}>
        <SkeletonLoader rows={2} />
      </div>
    );
  }

  if (state === "success") {
    return (
      <div
        className="rounded-lg border border-border bg-surface p-6 shadow-sm"
        role="status"
      >
        <p className="text-sm leading-relaxed text-ink">{t("verify.success")}</p>
        <Link
          href="/models"
          className="mt-4 inline-block text-[13px] font-medium underline-offset-4 hover:underline"
        >
          {t("verify.continue")} →
        </Link>
      </div>
    );
  }

  // There is no resend-verification endpoint — send_email_verification runs only
  // at registration — so neither branch offers to send a new link.
  return (
    <div
      className="rounded-lg border border-border bg-surface p-6 shadow-sm"
      role="alert"
    >
      <p className="text-sm leading-relaxed text-ink">
        {state === "invalid" ? t("verify.invalidToken") : t("error")}
      </p>
      <Link
        href="/login"
        className="mt-4 inline-block text-[13px] font-medium underline-offset-4 hover:underline"
      >
        {t("verify.toLogin")} →
      </Link>
    </div>
  );
}
