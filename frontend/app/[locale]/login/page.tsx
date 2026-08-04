import type { Metadata } from "next";
import { Suspense } from "react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/login-form";
import { SkeletonLoader } from "@/components/states/skeleton-loader";
import { localeAlternates } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.login" });
  return {
    title: t("title"),
    description: t("description"),
    alternates: localeAlternates(locale, "/login"),
    robots: { index: false, follow: true },
  };
}

export default async function LoginPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("auth");

  return (
    <AuthShell
      title={t("login.title")}
      description={t("login.description")}
      footer={
        <p>
          {t("login.noAccount")}{" "}
          <Link
            href="/register"
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            {t("login.toRegister")}
          </Link>
        </p>
      }
    >
      <Suspense fallback={<SkeletonLoader rows={4} />}>
        <LoginForm />
      </Suspense>
    </AuthShell>
  );
}
