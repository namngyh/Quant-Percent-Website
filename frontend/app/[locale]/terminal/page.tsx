import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { AuthShell } from "@/components/auth/auth-shell";
import { TerminalLauncher } from "@/components/terminal/terminal-launcher";
import { localeAlternates } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "terminalPage" });
  return {
    title: t("title"),
    description: t("description"),
    alternates: localeAlternates(locale, "/terminal"),
    robots: { index: false, follow: true },
  };
}

/**
 * The front door to terminal.quantpercent.com.
 *
 * The Terminal has no accounts of its own: the proxy asks the website API
 * about every request to it and sends a visitor who is not let in back here.
 * This page then does whichever of sign in, confirm email or "go" applies.
 */
export default async function TerminalPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ from?: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const { from } = await searchParams;
  const t = await getTranslations("terminalPage");

  return (
    <AuthShell title={t("title")} description={t("description")}>
      <TerminalLauncher bouncedBack={from === "terminal"} />
    </AuthShell>
  );
}
