import { getLocale, getTranslations } from "next-intl/server";
import { ArrowRight } from "lucide-react";
import { getModel } from "@/config/models";
import { FEATURED_STRATEGY, strategiesForSystem } from "@/config/strategies";
import { Link } from "@/i18n/navigation";
import { StatusBadge } from "@/components/market/badges";
import { ModusMascot } from "@/components/modus-mascot";

/**
 * Introduces the system whose validation runs are listed below, so the
 * reports read as "here is Model Modus and how it performed" rather than
 * three unexplained cards.
 */
/** The run this page publishes. */
const PUBLISHED = FEATURED_STRATEGY;

export async function SystemIntro({ systemSlug }: { systemSlug: string }) {
  const model = getModel(systemSlug);
  if (!model) return null;

  const locale = (await getLocale()) as "vi" | "en";
  const t = await getTranslations("performance.system");

  // The page publishes one run: the frozen brain scored over 2024-2026.
  const report = strategiesForSystem(systemSlug).find(
    (r) => r.slug === PUBLISHED
  );

  const facts = [
    { label: t("market"), value: model.markets.join(", ") },
    { label: t("timeframe"), value: locale === "vi" ? "5 phút" : "5 minutes" },
    {
      label: t("evaluated"),
      value: report
        ? `${report.periodStart.slice(0, 4)}–${report.periodEnd.slice(0, 4)}`
        : "—",
    },
    { label: t("method"), value: t("methodValue") },
  ];

  return (
    <section className="mt-10 overflow-hidden rounded-lg border border-border shadow-sm">
      <div className="grid gap-px bg-border desk:grid-cols-[1.35fr_1fr]">
        <div className="bg-background p-7">
          <p className="eyebrow">{t("eyebrow")}</p>
          {/* Mascot sits with the name rather than floating on its own, so it
              reads as this system's mark and not as generic decoration. */}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <ModusMascot className="size-14 shrink-0 rounded-xl" />
            <h2 className="title-md">{model.name}</h2>
            <span className="figure text-[11px] uppercase tracking-[0.08em] text-dim">
              {model.code} · v{model.version}
            </span>
            <StatusBadge status={model.status} />
          </div>

          <p className="mt-4 max-w-2xl leading-relaxed text-ink">
            {model.tagline[locale]}
          </p>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-dim">
            {t("reportsLead")}
          </p>

          <Link
            href={`/models/${model.slug}`}
            className="arrow-link mt-6 inline-flex items-center gap-2 text-[13px] font-medium text-brand underline-offset-4 hover:text-brand-strong hover:underline"
          >
            {t("learnMore", { name: model.name })}
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>

        <div className="flex flex-col justify-between bg-background p-7">
          <dl className="grid grid-cols-2 gap-5">
            {facts.map((f) => (
              <div key={f.label}>
                <dt className="text-[11px] uppercase tracking-[0.06em] text-dim">
                  {f.label}
                </dt>
                <dd className="figure mt-1.5 text-lg">{f.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}
