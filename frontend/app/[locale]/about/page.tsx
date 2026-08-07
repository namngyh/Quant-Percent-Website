import type { Metadata } from "next";
import { localeAlternates } from "@/lib/seo";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Reveal } from "@/components/reveal";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta.about" });
  return { title: t("title"), description: t("description"), alternates: localeAlternates(locale, "/about") };
}

export default async function AboutPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("about");

  // "Lý do thành lập" is now the lead line under the title rather than a
  // block of its own, and "Quy trình nghiên cứu" is replaced by what the
  // reports actually contain.
  const sections = [
    { title: t("whatTitle"), text: t("whatText") },
    { title: t("publishTitle"), text: t("publishText") },
    { title: t("philosophyTitle"), text: t("philosophyText") },
    { title: t("focusTitle"), text: t("focusText") },
    { title: t("visionTitle"), text: t("visionText") },
  ];

  return (
    <main>
      <section className="container-qp section-pad">
        <h1 className="title-xl max-w-3xl">{t("title")}</h1>
        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-ink">
          {t("lead")}
        </p>
      </section>

      {/* Abstract data graphic instead of office/staff imagery (§12) */}
      <div aria-hidden="true" className="border-y border-border bg-surface">
        <svg
          viewBox="0 0 1200 160"
          className="h-28 w-full desk:h-40"
          preserveAspectRatio="none"
        >
          {Array.from({ length: 40 }, (_, i) => (
            <line
              key={i}
              x1={i * 30}
              y1={160}
              x2={i * 30}
              y2={160 - (40 + Math.abs(Math.sin(i * 1.7)) * 100)}
              stroke={i % 5 === 0 ? "#ad7519" : "#cbd5e1"}
              strokeWidth="1.5"
            />
          ))}
          <polyline
            points={Array.from({ length: 41 }, (_, i) => `${i * 30},${110 - Math.sin(i * 0.55) * 32 - i * 0.6}`).join(" ")}
            fill="none"
            stroke="#3a72c4"
            strokeWidth="2"
          />
        </svg>
      </div>

      <section className="container-qp section-pad">
        {/* Operating stage, given its own panel rather than a line inside
            another block: it is the first thing an investor checks. */}
        <div className="mb-16 rounded-lg border border-border bg-surface/60 p-7 shadow-sm desk:p-9">
          <h2 className="title-md">{t("stageTitle")}</h2>
          {t("stageText")
            .split(/\n{2,}/)
            .map((para) => (
              <p key={para} className="mt-4 max-w-3xl leading-relaxed text-ink">
                {para}
              </p>
            ))}
        </div>

        <div className="grid gap-x-16 gap-y-14 desk:grid-cols-2">
          {sections.map((s, i) => (
            <Reveal key={s.title} index={i}>
              <h2 className="title-md">{s.title}</h2>
              {/* Blank lines in the message become paragraphs. A single
                  block of prose collapses a three-beat statement into a
                  wall of text. */}
              {s.text.split(/\n{2,}/).map((para) => (
                <p key={para} className="mt-4 leading-relaxed text-ink">
                  {para}
                </p>
              ))}
            </Reveal>
          ))}
        </div>

        <Reveal className="mt-20 border-t border-border pt-12">
          <h2 className="title-md">{t("developingTitle")}</h2>
          <ul className="mt-6 grid gap-3 desk:grid-cols-2">
            {(t.raw("developingItems") as string[]).map((item) => (
              <li key={item} className="flex gap-3 text-ink">
                <span className="text-brand" aria-hidden="true">
                  •
                </span>
                {item}
              </li>
            ))}
          </ul>
        </Reveal>

        <p className="mt-16 max-w-3xl border-l-2 border-brand pl-4 text-sm text-dim">
          {t("note")}
        </p>

        {/* The page previously ended without telling a reader what to do
            next. The contact form already carries an enquiry type for this. */}
        <Reveal className="mt-16 rounded-lg border border-brand/40 bg-brand-soft p-8 desk:p-10">
          <h2 className="title-md">{t("ctaTitle")}</h2>
          <p className="mt-3 max-w-2xl leading-relaxed text-ink">
            {t("ctaText")}
          </p>
          <Button asChild className="mt-7">
            <Link href="/contact?type=investor_interest">{t("ctaButton")}</Link>
          </Button>
        </Reveal>
      </section>
    </main>
  );
}
