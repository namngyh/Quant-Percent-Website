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
  /**
   * Min-height utility classes holding the space the loaded content will take.
   *
   * Without this, loading / error / empty collapse to the height of a small
   * notice, and any layout that measured itself against the loaded content
   * silently breaks — see the seam in `modus-comparison.tsx`, where the white
   * section is pulled up over the dark one by a fixed amount and ate the
   * headline whenever the chart was not there to hold the section open.
   *
   * It goes on an outer wrapper rather than on the notice itself, so the
   * error card keeps its own size and sits at the top of the reserved box
   * instead of being stretched into a half-empty panel.
   */
  reserve?: string;
  /**
   * Which ground the block sits on. The default styling is for the white
   * page; `"dark"` is for the navy sections, where `bg-surface` and
   * `text-ink` are all but invisible.
   */
  tone?: "light" | "dark";
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
  reserve,
  tone = "light",
  children,
}: DataStateProps) {
  const t = useTranslations("common.dataState");

  if (hidden) return null;

  const dark = tone === "dark";
  /* The notice's own box. On dark it cannot use `bg-surface`/`border-border`,
   * which are a near-white fill and a light hairline. */
  const card = dark
    ? "border-white/10 bg-white/5"
    : "border-border bg-surface";

  /* `reserve` holds the space; `className` stays on the notice so callers
   * keep control of its margins. When there is nothing to reserve the
   * wrapper is skipped entirely, which is what every existing call site
   * gets. */
  const hold = (node: React.ReactNode) =>
    reserve ? <div className={reserve}>{node}</div> : node;

  if (loading) {
    return hold(
      <div className={className} role="status" aria-label={t("loading")}>
        <SkeletonLoader
          rows={skeletonRows}
          barClassName={dark ? "bg-white/10" : undefined}
        />
      </div>
    );
  }

  if (error) {
    const maintenance = error instanceof ApiError && error.status === 503;
    return hold(
      <div
        className={cn(
          "flex flex-col items-start gap-3 rounded-lg border p-6",
          card,
          className
        )}
        role="alert"
      >
        <p
          className={cn(
            "flex items-center gap-2 text-sm",
            dark ? "text-white" : "text-ink"
          )}
        >
          <AlertTriangle
            className={cn("size-4", dark ? "text-white/60" : "text-dim")}
            aria-hidden="true"
          />
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
    return hold(
      <div
        className={cn("rounded-lg border p-6", card, className)}
        role="status"
      >
        <p className={cn("text-sm", dark ? "text-white/70" : "text-dim")}>
          {t("empty")}
        </p>
      </div>
    );
  }

  return (
    <div className={className}>
      {freshness?.is_stale && (
        <p
          className={cn(
            "mb-3 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs",
            card,
            dark ? "text-white/70" : "text-dim"
          )}
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
