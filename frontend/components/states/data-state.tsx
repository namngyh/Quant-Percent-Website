"use client";

import { useTranslations } from "next-intl";
import { AlertTriangle, Info } from "lucide-react";
import { ApiError } from "@/lib/api/fetcher";
import type { Freshness } from "@/lib/api/types";
import { SkeletonLoader } from "@/components/states/skeleton-loader";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface DataStateProps {
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** True when the payload arrived but contains nothing to plot */
  empty?: boolean;
  /** Freshness block from the payload. Renders a notice when is_stale. */
  freshness?: Freshness;
  /**
   * Drop the block entirely instead of reporting anything. For content the
   * API declines to publish by design — a model with no forecast — where an
   * error or "no data" panel would describe a fault that does not exist.
   */
  hidden?: boolean;
  skeletonRows?: number;
  className?: string;
  children: React.ReactNode;
}

/**
 * Wrapper enforcing spec §16.4: every data component must express
 * loading / error / empty / stale / maintenance. Charts are never left
 * blank without a message.
 */
export function DataState({
  loading,
  error,
  onRetry,
  empty,
  freshness,
  hidden,
  skeletonRows = 4,
  className,
  children,
}: DataStateProps) {
  const t = useTranslations("common.dataState");

  if (hidden) return null;

  if (loading) {
    return (
      <div className={className} role="status" aria-label={t("loading")}>
        <SkeletonLoader rows={skeletonRows} />
      </div>
    );
  }

  if (error) {
    const maintenance = error instanceof ApiError && error.status === 503;
    return (
      <div
        className={cn(
          "flex flex-col items-start gap-3 rounded-lg border border-border bg-surface p-6",
          className
        )}
        role="alert"
      >
        <p className="flex items-center gap-2 text-sm text-ink">
          <AlertTriangle className="size-4 text-dim" aria-hidden="true" />
          {maintenance ? t("maintenance") : t("error")}
        </p>
        {onRetry && !maintenance && (
          <Button variant="ghost" size="sm" onClick={onRetry}>
            {t("retry")}
          </Button>
        )}
      </div>
    );
  }

  if (empty) {
    return (
      <div
        className={cn("rounded-lg border border-border bg-surface p-6", className)}
        role="status"
      >
        <p className="text-sm text-dim">{t("empty")}</p>
      </div>
    );
  }

  return (
    <div className={className}>
      {freshness?.is_stale && (
        <p
          className="mb-3 flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-xs text-dim"
          role="status"
        >
          <Info className="size-3.5" aria-hidden="true" />
          {t("stale")}
        </p>
      )}
      {children}
    </div>
  );
}
