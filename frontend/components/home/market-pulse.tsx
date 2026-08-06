"use client";

import { useLocale, useTranslations } from "next-intl";
import { useApi } from "@/lib/api/fetcher";
import type { MarketOverview } from "@/lib/api/types";
import { DataFreshnessLabel } from "@/components/states/data-freshness-label";
import { RegimeBadge, RiskBadge } from "@/components/market/badges";
import { InfoTip } from "@/components/info-tip";
import { fmtPercent } from "@/lib/format";

/**
 * The model's read on the market, below the hero.
 *
 * Quotes are not repeated here — the hero board already carries them, and
 * showing the same three numbers twice on one screen made the page look
 * padded. What is left is the part the hero cannot show: regime, direction,
 * volatility and risk state.
 *
 * Every one of those comes from `quant.market_state`, which is empty until an
 * inference runner writes to it. Rather than render a row of empty cells —
 * the previous version left four blank columns in a seven-column grid, which
 * read as a broken layout — the whole section removes itself and reappears on
 * its own once the values exist.
 */
export function MarketPulse() {
  const t = useTranslations("home.pulse");
  const g = useTranslations("glossary");
  const locale = useLocale();
  const { data } = useApi<MarketOverview>("/api/v1/market/overview");

  if (!data) return null;

  const tiles = [
    data.regime !== null && {
      key: "regime",
      accent: "border-brand",
      label: t("regime"),
      tip: g("regime"),
      body: <RegimeBadge regime={data.regime} className="mt-3" />,
    },
    data.probability_up !== null && {
      key: "probabilityUp",
      accent: "border-positive",
      label: t("probabilityUp"),
      tip: g("probabilityUp"),
      body: (
        <p className="figure mt-2 text-3xl font-medium">
          {fmtPercent(data.probability_up, locale)}
        </p>
      ),
    },
    data.volatility !== null && {
      key: "volatility",
      accent: "border-signal",
      label: t("volatility"),
      tip: g("volatility"),
      body: (
        <p className="figure mt-2 text-3xl font-medium">
          {fmtPercent(data.volatility, locale)}
        </p>
      ),
    },
    data.risk_state !== null && {
      key: "riskState",
      accent: "border-negative",
      label: t("riskState"),
      tip: g("riskState"),
      body: <RiskBadge risk={data.risk_state} className="mt-3" />,
    },
  ].filter(Boolean) as {
    key: string;
    accent: string;
    label: string;
    tip: string;
    body: React.ReactNode;
  }[];

  if (tiles.length === 0) return null;

  return (
    <section className="border-y border-border bg-surface">
      <div className="container-qp py-12">
        <p className="eyebrow">{t("title")}</p>
        {/* Columns follow the number of tiles, so the row is never padded
            out with empty cells. */}
        <div
          className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2"
          style={{
            gridTemplateColumns:
              tiles.length > 2
                ? `repeat(${tiles.length}, minmax(0, 1fr))`
                : undefined,
          }}
        >
          {tiles.map((tile) => (
            <div
              key={tile.key}
              className={`border-t-2 bg-background p-6 ${tile.accent}`}
            >
              <p className="flex items-center gap-1.5 text-xs font-medium text-dim">
                {tile.label} <InfoTip text={tile.tip} />
              </p>
              {tile.body}
            </div>
          ))}
        </div>
        <DataFreshnessLabel freshness={data} />
      </div>
    </section>
  );
}
