import { getTranslations } from "next-intl/server";
import { ArrowRight } from "lucide-react";
import {
  getPublishedModels,
  usesDatabaseApi,
} from "@/lib/models/catalogue";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Reveal } from "@/components/reveal";
import { MetricCounter } from "@/components/home/metric-counter";
import { ModelCard } from "@/components/models/model-card";

/** "Quant Percent by the numbers" with counts derived from config. */
export async function ByTheNumbers() {
  const t = await getTranslations("home.numbers");
  const models = await getPublishedModels();
  const figures = [
    { value: models.length, label: t("models") },
    // Years of Model Modus's published test, not a count of reports: the
    // performance page now publishes one run covering 2024-2026, so "3
    // reports" described a page that no longer exists.
    { value: 3, label: t("strategies") },
    { value: 4, label: t("horizons") },
  ];
  return (
    /*
      Heading and figures sit side by side rather than stacked, and the
      figures are separated by rules instead of boxed in a grid of equal
      cells. Three identical boxes gave every number the same weight and
      read as filler; a row of large numerals against a short heading reads
      as a statement.
    */
    <section className="container-qp section-pad">
      <div className="grid gap-12 desk:grid-cols-[0.9fr_1.1fr] desk:gap-16">
        <div className="desk:sticky desk:top-24 desk:self-start">
          <p className="eyebrow">{t("eyebrow")}</p>
          <h2 className="title-lg mt-4">{t("title")}</h2>
          <ul className="mt-8 space-y-3 text-sm text-ink">
            {[t("validation"), t("focus")].map((line) => (
              <li key={line} className="flex gap-3">
                <span
                  aria-hidden="true"
                  className="mt-2 h-px w-5 shrink-0 bg-brand"
                />
                {line}
              </li>
            ))}
          </ul>
        </div>

        <dl className="divide-y divide-border border-y border-border">
          {figures.map((f, i) => (
            <Reveal key={f.label} index={i}>
              <div className="flex items-baseline gap-6 py-7 desk:gap-10">
                <dd className="figure w-24 shrink-0 text-right text-5xl font-medium leading-none text-brand desk:w-32 desk:text-6xl">
                  <MetricCounter value={f.value} />
                </dd>
                <dt className="text-sm leading-relaxed text-ink">{f.label}</dt>
              </div>
            </Reveal>
          ))}
        </dl>
      </div>
    </section>
  );
}

/** Research systems grid (§7.5). */
export async function ResearchSystems() {
  const t = await getTranslations("home.systems");
  const tc = await getTranslations("common");
  const models = (await getPublishedModels()).filter((model) => model.featured);
  return (
    <section className="border-t border-brand/20 bg-surface">
      <div className="container-qp section-pad">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <p className="eyebrow">{t("eyebrow")}</p>
            <h2 className="title-lg mt-4">{t("title")}</h2>
            <p className="mt-4 max-w-2xl text-ink">{t("description")}</p>
          </div>
          <Link
            href="/models"
            className="arrow-link inline-flex items-center gap-2 text-[13px] font-medium underline-offset-4 hover:underline"
          >
            {t("viewAllModels")} <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
        <div className="mt-12 grid gap-5 sm:grid-cols-2 desk:grid-cols-4">
          {models.map((m, i) => (
            <Reveal key={m.slug} index={i} className="h-full [&>article]:h-full">
              <ModelCard model={m} />
            </Reveal>
          ))}
        </div>
        {!usesDatabaseApi() && (
          <p className="mt-6 text-xs text-dim">{tc("mockNotice")}</p>
        )}
      </div>
    </section>
  );
}

/** Closing CTA without "invest now" style calls. */
export async function HomeCta() {
  const t = await getTranslations("home.cta");
  return (
    <section className="border-t border-brand/20 bg-brand-soft/40">
      <div className="container-qp section-pad text-center">
        <h2 className="title-lg mx-auto max-w-3xl">{t("title")}</h2>
        <div className="mt-10 flex flex-wrap justify-center gap-3">
          <Button asChild>
            <Link href="/contact">{t("contact")}</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/contact?type=investor_interest">{t("register")}</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}
