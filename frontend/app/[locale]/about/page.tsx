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
  return {
    title: t("title"),
    description: t("description"),
    alternates: localeAlternates(locale, "/about"),
  };
}

/** Blank lines in a message become paragraphs. */
function Prose({ text, className }: { text: string; className?: string }) {
  return (
    <>
      {text.split(/\n{2,}/).map((para) => (
        <p key={para} className={className ?? "mt-4 leading-relaxed text-ink"}>
          {para}
        </p>
      ))}
    </>
  );
}

export default async function AboutPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("about");

  // Identity first, then what gets published. Both are claims about the
  // organisation, so they sit above the method rather than beside it.
  const claims = [
    { title: t("whatTitle"), text: t("whatText") },
    { title: t("publishTitle"), text: t("publishText") },
  ];
  const principles = [
    { title: t("philosophyTitle"), text: t("philosophyText") },
    { title: t("focusTitle"), text: t("focusText") },
  ];

  return (
    <main>
      {/* The graphic behind the heading is a measurement lattice, not a chart:
          anything that read as a price series here would be decoration posing
          as evidence, on the one page where a reader is deciding whether to
          trust the evidence at all. */}
      <section className="relative overflow-hidden border-b border-border">
        <svg
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 h-full w-full text-brand/[0.07]"
          preserveAspectRatio="xMidYMid slice"
          viewBox="0 0 1200 400"
        >
          {Array.from({ length: 25 }, (_, i) => (
            <line
              key={`v${i}`}
              x1={i * 50}
              y1="0"
              x2={i * 50}
              y2="400"
              stroke="currentColor"
              strokeWidth="1"
            />
          ))}
          {Array.from({ length: 9 }, (_, i) => (
            <line
              key={`h${i}`}
              x1="0"
              y1={i * 50}
              x2="1200"
              y2={i * 50}
              stroke="currentColor"
              strokeWidth="1"
            />
          ))}
        </svg>

        <div className="container-qp relative section-pad">
          <h1 className="title-xl max-w-4xl">{t("title")}</h1>
          <p className="mt-7 max-w-3xl text-lg leading-relaxed text-ink">
            {t("lead")}
          </p>
        </div>
      </section>

      <section className="container-qp section-pad">
        <div className="grid gap-x-16 gap-y-12 desk:grid-cols-2">
          {claims.map((c, i) => (
            <Reveal key={c.title} index={i}>
              <h2 className="title-md">{c.title}</h2>
              <Prose text={c.text} />
            </Reveal>
          ))}
        </div>

        {/* The person behind the work, placed where a reader has just learned
            what the group is and naturally asks who is doing it.
            Deliberately no photograph: the site uses abstract marks rather
            than staff imagery, and a monogram keeps that rule while still
            giving the block a face. The dark panel is the only one on an
            otherwise light page, which is what makes it register. */}
        <Reveal className="relative mt-24 overflow-hidden rounded-lg bg-foreground text-background shadow-lg">
          <svg
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 h-full w-full text-white/[0.05]"
            preserveAspectRatio="none"
            viewBox="0 0 600 200"
          >
            {Array.from({ length: 13 }, (_, i) => (
              <line
                key={`fv${i}`}
                x1={i * 50}
                y1="0"
                x2={i * 50}
                y2="200"
                stroke="currentColor"
                strokeWidth="1"
              />
            ))}
            {Array.from({ length: 5 }, (_, i) => (
              <line
                key={`fh${i}`}
                x1="0"
                y1={i * 50}
                x2="600"
                y2={i * 50}
                stroke="currentColor"
                strokeWidth="1"
              />
            ))}
          </svg>

          <div className="relative flex flex-col gap-7 p-8 sm:flex-row sm:items-center sm:gap-10 desk:p-12">
            <span
              aria-hidden="true"
              className="figure flex size-20 shrink-0 items-center justify-center rounded-md border border-brand/50 bg-brand/15 text-lg font-semibold tracking-[0.12em] text-white desk:size-24 desk:text-xl"
            >
              PMH
            </span>

            <div className="min-w-0">
              <p className="title-md text-background">{t("founder.name")}</p>

              {/* Rendered as separated items rather than a literal "A | B | C".
                  Same information, but the divider is a hairline the eye reads
                  as structure instead of a character it has to parse. */}
              <ul className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                {(t.raw("founder.roles") as string[]).map((role, i) => (
                  <li key={role} className="flex items-center gap-3">
                    {i > 0 && (
                      <span
                        aria-hidden="true"
                        className="h-3 w-px bg-white/25"
                      />
                    )}
                    <span className="text-[13px] font-medium tracking-[0.04em] text-brand-soft">
                      {role}
                    </span>
                  </li>
                ))}
              </ul>

              <span
                aria-hidden="true"
                className="mt-6 block h-px w-16 bg-brand"
              />

              {/* First person, and larger than the labels above it: this is
                  the one thing on the page only he can say, and it is the
                  reason the rest of the site is built the way it is. */}
              <p className="mt-5 max-w-2xl text-[15px] leading-[1.75] text-white/80 desk:text-base">
                {t("founder.bio")}
              </p>
            </div>
          </div>
        </Reveal>

        <Reveal className="mt-24 rounded-lg border border-border bg-surface/60 p-7 shadow-sm desk:p-10">
          <h2 className="title-md">{t("stageTitle")}</h2>
          <Prose
            text={t("stageText")}
            className="mt-4 max-w-3xl leading-relaxed text-ink"
          />
        </Reveal>

        <div className="mt-24 grid gap-x-16 gap-y-12 desk:grid-cols-2">
          {principles.map((p, i) => (
            <Reveal key={p.title} index={i}>
              <h2 className="title-md">{p.title}</h2>
              <Prose text={p.text} />
            </Reveal>
          ))}
        </div>

        <Reveal className="mt-24 border-t border-border pt-12">
          <h2 className="title-md">{t("developingTitle")}</h2>
          <ul className="mt-7 grid gap-4 desk:grid-cols-2">
            {(t.raw("developingItems") as string[]).map((item) => (
              <li key={item} className="flex gap-3 leading-relaxed text-ink">
                <span aria-hidden="true" className="mt-2.5 h-1 w-4 shrink-0 bg-brand" />
                {item}
              </li>
            ))}
          </ul>
        </Reveal>

        <p className="mt-16 max-w-3xl border-l-2 border-brand pl-4 text-sm leading-relaxed text-dim">
          {t("note")}
        </p>

        {/* The enquiry type matches what this page now asks for: research
            collaboration, not an investor introduction. */}
        <Reveal className="mt-20 rounded-lg border border-brand/40 bg-brand-soft p-8 desk:p-10">
          <h2 className="title-md">{t("ctaTitle")}</h2>
          <p className="mt-3 max-w-2xl leading-relaxed text-ink">
            {t("ctaText")}
          </p>
          <Button asChild className="mt-7">
            <Link href="/contact?type=research_collaboration">
              {t("ctaButton")}
            </Link>
          </Button>
        </Reveal>
      </section>
    </main>
  );
}
