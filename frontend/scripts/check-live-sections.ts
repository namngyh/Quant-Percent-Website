/**
 * Print which Market Intelligence tabs are visible for the current
 * LIVE_SECTIONS flags, and which `quant` tables each hidden tab is waiting
 * for. The tab list renders on the client, so this is the cheap way to
 * confirm the flags without driving a browser.
 *
 * Run: npx tsx scripts/check-live-sections.ts
 */
import { LIVE_SECTIONS } from "../config/live-sections";

const ALL_TABS = [
  { id: "overview", needs: null },
  { id: "vnindex", needs: null },
  { id: "vn30", needs: null },
  { id: "vn30f1m", needs: null },
  { id: "stocks", needs: "quant.stock_rankings" },
  { id: "risk", needs: "quant.risk_metrics" },
] as const;

// Must mirror the filter in components/market/market-tabs.tsx
const visible = ALL_TABS.filter(
  (tab) =>
    (tab.id !== "risk" || LIVE_SECTIONS.risk) &&
    (tab.id !== "stocks" || LIVE_SECTIONS.stockRankings)
);

console.log("LIVE_SECTIONS:", LIVE_SECTIONS);
console.log();
for (const tab of ALL_TABS) {
  const shown = visible.some((v) => v.id === tab.id);
  const note = shown ? "" : `  ← chờ ${tab.needs}`;
  console.log(`  ${shown ? "hiện" : "ẩn "}  ${tab.id.padEnd(9)}${note}`);
}
console.log();
console.log(
  `${visible.length}/${ALL_TABS.length} tab hiển thị:`,
  visible.map((t) => t.id).join(", ")
);
