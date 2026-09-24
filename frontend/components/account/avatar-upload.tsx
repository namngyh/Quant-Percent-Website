"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Camera } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AuthorAvatar } from "@/components/articles/author-avatar";
import { ApiError, apiRequest } from "@/lib/api/fetcher";
import { displayName, useAuth } from "@/lib/auth/auth-context";
import { usesApiAuth } from "@/lib/auth/mode";

const MAX_BYTES = 5 * 1024 * 1024;
const TYPES = ["image/jpeg", "image/png", "image/webp"];

interface Signature {
  cloud_name: string;
  api_key: string;
  timestamp: number;
  signature: string;
  public_id: string;
  overwrite: boolean;
  allowed_formats: string;
}

/**
 * Change or remove the member's avatar.
 *
 * The file goes from the browser straight to Cloudinary, carrying a signature
 * the API issued for this member's own public id; the API then only has to
 * check the URL Cloudinary hands back. Image bytes never touch our server,
 * and the Cloudinary secret never touches the browser.
 */
export function AvatarUpload() {
  const t = useTranslations("auth.account");
  const { user, updateAvatar } = useAuth();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  if (!user) return null;
  // The mock session has no backend to sign an upload with.
  const canUpload = usesApiAuth() && !unavailable;

  const fail = (text: string) => setMessage({ ok: false, text });

  async function upload(file: File) {
    setMessage(null);
    if (!TYPES.includes(file.type)) return fail(t("avatarWrongType"));
    if (file.size > MAX_BYTES) return fail(t("avatarTooLarge"));

    setBusy(true);
    try {
      const sig = await apiRequest<Signature>("/api/v1/auth/me/avatar-signature", {
        method: "POST",
      });
      const form = new FormData();
      form.append("file", file);
      form.append("api_key", sig.api_key);
      form.append("timestamp", String(sig.timestamp));
      form.append("signature", sig.signature);
      form.append("public_id", sig.public_id);
      form.append("overwrite", String(sig.overwrite));
      form.append("allowed_formats", sig.allowed_formats);

      const response = await fetch(
        `https://api.cloudinary.com/v1_1/${encodeURIComponent(sig.cloud_name)}/image/upload`,
        { method: "POST", body: form }
      );
      if (!response.ok) throw new Error(`cloudinary ${response.status}`);
      const uploaded = (await response.json()) as { secure_url?: string };
      if (!uploaded.secure_url) throw new Error("cloudinary: no url");

      await updateAvatar(uploaded.secure_url);
      setMessage({ ok: true, text: t("avatarSaved") });
    } catch (error) {
      if (error instanceof ApiError && error.status === 503) {
        setUnavailable(true);
        fail(t("avatarUnavailable"));
      } else if (error instanceof ApiError && error.status === 429) {
        fail(t("avatarRateLimited"));
      } else {
        fail(t("avatarFailed"));
      }
    } finally {
      setBusy(false);
      // Picking the same file again must fire change again.
      if (input.current) input.current.value = "";
    }
  }

  async function remove() {
    setMessage(null);
    setBusy(true);
    try {
      await updateAvatar(null);
      setMessage({ ok: true, text: t("avatarSaved") });
    } catch {
      fail(t("avatarFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-5">
      <div className="relative">
        <AuthorAvatar name={displayName(user)} src={user.avatar_url} size="xl" />
        {canUpload && (
          <button
            type="button"
            onClick={() => input.current?.click()}
            disabled={busy}
            aria-label={user.avatar_url ? t("avatarChange") : t("avatarUpload")}
            className="absolute -bottom-1 -right-1 flex size-9 items-center justify-center rounded-full border border-border bg-background text-brand-strong shadow-sm transition-colors hover:bg-brand-soft disabled:opacity-60"
          >
            <Camera className="size-4" aria-hidden="true" />
          </button>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">{t("avatarTitle")}</p>
        <p className="mt-1 text-xs leading-relaxed text-dim">{t("avatarHint")}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {canUpload && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => input.current?.click()}
            >
              {busy
                ? t("avatarUploading")
                : user.avatar_url
                  ? t("avatarChange")
                  : t("avatarUpload")}
            </Button>
          )}
          {user.avatar_url && usesApiAuth() && (
            <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={remove}>
              {t("avatarRemove")}
            </Button>
          )}
        </div>
        {message && (
          <p
            role={message.ok ? "status" : "alert"}
            className={message.ok ? "mt-2 text-xs text-ink" : "mt-2 text-xs text-negative"}
          >
            {message.text}
          </p>
        )}
      </div>

      <input
        ref={input}
        type="file"
        accept={TYPES.join(",")}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void upload(file);
        }}
      />
    </div>
  );
}
