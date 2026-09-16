"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { useApi } from "@/lib/api/fetcher";
import type {
  ForecastHistory,
  ForecastRecord,
  History,
} from "@/lib/api/types";
import { CHART, EChart } from "@/components/charts/echart";
import { DataState } from "@/components/states/data-state";
import { DataFreshnessLabel } from "@/components/states/data-freshness-label";
import { RegimeBadge, RiskBadge } from "@/components/market/badges";
import { InfoTip } from "@/components/info-tip";
import { Button } from "@/components/ui/button";
import { fmtDate, fmtPercent, fmtPrice, fmtSignedPercent } from "@/lib/format";
import { useIsMobile } from "@/lib/use-is-mobile";
import { cn } from "@/lib/utils";

/** Current output cards (§9.2) for a forecasting model. */
export function CurrentOutput({
  modelSlug,
  symbol,
}: {
  modelSlug: string;
  symbol: string;
}) {
  const t = useTranslations("models.detail");
  const tm = useTranslations("market.chart");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { data, error, isLoading, mutate } = useApi<{
    records: ForecastRecord[];
  }>(`/api/v1/models/${modelSlug}/latest?symbol=${symbol}`);
  const records = data?.records ?? [];
  const first = records[0];

  return (
    // A container, not a media query, decides the card layout below. This
    // panel sits full width on the model's own page and in a third of a row
    // on the combined one, and the viewport cannot tell those apart.
    <section className="@container">
      <h2 className="title-md">{t("currentOutput")}</h2>
      <DataState
        className="mt-5"
        loading={isLoading}
        error={error}
        onRetry={() => mutate()}
        empty={data && records.length === 0}
        skeletonRows={4}
      >
        {first && (
          <>
            {/* A distributional model makes no regime call and assigns no
                risk grade; the row is left out rather than filled in. */}
            {(first.regime !== null || first.risk_state !== null) && (
              <div className="flex flex-wrap items-center gap-2">
                {first.regime !== null && <RegimeBadge regime={first.regime} />}
                {first.risk_state !== null && (
                  <RiskBadge risk={first.risk_state} />
                )}
                {first.regime_probability !== null && (
                  <span className="figure text-xs text-dim">
                    {locale === "vi"
                      ? "Khả năng của trạng thái này"
                      : "State probability"}{" "}
                    = {fmtPercent(first.regime_probability, locale)}
                  </span>
                )}
              </div>
            )}
            {/* Column count follows the number of horizons the model
                publishes. Fixed at four, a model with three left a blank
                grey cell that reads as a panel that failed to load. */}
            <div
              className={cn(
                "mt-4 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm @md:grid-cols-2",
                records.length >= 4 ? "@3xl:grid-cols-4" : "@3xl:grid-cols-3",
              )}
            >
              {records.map((r) => (
                <div key={r.horizon} className="bg-background p-5">
                  <p className="figure text-xs uppercase tracking-[0.08em] text-dim">
                    {tc("horizonDays", { count: r.horizon })}
                  </p>
                  <p className="figure mt-2 text-2xl font-medium">
                    {fmtPrice(r.forecast_value, locale)}
                  </p>
                  <p className="figure mt-1 text-sm text-ink">
                    {tm("expectedReturn")}:{" "}
                    {fmtSignedPercent(r.forecast_return, locale)}
                  </p>
                  <p className="figure mt-2 text-xs text-dim">
                    {tm("interval", {
                      level: fmtPercent(r.interval_level, locale, 0),
                    })}
                    : {fmtPrice(r.interval_lower, locale)} –{" "}
                    {fmtPrice(r.interval_upper, locale)}
                  </p>
                  <p className="figure mt-1 text-xs text-dim">
                    {locale === "vi" ? "Khả năng tăng" : "P(↑)"} ={" "}
                    {fmtPercent(r.probability_up, locale)} ·{" "}
                    {locale === "vi" ? "Biến động dự kiến" : "σ"} ={" "}
                    {fmtPercent(r.volatility, locale)}
                  </p>
                </div>
              ))}
            </div>
            {/* Without this line the panel reads as a settled result. These
                are estimates for periods that have not elapsed, and none of
                them has yet been compared with what the market did — the
                history table below is empty for exactly that reason. */}
            <p className="mt-4 max-w-3xl border-l-2 border-lightgray pl-4 text-sm leading-relaxed text-dim">
              {t("currentOutputCaveat")}
            </p>
          </>
        )}
      </DataState>
    </section>
  );
}

