"use client";

import { useLocale, useTranslations } from "next-intl";
import { useApi } from "@/lib/api/fetcher";
import type { MarketOverview } from "@/lib/api/types";
import { DataState } from "@/components/states/data-state";
import { DataFreshnessLabel } from "@/components/states/data-freshness-label";
import { RegimeBadge, RiskBadge } from "@/components/market/badges";
import { InfoTip } from "@/components/info-tip";
import {
  directionSymbol,
  fmtPercent,
  fmtPrice,
  fmtSignedPercent,
} from "@/lib/format";
import { cn } from "@/lib/utils";

export function MarketPulse() {
  const t = useTranslations("home.pulse");
  const g = useTranslations("glossary");
  const locale = useLocale();
  const { data, error, isLoading, mutate } = useApi<MarketOverview>(
    "/api/v1/market/overview"
  );

  return (
    <section className="border-y border-border bg-surface">
      <div className="container-qp py-10">
        <p className="eyebrow">{t("title")}</p>
        <DataState
          className="mt-6"
          loading={isLoading}
          error={error}
          onRetry={() => mutate()}
          empty={data && data.quotes.length === 0}
          freshness={data}
          skeletonRows={3}
        >
          {data && (
            <>
              <div className="market-pulse-grid grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4 xl:grid-cols-7">
                {data.quotes.map((q) => (
                  <div
                    key={q.symbol}
                    className={cn(
                      "border-t-2 bg-background p-5",
                      q.change_percent > 0 && "border-positive",
                      q.change_percent < 0 && "border-negative",
                      q.change_percent === 0 && "border-lightgray"
                    )}
                  >
                    <p className="text-xs font-medium text-dim">{q.name}</p>
                    <p className="figure mt-2 text-2xl font-medium">
                      {fmtPrice(q.price, locale)}
                    </p>
                    <p
                      className={cn(
                        "figure mt-1 text-sm",
                        q.change_percent > 0 && "text-positive",
                        q.change_percent < 0 && "text-negative"
                      )}
                    >
                      <span aria-hidden="true">
                        {directionSymbol(q.change_percent)}{" "}
                      </span>
                      {fmtSignedPercent(q.change_percent / 100, locale)}
                    </p>
                  </div>
                ))}
                <div className="border-t-2 border-brand bg-background p-5">
                  <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
                    {t("regime")} <InfoTip text={g("regime")} />
                  </p>
                  <RegimeBadge regime={data.regime} className="mt-3" />
                </div>
                <div className="border-t-2 border-brand bg-background p-5">
                  <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
                    {t("probabilityUp")} <InfoTip text={g("probabilityUp")} />
                  </p>
                  <p className="figure mt-2 text-2xl font-medium">
                    {fmtPercent(data.probability_up, locale)}
                  </p>
                </div>
                <div className="border-t-2 border-signal bg-background p-5">
                  <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
                    {t("volatility")} <InfoTip text={g("volatility")} />
                  </p>
                  <p className="figure mt-2 text-2xl font-medium">
                    {fmtPercent(data.volatility, locale)}
                  </p>
                </div>
                <div className="border-t-2 border-negative bg-background p-5">
                  <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
                    {t("riskState")} <InfoTip text={g("riskState")} />
                  </p>
                  <RiskBadge risk={data.risk_state} className="mt-3" />
                </div>
              </div>
              <DataFreshnessLabel freshness={data} />
            </>
          )}
        </DataState>
      </div>
    </section>
  );
}
