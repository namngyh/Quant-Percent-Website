"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { useApi } from "@/lib/api/fetcher";
import type { RiskDashboard } from "@/lib/api/types";
import { CHART, EChart } from "@/components/charts/echart";
import { DataState } from "@/components/states/data-state";
import { DataFreshnessLabel } from "@/components/states/data-freshness-label";
import { RiskBadge } from "@/components/market/badges";
import { InfoTip } from "@/components/info-tip";
import { fmtNumber, fmtPercent } from "@/lib/format";

function Metric({
  label,
  tip,
  value,
}: {
  label: string;
  tip: string;
  value: string;
}) {
  return (
    <div className="bg-background p-5">
      <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
        {label} <InfoTip text={tip} />
      </p>
      <p className="figure mt-2 text-2xl font-medium">{value}</p>
    </div>
  );
}

/** Risk dashboard with every metric explained in a tooltip. */
export function RiskTab() {
  const t = useTranslations("market.risk");
  const g = useTranslations("glossary");
  const locale = useLocale();
  const { data, error, isLoading, mutate } = useApi<RiskDashboard>(
    "/api/v1/market/risk"
  );

  const mcOption = useMemo<EChartsCoreOption>(() => {
    const dist = data?.mc_drawdown_distribution ?? [];
    return {
      xAxis: {
        type: "category",
        data: dist.map((d) => fmtPercent(d.bucket, locale, 0)),
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: { color: CHART.dim },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          color: CHART.dim,
          formatter: (v: number) => fmtPercent(v, locale, 0),
        },
        splitLine: { lineStyle: { color: CHART.surface } },
      },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) => fmtPercent(Number(v), locale),
      },
      series: [
        {
          type: "bar",
          data: dist.map((d) => d.probability),
          itemStyle: { color: CHART.negative, borderRadius: [2, 2, 0, 0] },
          barWidth: "55%",
        },
      ],
    };
  }, [data, locale]);

  return (
    <DataState
      loading={isLoading}
      error={error}
      onRetry={() => mutate()}
      empty={data && data.mc_drawdown_distribution.length === 0}
      freshness={data}
      skeletonRows={8}
    >
      {data && (
        <div className="space-y-10">
          <div>
            <div className="grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-3">
              <Metric
                label={t("currentDrawdown")}
                tip={g("drawdown")}
                value={fmtPercent(data.current_drawdown, locale)}
              />
              <Metric
                label={t("rollingDrawdown")}
                tip={g("drawdown")}
                value={fmtPercent(data.rolling_drawdown_60d, locale)}
              />
              <Metric
                label={t("volatility")}
                tip={g("volatility")}
                value={fmtPercent(data.volatility, locale)}
              />
              {data.var_95 !== null && (
                <Metric
                  label={t("var")}
                  tip={g("var")}
                  value={fmtPercent(data.var_95, locale)}
                />
              )}
              {data.es_95 !== null && (
                <Metric
                  label={t("es")}
                  tip={g("es")}
                  value={fmtPercent(data.es_95, locale)}
                />
              )}
              <Metric
                label={t("downsideProbability")}
                tip={g("downsideProbability")}
                value={fmtPercent(data.downside_probability, locale)}
              />
            </div>
            <div className="mt-4 flex items-center gap-3">
              <span className="text-xs font-medium text-dim">
                {t("riskRegime")}:
              </span>
              <RiskBadge risk={data.risk_state} />
            </div>
          </div>

          <div className="qp-panel p-5">
            <h3 className="flex items-center gap-2 text-sm font-medium">
              {t("mcDistribution")} <InfoTip text={g("monteCarlo")} />
            </h3>
            <p className="mt-1 text-xs text-dim">
              {t("mcDescription", { n: fmtNumber(data.mc_paths, locale) })}
            </p>
            <EChart
              option={mcOption}
              ariaLabel={t("mcDistribution")}
              className="mt-4 h-64"
            />
          </div>

          <div className="qp-panel p-5">
            <h3 className="text-sm font-medium">{t("stress")}</h3>
            <p className="mt-1 text-xs text-dim">{t("stressDescription")}</p>
            <ul className="mt-4 space-y-2.5">
              {data.stress_scenarios.map((s) => {
                const width = Math.min(100, Math.abs(s.impact_percent) * 8);
                return (
                  <li
                    key={s.id}
                    className="grid grid-cols-[1fr_auto] items-center gap-4 desk:grid-cols-[220px_1fr_auto]"
                  >
                    <span className="text-[13px]">{t(`scenarios.${s.id}`)}</span>
                    <span
                      aria-hidden="true"
                      className="hidden h-2 bg-surface desk:block"
                    >
                      <span
                        className="block h-full bg-negative/60"
                        style={{ width: `${width}%` }}
                      />
                    </span>
                    <span className="figure text-[13px] text-negative">
                      {fmtPercent(s.impact_percent / 100, locale)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>

          <DataFreshnessLabel freshness={data} />
        </div>
      )}
    </DataState>
  );
}
