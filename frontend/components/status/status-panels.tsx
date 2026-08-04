"use client";

import { useLocale, useTranslations } from "next-intl";
import { useApi } from "@/lib/api/fetcher";
import type {
  DataFreshnessReport,
  ModelStatusReport,
  SystemStatus,
} from "@/lib/api/types";
import { DataState } from "@/components/states/data-state";
import { StatusBadge } from "@/components/market/badges";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const SERVICE_NAME_KEYS = {
  market_data: "serviceNames.market_data",
  model_output: "serviceNames.model_output",
  performance: "serviceNames.performance",
  public_api: "serviceNames.public_api",
  contact: "serviceNames.contact",
} as const;

/** ModelStatusIndicator + service/data-freshness panels for /system-status. */
export function StatusPanels() {
  const t = useTranslations("status");
  const tc = useTranslations("common");
  const locale = useLocale();
  const services = useApi<SystemStatus>("/api/v1/status");
  const freshness = useApi<DataFreshnessReport>("/api/v1/data-freshness");
  const models = useApi<ModelStatusReport>("/api/v1/model-status");
  const serviceName = (id: string, fallback: string) => {
    const key = SERVICE_NAME_KEYS[id as keyof typeof SERVICE_NAME_KEYS];
    return key ? t(key) : fallback;
  };

  const dot = (status: "operational" | "degraded" | "down") => (
    <span
      aria-hidden="true"
      className={cn(
        "size-2 rounded-full",
        status === "operational" && "bg-positive",
        status === "degraded" && "bg-caution",
        status === "down" && "bg-negative"
      )}
    />
  );

  return (
    <div className="space-y-10">
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-dim">
          {t("services")}
        </h2>
        <DataState
          className="mt-4"
          loading={services.isLoading}
          error={services.error}
          onRetry={() => services.mutate()}
          skeletonRows={5}
        >
          {services.data && (
            <>
              <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border shadow-sm">
                {services.data.services.map((s) => (
                  <li
                    key={s.id}
                    className="flex items-center justify-between px-4 py-3"
                  >
                    <span className="text-sm">{serviceName(s.id, s.name)}</span>
                    <span className="flex items-center gap-2 text-[13px] text-dim">
                      {dot(s.status)}
                      {t(s.status)}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="figure mt-3 text-[11px] text-dim">
                {t("lastChecked")}:{" "}
                {fmtDateTime(services.data.generated_at, locale)}
              </p>
            </>
          )}
        </DataState>
      </section>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-dim">
          {t("dataFreshness")}
        </h2>
        <DataState
          className="mt-4"
          loading={freshness.isLoading}
          error={freshness.error}
          onRetry={() => freshness.mutate()}
          skeletonRows={4}
        >
          {freshness.data && (
            <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border shadow-sm">
              {freshness.data.feeds.map((f) => (
                <li
                  key={f.id}
                  className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
                >
                  <span className="figure text-sm">{f.symbol}</span>
                  <span className="figure text-[12px] text-dim">
                    {tc("freshness.dataAsOf")}:{" "}
                    {fmtDateTime(f.data_as_of, locale)} ·{" "}
                    {tc("freshness.delayedBy", { minutes: f.delay_minutes })}
                    {f.is_stale && (
                      <span className="ml-2 border border-caution/50 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.06em] text-caution">
                        {tc("dataState.stale")}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </DataState>
      </section>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-dim">
          {t("modelStatus")}
        </h2>
        <DataState
          className="mt-4"
          loading={models.isLoading}
          error={models.error}
          onRetry={() => models.mutate()}
          skeletonRows={6}
        >
          {models.data && (
            <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border shadow-sm">
              {models.data.models.map((m) => (
                <li
                  key={m.model_id}
                  className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
                >
                  <span className="figure text-sm">{m.model_id}</span>
                  <span className="flex items-center gap-3">
                    <StatusBadge status={m.status} />
                    {m.last_run_at && (
                      <span className="figure hidden text-[12px] text-dim sm:inline">
                        {tc("freshness.updated")}:{" "}
                        {fmtDateTime(m.last_run_at, locale)}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </DataState>
      </section>
    </div>
  );
}
