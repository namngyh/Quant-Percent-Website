"use client";

import { useLocale, useTranslations } from "next-intl";
import { useApi } from "@/lib/api/fetcher";
import type { MarketOverview } from "@/lib/api/types";
import { fmtDateTime, fmtPrice, fmtSignedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Live index board for the dark hero.
 *
 * The old homepage opened with a sentence and made a visitor scroll before
 * anything proved the site was connected to a market. This puts real quotes
 * in the first screen, styled as a trading panel: monospaced figures on a
 * dark surface, aligned on the decimal so the column scans vertically.
 *
 * It renders resting rows instead of an error card while data is in flight —
 * a red failure panel would be a worse first impression than a board that has
 * not filled in yet.
 */
export function LiveBoard() {
  const t = useTranslations("home.pulse");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { data } = useApi<MarketOverview>("/api/v1/market/overview");
  const quotes = data?.quotes ?? [];
  const live = quotes.length > 0;

  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-white/[0.03] shadow-2xl shadow-black/40 backdrop-blur">
      <div className="flex items-center justify-between border-b border-white/10 px-5 py-3.5">
        <p className="text-[11px] uppercase tracking-[0.14em] text-white/50">
          {t("title")}
        </p>
        <span className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className={cn(
              "size-1.5 rounded-full",
              live ? "animate-pulse bg-positive" : "bg-white/25"
            )}
          />
          <span className="tick text-[10px] uppercase tracking-[0.12em] text-white/40">
            {live ? "LIVE" : "···"}
          </span>
        </span>
      </div>

      <div className="divide-y divide-white/[0.07]">
        {(live ? quotes : [null, null, null]).map((q, i) => (
          <div
            key={q?.symbol ?? i}
            className="grid grid-cols-[1fr_auto_5.5rem] items-baseline gap-4 px-5 py-4"
          >
            {q ? (
              <>
                <span className="tick text-[13px] uppercase tracking-[0.06em] text-white/70">
                  {q.name}
                </span>
                <span className="tick text-xl font-medium tabular-nums text-white">
                  {fmtPrice(q.price, locale)}
                </span>
                <span
                  className={cn(
                    "tick text-right text-sm tabular-nums",
                    q.change_percent > 0 && "text-positive",
                    q.change_percent < 0 && "text-negative",
                    q.change_percent === 0 && "text-white/40"
                  )}
                >
                  {q.change_percent > 0 ? "▲" : q.change_percent < 0 ? "▼" : "—"}{" "}
                  {fmtSignedPercent(q.change_percent / 100, locale)}
                </span>
              </>
            ) : (
              <>
                <span className="h-3 w-20 rounded bg-white/10" />
                <span className="h-3 w-24 rounded bg-white/10" />
                <span className="h-3 w-14 justify-self-end rounded bg-white/10" />
              </>
            )}
          </div>
        ))}
      </div>

      {data && (
        <p className="figure border-t border-white/10 px-5 py-3 text-[10px] leading-relaxed text-white/35">
          {tc("freshness.dataAsOf")}: {fmtDateTime(data.data_as_of, locale)}
          {data.delay_minutes > 0 && (
            <>
              {" · "}
              {tc("freshness.delayedBy", { minutes: data.delay_minutes })}
            </>
          )}
        </p>
      )}
    </div>
  );
}
