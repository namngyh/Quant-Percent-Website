"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { ResendVerification } from "@/components/auth/resend-verification";
import { useAuth } from "@/lib/auth/auth-context";
import { isVerifiedMember } from "@/lib/auth/verified";
import { TERMINAL_URL } from "@/lib/terminal";

/**
 * Sends a signed-in, confirmed member on to the Terminal, and everyone else to
 * the step they are missing.
 *
 * `bouncedBack` is set when the Terminal's gate sent the visitor here. If this
 * page still thinks they are fine to go, sending them again would loop between
 * the two sites forever — most likely a session cookie from before the cookie
 * was shared with the subdomain — so it stops and says what to do instead.
 * Loading the session here (auth context → /auth/me, refreshing on 401) is
 * itself what re-issues the cookies on the shared domain, so a plain second
 * attempt usually works, and sign out / in always does.
 */
export function TerminalLauncher({ bouncedBack }: { bouncedBack: boolean }) {
  const t = useTranslations("terminalPage");
  const router = useRouter();
  const { user, status, signOut } = useAuth();
  const verified = isVerifiedMember(user);
  const go = status === "authenticated" && verified && !bouncedBack;

  useEffect(() => {
    if (status === "anonymous") {
      router.replace("/login?next=/terminal");
    } else if (go) {
      window.location.replace(TERMINAL_URL);
    }
  }, [status, go, router]);

  if (status === "loading" || status === "anonymous" || go) {
    return (
      <p role="status" className="text-sm text-dim">
        {t("opening")}
      </p>
    );
  }

  if (!verified) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6 shadow-sm">
        <h2 className="text-[15px] font-medium text-foreground">
          {t("unverifiedTitle")}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink">
          {t("unverified", { email: user?.email ?? "" })}
        </p>
        <ResendVerification className="mt-4 text-sm" />
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-6 shadow-sm">
      <h2 className="text-[15px] font-medium text-foreground">{t("loopTitle")}</h2>
      <p className="mt-2 text-sm leading-relaxed text-ink">{t("loop")}</p>
      <div className="mt-5 flex flex-wrap gap-3">
        <Button
          size="sm"
          onClick={async () => {
            await signOut();
            router.replace("/login?next=/terminal");
          }}
        >
          {t("signOutAndIn")}
        </Button>
        <Button size="sm" variant="outline" asChild>
          <a href={TERMINAL_URL}>{t("openManually")}</a>
        </Button>
      </div>
      <p className="mt-5 text-[12px] leading-relaxed text-dim">{t("sharedNote")}</p>
    </div>
  );
}
