"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useAuth } from "@/lib/auth/auth-context";
import { isAdmin } from "@/lib/auth/verified";
import {
  NavDropdown,
  NavDropdownButton,
  NavDropdownLink,
  NavDropdownSeparator,
} from "@/components/layout/nav-dropdown";

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
    /* One control instead of three links side by side. The name, not the
       email: it is what the member chose to be called, and it survives the
       truncation far better. 8rem, not the old 11rem: with Community on the
       bar, a wider name pushed it past 980px. text-brand rather than the nav
       links' text-ink so "you" reads as a different kind of thing from the
       sections of the site. The email heads the menu so it is still
       reachable. */
    return (
      <NavDropdown
        align="end"
        label={<span className="max-w-[8rem] truncate">{user.name}</span>}
        triggerClassName="text-brand hover:text-brand-strong"
      >
        <p className="truncate px-3 pb-1.5 pt-1 text-[12px] text-dim">{user.email}</p>
        <NavDropdownSeparator />
        <NavDropdownLink href="/account">{t("account")}</NavDropdownLink>
        {admin && <NavDropdownLink href="/admin">{tAdmin("title")}</NavDropdownLink>}
        <NavDropdownSeparator />
        <NavDropdownButton onSelect={() => void signOut()}>
          {t("signOut")}
        </NavDropdownButton>
      </NavDropdown>
    );
  }

  // Sign-in only: the sign-in page links to registration, so a second link
  // here cost bar width without adding a route anyone could not reach.
  return (
    <Link
      href="/login"
      className="whitespace-nowrap rounded-full bg-accent px-5 py-2 text-[13px] font-medium text-white transition-colors hover:bg-accent-strong"
    >
      {t("signIn")}
    </Link>
  );
}
