import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { getPublishedModel } from "@/lib/models/catalogue";
import { DisclosureBanner } from "@/components/layout/disclosure-banner";
import { StatusBadge } from "@/components/market/badges";
import { MemberGate } from "@/components/models/member-gate";
import { Architecture } from "@/components/models/architecture";
import { ValidatedPerformance } from "@/components/models/validated-performance";
import { ResearchEvidence } from "@/components/models/research-evidence";
import {
  CurrentOutput,
  ForecastChart,
  HistoricalForecasts,
} from "@/components/models/model-output";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}): Promise<Metadata> {
  const { locale, slug } = await params;
  const published = await getPublishedModel(slug);
  if (!published) return {};
  const { model } = published;
  const l = locale as "vi" | "en";
  return { title: model.name, description: model.tagline[l] };
}

/** Model detail page (§9.2). */
export default async function ModelDetailPage({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  setRequestLocale(locale);
  const published = await getPublishedModel(slug);
  if (!published) notFound();
  const { model, research } = published;
  const l = locale as "vi" | "en";
  const t = await getTranslations("models");
  const tc = await getTranslations("common");
  const symbol = model.markets[0];

  const overviewRows: { label: string; value: React.ReactNode }[] = [
    { label: t("detail.problem"), value: t(`categories.${model.category}`) },
    { label: t("detail.assets"), value: model.markets.join(", ") },
    {
      label: t("detail.horizons"),
      value: model.horizons
        .map((h) =>
          research
            ? `${h} ${l === "vi" ? "phiên" : h === 1 ? "session" : "sessions"}`
            : tc("horizonDays", { count: h })
        )
        .join(" · "),
    },
    { label: t("detail.version"), value: `v${model.version}` },
  ];

  const description = model.description;
  const descriptionRows = [
    { label: t("detail.objective"), value: description.objective[l] },
    { label: t("detail.intuition"), value: description.intuition[l] },
    { label: t("detail.modelType"), value: description.modelType[l] },
    { label: t("detail.validation"), value: description.validation[l] },
  ];

  return (
    <main>
      <DisclosureBanner variant="legal" />
      <div className="container-qp py-12 desk:py-16">
        {/* Overview (§9.2) */}
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div>
            <p className="figure text-xs uppercase tracking-[0.08em] text-dim">
              {model.code}
            </p>
            <h1 className="title-lg mt-2">{model.name}</h1>
            <p className="mt-4 max-w-2xl text-lg text-ink">{model.tagline[l]}</p>
          </div>
          <StatusBadge status={model.status} />
        </div>

        <dl className="mt-8 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4">
          {overviewRows.map((row) => (
            <div key={row.label} className="bg-background p-5">
              <dt className="text-[11px] uppercase tracking-[0.08em] text-dim">
                {row.label}
              </dt>
              <dd className="mt-1.5 text-sm font-medium">{row.value}</dd>
            </div>
          ))}
        </dl>

        <MemberGate locked={model.access === "members"} slug={model.slug}>
        <div className="mt-14 space-y-14">
          {model.show_forecast && (
            <>
              <CurrentOutput modelSlug={model.slug} symbol={symbol} />
              <ForecastChart modelSlug={model.slug} symbol={symbol} />
              <HistoricalForecasts modelSlug={model.slug} symbol={symbol} />
            </>
          )}

          {research ? (
            <ResearchEvidence profile={research} locale={l} />
          ) : (
            <Architecture model={model} />
          )}

          {model.show_performance && <ValidatedPerformance systemSlug={model.slug} />}

          {/* Description includes objectives and limits only, with no internals. */}
          {!research && <section>
            <h2 className="title-md">{t("detail.description")}</h2>
            <dl className="mt-6 max-w-3xl space-y-6">
              {descriptionRows.map((row) => (
                <div key={row.label}>
                  <dt className="text-sm font-semibold">{row.label}</dt>
                  <dd className="mt-1.5 leading-relaxed text-ink">{row.value}</dd>
                </div>
              ))}
              <div>
                <dt className="text-sm font-semibold">{t("detail.outputs")}</dt>
                <dd className="mt-1.5">
                  <ul className="space-y-1.5 text-ink">
                    {description.outputs[l].map((o) => (
                      <li key={o} className="flex gap-2.5">
                        <span aria-hidden="true" className="text-brand">
                          •
                        </span>
                        {o}
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
              <div>
                <dt className="text-sm font-semibold">
                  {t("detail.limitations")}
                </dt>
                <dd className="mt-1.5">
                  <ul className="space-y-1.5 text-ink">
                    {description.limitations[l].map((o) => (
                      <li key={o} className="flex gap-2.5">
                        <span aria-hidden="true" className="text-signal-strong">
                          •
                        </span>
                        {o}
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            </dl>
            <p className="mt-8 max-w-3xl border-l-2 border-lightgray pl-4 text-sm text-dim">
              {t("detail.disclosureNote")}
            </p>
          </section>}
        </div>
        </MemberGate>
      </div>
    </main>
  );
}
