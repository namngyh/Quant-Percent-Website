"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { Link } from "@/i18n/navigation";
import { useApi } from "@/lib/api/fetcher";
import type {
  History,
  MarketOverview,
  Quote,
  StrategyMetrics,
} from "@/lib/api/types";
import { FEATURED_STRATEGY } from "@/config/strategies";
import { CHART, EChart } from "@/components/charts/echart";
import { DataState } from "@/components/states/data-state";
import { DataFreshnessLabel } from "@/components/states/data-freshness-label";
import { RegimeBadge, RiskBadge, SignalBadge } from "@/components/market/badges";
import { InfoTip } from "@/components/info-tip";
import {
  directionSymbol,
  fmtNumber,
  fmtPercent,
  fmtPrice,
  fmtSignedPercent,
} from "@/lib/format";
import { useIsMobile } from "@/lib/use-is-mobile";
import { cn } from "@/lib/utils";

/** VN30F1M tab publishes only cleared information. */
export function FuturesTab() {
  const t = useTranslations("market.vn30f1m");
  const tm = useTranslations("market.chart");
  const tp = useTranslations("home.pulse");
  const tperf = useTranslations("performance");
  const tc = useTranslations("common");
  const g = useTranslations("glossary");
  const locale = useLocale();
  const isMobile = useIsMobile();

  const quote = useApi<Quote>("/api/v1/market/VN30F1M/quote");
  const spot = useApi<Quote>("/api/v1/market/VN30/quote");
  const history = useApi<History>("/api/v1/market/VN30F1M/history?count=250");
  const overview = useApi<MarketOverview>("/api/v1/market/overview");
  const metrics = useApi<StrategyMetrics>(
    `/api/v1/strategies/${FEATURED_STRATEGY}/metrics`
  );

  const bars = useMemo(() => {
    const all = history.data?.bars ?? [];
    return isMobile ? all.slice(-100) : all;
  }, [history.data, isMobile]);

  const priceOption = useMemo<EChartsCoreOption>(
    () => ({
      xAxis: {
        type: "category",
        data: bars.map((b) => b.time),
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: { color: CHART.dim },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitLine: { lineStyle: { color: CHART.surface } },
        axisLabel: { color: CHART.dim },
      },
      series: [
        {
          name: tm("price"),
          type: "line",
          data: bars.map((b) => b.close),
          showSymbol: false,
          lineStyle: { color: CHART.brand, width: 2 },
          itemStyle: { color: CHART.brand },
        },
      ],
    }),
    [bars, tm]
  );

  const basis =
    quote.data && spot.data ? quote.data.price - spot.data.price : null;
  const m = metrics.data?.metrics;

  return (
    <div className="space-y-10">
      {/* §8.5: no entry signals, positions or strategy parameters */}
      <p className="rounded-lg border border-border bg-surface px-4 py-3 text-xs leading-relaxed text-dim">
        {t("notice")}
      </p>

      <DataState
        loading={quote.isLoading || spot.isLoading || overview.isLoading}
        error={quote.error || spot.error || overview.error}
        onRetry={() => {
          quote.mutate();
          spot.mutate();
          overview.mutate();
        }}
        freshness={quote.data}
        skeletonRows={4}
      >
        {quote.data && overview.data && (
          <>
            <div className="grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4">
              <div className="bg-background p-5">
                <p className="text-xs font-medium text-dim">{quote.data.name}</p>
                <p className="tick mt-2 text-2xl font-medium">
                  {fmtPrice(quote.data.price, locale)}
                </p>
                <p
                  className={cn(
                    "tick mt-1 text-sm",
                    quote.data.change_percent > 0 && "text-positive",
                    quote.data.change_percent < 0 && "text-negative"
                  )}
                >
                  <span aria-hidden="true">
                    {directionSymbol(quote.data.change_percent)}{" "}
                  </span>
                  {fmtSignedPercent(quote.data.change_percent / 100, locale)}
                </p>
              </div>
              <div className="bg-background p-5">
                <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
                  {t("basis")} <InfoTip text={g("basis")} />
                </p>
                <p className="tick mt-2 text-2xl font-medium">
                  {basis === null
                    ? locale === "vi"
                      ? "Chưa có"
                      : "Not available"
                    : fmtNumber(basis, locale)}
                </p>
              </div>
              <div className="bg-background p-5">
                <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
                  {tm("volume")}
                </p>
                <p className="tick mt-2 text-2xl font-medium">
                  {fmtNumber(quote.data.volume, locale, {
                    notation: "compact",
                  })}
                </p>
              </div>
              {overview.data.volatility !== null && (
                <div className="bg-background p-5">
                  <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
                    {tp("volatility")} <InfoTip text={g("volatility")} />
                  </p>
                  <p className="tick mt-2 text-2xl font-medium">
                    {fmtPercent(overview.data.volatility, locale)}
                  </p>
                </div>
              )}
            </div>

            {/* Model-derived badges; the whole row disappears until an
                inference runner has written quant.market_state. */}
            {(overview.data.regime !== null ||
              overview.data.risk_state !== null ||
              overview.data.public_signal !== null) && (
              <div className="mt-4 flex flex-wrap items-center gap-2">
                {overview.data.regime !== null && (
                  <RegimeBadge regime={overview.data.regime} />
                )}
                {overview.data.risk_state !== null && (
                  <RiskBadge risk={overview.data.risk_state} />
                )}
                {overview.data.public_signal !== null && (
                  <>
                    <span className="mx-1 text-xs text-dim">
                      {t("systemState")}:
                    </span>
                    <SignalBadge signal={overview.data.public_signal} />
                  </>
                )}
              </div>
            )}
            <DataFreshnessLabel freshness={quote.data} />
          </>
        )}
      </DataState>

      <DataState
        loading={history.isLoading}
        error={history.error}
        onRetry={() => history.mutate()}
        empty={history.data && history.data.bars.length === 0}
        skeletonRows={6}
      >
        {history.data && (
          <div className="qp-panel p-5">
            <p className="text-sm font-medium">{tm("history")}</p>
            <EChart
              option={priceOption}
              ariaLabel={`VN30F1M: ${tm("history")}`}
              className="mt-4 h-96"
            />
          </div>
        )}
      </DataState>

      {/* Aggregate performance only, clearly labeled as paper trading. */}
      <DataState
        loading={metrics.isLoading}
        error={metrics.error}
        onRetry={() => metrics.mutate()}
        skeletonRows={3}
      >
        {m && (
          <div className="qp-panel p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm font-medium">{t("aggregatePerformance")}</p>
              <span className="rounded-full border border-border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-dim">
                {tc("resultType.walk_forward")}
              </span>
            </div>
            <dl className="mt-5 grid grid-cols-2 gap-4 desk:grid-cols-4">
              {m.annualizedReturn !== null && (
                <div>
                  <dt className="text-[11px] uppercase tracking-[0.08em] text-dim">
                    {tperf("detail.metricNames.annualizedReturn")}
                  </dt>
                  <dd className="tick mt-1 text-lg">
                    {fmtPercent(m.annualizedReturn, locale)}
                  </dd>
                </div>
              )}
              {m.maxDrawdown !== null && (
                <div>
                  <dt className="text-[11px] uppercase tracking-[0.08em] text-dim">
                    {tperf("detail.metricNames.maxDrawdown")}
                  </dt>
                  <dd className="tick mt-1 text-lg">
                    {fmtPercent(m.maxDrawdown, locale)}
                  </dd>
                </div>
              )}
              {m.sharpe !== null && (
                <div>
                  <dt className="text-[11px] uppercase tracking-[0.08em] text-dim">
                    {tperf("detail.metricNames.sharpe")}
                  </dt>
                  <dd className="tick mt-1 text-lg">{m.sharpe}</dd>
                </div>
              )}
              {m.winRate !== null && (
                <div>
                  <dt className="text-[11px] uppercase tracking-[0.08em] text-dim">
                    {tperf("detail.metricNames.winRate")}
                  </dt>
                  <dd className="tick mt-1 text-lg">
                    {fmtPercent(m.winRate, locale)}
                  </dd>
                </div>
              )}
            </dl>
            <p className="mt-4 text-xs text-dim">{tperf("labelNote")}</p>
            <Link
              href={`/performance/${FEATURED_STRATEGY}`}
              className="mt-4 inline-block text-[13px] font-medium underline-offset-4 hover:underline"
            >
              {tc("viewDetails")} →
            </Link>
          </div>
        )}
      </DataState>
    </div>
  );
}
