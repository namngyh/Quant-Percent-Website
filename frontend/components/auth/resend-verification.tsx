"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { ApiError, apiRequest } from "@/lib/api/fetcher";

type State = "idle" | "sending" | "sent" | "rate_limited" | "error";

/**
 * Sends a fresh confirmation link to the signed-in member.
 *
 * The link from registration lasts three days, and it used to be the only one
 * anybody ever got. Now that an unconfirmed address is locked out of
 * members-only output, that would be a trapdoor without this button.
 */
export function ResendVerification({ className }: { className?: string }) {
  const t = useTranslations("auth.verify");
  const [state, setState] = useState<State>("idle");

  const send = async () => {
    setState("sending");
    try {
      await apiRequest<{ success: boolean }>(
        "/api/v1/auth/resend-verification",
        { method: "POST" }
      );
      setState("sent");
    } catch (error) {
      setState(
        error instanceof ApiError && error.status === 429
          ? "rate_limited"
          : "error"
      );
    }
  };

  if (state === "sent") {
    return (
      <p role="status" className={className}>
        {t("resendSent")}
      </p>
    );
  }

  return (
    <div className={className}>
      <Button type="button" onClick={() => void send()} disabled={state === "sending"}>
        {state === "sending" ? t("resendSending") : t("resend")}
      </Button>
      {(state === "rate_limited" || state === "error") && (
        <p role="alert" className="mt-3 text-sm text-negative">
          {state === "rate_limited" ? t("resendRateLimited") : t("resendError")}
        </p>
      )}
    </div>
  );
}
