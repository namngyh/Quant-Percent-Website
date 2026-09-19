import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { AuthShell } from "@/components/auth/auth-shell";
import { VerifyEmailStatus } from "@/components/auth/verify-email-status";
import { localeAlternates } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.verifyEmail" });
  return {
    title: t("title"),
    description: t("description"),
    alternates: localeAlternates(locale, "/verify-email"),
    robots: { index: false, follow: true },
  };
}

export default async function VerifyEmailPage({
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

  const usable = typeof token === "string" && token.length >= 10;

  return (
    <AuthShell
      title={t("verify.title")}
      description={t("verify.description")}
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
        <VerifyEmailStatus token={token} />
      ) : (
        <div
          className="rounded-lg border border-border bg-surface p-6 shadow-sm"
          role="status"
        >
          <p className="text-sm leading-relaxed text-ink">
            {t("verify.missingToken")}
          </p>
        </div>
      )}
    </AuthShell>
  );
}
