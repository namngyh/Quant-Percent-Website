"use client";

import { useLocale, useTranslations } from "next-intl";
import { useApi } from "@/lib/api/fetcher";
import type { MarketOverview } from "@/lib/api/types";
import { fmtDateTime, fmtPrice, fmtSignedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Live index board, the evidence half of the hero.
 *
 * The old homepage opened with a sentence and made a visitor scroll before
 * anything proved the site was connected to a market. This puts real quotes
 * in the first screen, styled as a trading panel: monospaced figures aligned
 * on the decimal so the column scans vertically.
 *
 * It renders resting rows instead of an error card while data is in flight —
 * a red failure panel would be a worse first impression than a board that has
 * not filled in yet.
 *
 * The panel is the site's dark surface — the same navy the Model Modus section
 * uses, so the two dark moments on the page are recognisably one treatment
 * rather than two decisions. On a white hero it does the job an outline could
 * not: it reads as an instrument set on the page instead of a table that
 * failed to load its background.
 *
 * Gains and losses take `--positive-on-dark` / `--negative-on-dark`, which are
 * the same two hues as everywhere else lifted until they read against navy.
 * The meaning of the colour never changes with the surface; only its
 * lightness does.
 */
export function LiveBoard() {
  const t = useTranslations("home.pulse");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { data } = useApi<MarketOverview>("/api/v1/market/overview");
  const quotes = data?.quotes ?? [];
  const live = quotes.length > 0;

  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-accent-deep shadow-[0_30px_74px_-24px_rgb(16_39_61_/_0.55),0_6px_18px_rgb(15_27_42_/_0.12)]">
      <div className="flex items-center justify-between border-b border-white/10 bg-white/[0.04] px-5 py-3.5">
        <p className="text-[11px] uppercase tracking-[0.12em] text-white/55">
          {t("title")}
        </p>
        <span className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className={cn(
              "size-1.5 rounded-full",
              live ? "animate-pulse bg-positive-on-dark" : "bg-white/25"
            )}
          />
          <span className="tick text-[10px] uppercase tracking-[0.12em] text-white/45">
            {live ? "LIVE" : "···"}
          </span>
        </span>
      </div>

      <div className="divide-y divide-white/[0.08]">
        {(live ? quotes : [null, null, null]).map((q, i) => (
          <div
            key={q?.symbol ?? i}
            className="grid grid-cols-[1fr_auto_5.5rem] items-baseline gap-4 px-5 py-4"
          >
            {q ? (
              <>
                <span className="tick text-[13px] uppercase tracking-[0.06em] text-white/60">
                  {q.name}
                </span>
                <span className="tick text-xl font-medium tabular-nums text-white">
                  {fmtPrice(q.price, locale)}
                </span>
                <span
                  className={cn(
                    "tick text-right text-sm tabular-nums",
                    q.change_percent > 0 && "text-positive-on-dark",
                    q.change_percent < 0 && "text-negative-on-dark",
                    q.change_percent === 0 && "text-white/45"
                  )}
                >
                  {q.change_percent > 0 ? "▲" : q.change_percent < 0 ? "▼" : "—"}{" "}
                  {fmtSignedPercent(q.change_percent / 100, locale)}
                </span>
              </>
            ) : (
              <>
                <span className="h-3 w-20 rounded-full bg-white/10" />
                <span className="h-3 w-24 rounded-full bg-white/10" />
                <span className="h-3 w-14 justify-self-end rounded-full bg-white/10" />
              </>
            )}
          </div>
        ))}
      </div>

      {data && (
        <p className="figure border-t border-white/10 bg-white/[0.03] px-5 py-3 text-[10px] leading-relaxed text-white/45">
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
