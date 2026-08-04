"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useApi } from "@/lib/api/fetcher";
import type { Constituents, Regime, StockRow } from "@/lib/api/types";
import { DataState } from "@/components/states/data-state";
import { DataFreshnessLabel } from "@/components/states/data-freshness-label";
import { RegimeBadge, RiskBadge } from "@/components/market/badges";
import { Input } from "@/components/ui/input";
import {
  directionSymbol,
  fmtPercent,
  fmtPrice,
  fmtSignedPercent,
} from "@/lib/format";
import { cn } from "@/lib/utils";

type SortKey = keyof Pick<
  StockRow,
  "ticker" | "price" | "change_percent" | "probability_up" | "volatility" | "rank"
>;

const REGIME_OPTIONS: Regime[] = [
  "bullish",
  "bullish_transition",
  "sideways",
  "bearish_transition",
  "bearish",
  "turbulent",
];

/** VN30 stock ranking table (§8.6): search, sort, filter, pagination, mobile cards. */
export function StocksTab() {
  const t = useTranslations("market.stocks");
  const tc = useTranslations("common");
  const tr = useTranslations("common.regime");
  const locale = useLocale();
  const { data, error, isLoading, mutate } = useApi<Constituents>(
    "/api/v1/market/vn30/constituents"
  );

  const [search, setSearch] = useState("");
  const [regime, setRegime] = useState<Regime | "all">("all");
  const [sortKey, setSortKey] = useState<SortKey>("rank");
  const [sortDir, setSortDir] = useState<1 | -1>(1);

  const rows = useMemo(() => {
    let out = data?.rows ?? [];
    if (search) {
      out = out.filter((r) =>
        r.ticker.toLowerCase().includes(search.trim().toLowerCase())
      );
    }
    if (regime !== "all") out = out.filter((r) => r.regime === regime);
    out = [...out].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp =
        typeof av === "string"
          ? av.localeCompare(bv as string)
          : (av as number) - (bv as number);
      return cmp * sortDir;
    });
    return out;
  }, [data, search, regime, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 1 ? -1 : 1));
    } else {
      setSortKey(key);
      setSortDir(1);
    }
  };

  const headers: { key: SortKey | "regime" | "risk_state"; label: string; sortable: boolean; numeric?: boolean }[] = [
    { key: "ticker", label: t("columns.ticker"), sortable: true },
    { key: "price", label: t("columns.price"), sortable: true, numeric: true },
    { key: "change_percent", label: t("columns.change"), sortable: true, numeric: true },
    { key: "regime", label: t("columns.regime"), sortable: false },
    { key: "probability_up", label: t("columns.probabilityUp"), sortable: true, numeric: true },
    { key: "volatility", label: t("columns.volatility"), sortable: true, numeric: true },
    { key: "risk_state", label: t("columns.risk"), sortable: false },
    { key: "rank", label: t("columns.rank"), sortable: true, numeric: true },
  ];

  return (
    <DataState
      loading={isLoading}
      error={error}
      onRetry={() => mutate()}
      empty={data && data.rows.length === 0}
      freshness={data}
      skeletonRows={10}
    >
      {data && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("searchPlaceholder")}
              aria-label={tc("search")}
              className="h-10 max-w-56"
            />
            <select
              value={regime}
              onChange={(e) => setRegime(e.target.value as Regime | "all")}
              aria-label={t("filterRegime")}
              className="h-10 rounded-lg border border-input bg-background px-3 text-sm outline-none transition-[border-color,box-shadow] focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand/15"
            >
              <option value="all">{tc("all")}</option>
              {REGIME_OPTIONS.map((r) => (
                <option key={r} value={r}>
                  {tr(r)}
                </option>
              ))}
            </select>
          </div>

          {rows.length === 0 ? (
            <p className="mt-6 rounded-lg border border-border bg-surface p-6 text-sm text-dim">
              {t("noResults")}
            </p>
          ) : (
            <>
              {/* Desktop table */}
              <div className="mt-5 hidden overflow-x-auto rounded-lg border border-border shadow-sm sm:block">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="border-b border-border bg-surface text-left">
                      {headers.map((h) => (
                        <th
                          key={h.key}
                          scope="col"
                          aria-sort={
                            h.key === sortKey
                              ? sortDir === 1
                                ? "ascending"
                                : "descending"
                              : undefined
                          }
                          className={cn(
                            "px-4 py-3 font-medium text-dim",
                            h.numeric && "text-right"
                          )}
                        >
                          {h.sortable ? (
                            <button
                              type="button"
                              onClick={() => toggleSort(h.key as SortKey)}
                              className="inline-flex items-center gap-1 hover:text-foreground"
                            >
                              {h.label}
                              {h.key === sortKey &&
                                (sortDir === 1 ? (
                                  <ArrowUp className="size-3" aria-hidden="true" />
                                ) : (
                                  <ArrowDown className="size-3" aria-hidden="true" />
                                ))}
                            </button>
                          ) : (
                            h.label
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.ticker} className="border-b border-border last:border-0">
                        <td className="figure px-4 py-3 font-semibold">{r.ticker}</td>
                        <td className="figure px-4 py-3 text-right">
                          {fmtPrice(r.price, locale)}
                        </td>
                        <td
                          className={cn(
                            "figure px-4 py-3 text-right",
                            r.change_percent > 0 && "text-positive",
                            r.change_percent < 0 && "text-negative"
                          )}
                        >
                          <span aria-hidden="true">
                            {directionSymbol(r.change_percent)}{" "}
                          </span>
                          {fmtSignedPercent(r.change_percent / 100, locale)}
                        </td>
                        <td className="px-4 py-3">
                          <RegimeBadge regime={r.regime} />
                        </td>
                        <td className="figure px-4 py-3 text-right">
                          {fmtPercent(r.probability_up, locale)}
                        </td>
                        <td className="figure px-4 py-3 text-right">
                          {fmtPercent(r.volatility, locale)}
                        </td>
                        <td className="px-4 py-3">
                          <RiskBadge risk={r.risk_state} />
                        </td>
                        <td className="figure px-4 py-3 text-right">{r.rank}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Mobile stacked cards (§16.5) */}
              <ul className="mt-5 space-y-3 sm:hidden">
                {rows.map((r) => (
                  <li key={r.ticker} className="qp-panel p-4">
                    <div className="flex items-center justify-between">
                      <p className="figure text-base font-semibold">{r.ticker}</p>
                      <p className="figure text-sm">
                        #{r.rank} · {fmtPrice(r.price, locale)}
                      </p>
                    </div>
                    <p
                      className={cn(
                        "figure mt-1 text-sm",
                        r.change_percent > 0 && "text-positive",
                        r.change_percent < 0 && "text-negative"
                      )}
                    >
                      <span aria-hidden="true">
                        {directionSymbol(r.change_percent)}{" "}
                      </span>
                      {fmtSignedPercent(r.change_percent / 100, locale)}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <RegimeBadge regime={r.regime} />
                      <RiskBadge risk={r.risk_state} />
                    </div>
                    <p className="figure mt-3 text-xs text-dim">
                      {t("columns.probabilityUp")}:{" "}
                      {fmtPercent(r.probability_up, locale)} ·{" "}
                      {t("columns.volatility")}: {fmtPercent(r.volatility, locale)}
                    </p>
                  </li>
                ))}
              </ul>

            </>
          )}
          <DataFreshnessLabel freshness={data} />
        </>
      )}
    </DataState>
  );
}