/** Forecast chart (§9.2): actual price, central forecast and interval band. */
export function ForecastChart({
  modelSlug,
  symbol,
}: {
  modelSlug: string;
  symbol: string;
}) {
  const t = useTranslations("models.detail");
  const tm = useTranslations("market.chart");
  const isMobile = useIsMobile();
  const history = useApi<History>(`/api/v1/market/${symbol}/history?count=80`);
  const latest = useApi<{ records: ForecastRecord[] }>(
    `/api/v1/models/${modelSlug}/latest?symbol=${symbol}`
  );

  const option = useMemo<EChartsCoreOption | null>(() => {
    const bars = (history.data?.bars ?? []).slice(isMobile ? -40 : -80);
    const records = [...(latest.data?.records ?? [])].sort(
      (a, b) => a.horizon - b.horizon
    );
    if (bars.length === 0 || records.length === 0) return null;

    const lastClose = bars[bars.length - 1].close;
    const n = bars.length;

    // The forecast occupies the width its horizon actually spans.
    //
    // Each published horizon used to take one category slot, so a 60-session
    // forecast rendered as three columns beside eighty of history — about a
    // twentieth of the chart for the half of it a reader came to see, and a
    // widening interval that did not visibly widen. Giving every session
    // between here and the last horizon its own slot puts the +60d point
    // sixty slots out, where it belongs, and the cone opens across it.
    //
    // Values between two published horizons are read off the straight line
    // joining them, which is the same line the chart drew before; positioning
    // the endpoints correctly is what changed, not the model's output.
    const horizons = records.map((r) => r.horizon);
    const maxHorizon = horizons[horizons.length - 1];
    const anchorDays = [0, ...horizons];

    const along = (values: number[]) => (day: number) => {
      for (let i = 1; i < anchorDays.length; i += 1) {
        if (day <= anchorDays[i]) {
          const from = anchorDays[i - 1];
          const span = anchorDays[i] - from || 1;
          const w = (day - from) / span;
          return values[i - 1] + (values[i] - values[i - 1]) * w;
        }
      }
      return values[values.length - 1];
    };

    const centerAt = along([lastClose, ...records.map((r) => r.forecast_value)]);
    const lowerAt = along([lastClose, ...records.map((r) => r.interval_lower)]);
    const upperAt = along([lastClose, ...records.map((r) => r.interval_upper)]);

    const days = Array.from({ length: maxHorizon }, (_, i) => i + 1);
    const categories = [...bars.map((b) => b.time), ...days.map((d) => `+${d}d`)];

    // Where a published horizon sits, for the axis ticks and the markers.
    const anchorIndex = new Set(horizons.map((h) => n - 1 + h));

    const actual = [...bars.map((b) => b.close), ...days.map(() => null)];
    const center = [
      ...bars.map((_, i) => (i === n - 1 ? lastClose : null)),
      ...days.map(centerAt),
    ];
    const lower = [
      ...bars.map((_, i) => (i === n - 1 ? lastClose : null)),
      ...days.map(lowerAt),
    ];
    const bandWidth = [
      ...bars.map((_, i) => (i === n - 1 ? 0 : null)),
      ...days.map((d) => upperAt(d) - lowerAt(d)),
    ];

    // One date every so often across the history, then every published
    // horizon. Left to itself the axis spaces ticks evenly and lands them on
    // unremarkable filler days instead of on +5d, +20d and +60d.
    const stride = Math.max(Math.ceil(n / (isMobile ? 3 : 5)), 1);

    const actualLabel = tm("actual");
    const intervalLabel = tm("interval", { level: "95%" });
    const forecastLabel = tm("forecastCenter");

    return {
      grid: {
        left: 8,
        right: 8,
        top: isMobile ? 86 : 48,
        bottom: 8,
        containLabel: true,
      },
      legend: {
        show: true,
        type: isMobile ? "plain" : "scroll",
        orient: isMobile ? "vertical" : "horizontal",
        top: 0,
        left: 0,
        right: 0,
        itemWidth: 14,
        itemHeight: 6,
        itemGap: isMobile ? 6 : 18,
        textStyle: {
          color: CHART.dim,
          fontFamily: CHART.mono,
          fontSize: 11,
        },
        data: [
          { name: actualLabel, icon: "roundRect" },
          { name: intervalLabel, icon: "roundRect" },
          { name: forecastLabel, icon: "roundRect" },
        ],
      },
      xAxis: {
        type: "category",
        data: categories,
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: {
          color: CHART.dim,
          interval: (index: number) =>
            index < n ? index % stride === 0 : anchorIndex.has(index),
          // The panel is two thirds of a row here and full width on the
          // model's own page; a tick count that fits one runs the dates into
          // each other on the other.
          hideOverlap: true,
        },
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
          name: actualLabel,
          type: "line",
          data: actual,
          showSymbol: false,
          lineStyle: { color: CHART.ink, width: 1.8 },
          itemStyle: { color: CHART.ink },
        },
        {
          // invisible base of the interval band
          name: "_lower",
          type: "line",
          data: lower,
          stack: "band",
          showSymbol: false,
          lineStyle: { opacity: 0 },
          itemStyle: { opacity: 0 },
          tooltip: { show: false },
        },
        {
          name: intervalLabel,
          type: "line",
          data: bandWidth,
          stack: "band",
          showSymbol: false,
          lineStyle: { opacity: 0 },
          itemStyle: { color: CHART.signal },
          areaStyle: { color: CHART.signalSoft, opacity: 0.72 },
        },
        {
          name: forecastLabel,
          type: "line",
          data: center,
          showSymbol: true,
          // A dot marks a horizon the model published. The dashed line
          // between two dots is the path drawn between them, not sixty
          // separate forecasts, and marking every session would say it was.
          symbol: (_v: unknown, params: { dataIndex: number }) =>
            anchorIndex.has(params.dataIndex) ? "circle" : "none",
          symbolSize: 7,
          lineStyle: { color: CHART.brand, width: 2, type: "dashed" },
          itemStyle: { color: CHART.brand },
        },
      ],
    };
  }, [history.data, latest.data, isMobile, tm]);

  return (
    <section>
      <h2 className="title-md">{t("forecastChart")}</h2>
      <DataState
        className="mt-5"
        loading={history.isLoading || latest.isLoading}
        error={history.error || latest.error}
        onRetry={() => {
          history.mutate();
          latest.mutate();
        }}
        empty={!option && !history.isLoading && !latest.isLoading}
        skeletonRows={6}
      >
        {option && (
          <div className="qp-panel p-5">
            <EChart
              option={option}
              ariaLabel={`${symbol}: ${t("forecastChart")}`}
              className="h-[26rem] desk:h-[34rem]"
            />
          </div>
        )}
      </DataState>
    </section>
  );
}

