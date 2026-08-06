"use client";

import { useCallback, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { OverviewTab } from "@/components/market/overview-tab";
import { IndexTab } from "@/components/market/index-tab";
import { FuturesTab } from "@/components/market/futures-tab";
import { StocksTab } from "@/components/market/stocks-tab";
import { RiskTab } from "@/components/market/risk-tab";
import { LIVE_SECTIONS } from "@/config/live-sections";
import { cn } from "@/lib/utils";

const ALL_TABS = [
  { id: "overview", key: "overview" },
  { id: "vnindex", key: "vnindex" },
  { id: "vn30", key: "vn30" },
  { id: "vn30f1m", key: "vn30f1m" },
  { id: "stocks", key: "stocks" },
  { id: "risk", key: "risk" },
] as const;

type TabId = (typeof ALL_TABS)[number]["id"];

/** Tabs whose data the model pipeline has not produced yet stay hidden. */
const TABS = ALL_TABS.filter(
  (tab) =>
    (tab.id !== "risk" || LIVE_SECTIONS.risk) &&
    (tab.id !== "stocks" || LIVE_SECTIONS.stockRankings)
);

/** Active tab lives in ?tab= so views are linkable. */
export function MarketTabs() {
  const t = useTranslations("market.tabs");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const listRef = useRef<HTMLDivElement>(null);

  const raw = searchParams.get("tab");
  const active: TabId = TABS.some((tab) => tab.id === raw)
    ? (raw as TabId)
    : "overview";

  const select = useCallback(
    (id: TabId) => {
      router.replace(
        id === "overview" ? pathname : `${pathname}?tab=${id}`,
        { scroll: false }
      );
    },
    [pathname, router]
  );

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const idx = TABS.findIndex((tab) => tab.id === active);
    const next =
      TABS[(idx + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
    select(next.id);
    const btn = listRef.current?.querySelector<HTMLButtonElement>(
      `[data-tab="${next.id}"]`
    );
    btn?.focus();
  };

  return (
    <div>
      <div
        ref={listRef}
        role="tablist"
        aria-label={t("overview")}
        onKeyDown={onKeyDown}
        className="scrollbar-none -mx-6 flex gap-1 overflow-x-auto border-b border-border px-6"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            data-tab={tab.id}
            aria-selected={active === tab.id}
            aria-controls={`panel-${tab.id}`}
            tabIndex={active === tab.id ? 0 : -1}
            onClick={() => select(tab.id)}
            className={cn(
              "-mb-px shrink-0 whitespace-nowrap border-b-2 px-4 py-3 text-[13px] font-medium transition-colors",
              active === tab.id
                ? "border-brand text-brand"
                : "border-transparent text-dim hover:text-brand"
            )}
          >
            {t(tab.key)}
          </button>
        ))}
      </div>

      <div
        id={`panel-${active}`}
        role="tabpanel"
        aria-labelledby={active}
        className="pt-8"
      >
        {active === "overview" && <OverviewTab />}
        {active === "vnindex" && <IndexTab symbol="VNINDEX" />}
        {active === "vn30" && <IndexTab symbol="VN30" />}
        {active === "vn30f1m" && <FuturesTab />}
        {active === "stocks" && <StocksTab />}
        {active === "risk" && <RiskTab />}
      </div>
    </div>
  );
}
