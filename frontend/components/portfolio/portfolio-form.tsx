"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Plus, Trash2 } from "lucide-react";
import { useApi } from "@/lib/api/fetcher";
import type { PortfolioRequestPayload, TradableSymbols } from "@/lib/api/types";

/**
 * Portfolio entry.
 *
 * Cost basis is optional on purpose: a reader testing a hypothetical basket
 * has no cost basis, and demanding one would push them to invent a number
 * that then shows up as a profit figure. Leave it blank and the profit
 * columns report nothing rather than something wrong.
 *
 * Money is entered in dong, the unit a reader thinks in. The feed quotes
 * stocks in thousands; the backend does that conversion.
 */

interface Row {
  id: number;
  symbol: string;
  quantity: string;
  costBasis: string;
}

const HORIZONS = [
  { days: 21, key: "m1" },
  { days: 63, key: "m3" },
  { days: 126, key: "m6" },
  { days: 252, key: "y1" },
] as const;

let nextId = 1;
const blankRow = (): Row => ({
  id: nextId++,
  symbol: "",
  quantity: "",
  costBasis: "",
});

function parseNumber(raw: string): number | null {
  // Accept "1.000" and "1,000" and "1 000": VN keyboards produce all three
  // and rejecting them would read as the form being broken.
  const cleaned = raw.replace(/[\s.,]/g, "");
  if (cleaned === "") return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

export function PortfolioForm({
  onSubmit,
  pending,
}: {
  onSubmit: (payload: PortfolioRequestPayload) => void;
  pending: boolean;
}) {
  const t = useTranslations("portfolio.form");
  const [rows, setRows] = useState<Row[]>(() => [blankRow(), blankRow()]);
  const [cash, setCash] = useState("");
  const [horizon, setHorizon] = useState<number>(63);
  const [error, setError] = useState<string | null>(null);

  // ~390 HOSE tickers: a native datalist gives type-ahead without shipping a
  // combobox library, and it degrades to a plain text field if unsupported.
  const symbols = useApi<TradableSymbols>("/api/v1/market/symbols");
  const known = useMemo(() => {
    const map = new Map<string, { name: string; sessions: number }>();
    for (const row of symbols.data?.rows ?? []) {
      map.set(row.symbol, { name: row.name, sessions: row.sessions });
    }
    return map;
  }, [symbols.data]);

  const update = (id: number, patch: Partial<Row>) =>
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  const remove = (id: number) =>
    setRows((prev) => (prev.length > 1 ? prev.filter((r) => r.id !== id) : prev));

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const holdings = [];
    const seen = new Set<string>();
    for (const row of rows) {
      const symbol = row.symbol.trim().toUpperCase();
      if (!symbol) continue;
      const quantity = parseNumber(row.quantity);
      if (quantity === null || quantity <= 0) {
        setError(t("errors.quantity", { symbol }));
        return;
      }
      if (seen.has(symbol)) {
        setError(t("errors.duplicate", { symbol }));
        return;
      }
      seen.add(symbol);
      const costBasis = parseNumber(row.costBasis);
      holdings.push({
        symbol,
        quantity,
        cost_basis: costBasis !== null && costBasis > 0 ? costBasis : null,
      });
    }

    if (holdings.length === 0) {
      setError(t("errors.empty"));
      return;
    }

    onSubmit({
      holdings,
      cash: parseNumber(cash) ?? 0,
      horizon_days: horizon,
    });
  }

  return (
    <form onSubmit={submit} className="qp-panel p-6 sm:p-7">
      <h2 className="text-lg font-semibold">{t("heading")}</h2>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-dim">
        {t("lead")}
      </p>

      <datalist id="qp-symbols">
        {[...known.entries()].map(([code, info]) => (
          <option key={code} value={code}>
            {info.name}
          </option>
        ))}
      </datalist>

      {/* A three-column table needs ~576px and would push a 390px screen
          sideways, so the fields stack on mobile and line up from `sm` on.
          Column headings only exist once the columns do; below that each
          field carries its own visible label. */}
      <div className="mt-6">
        <div className="hidden border-b border-border pb-2 sm:grid sm:grid-cols-[1fr_1fr_1fr_2.5rem] sm:gap-3">
          {(["symbol", "quantity", "costBasis"] as const).map((key) => (
            <span
              key={key}
              className="text-xs font-medium uppercase tracking-[0.06em] text-dim"
            >
              {t(key)}
            </span>
          ))}
          <span className="sr-only">{t("remove")}</span>
        </div>

        <ul className="space-y-4 sm:space-y-0">
          {rows.map((row) => (
            <li
              key={row.id}
              className="grid gap-3 rounded-lg border border-border p-4 sm:grid-cols-[1fr_1fr_1fr_2.5rem] sm:items-center sm:rounded-none sm:border-0 sm:border-b sm:border-border/60 sm:p-0 sm:py-2"
            >
              <label className="grid gap-1.5">
                <span className="text-xs font-medium uppercase tracking-[0.06em] text-dim sm:sr-only">
                  {t("symbol")}
                </span>
                <input
                  value={row.symbol}
                  onChange={(e) => update(row.id, { symbol: e.target.value })}
                  placeholder={t("symbolPlaceholder")}
                  list="qp-symbols"
                  autoComplete="off"
                  spellCheck={false}
                  className="figure w-full rounded-md border border-border bg-background px-3 py-2 uppercase outline-none focus:border-brand"
                />
                {(() => {
                  const code = row.symbol.trim().toUpperCase();
                  if (!code) return null;
                  const hit = known.get(code);
                  return hit ? (
                    <span className="truncate text-xs text-dim">{hit.name}</span>
                  ) : known.size > 0 ? (
                    <span className="text-xs text-caution">{t("unknownSymbol")}</span>
                  ) : null;
                })()}
              </label>

              <label className="grid gap-1.5">
                <span className="text-xs font-medium uppercase tracking-[0.06em] text-dim sm:sr-only">
                  {t("quantity")}
                </span>
                <input
                  value={row.quantity}
                  onChange={(e) => update(row.id, { quantity: e.target.value })}
                  inputMode="numeric"
                  placeholder="1.000"
                  className="figure w-full rounded-md border border-border bg-background px-3 py-2 text-right outline-none focus:border-brand"
                />
              </label>

              <label className="grid gap-1.5">
                <span className="text-xs font-medium uppercase tracking-[0.06em] text-dim sm:sr-only">
                  {t("costBasis")}
                </span>
                <input
                  value={row.costBasis}
                  onChange={(e) => update(row.id, { costBasis: e.target.value })}
                  inputMode="numeric"
                  placeholder={t("optional")}
                  className="figure w-full rounded-md border border-border bg-background px-3 py-2 text-right outline-none focus:border-brand"
                />
              </label>

              <div className="justify-self-end">
                <button
                  type="button"
                  onClick={() => remove(row.id)}
                  disabled={rows.length === 1}
                  aria-label={t("remove")}
                  className="rounded-md p-2 text-dim transition-colors hover:bg-surface hover:text-negative disabled:opacity-30"
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <button
        type="button"
        onClick={() => setRows((prev) => [...prev, blankRow()])}
        className="mt-3 inline-flex items-center gap-2 text-[13px] font-medium text-brand hover:underline"
      >
        <Plus className="h-4 w-4" aria-hidden="true" />
        {t("addRow")}
      </button>

      <div className="mt-7 grid gap-6 sm:grid-cols-2">
        <div>
          <label
            htmlFor="portfolio-cash"
            className="text-xs font-medium uppercase tracking-[0.06em] text-dim"
          >
            {t("cash")}
          </label>
          <input
            id="portfolio-cash"
            value={cash}
            onChange={(e) => setCash(e.target.value)}
            inputMode="numeric"
            placeholder="50.000.000"
            className="figure mt-2 w-full rounded-md border border-border bg-background px-3 py-2 text-right outline-none focus:border-brand"
          />
          <p className="mt-1.5 text-xs text-dim">{t("cashNote")}</p>
        </div>

        <div>
          <span className="text-xs font-medium uppercase tracking-[0.06em] text-dim">
            {t("horizon")}
          </span>
          <div className="mt-2 flex flex-wrap gap-2">
            {HORIZONS.map((h) => (
              <button
                key={h.days}
                type="button"
                onClick={() => setHorizon(h.days)}
                aria-pressed={horizon === h.days}
                className={
                  horizon === h.days
                    ? "rounded-md border border-brand bg-brand-soft px-3 py-2 text-[13px] font-medium text-brand"
                    : "rounded-md border border-border px-3 py-2 text-[13px] text-ink transition-colors hover:border-brand"
                }
              >
                {t(`horizons.${h.key}`)}
              </button>
            ))}
          </div>
          <p className="mt-1.5 text-xs text-dim">{t("horizonNote")}</p>
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-5 text-sm text-negative">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="mt-7 rounded-md bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-strong disabled:opacity-60"
      >
        {pending ? t("analysing") : t("analyse")}
      </button>

      <p className="mt-4 max-w-2xl text-xs leading-relaxed text-dim">
        {t("privacy")}
      </p>
    </form>
  );
}