const HISTORY_PAGE = 10;

/** Historical forecasts vs realized values with interval coverage (§9.2). */
export function HistoricalForecasts({
  modelSlug,
  symbol,
}: {
  modelSlug: string;
  symbol: string;
}) {
  const t = useTranslations("models.detail");
  const tc = useTranslations("common");
  const g = useTranslations("glossary");
  const locale = useLocale();
  const [page, setPage] = useState(0);
  const { data, error, isLoading, mutate } = useApi<ForecastHistory>(
    `/api/v1/models/${modelSlug}/history?symbol=${symbol}`
  );

  const points = useMemo(
    () => [...(data?.points ?? [])].reverse(),
    [data]
  );
  const pageCount = Math.max(1, Math.ceil(points.length / HISTORY_PAGE));
  const current = Math.min(page, pageCount - 1);
  const visible = points.slice(
    current * HISTORY_PAGE,
    (current + 1) * HISTORY_PAGE
  );

  return (
    <section>
      <h2 className="title-md">{t("historicalForecasts")}</h2>
      <p className="mt-2 max-w-2xl text-sm text-dim">
        {t("historicalDescription")}
      </p>
      <DataState
        className="mt-5"
        loading={isLoading}
        error={error}
        onRetry={() => mutate()}
        empty={data && points.length === 0}
        freshness={data}
        skeletonRows={8}
      >
        {data && (
          <>
            <p className="flex items-center gap-2 text-sm">
              <span className="font-medium">
                {t("coverage", {
                  level: fmtPercent(data.interval_level, locale, 0),
                })}
                :
              </span>
              <span className="figure">{fmtPercent(data.coverage, locale)}</span>
              <InfoTip text={g("coverage")} />
            </p>

            <div className="mt-4 overflow-x-auto rounded-lg border border-border shadow-sm">
              <table className="w-full min-w-[560px] text-[13px]">
                <thead>
                  <tr className="border-b border-border bg-surface text-left">
                    <th scope="col" className="px-4 py-3 font-medium text-dim">
                      {t("forecastAt")}
                    </th>
                    <th scope="col" className="px-4 py-3 text-right font-medium text-dim">
                      {t("predicted")}
                    </th>
                    <th scope="col" className="px-4 py-3 text-right font-medium text-dim">
                      {t("actual")}
                    </th>
                    <th scope="col" className="px-4 py-3 text-right font-medium text-dim">
                      {t("error")}
                    </th>
                    <th scope="col" className="px-4 py-3 text-center font-medium text-dim">
                      {t("inInterval")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((p) => (
                    <tr
                      key={p.forecast_at}
                      className="border-b border-border last:border-0"
                    >
                      <td className="figure px-4 py-2.5">
                        {fmtDate(p.forecast_at, locale)} (+{p.horizon}d)
                      </td>
                      <td className="figure px-4 py-2.5 text-right">
                        {fmtPrice(p.predicted, locale)}
                      </td>
                      <td className="figure px-4 py-2.5 text-right">
                        {fmtPrice(p.actual, locale)}
                      </td>
                      <td
                        className={cn(
                          "figure px-4 py-2.5 text-right",
                          Math.abs(p.error_percent) > 2 && "text-negative"
                        )}
                      >
                        {fmtSignedPercent(p.error_percent / 100, locale)}
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        <span aria-hidden="true">{p.in_interval ? "✓" : "✗"}</span>
                        <span className="sr-only">
                          {p.in_interval ? "yes" : "no"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {pageCount > 1 && (
              <div className="mt-4 flex items-center justify-between">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={current === 0}
                  onClick={() => setPage(current - 1)}
                >
                  {tc("previous")}
                </Button>
                <p className="figure text-xs text-dim">
                  {tc("page", { page: current + 1, total: pageCount })}
                </p>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={current >= pageCount - 1}
                  onClick={() => setPage(current + 1)}
                >
                  {tc("next")}
                </Button>
              </div>
            )}
            <DataFreshnessLabel freshness={data} />
          </>
        )}
      </DataState>
    </section>
  );
}
