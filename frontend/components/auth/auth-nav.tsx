"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useAuth } from "@/lib/auth/auth-context";

/**
 * Header account controls. Renders nothing until the stored session is
 * read so the two states never flash past each other.
 */
export function AuthNav({
  variant = "desktop",
  onNavigate,
}: {
  variant?: "desktop" | "mobile";
  onNavigate?: () => void;
}) {
  const t = useTranslations("auth.nav");
  const { user, status, signOut } = useAuth();

  if (status === "loading") {
    return variant === "desktop" ? <span className="w-28" aria-hidden="true" /> : null;
  }

  if (variant === "mobile") {
    return (
      <>
        {user ? (
          <>
            <p className="border-b border-border py-5 text-sm text-dim">
              {user.email}
            </p>
            <button
              type="button"
              onClick={() => {
                void signOut();
                onNavigate?.();
              }}
              className="border-b border-border py-5 text-left text-xl font-medium tracking-normal"
            >
              {t("signOut")}
            </button>
          </>
        ) : (
          <>
            <Link
              href="/login"
              onClick={onNavigate}
              className="border-b border-border py-5 text-xl font-medium tracking-normal"
            >
              {t("signIn")}
            </Link>
            <Link
              href="/register"
              onClick={onNavigate}
              className="border-b border-border py-5 text-xl font-medium tracking-normal"
            >
              {t("signUp")}
            </Link>
          </>
        )}
      </>
    );
  }

  if (user) {
    return (
      <div className="flex items-center gap-3">
        <span
          className="max-w-[11rem] truncate text-[13px] text-dim"
          title={user.email}
        >
          {user.email}
        </span>
        <button
          type="button"
          onClick={() => void signOut()}
          className="text-[13px] font-medium text-dim transition-colors hover:text-foreground"
        >
          {t("signOut")}
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-4">
      <Link
        href="/register"
        className="text-[13px] font-medium text-dim transition-colors hover:text-brand"
      >
        {t("signUp")}
      </Link>
      <Link
        href="/login"
        className="rounded-full bg-accent px-5 py-2 text-[13px] font-medium text-white transition-colors hover:bg-accent-strong"
      >
        {t("signIn")}
      </Link>
    </div>
  );
}
