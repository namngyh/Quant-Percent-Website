"use client";

import { Lock } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { SkeletonLoader } from "@/components/states/skeleton-loader";
import { VerifyEmailGate } from "@/components/auth/verify-email-gate";
import { useAuth } from "@/lib/auth/auth-context";
import { isVerifiedMember } from "@/lib/auth/verified";

/**
 * Gates members-only model content on the detail page. Presentation only —
 * the server already refused the data; this just explains which wall was hit.
 */
export function MemberGate({
  locked,
  slug,
  children,
}: {
  locked: boolean;
  slug: string;
  children: React.ReactNode;
}) {
  const t = useTranslations("models.locked");
  const tAuth = useTranslations("auth.nav");
  const { user, status } = useAuth();

  if (!locked) return <>{children}</>;

  if (status === "loading") {
    return <SkeletonLoader rows={6} className="mt-4" />;
  }

  if (isVerifiedMember(user)) return <>{children}</>;

  // Signed in, but the address was never confirmed. A sign-in button here
  // would be a loop: they already are signed in.
  if (user) return <VerifyEmailGate />;

  return (
    <section className="flex flex-col items-center rounded-lg border border-border bg-surface px-6 py-16 text-center shadow-sm">
      <span className="flex size-12 items-center justify-center rounded-full border border-border bg-background">
        <Lock className="size-5" aria-hidden="true" />
      </span>
      <h2 className="title-md mt-6">{t("detailTitle")}</h2>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-ink">
        {t("detailText")}
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Button asChild>
          <Link href={`/login?next=/models/${slug}`}>{tAuth("signIn")}</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href={`/register?next=/models/${slug}`}>{tAuth("signUp")}</Link>
        </Button>
      </div>
    </section>
  );
}
