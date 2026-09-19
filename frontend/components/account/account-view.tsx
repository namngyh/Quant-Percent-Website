"use client";

import { Lock } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { SkeletonLoader } from "@/components/states/skeleton-loader";
import { ChangePasswordForm } from "@/components/account/change-password-form";
import { ProfileForm } from "@/components/account/profile-form";
import { AuthorRequest } from "@/components/account/author-request";
import { ResendVerification } from "@/components/auth/resend-verification";
import { useAuth } from "@/lib/auth/auth-context";
import { isVerifiedMember } from "@/lib/auth/verified";

export function AccountView() {
  const t = useTranslations("auth");
  const { user, status } = useAuth();

  // Reading the session takes a tick; showing the locked panel first would
  // flash "please sign in" at someone who already is.
  if (status === "loading") {
    return <SkeletonLoader rows={6} />;
  }

  if (!user) {
    return (
      <section className="flex flex-col items-center rounded-lg border border-border bg-surface px-6 py-16 text-center shadow-sm">
        <span className="flex size-12 items-center justify-center rounded-full border border-border bg-background">
          <Lock className="size-5" aria-hidden="true" />
        </span>
        <h2 className="title-md mt-6">{t("account.gateTitle")}</h2>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-ink">
          {t("account.gateDescription")}
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Button asChild>
            <Link href="/login?next=/account">{t("nav.signIn")}</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/register?next=/account">{t("nav.signUp")}</Link>
          </Button>
        </div>
      </section>
    );
  }

  return (
    <div className="max-w-xl space-y-14">
      {/* The locked model cards and the members banner both send unverified
          members here, so the thing that unblocks them has to be here too. */}
      {!isVerifiedMember(user) && (
        <section className="rounded-lg border border-border bg-surface-2 px-5 py-5">
          <h2 className="text-sm font-semibold">{t("verify.gateTitle")}</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink">
            {t("verify.gateText", { email: user.email })}
          </p>
          <ResendVerification className="mt-5" />
        </section>
      )}

      <section>
        <h2 className="title-md">{t("account.profileTitle")}</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink">
          {t("account.profileDescription")}
        </p>
        <div className="mt-7">
          <ProfileForm />
        </div>
      </section>

      <AuthorRequest />

      <section className="border-t border-border pt-12">
        <h2 className="title-md">{t("account.passwordTitle")}</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink">
          {t("account.passwordDescription")}
        </p>
        <div className="mt-7">
          <ChangePasswordForm />
        </div>
      </section>
    </div>
  );
}
