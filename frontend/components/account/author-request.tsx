"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { apiRequest } from "@/lib/api/fetcher";
import { useAuth } from "@/lib/auth/auth-context";

interface AuthResponse {
  user: { role?: string; author_request_status?: string | null };
}

/**
 * Lets an ordinary member ask an admin for author access.
 *
 * Publishing itself does not exist yet — this only moves the account into the
 * queue an admin reviews, so the wording promises a decision and nothing more.
 */
export function AuthorRequest() {
  const t = useTranslations("auth.author");
  const { user, refreshUser } = useAuth();
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState(false);

  if (!user) return null;

  const role = user.role ?? "user";
  const request = user.author_request_status ?? null;

  const send = async () => {
    setSending(true);
    setFailed(false);
    try {
      await apiRequest<AuthResponse>("/api/v1/auth/request-author", {
        method: "POST",
      });
      await refreshUser();
    } catch {
      // Nothing to distinguish: the endpoint has no rate limit and no
      // per-status branch, so every failure is the same "try again" here.
      setFailed(true);
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="border-t border-border pt-12">
      <h2 className="title-md">{t("title")}</h2>
      <p className="mt-2 text-sm leading-relaxed text-ink">{t("description")}</p>

      <div className="mt-7">
        {role !== "user" ? (
          <p
            role="status"
            className="rounded-lg border border-border bg-surface-2 px-4 py-3 text-sm text-ink"
          >
            {t("granted")}
          </p>
        ) : request === "pending" ? (
          <p
            role="status"
            className="rounded-lg border border-border bg-surface-2 px-4 py-3 text-sm text-ink"
          >
            {t("pending")}
          </p>
        ) : (
          <>
            {request === "rejected" && (
              <p className="mb-4 text-sm leading-relaxed text-dim">
                {t("rejected")}
              </p>
            )}
            <Button type="button" disabled={sending} onClick={() => void send()}>
              {sending ? t("requesting") : t("request")}
            </Button>
          </>
        )}
        {failed && (
          <p role="alert" className="mt-3 text-sm text-negative">
            {t("error")}
          </p>
        )}
      </div>
    </section>
  );
}
