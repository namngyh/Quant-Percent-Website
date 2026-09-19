import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { AuthShell } from "@/components/auth/auth-shell";
import { ResetPasswordForm } from "@/components/auth/reset-password-form";
import { localeAlternates } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.resetPassword" });
  return {
    title: t("title"),
    description: t("description"),
    alternates: localeAlternates(locale, "/reset-password"),
    robots: { index: false, follow: true },
  };
}

export default async function ResetPasswordPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ token?: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const { token } = await searchParams;
  const t = await getTranslations("auth");

  // Reading the token on the server means the missing-token case renders with no
  // JavaScript and no Suspense boundary flashing a skeleton first. The backend
  // requires at least 10 characters, so anything shorter is a broken link.
  const usable = typeof token === "string" && token.length >= 10;

  return (
    <AuthShell
      title={t("reset.title")}
      description={t("reset.description")}
      footer={
        <p>
          <Link
            href="/login"
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            {t("forgot.backToLogin")}
          </Link>
        </p>
      }
    >
      {usable ? (
        <ResetPasswordForm token={token} />
      ) : (
        <div
          className="rounded-lg border border-border bg-surface p-6 shadow-sm"
          role="status"
        >
          <p className="text-sm leading-relaxed text-ink">
            {t("reset.missingToken")}
          </p>
          <Link
            href="/forgot-password"
            className="mt-4 inline-block text-[13px] font-medium underline-offset-4 hover:underline"
          >
            {t("reset.requestNew")} →
          </Link>
        </div>
      )}
    </AuthShell>
  );
}
