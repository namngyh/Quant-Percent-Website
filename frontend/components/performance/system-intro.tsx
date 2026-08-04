import { getLocale, getTranslations } from "next-intl/server";
import { ArrowRight } from "lucide-react";
import { getModel } from "@/config/models";
import { strategiesForSystem } from "@/config/strategies";
import { Link } from "@/i18n/navigation";
import { StatusBadge } from "@/components/market/badges";
import { Sparkline } from "@/components/sparkline";
import { getSeries } from "@/lib/performance/reports";

/**
 * Introduces the system whose validation runs are listed below, so the
 * reports read as "here is Model Modus and how it performed" rather than
 * three unexplained cards.
 */
export async function SystemIntro({ systemSlug }: { systemSlug: string }) {
  const model = getModel(systemSlug);
  if (!model) return null;

  const locale = (await getLocale()) as "vi" | "en";
  const t = await getTranslations("performance.system");

  const reports = strategiesForSystem(systemSlug);
  const periods = reports.flatMap((r) => [r.periodStart, r.periodEnd]).sort();

  // Real equity curve of the walk-forward-adjacent run, as a quiet visual
  const curve = getSeries("vn30f1m-multiseed-test")?.points ?? [];

  const facts = [
    { label: t("market"), value: model.markets.join(", ") },
    { label: t("timeframe"), value: locale === "vi" ? "5 phút" : "5 minutes" },
    {
      label: t("evaluated"),
      value: `${periods[0].slice(0, 4)}–${periods[periods.length - 1].slice(0, 4)}`,
    },
    { label: t("runs"), value: String(reports.length) },
  ];

  return (
    <section className="mt-10 overflow-hidden rounded-lg border border-border shadow-sm">
      <div className="grid gap-px bg-border desk:grid-cols-[1.35fr_1fr]">
        <div className="bg-background p-7">
          <p className="eyebrow">{t("eyebrow")}</p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
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
            {t("reportsLead", { count: reports.length })}
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

          {curve.length > 0 && (
            <div className="mt-6 text-brand">
              <Sparkline
                values={curve.map((p) => p.equity_pct)}
                width={320}
                height={56}
                className="h-14 w-full"
                label={t("curveCaption")}
              />
              <p className="mt-2 text-[11px] leading-snug text-dim">
                {t("curveCaption")}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
