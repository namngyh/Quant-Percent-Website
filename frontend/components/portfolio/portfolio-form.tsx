"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ChevronDown, Plus, Trash2 } from "lucide-react";
import { useApi } from "@/lib/api/fetcher";
import type { PortfolioRequestPayload, TradableSymbols } from "@/lib/api/types";
import { fmtNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Portfolio entry.
 *
 * Cost basis is optional on purpose: a reader testing a hypothetical basket
 * has no cost basis, and demanding one would push them to invent a number
 * that then shows up as a profit figure. Leave it blank and the profit
 * columns report nothing rather than something wrong.
 *
 * Cash is entered in dong. Cost basis is entered the way a price board
 * shows it — in thousands, "25.5" for 25,500 — because that is the number a
 * reader has in front of them; see `costBasisVnd` for how a figure typed in
 * dong is still accepted. The request carries dong throughout.
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

export function parseNumber(raw: string): number | null {
  // VN keyboards produce "1.000", "1,000" and "1 000" for a thousand, and
  // "25.5" or "25,5" for twenty-five and a half. Stripping every separator
  // read the second kind as 255. The rule that tells them apart: a
  // separator followed by exactly three digits, possibly repeated, is
  // grouping; a separator followed by anything else is a decimal point.
  const compact = raw.replace(/\s/g, "");
  if (compact === "") return null;
  const grouped = /^\d{1,3}([.,]\d{3})+$/.test(compact);
  const cleaned = grouped
    ? compact.replace(/[.,]/g, "")
    : compact.replace(",", ".");
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

// No HOSE stock has ever traded near 1,000,000 dong a share, and a price
// board never shows one below 1 (thousand). So a cost basis under this is
// in thousands and one at or above it is in dong, and both are accepted.
// The field echoes the dong figure it understood so the reader can check.
const COST_BASIS_DONG_FROM = 1_000;

/**
 * Group a typed integer into thousands as the reader types: "1000000"
 * becomes "1.000.000". Anything that is not a digit is dropped, so a
 * pasted "1,000,000" or "1 000 000" lands in the same place.
 */
export function groupDigits(raw: string): string {
  const digits = raw.replace(/\D/g, "").replace(/^0+(?=\d)/, "");
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

export function costBasisVnd(raw: string): number | null {
  const value = parseNumber(raw);
  if (value === null || value <= 0) return null;
  return value < COST_BASIS_DONG_FROM ? value * 1_000 : value;
}

/** Percent fraction → the string the field shows ("0.12" → "12"). */
const pctString = (v: number) => String(+(v * 100).toFixed(2));

export function PortfolioForm({
  onSubmit,
  pending,
  initial,
}: {
  onSubmit: (payload: PortfolioRequestPayload) => void;
  pending: boolean;
  /** A saved portfolio to start from. Remount (key) to apply a new one. */
  initial?: PortfolioRequestPayload | null;
}) {
  const t = useTranslations("portfolio.form");
  const locale = useLocale();
  const [rows, setRows] = useState<Row[]>(() =>
    initial && initial.holdings.length > 0
      ? initial.holdings.map((h) => ({
          ...blankRow(),
          symbol: h.symbol,
          quantity: groupDigits(String(h.quantity)),
          costBasis:
            h.cost_basis === null || h.cost_basis === undefined
              ? ""
              : String(h.cost_basis / 1_000),
        }))
      : [blankRow(), blankRow()],
  );
  const [cash, setCash] = useState(
    initial && initial.cash > 0 ? groupDigits(String(Math.round(initial.cash))) : "",
  );
  const [horizon, setHorizon] = useState<number>(initial?.horizon_days ?? 63);
  // The loan block is closed until opened: most readers do not borrow, and
  // an open block of empty fields reads as something they were meant to
  // fill. Defaults are the common Vietnamese figures and the copy says to
  // check them against the broker's own.
  const loan = initial?.margin ?? null;
  const [marginOpen, setMarginOpen] = useState(loan !== null);
  const [debt, setDebt] = useState(
    loan ? groupDigits(String(Math.round(loan.debt))) : "",
  );
  const [rate, setRate] = useState(loan ? pctString(loan.rate) : "12");
  const [callRatio, setCallRatio] = useState(
    loan ? pctString(loan.call_ratio) : "30",
  );
  const [forceRatio, setForceRatio] = useState(
    loan ? pctString(loan.force_ratio) : "28",
  );
  // A bank loan or a mortgage put into stocks: leverage and interest are
  // real, but there is no broker threshold, so those fields are hidden and
  // the analysis omits everything that depends on them.
  const [external, setExternal] = useState(loan?.external ?? false);
  // The reader's own limit. Optional: blank means the section stays off.
  const [budgetOpen, setBudgetOpen] = useState(
    initial?.risk_budget !== null && initial?.risk_budget !== undefined,
  );
  const [maxLoss, setMaxLoss] = useState(
    initial?.risk_budget ? pctString(initial.risk_budget.max_loss_pct) : "",
  );
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
      // Whole shares: "1.5" is a mistyped "1.500", not a position.
      if (quantity === null || quantity <= 0 || !Number.isInteger(quantity)) {
        setError(t("errors.quantity", { symbol }));
        return;
      }
      if (seen.has(symbol)) {
        setError(t("errors.duplicate", { symbol }));
        return;
      }
      seen.add(symbol);
      holdings.push({
        symbol,
        quantity,
        cost_basis: costBasisVnd(row.costBasis),
      });
    }

    if (holdings.length === 0) {
      setError(t("errors.empty"));
      return;
    }

    // A loan only counts when the block is open and a debt was typed; a
    // closed block with a stale number in it is not a loan.
    let margin: PortfolioRequestPayload["margin"] = null;
    const debtValue = parseNumber(debt);
    if (marginOpen && debtValue !== null && debtValue > 0) {
      const pct = (raw: string) => {
        const v = parseNumber(raw);
        return v === null || v < 0 || v > 100 ? null : v / 100;
      };
      const rateValue = pct(rate);
      const callValue = pct(callRatio);
      const forceValue = pct(forceRatio);
      if (rateValue === null) {
        setError(t("errors.rate"));
        return;
      }
      if (
        !external &&
        (callValue === null ||
          forceValue === null ||
          callValue <= 0 ||
          forceValue <= 0 ||
          callValue >= 1 ||
          forceValue >= callValue)
      ) {
        setError(t("errors.thresholds"));
        return;
      }
      margin = {
        debt: debtValue,
        rate: rateValue,
        // The backend still wants valid ratios on an external loan; it
        // ignores them. Keep whatever was typed if valid, else defaults.
        call_ratio: external && (callValue === null || callValue <= 0 || callValue >= 1) ? 0.3 : (callValue as number),
        force_ratio:
          external && (forceValue === null || forceValue <= 0 || forceValue >= 1)
            ? 0.28
            : (forceValue as number),
        external,
      };
    }

    let risk_budget: PortfolioRequestPayload["risk_budget"] = null;
    const maxLossValue = parseNumber(maxLoss);
    if (budgetOpen && maxLossValue !== null) {
      if (maxLossValue <= 0 || maxLossValue >= 100) {
        setError(t("errors.budget"));
        return;
      }
      risk_budget = { max_loss_pct: maxLossValue / 100 };
    }

    onSubmit({
      holdings,
      cash: parseNumber(cash) ?? 0,
      margin,
      risk_budget,
      horizon_days: horizon,
    });
  }

  return (
    <form onSubmit={submit} className="qp-panel p-6 sm:p-7">
      <h2 className="text-lg font-semibold">{t("heading")}</h2>

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
              className="grid gap-3 rounded-lg border border-border p-4 sm:grid-cols-[1fr_1fr_1fr_2.5rem] sm:items-start sm:rounded-none sm:border-0 sm:border-b sm:border-border/60 sm:p-0 sm:py-2"
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
                {/* Every cell ends with a hint line of the same height,
                    filled or not, so the three inputs sit level. */}
                {(() => {
                  const code = row.symbol.trim().toUpperCase();
                  const hit = code ? known.get(code) : undefined;
                  return (
                    <span
                      className={cn(
                        "min-h-4 truncate text-xs",
                        hit || !code || known.size === 0 ? "text-dim" : "text-caution",
                      )}
                    >
                      {hit ? hit.name : code && known.size > 0 ? t("unknownSymbol") : " "}
                    </span>
                  );
                })()}
              </label>

              <label className="grid gap-1.5">
                <span className="text-xs font-medium uppercase tracking-[0.06em] text-dim sm:sr-only">
                  {t("quantity")}
                </span>
                <input
                  value={row.quantity}
                  onChange={(e) => update(row.id, { quantity: groupDigits(e.target.value) })}
                  inputMode="numeric"
                  placeholder="1.000"
                  className="figure w-full rounded-md border border-border bg-background px-3 py-2 text-right outline-none focus:border-brand"
                />
                <span className="min-h-4 text-xs" aria-hidden="true">
                  {" "}
                </span>
              </label>

              <label className="grid gap-1.5">
                <span className="text-xs font-medium uppercase tracking-[0.06em] text-dim sm:sr-only">
                  {t("costBasis")}
                </span>
                <input
                  value={row.costBasis}
                  onChange={(e) => update(row.id, { costBasis: e.target.value })}
                  inputMode="decimal"
                  placeholder={t("costBasisPlaceholder")}
                  className="figure w-full rounded-md border border-border bg-background px-3 py-2 text-right outline-none focus:border-brand"
                />
                {(() => {
                  const vnd = costBasisVnd(row.costBasis);
                  return (
                    <span className="figure min-h-4 text-right text-xs text-dim">
                      {vnd === null
                        ? " "
                        : t("costBasisHint", {
                            amount: fmtNumber(vnd, locale, { maximumFractionDigits: 0 }),
                          })}
                    </span>
                  );
                })()}
              </label>

              <div className="justify-self-end sm:mt-[3px]">
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
            onChange={(e) => setCash(groupDigits(e.target.value))}
            inputMode="numeric"
            placeholder="50.000.000"
            className="figure mt-2 w-full rounded-md border border-border bg-background px-3 py-2 text-right outline-none focus:border-brand"
          />
        </div>

        <div>
          <span className="text-xs font-medium uppercase tracking-[0.06em] text-dim">
            {marginOpen && (parseNumber(debt) ?? 0) > 0
              ? t("horizonWithMargin")
              : t("horizon")}
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

      <div className="mt-7 rounded-lg border border-border">
        <button
          type="button"
          onClick={() => setMarginOpen((v) => !v)}
          aria-expanded={marginOpen}
          aria-controls="portfolio-margin"
          className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left"
        >
          <span>
            <span className="block text-sm font-semibold">{t("margin.heading")}</span>
            <span className="mt-0.5 block text-xs text-dim">{t("margin.lead")}</span>
          </span>
          <ChevronDown
            className={marginOpen ? "h-4 w-4 rotate-180 text-dim" : "h-4 w-4 text-dim"}
            aria-hidden="true"
          />
        </button>

        {marginOpen && (
          <div
            id="portfolio-margin"
            className="grid gap-5 border-t border-border px-4 py-5 sm:grid-cols-2"
          >
            <div className="sm:col-span-2">
              <label
                htmlFor="portfolio-debt"
                className="text-xs font-medium uppercase tracking-[0.06em] text-dim"
              >
                {t("margin.debt")}
              </label>
              <input
                id="portfolio-debt"
                value={debt}
                onChange={(e) => setDebt(groupDigits(e.target.value))}
                inputMode="numeric"
                placeholder="300.000.000"
                className="figure mt-2 w-full rounded-md border border-border bg-background px-3 py-2 text-right outline-none focus:border-brand"
              />
              <p className="mt-1.5 text-xs text-dim">{t("margin.debtNote")}</p>
              <label className="mt-3 flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={external}
                  onChange={(e) => setExternal(e.target.checked)}
                  className="mt-1 h-4 w-4 rounded border-border accent-brand"
                />
                <span>
                  <span className="block">{t("margin.external")}</span>
                  <span className="block text-xs text-dim">{t("margin.externalNote")}</span>
                </span>
              </label>
            </div>

            <div>
              <label
                htmlFor="portfolio-rate"
                className="text-xs font-medium uppercase tracking-[0.06em] text-dim"
              >
                {t("margin.rate")}
              </label>
              <div className="relative mt-2">
                <input
                  id="portfolio-rate"
                  value={rate}
                  onChange={(e) => setRate(e.target.value)}
                  inputMode="decimal"
                  className="figure w-full rounded-md border border-border bg-background px-3 py-2 pr-16 text-right outline-none focus:border-brand"
                />
                <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-dim">
                  {t("margin.perYear")}
                </span>
              </div>
            </div>

            {!external && (
            <div>
              <span className="text-xs font-medium uppercase tracking-[0.06em] text-dim">
                {t("margin.thresholds")}
              </span>
              <div className="mt-2 grid grid-cols-2 gap-3">
                <label className="grid gap-1">
                  <span className="text-xs text-dim">{t("margin.callRatio")}</span>
                  <div className="relative">
                    <input
                      value={callRatio}
                      onChange={(e) => setCallRatio(e.target.value)}
                      inputMode="decimal"
                      className="figure w-full rounded-md border border-border bg-background px-3 py-2 pr-8 text-right outline-none focus:border-brand"
                    />
                    <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-dim">%</span>
                  </div>
                </label>
                <label className="grid gap-1">
                  <span className="text-xs text-dim">{t("margin.forceRatio")}</span>
                  <div className="relative">
                    <input
                      value={forceRatio}
                      onChange={(e) => setForceRatio(e.target.value)}
                      inputMode="decimal"
                      className="figure w-full rounded-md border border-border bg-background px-3 py-2 pr-8 text-right outline-none focus:border-brand"
                    />
                    <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-dim">%</span>
                  </div>
                </label>
              </div>
              <p className="mt-1.5 text-xs text-dim">{t("margin.thresholdsNote")}</p>
            </div>
            )}
          </div>
        )}
      </div>

      <div className="mt-4 rounded-lg border border-border">
        <button
          type="button"
          onClick={() => setBudgetOpen((v) => !v)}
          aria-expanded={budgetOpen}
          aria-controls="portfolio-budget"
          className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left"
        >
          <span>
            <span className="block text-sm font-semibold">{t("budget.heading")}</span>
            <span className="mt-0.5 block text-xs text-dim">{t("budget.lead")}</span>
          </span>
          <ChevronDown
            className={budgetOpen ? "h-4 w-4 rotate-180 text-dim" : "h-4 w-4 text-dim"}
            aria-hidden="true"
          />
        </button>
        {budgetOpen && (
          <div id="portfolio-budget" className="border-t border-border px-4 py-5">
            <label
              htmlFor="portfolio-max-loss"
              className="text-xs font-medium uppercase tracking-[0.06em] text-dim"
            >
              {t("budget.maxLoss")}
            </label>
            <div className="relative mt-2 sm:max-w-xs">
              <input
                id="portfolio-max-loss"
                value={maxLoss}
                onChange={(e) => setMaxLoss(e.target.value)}
                inputMode="decimal"
                placeholder="15"
                className="figure w-full rounded-md border border-border bg-background px-3 py-2 pr-10 text-right outline-none focus:border-brand"
              />
              <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-dim">
                %
              </span>
            </div>
            <p className="mt-1.5 text-xs text-dim">{t("budget.note")}</p>
          </div>
        )}
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
    </form>
  );
}
