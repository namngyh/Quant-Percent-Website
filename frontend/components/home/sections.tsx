import { getTranslations } from "next-intl/server";
import { ArrowRight } from "lucide-react";
import {
  getPublishedModels,
  usesDatabaseApi,
} from "@/lib/models/catalogue";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Reveal } from "@/components/reveal";
import { ModelCard } from "@/components/models/model-card";

/**
 * Research systems grid (§7.5).
 *
 * The cards are the compact variant. The full card carries a version string, a
 * status badge, a forecast strip and a four-row specification table — which is
 * what a reader comparing models on /models needs, and four of them side by
 * side on a homepage is a wall of specification for someone who does not yet
 * know what any of these are. Here each card is a name, a sentence and a way
 * in; the detail is one click away and no longer competes with the sentence.
 */
export async function ResearchSystems() {
  const t = await getTranslations("home.systems");
  const tc = await getTranslations("common");
  const models = (await getPublishedModels()).filter((model) => model.featured);
  return (
    <section className="relative overflow-hidden border-b border-border bg-background">
      <div aria-hidden="true" className="numeral-clip">
        <span className="section-numeral">03</span>
      </div>
      <div className="container-qp section-pad relative">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <p className="eyebrow">
              <span className="tick text-accent/60">03</span>
              {t("eyebrow")}
            </p>
            <h2 className="title-lg mt-5">{t("title")}</h2>
          </div>
          <Link
            href="/models"
            className="arrow-link inline-flex items-center gap-2 text-sm font-medium text-brand underline-offset-4 hover:underline"
          >
            {t("viewAllModels")} <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
        <div className="mt-14 grid gap-5 sm:grid-cols-2 desk:grid-cols-4">
          {models.map((m, i) => (
            <Reveal key={m.slug} index={i} className="h-full [&>article]:h-full">
              <ModelCard model={m} compact />
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
    /* Tinted, closing the alternation that the dark Modus band anchors. */
    <section className="tint">
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
