/**
 * Sections that depend on the model pipeline writing to the `quant` schema.
 *
 * Those tables are empty until an inference runner fills them, and a section
 * with no data is worse than no section: it renders as an empty table or an
 * error panel on a page a visitor was told holds model output. Each flag
 * hides one section until its writer exists.
 *
 * Flip a flag to `true` once the matching table has rows. Nothing else needs
 * to change — the components, API routes and translations all stay in place.
 *
 * Status checked 2026-08-04: every table below is empty.
 */
export const LIVE_SECTIONS = {
  /**
   * Market Intelligence → Risk tab.
   * Needs `quant.risk_metrics`, plus `risk_mc_distribution` and
   * `risk_scenarios` for the distribution chart and stress table.
   * While empty, `/api/v1/market/risk` returns 503.
   */
  risk: false,

  /**
   * Market Intelligence → Stocks tab (VN30 ranking table).
   * Needs `quant.stock_rankings`.
   * While empty, `/api/v1/market/vn30/constituents` returns zero rows.
   */
  stockRankings: false,
} as const;

/**
 * Deliberately not a flag: the model's read on the market — regime, public
 * signal, model consensus, up/down probability, volatility, risk state —
 * shown on the homepage pulse, the Overview tab and the VN30F1M tab.
 *
 * `/api/v1/market/overview` returns null for each of those until a run has
 * written `quant.market_state`, and the components drop the matching tile
 * when the value is null. That is self-correcting: the tiles reappear the
 * moment real values arrive, with no flag to remember to flip.
 */

export type LiveSection = keyof typeof LIVE_SECTIONS;
