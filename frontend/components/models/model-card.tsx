import { getLocale, getTranslations } from "next-intl/server";
import type { ModelCardData } from "@/config/models";
import { Link } from "@/i18n/navigation";
import { StatusBadge } from "@/components/market/badges";
import { MetricStrip } from "@/components/models/metric-strip";
import { Sparkline } from "@/components/sparkline";
import { fmtDate } from "@/lib/format";

/**
 * Model card fed by the database in production and the fixture in mock mode.
 *
 * `compact` drops everything below the tagline — the forecast strip and the
 * market/category/output/last-run table. Those answer "which of these should I
 * open", which is the question on /models and not the question on a homepage,
 * where four full cards read as a specification sheet before a visitor knows
 * what a model here even is.
 */
export async function ModelCard({
  model,
  compact = false,
}: {
  model: ModelCardData;
  compact?: boolean;
}) {
  const locale = (await getLocale()) as "vi" | "en";
  const t = await getTranslations("models");
  const tc = await getTranslations("common");

  // The date a reader wants here is "when did this model last produce
  // something", and only quant.model_forecasts can answer it. The row used to
  // fall back to `updatedAt` — the day the catalogue entry was edited — and
  // then to `lastTradingDay()`, a date computed from the calendar. Eleven of
  // the twelve models have never published output, so that fallback printed a
  // fresh-looking date under an "Updated" label for models that had never run.
  const lastOutput = model.lastOutputAt ?? null;

  // A scale is only meaningful when there is exactly one value per horizon.
  // Anything else falls back to the trend line rather than inventing labels.
  const scale =
    model.sparkline &&
    model.sparklineScale &&
    model.sparkline.length === model.horizons.length
      ? model.sparklineScale
      : undefined;
  const bars = scale
    ? model.horizons.map((h, i) => ({
        label: String(h),
        value: model.sparkline![i],
      }))
    : undefined;

  return (
    <article className="glow-card accent-top flex min-w-0 flex-col overflow-hidden p-7">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
        <div className="min-w-0">
          <h3 className="whitespace-nowrap text-lg font-medium leading-tight tracking-[-0.015em]">
            {model.name}
          </h3>
          {/* An internal code and a version number tell a visitor nothing
              until they have decided to read about the model. */}
          {!compact && (
            <p className="figure mt-1 text-[11px] uppercase tracking-[0.08em] text-dim">
              {model.code} · v{model.version}
            </p>
          )}
        </div>
        <StatusBadge
          status={model.status}
          compact
        />
      </div>

      <p
        className={
          compact
            ? "mt-4 flex-1 text-sm leading-relaxed text-dim"
            : "mt-4 text-sm leading-relaxed text-ink"
        }
      >
        {model.tagline[locale]}
      </p>

      {/*
        The compact card gets the trend line but not the labelled bars.
        Stripping it entirely left a card that was a name, a sentence and a
        link, with most of its height empty — which is what made the row look
        thin. A line is texture and information at the same time, where a
        decorative shape would only have been the first.
      */}
      {compact && model.sparkline && (
        <div className="mt-5 text-accent/70">
          <Sparkline
            values={model.sparkline}
            width={280}
            height={34}
            className="h-9 w-full"
          />
        </div>
      )}

      {!compact && model.sparkline && (
        <div className="mt-5">
          {model.sparklineLabel && (
            <p className="mb-2.5 text-[11px] text-dim">
              {model.sparklineLabel[locale]}
            </p>
          )}
          {/* One value per horizon is a comparison, not a trend, so it is
              drawn as labelled bars on a stated scale. A sequence over time
              is a trend and keeps the line. */}
          {scale && bars ? (
            <MetricStrip
              bars={bars}
              suffix={scale.suffix}
              min={scale.min}
              max={scale.max}
              reference={scale.reference}
              referenceLabel={scale.referenceLabel?.[locale]}
              locale={locale}
            />
          ) : (
            <div className="text-brand">
              <Sparkline
                values={model.sparkline}
                width={280}
                height={48}
                className="h-12 w-full"
              />
              <p className="figure mt-1.5 flex justify-between text-[10px] text-dim">
                <span>
                  {t("card.rangeLow")}{" "}
                  {Math.min(...model.sparkline).toLocaleString(locale, {
                    maximumFractionDigits: 1,
                  })}
                </span>
                <span>
                  {t("card.rangeHigh")}{" "}
                  {Math.max(...model.sparkline).toLocaleString(locale, {
                    maximumFractionDigits: 1,
                  })}
                </span>
              </p>
            </div>
          )}
        </div>
      )}

      {!compact && (
      <dl className="mt-5 flex-1 space-y-2.5 border-t border-border pt-5 text-[13px]">
        <div className="flex justify-between gap-4">
          <dt className="text-dim">{t("card.market")}</dt>
          <dd className="figure text-right">{model.markets.join(", ")}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-dim">{t("card.category")}</dt>
          <dd className="text-right">{t(`categories.${model.category}`)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-dim">{t("card.keyOutput")}</dt>
          <dd className="min-w-0 break-words text-right">{model.keyOutput[locale]}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-dim">{t("card.lastOutput")}</dt>
          <dd className="figure text-right">
            {model.status === "archived"
              ? locale === "vi"
                ? "Đã lưu trữ"
                : "Archived"
              : lastOutput
                ? fmtDate(lastOutput, locale)
                : t("card.noOutput")}
          </dd>
        </div>
      </dl>
      )}

      <Link
        href={`/models/${model.slug}`}
        className="arrow-link mt-6 inline-flex items-center gap-2 text-[13px] font-medium text-brand underline-offset-4 hover:text-brand-strong hover:underline"
      >
        {tc("viewDetails")} <span aria-hidden="true" data-arrow>→</span>
      </Link>
    </article>
  );
}
