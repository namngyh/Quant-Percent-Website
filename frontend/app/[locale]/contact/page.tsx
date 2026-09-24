import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ContactForm } from "@/components/contact/contact-form";
import { FacebookIcon } from "@/components/social/facebook-icon";
import { FACEBOOK_URL } from "@/lib/social";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.contact" });
  return { title: t("title"), description: t("description"), alternates: localeAlternates(locale, "/contact") };
}

const INQUIRY_TYPES = [
  "investor_interest",
  "research_collaboration",
  "data_partnership",
  "technology_partnership",
  "general",
] as const;

export default async function ContactPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ type?: string }>;
}) {
  const { locale } = await params;
  const { type } = await searchParams;
  setRequestLocale(locale);
  const t = await getTranslations("contact");
  const tFooter = await getTranslations("footer");
  const defaultInquiry = (INQUIRY_TYPES as readonly string[]).includes(type ?? "")
    ? (type as (typeof INQUIRY_TYPES)[number])
    : undefined;

  return (
    <main className="container-qp section-pad">
      <div className="grid gap-14 desk:grid-cols-[1fr_1.3fr]">
        <div>
          <h1 className="title-lg">{t("title")}</h1>
          <p className="mt-5 max-w-md text-ink">{t("description")}</p>
          <p className="mt-8 max-w-md border-l-2 border-lightgray pl-4 text-sm text-dim">
            {t("registerNote")}
          </p>
          <div className="mt-8 flex flex-col gap-3 text-sm">
            <a
              href={`mailto:${tFooter("contactEmail")}`}
              className="text-brand underline-offset-4 hover:underline"
            >
              {tFooter("contactEmail")}
            </a>
            <a
              href={FACEBOOK_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={tFooter("facebookLabel")}
              className="inline-flex items-center gap-2 text-brand underline-offset-4 hover:underline"
            >
              <FacebookIcon className="size-4" />
              {tFooter("facebook")}
            </a>
          </div>
        </div>
        <ContactForm defaultInquiry={defaultInquiry} />
      </div>
    </main>
  );
}
