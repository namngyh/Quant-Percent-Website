import { getTranslations } from "next-intl/server";
import { ArrowRight } from "lucide-react";
import { strategyCount } from "@/config/strategies";
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
    { value: strategyCount(), label: t("strategies") },
    { value: 4, label: t("horizons") },
  ];
  return (
    <section className="container-qp section-pad">
      <p className="eyebrow">{t("eyebrow")}</p>
      <h2 className="title-lg mt-4 max-w-2xl">{t("title")}</h2>
      <div className="mt-12 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-3">
        {figures.map((f, i) => (
          <div key={f.label} className="bg-background p-8">
            <Reveal index={i}>
              <p
                className={`figure text-5xl font-medium ${
                  i === 1 ? "text-signal-strong" : "text-brand"
                }`}
              >
                <MetricCounter value={f.value} />
              </p>
              <p className="mt-3 text-sm text-dim">{f.label}</p>
            </Reveal>
          </div>
        ))}
      </div>
      <div className="mt-6 grid gap-4 text-sm text-ink desk:grid-cols-2">
        <p className="flex gap-3">
          <span aria-hidden="true" className="text-brand">•</span>
          {t("validation")}
        </p>
        <p className="flex gap-3">
          <span aria-hidden="true" className="text-brand">•</span>
          {t("focus")}
        </p>
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
