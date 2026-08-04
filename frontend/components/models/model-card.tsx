import { getLocale, getTranslations } from "next-intl/server";
import type { ModelCardData } from "@/config/models";
import { Link } from "@/i18n/navigation";
import { StatusBadge } from "@/components/market/badges";
import { Sparkline } from "@/components/sparkline";
import { fmtDate } from "@/lib/format";
import { lastTradingDay } from "@/lib/mock/market";

/** Model card fed by the database in production and the fixture in mock mode. */
export async function ModelCard({ model }: { model: ModelCardData }) {
  const locale = (await getLocale()) as "vi" | "en";
  const t = await getTranslations("models");
  const tc = await getTranslations("common");

  const updated = model.updatedAt ?? lastTradingDay().toISOString();

  return (
    <article className="qp-panel-interactive min-w-0 overflow-hidden flex flex-col p-6 hover:border-brand">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
        <div className="min-w-0">
          <h3 className="whitespace-nowrap text-lg font-semibold leading-tight">
            {model.name}
          </h3>
          <p className="figure mt-1 text-[11px] uppercase tracking-[0.08em] text-dim">
            {model.code} · v{model.version}
          </p>
        </div>
        <StatusBadge
          status={model.status}
          compact
        />
      </div>

      <p className="mt-4 text-sm leading-relaxed text-ink">
        {model.tagline[locale]}
      </p>

      {model.sparkline && (
        <div className="mt-5">
          {model.sparklineLabel && (
            <p className="mb-2 text-[11px] text-dim">{model.sparklineLabel[locale]}</p>
          )}
          <div className="text-brand">
            <Sparkline
              values={model.sparkline}
              width={280}
              height={48}
              className="h-12 w-full"
            />
          </div>
        </div>
      )}

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
          <dt className="text-dim">{t("card.updated")}</dt>
          <dd className="figure text-right">
            {model.status === "archived"
              ? locale === "vi"
                ? "Đã lưu trữ"
                : "Archived"
              : fmtDate(updated, locale)}
          </dd>
        </div>
      </dl>

      <Link
        href={`/models/${model.slug}`}
        className="arrow-link mt-6 inline-flex items-center gap-2 text-[13px] font-medium text-brand underline-offset-4 hover:text-brand-strong hover:underline"
      >
        {tc("viewDetails")} <span aria-hidden="true" data-arrow>→</span>
      </Link>
    </article>
  );
}
