"use client";

import { useLocale, useTranslations } from "next-intl";
import { useApi } from "@/lib/api/fetcher";
import type { MarketOverview, SystemStatus } from "@/lib/api/types";
import { DataState } from "@/components/states/data-state";
import { DataFreshnessLabel } from "@/components/states/data-freshness-label";
import { RegimeBadge, RiskBadge, SignalBadge } from "@/components/market/badges";
import { InfoTip } from "@/components/info-tip";
import {
  directionSymbol,
  fmtPercent,
  fmtPrice,
  fmtSignedPercent,
} from "@/lib/format";
import { cn } from "@/lib/utils";

function Tile({
  label,
  tip,
  accent,
  children,
}: {
  label: string;
  tip?: string;
  accent?: "brand" | "signal" | "positive" | "negative";
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "border-t-2 border-transparent bg-background p-5",
        accent === "brand" && "border-brand",
        accent === "signal" && "border-signal",
        accent === "positive" && "border-positive",
        accent === "negative" && "border-negative"
      )}
    >
      <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
        {label} {tip && <InfoTip text={tip} />}
      </p>
      <div className="mt-2.5">{children}</div>
    </div>
  );
}

export function OverviewTab() {
  const t = useTranslations("market.overview");
  const g = useTranslations("glossary");
  const tp = useTranslations("home.pulse");
  const locale = useLocale();
  const { data, error, isLoading, mutate } = useApi<MarketOverview>(
    "/api/v1/market/overview"
  );
  const status = useApi<SystemStatus>("/api/v1/status");

  return (
    <DataState
      loading={isLoading}
      error={error}
      onRetry={() => mutate()}
      empty={data && data.quotes.length === 0}
      freshness={data}
      skeletonRows={8}
    >
      {data && (
        <>
          <div className="grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-3">
            {/* Model-derived tiles. Each renders only when the pipeline has
                produced that value; a missing reading is shown as missing by
                leaving the tile out entirely. */}
            {data.regime !== null && (
              <Tile label={t("marketState")} tip={g("regime")} accent="brand">
                <div className="flex flex-wrap items-center gap-2">
                  <RegimeBadge regime={data.regime} />
                  {data.regime_probability !== null && (
                    <span className="figure text-xs text-dim">
                      {locale === "vi" ? "Xác suất" : "Probability"}:{" "}
                      {fmtPercent(data.regime_probability, locale)}
                    </span>
                  )}
                </div>
              </Tile>
            )}
            {data.public_signal !== null && (
              <Tile label={t("signal")} accent="signal">
                <SignalBadge signal={data.public_signal} />
              </Tile>
            )}
            {data.model_consensus !== null && (
              <Tile label={t("modelConsensus")} tip={g("modelConsensus")} accent="brand">
                <p className="figure text-2xl font-medium text-brand-strong">
                  {fmtPercent(data.model_consensus, locale)}
                </p>
              </Tile>
            )}
            {data.probability_up !== null && (
              <Tile label={tp("probabilityUp")} tip={g("probabilityUp")} accent="positive">
                <p className="figure text-2xl font-medium text-positive">
                  {fmtPercent(data.probability_up, locale)}
                </p>
              </Tile>
            )}
            {data.probability_down !== null && (
              <Tile label={t("probabilityDown")} tip={g("downsideProbability")} accent="negative">
                <p className="figure text-2xl font-medium text-negative">
                  {fmtPercent(data.probability_down, locale)}
                </p>
              </Tile>
            )}
            {data.volatility !== null && (
              <Tile label={tp("volatility")} tip={g("volatility")} accent="signal">
                <p className="figure text-2xl font-medium text-signal-strong">
                  {fmtPercent(data.volatility, locale)}
                </p>
              </Tile>
            )}
            {data.risk_state !== null && (
              <Tile label={tp("riskState")} tip={g("riskState")} accent="negative">
                <div className="flex flex-wrap items-center gap-2">
                  <RiskBadge risk={data.risk_state} />
                  {data.risk_score !== null && (
                    <span className="figure text-xs text-dim">
                      {data.risk_score}/100
                    </span>
                  )}
                </div>
              </Tile>
            )}
            {data.quotes.map((q) => (
              <Tile key={q.symbol} label={q.name}>
                <p className="figure text-2xl font-medium">
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
              </Tile>
            ))}
            <Tile label={t("systemStatus")}>
              {status.data ? (
                <p className="flex items-center gap-2 text-sm">
                  <span
                    aria-hidden="true"
                    className={cn(
                      "size-2 rounded-full",
                      status.data.services.every((s) => s.status === "operational")
                        ? "bg-positive"
                        : "bg-caution"
                    )}
                  />
                  {t("operational")}
                </p>
              ) : (
                <p className="text-sm text-dim">
                  {locale === "vi" ? "Chưa có dữ liệu" : "Not available"}
                </p>
              )}
            </Tile>
          </div>
          <DataFreshnessLabel freshness={data} />
        </>
      )}
    </DataState>
  );
}
