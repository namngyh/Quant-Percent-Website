"use client";

import { useTranslations } from "next-intl";
import {
  Archive,
  CircleCheck,
  FlaskConical,
  Radio,
  type LucideIcon,
} from "lucide-react";
import type { PublicSignal, Regime, RiskState } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/**
 * State badges use a symbol and text label, never color alone.
 * alone (spec §15.1). Colors stay muted and secondary.
 */

const REGIME_GLYPH: Record<Regime, string> = {
  bullish: "▲",
  bullish_transition: "△",
  bearish: "▼",
  bearish_transition: "▽",
  sideways: "–",
  turbulent: "≈",
};

export function RegimeBadge({
  regime,
  className,
}: {
  regime: Regime;
  className?: string;
}) {
  const t = useTranslations("common.regime");
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs font-medium",
        (regime === "bullish" || regime === "bullish_transition") &&
          "border-positive/35 bg-positive/5 text-positive",
        (regime === "bearish" || regime === "bearish_transition") &&
          "border-negative/35 bg-negative/5 text-negative",
        regime === "turbulent" &&
          "border-signal/35 bg-signal-soft text-signal-strong",
        className
      )}
    >
      <span aria-hidden="true">
        {REGIME_GLYPH[regime]}
      </span>
      {t(regime)}
    </span>
  );
}

const RISK_LEVEL: Record<RiskState, number> = {
  low: 1,
  moderate: 2,
  elevated: 3,
  high: 4,
};

export function RiskBadge({
  risk,
  className,
}: {
  risk: RiskState;
  className?: string;
}) {
  const t = useTranslations("common.riskState");
  const level = RISK_LEVEL[risk];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs font-medium",
        level === 4 && "border-negative/40 bg-negative/5 text-negative",
        level === 3 && "border-signal/35 bg-signal-soft text-signal-strong",
        level === 1 && "border-positive/30 bg-positive/5 text-positive",
        className
      )}
    >
      <span aria-hidden="true" className="tracking-[0.15em]">
        {"●".repeat(level)}
        {"○".repeat(4 - level)}
      </span>
      {t(risk)}
    </span>
  );
}

/** Public trading-system state (§8.5): Bullish/Neutral/Defensive/High Risk/Low Conviction. */
export function SignalBadge({
  signal,
  className,
}: {
  signal: PublicSignal;
  className?: string;
}) {
  const t = useTranslations("common.signal");
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.08em]",
        signal === "bullish" &&
          "border-positive/35 bg-positive/5 text-positive",
        signal === "neutral" &&
          "border-border bg-surface text-foreground",
        signal === "defensive" &&
          "border-signal/35 bg-signal-soft text-signal-strong",
        signal === "high_risk" &&
          "border-negative/40 bg-negative/5 text-negative",
        signal === "low_conviction" &&
          "border-brand/35 bg-brand-soft text-brand-strong",
        className
      )}
    >
      {t(signal)}
    </span>
  );
}

export function StatusBadge({
  status,
  className,
  compact = false,
}: {
  status: "active" | "paper_trading" | "experimental" | "archived";
  className?: string;
  compact?: boolean;
}) {
  const t = useTranslations("common.modelStatus");
  const iconByStatus: Record<
    "active" | "paper_trading" | "experimental" | "archived",
    LucideIcon
  > = {
    active: CircleCheck,
    paper_trading: Radio,
    experimental: FlaskConical,
    archived: Archive,
  };
  const Icon = iconByStatus[status];

  if (compact) {
    return (
      <span
        title={t(status)}
        aria-label={t(status)}
        className={cn(
          "inline-flex size-8 shrink-0 items-center justify-center rounded-full border bg-background",
          status === "active" && "border-positive/35 text-positive",
          status === "paper_trading" && "border-signal/35 text-signal-strong",
          status === "experimental" && "border-brand/35 text-brand",
          status === "archived" && "border-border text-dim",
          className
        )}
      >
        <Icon className="size-4" aria-hidden="true" />
      </span>
    );
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.08em]",
        status === "archived" ? "text-dim" : "text-foreground",
        className
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "size-1.5 rounded-full",
          status === "active" && "bg-positive",
          status === "paper_trading" && "bg-signal",
          status === "experimental" && "bg-brand",
          status === "archived" && "bg-lightgray"
        )}
      />
      {t(status)}
    </span>
  );
}
