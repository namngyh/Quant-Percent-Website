import type { Metadata } from "next";
import { Suspense } from "react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { AuthShell } from "@/components/auth/auth-shell";
import { RegisterForm } from "@/components/auth/register-form";
import { SkeletonLoader } from "@/components/states/skeleton-loader";
import { localeAlternates } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.register" });
  return {
    title: t("title"),
    description: t("description"),
    alternates: localeAlternates(locale, "/register"),
    robots: { index: false, follow: true },
  };
}

export default async function RegisterPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("auth");

  return (
    <AuthShell
      title={t("register.title")}
      description={t("register.description")}
      footer={
        <p>
          {t("register.hasAccount")}{" "}
          <Link
            href="/login"
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            {t("register.toLogin")}
          </Link>
        </p>
      }
    >
      <Suspense fallback={<SkeletonLoader rows={6} />}>
        <RegisterForm />
      </Suspense>
    </AuthShell>
  );
}
