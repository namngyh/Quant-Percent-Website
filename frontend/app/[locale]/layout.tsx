import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Be_Vietnam_Pro, Geist, IBM_Plex_Mono } from "next/font/google";
import { routing } from "@/i18n/routing";
import { Header } from "@/components/layout/header";
import { Footer } from "@/components/layout/footer";
import { AuthProvider } from "@/lib/auth/auth-context";
import { SiteIntro } from "@/components/intro/site-intro";
import { localeAlternates, SITE_URL } from "@/lib/seo";
import "../globals.css";

const beVietnamPro = Be_Vietnam_Pro({
  variable: "--font-be-vietnam",
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
});

const geist = Geist({
  variable: "--font-geist",
  subsets: ["latin"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600"],
});

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta" });
  return {
    metadataBase: new URL(SITE_URL),
    title: {
      default: t("home.title"),
      template: `%s | ${t("siteName")}`,
    },
    description: t("home.description"),
    alternates: localeAlternates(locale, "/"),
    openGraph: {
      siteName: t("siteName"),
      locale: locale === "vi" ? "vi_VN" : "en_US",
      type: "website",
    },
  };
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);

  return (
    /*
      `suppressHydrationWarning` is scoped to this one element's attributes and
      is required, not cosmetic.

      The opening sequence has to decide whether to play before the first paint
      — that is the whole point of it — so an inline script in <head> reads
      sessionStorage and stamps `data-intro="play"` on <html>. The server cannot
      know what is in a visitor's sessionStorage, so its HTML never carries the
      attribute and React finds one that it did not render. Without this, every
      first page of every session logged a hydration mismatch, which in turn
      would hide any real mismatch appearing later.

      It suppresses warnings for this element only, not for its subtree, so a
      genuine mismatch anywhere inside the page is still reported.
    */
    <html
      lang={locale}
      suppressHydrationWarning
      className={`${beVietnamPro.variable} ${geist.variable} ${plexMono.variable} antialiased`}
    >
      <body className="flex min-h-dvh flex-col">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "Organization",
              name: "Quant Percent",
              url: SITE_URL,
              logo: `${SITE_URL}/icon.svg`,
              description:
                locale === "vi"
                  ? "Nghiên cứu thị trường tài chính Việt Nam bằng dữ liệu."
                  : "A quantitative research organization for Vietnam's financial markets.",
            }),
          }}
        />
        <NextIntlClientProvider>
          <AuthProvider>
            <SiteIntro />
            <Header />
            <div className="flex-1">{children}</div>
            <Footer />
          </AuthProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
