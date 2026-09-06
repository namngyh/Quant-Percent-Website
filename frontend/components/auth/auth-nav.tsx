"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useAuth } from "@/lib/auth/auth-context";
import { isAdmin } from "@/lib/auth/verified";

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
  const tAdmin = useTranslations("admin");
  const { user, status, signOut } = useAuth();
  const admin = isAdmin(user);

  if (status === "loading") {
    return variant === "desktop" ? <span className="w-28" aria-hidden="true" /> : null;
  }

  if (variant === "mobile") {
    return (
      <>
        {user ? (
          <>
            <Link
              href="/account"
              onClick={onNavigate}
              className="border-b border-border py-5 text-xl font-medium tracking-normal text-brand"
              title={user.email}
            >
              {user.name}
            </Link>
            {admin && (
              <Link
                href="/admin"
                onClick={onNavigate}
                className="border-b border-border py-5 text-xl font-medium tracking-normal"
              >
                {tAdmin("title")}
              </Link>
            )}
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
        {/* The name, not the email: it is what the member chose to be called,
            and it survives the 11rem truncation far better. text-brand rather
            than the nav links' text-ink so "you" reads as a different kind of
            thing from the sections of the site. The email stays reachable in
            the tooltip. */}
        {admin && (
          <Link
            href="/admin"
            className="text-[13px] font-medium text-dim transition-colors hover:text-foreground"
          >
            {tAdmin("title")}
          </Link>
        )}
        <Link
          href="/account"
          className="max-w-[11rem] truncate text-[13px] font-medium text-brand transition-colors hover:text-brand-strong"
          title={user.email}
        >
          {user.name}
        </Link>
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
