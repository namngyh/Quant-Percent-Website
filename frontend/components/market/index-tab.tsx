"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { Link } from "@/i18n/navigation";
import { ApiError, useApi } from "@/lib/api/fetcher";
import type { ForecastRecord, History } from "@/lib/api/types";
import { CHART, EChart } from "@/components/charts/echart";
import { DataState } from "@/components/states/data-state";
import { DataFreshnessLabel } from "@/components/states/data-freshness-label";
import { RegimeBadge, RiskBadge } from "@/components/market/badges";
import { InfoTip } from "@/components/info-tip";
import { fmtPercent, fmtPrice, fmtSignedPercent } from "@/lib/format";
import { useIsMobile } from "@/lib/use-is-mobile";

/** Which public model feeds each index tab's forecasts. */
const FORECAST_MODEL: Record<string, string> = {
  VNINDEX: "raemf-mc",
  VN30: "rarf-fhe",
};

export function IndexTab({ symbol }: { symbol: "VNINDEX" | "VN30" }) {
  const t = useTranslations("market.chart");
  const tc = useTranslations("common");
  const g = useTranslations("glossary");
  const tp = useTranslations("home.pulse");
  const locale = useLocale();
  const isMobile = useIsMobile();

  const history = useApi<History>(`/api/v1/market/${symbol}/history?count=250`);
  const modelSlug = FORECAST_MODEL[symbol];
  const latest = useApi<{ records: ForecastRecord[] }>(
    `/api/v1/models/${modelSlug}/latest?symbol=${symbol}`
  );

  const bars = useMemo(() => {
    const all = history.data?.bars ?? [];
    return isMobile ? all.slice(-100) : all;
  }, [history.data, isMobile]);

  const priceOption = useMemo<EChartsCoreOption>(() => {
    const dates = bars.map((b) => b.time);
    return {
      grid: [
        { left: 8, right: 8, top: 28, height: "58%", containLabel: true },
        { left: 8, right: 8, bottom: 4, height: "18%", containLabel: true },
      ],
      xAxis: [
        {
          type: "category",
          data: dates,
          gridIndex: 0,
          axisLine: { lineStyle: { color: CHART.border } },
          axisLabel: { show: false },
          axisTick: { show: false },
        },
        {
          type: "category",
          data: dates,
          gridIndex: 1,
          axisLine: { lineStyle: { color: CHART.border } },
          axisLabel: { color: CHART.dim },
          axisTick: { show: false },
        },
      ],
      yAxis: [
        {
          type: "value",
          gridIndex: 0,
          scale: true,
          splitLine: { lineStyle: { color: CHART.surface } },
          axisLabel: { color: CHART.dim },
        },
        {
          type: "value",
          gridIndex: 1,
          splitLine: { show: false },
          axisLabel: { show: false },
        },
      ],
      axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
      series: [
        {
          name: t("price"),
          type: "line",
          data: bars.map((b) => b.close),
          xAxisIndex: 0,
          yAxisIndex: 0,
          showSymbol: false,
          lineStyle: { color: CHART.brand, width: 2 },
          itemStyle: { color: CHART.brand },
        },
        {
          name: t("volume"),
          type: "bar",
          data: bars.map((b) => b.volume),
          xAxisIndex: 1,
          yAxisIndex: 1,
          itemStyle: { color: CHART.signal, opacity: 0.55 },
        },
      ],
    };
  }, [bars, t]);

  const records = latest.data?.records ?? [];
  const first = records[0];
  // 404 from /latest means the model does not publish forecasts, which is a
  // configuration choice rather than an outage.
  const forecastUnavailable =
    latest.error instanceof ApiError && latest.error.status === 404;

  // Current drawdown from the price series
  const drawdown = useMemo(() => {
    let peak = 0;
    let dd = 0;
    for (const b of bars) {
      peak = Math.max(peak, b.close);
      dd = Math.min(dd, b.close / peak - 1);
    }
    const last = bars[bars.length - 1];
    return last ? last.close / peak - 1 : 0;
  }, [bars]);

  return (
    <div className="space-y-10">
      <DataState
        loading={history.isLoading}
        error={history.error}
        onRetry={() => history.mutate()}
        empty={history.data && history.data.bars.length === 0}
        freshness={history.data}
        skeletonRows={7}
      >
        {history.data && (
          <div className="qp-panel p-5">
            <p className="text-sm font-medium">{t("history")}</p>
            <EChart
              option={priceOption}
              ariaLabel={`${symbol}: ${t("history")}`}
              className="mt-4 h-[26rem]"
            />
            <DataFreshnessLabel freshness={history.data} />
          </div>
        )}
      </DataState>

      {/*
        A 404 here is not a failure. Models that publish no forecast return
        "not_available" by design, and rendering that as "could not load the
        data, please retry" put a red error panel with a dead retry button
        under a perfectly healthy chart. When the model publishes nothing,
        the section is simply absent, and it comes back on its own once the
        model starts publishing.
      */}
      <DataState
        loading={latest.isLoading}
        error={forecastUnavailable ? undefined : latest.error}
        onRetry={() => latest.mutate()}
        empty={
          forecastUnavailable || (latest.data && records.length === 0)
            ? false
            : undefined
        }
        hidden={forecastUnavailable}
        skeletonRows={4}
      >
        {first && (
          <div>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="flex items-center gap-2 text-sm font-medium">
                {t("forecastTitle")} <InfoTip text={g("forecastInterval")} />
              </h3>
              <div className="flex flex-wrap items-center gap-2">
                {/* Null when the model forecasts a distribution only. */}
                {first.regime !== null && <RegimeBadge regime={first.regime} />}
                {first.risk_state !== null && (
                  <RiskBadge risk={first.risk_state} />
                )}
              </div>
            </div>

            <div className="mt-4 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4">
              {records.map((r) => (
                <div key={r.horizon} className="bg-background p-5">
                  <p className="tick text-xs uppercase tracking-[0.08em] text-dim">
                    {tc("horizonDays", { count: r.horizon })}
                  </p>
                  <p className="tick mt-2 text-2xl font-medium">
                    {fmtPrice(r.forecast_value, locale)}
                  </p>
                  <p className="tick mt-1 text-sm text-ink">
                    {t("expectedReturn")}:{" "}
                    {fmtSignedPercent(r.forecast_return, locale)}
                  </p>
                  <p className="tick mt-2 text-xs text-dim">
                    {t("interval", {
                      level: fmtPercent(r.interval_level, locale, 0),
                    })}
                    : {fmtPrice(r.interval_lower, locale)} –{" "}
                    {fmtPrice(r.interval_upper, locale)}
                  </p>
                  <p className="tick mt-1 text-xs text-dim">
                    P(↑) = {fmtPercent(r.probability_up, locale)}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-4 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-3">
              <div className="bg-background p-5">
                <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
                  {t("currentDrawdown")} <InfoTip text={g("drawdown")} />
                </p>
                <p className="tick mt-2 text-2xl font-medium">
                  {fmtPercent(drawdown, locale)}
                </p>
              </div>
              <div className="bg-background p-5">
                <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
                  {tp("volatility")} <InfoTip text={g("volatility")} />
                </p>
                <p className="tick mt-2 text-2xl font-medium">
                  {fmtPercent(first.volatility, locale)}
                </p>
              </div>
              <div className="bg-background p-5">
                <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
                  {t("riskScore")} <InfoTip text={g("riskState")} />
                </p>
                <p className="tick mt-2 text-2xl font-medium">
                  {first.risk_score}/100
                </p>
              </div>
            </div>

            <div className="mt-4 flex items-center justify-between gap-4">
              <DataFreshnessLabel
                freshness={first}
                modelVersion={first.model_version}
              />
              <Link
                href={`/models/${modelSlug}`}
                className="shrink-0 text-[13px] font-medium underline-offset-4 hover:underline"
              >
                {t("viewModel")} →
              </Link>
            </div>
          </div>
        )}
      </DataState>
    </div>
  );
}
