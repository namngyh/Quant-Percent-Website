import { getStrategy } from "@/config/strategies";
import type { Freshness } from "@/lib/api/types";

/**
 * Freshness for a performance report. Unlike market data these are
 * finished research runs: `data_as_of` is the last day of the evaluation
 * window and the payload is never stale in the market-data sense.
 */
export function reportFreshness(slug: string): Freshness {
  const strategy = getStrategy(slug);
  const asOf = strategy
    ? new Date(`${strategy.periodEnd}T15:00:00+07:00`).toISOString()
    : new Date().toISOString();
  return {
    data_as_of: asOf,
    // The extraction date of the published run
    generated_at: new Date("2026-07-25T00:00:00+07:00").toISOString(),
    source_status: "ok",
    is_stale: false,
    delay_minutes: 0,
  };
}
