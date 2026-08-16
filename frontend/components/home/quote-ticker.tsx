"use client";

import { useLocale, useTranslations } from "next-intl";
import { useApi } from "@/lib/api/fetcher";
import type { MarketOverview } from "@/lib/api/types";
import { fmtPrice, fmtSignedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * A band of live quotes scrolling under the hero.
 *
 * It is on the page for texture as much as for information — but it earns the
 * space because the texture is real data. The homepage read as flat partly
 * because nothing on it moved on its own; a strip of live prices moving is the
 * one decoration a market research site can add without inventing anything.
 *
 * Three quotes is not enough to fill a screen, so the list repeats until it
 * comfortably overflows and is then rendered twice more for the seamless loop
 * (see `.ticker` in globals.css). Rendering nothing until the feed answers is
 * deliberate: an empty scrolling band is worse than no band.
 */

/** Enough repeats that even three symbols overflow a wide viewport. */
const MIN_ITEMS = 12;

export function QuoteTicker() {
  // The band is the market overview, so it takes the board's own label rather
  // than introducing a second name for the same thing.
  const t = useTranslations("home.pulse");
  const locale = useLocale();
  const { data } = useApi<MarketOverview>("/api/v1/market/overview");
  const quotes = data?.quotes ?? [];

  if (quotes.length === 0) return null;

  const filled = Array.from(
    { length: Math.ceil(MIN_ITEMS / quotes.length) },
    () => quotes,
  ).flat();

  const row = (copy: number) =>
    filled.map((q, i) => (
      <span
        key={`${copy}-${q.symbol}-${i}`}
        className="flex shrink-0 items-baseline gap-3 px-7"
      >
        <span className="tick text-[11px] uppercase tracking-[0.12em] text-dim">
          {q.name}
        </span>
        <span className="tick text-[13px] font-medium tabular-nums text-foreground">
          {fmtPrice(q.price, locale)}
        </span>
        <span
          className={cn(
            "tick text-[12px] tabular-nums",
            q.change_percent > 0 && "text-positive",
            q.change_percent < 0 && "text-negative",
            q.change_percent === 0 && "text-dim",
          )}
        >
          {q.change_percent > 0 ? "▲" : q.change_percent < 0 ? "▼" : "—"}{" "}
          {fmtSignedPercent(q.change_percent / 100, locale)}
        </span>
        <span aria-hidden="true" className="ml-4 h-3 w-px bg-border" />
      </span>
    ));

  return (
    <div
      className="tint overflow-hidden border-y border-border py-3"
      /*
       * One label for the whole strip, and the contents hidden from assistive
       * technology. A screen reader announcing a dozen repeated quotes as they
       * scroll past is noise, and every figure in here is also on the board
       * above it, in a table, in reading order.
       */
      role="marquee"
      aria-label={t("title")}
    >
      <div className="ticker" aria-hidden="true">
        <div className="flex">{row(1)}</div>
        <div className="flex">{row(2)}</div>
      </div>
    </div>
  );
}
