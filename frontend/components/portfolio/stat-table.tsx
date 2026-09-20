"use client";

import { fmtPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Figures that are not a chart are a vertical table: one row per figure,
 * name on the left, value on the right, the one-line note under the name.
 * Reads top to bottom, sits in half the height of the tile grid it
 * replaces, and never puts four unrelated numbers side by side.
 */

export type Tone = "positive" | "negative" | "caution";

export interface StatRow {
  label: string;
  value: string;
  note?: string;
  tone?: Tone;
}

const TONE: Record<Tone, string> = {
  positive: "text-positive",
  negative: "text-negative",
  caution: "text-caution",
};

export function StatTable({
  rows,
  className,
  columns = 1,
}: {
  rows: StatRow[];
  className?: string;
  /** Two columns on wide screens for groups of four or more short rows. */
  columns?: 1 | 2;
}) {
  return (
    <dl
      className={cn(
        "overflow-hidden rounded-lg border border-border bg-background shadow-sm",
        columns === 2 && "desk:grid desk:grid-cols-2",
        className,
      )}
    >
      {rows.map((r, i) => (
        <div
          key={r.label}
          className={cn(
            "flex items-baseline justify-between gap-4 px-4 py-2.5",
            "border-b border-border/70 last:border-b-0",
            columns === 2 && i % 2 === 0 && "desk:border-r desk:border-border/70",
            columns === 2 && i >= rows.length - 2 && "desk:border-b-0",
          )}
        >
          <dt className="min-w-0">
            <span className="block text-sm text-ink">{r.label}</span>
            {r.note && (
              <span className="block text-xs leading-snug text-dim">{r.note}</span>
            )}
          </dt>
          <dd
            className={cn(
              "figure shrink-0 text-base font-semibold tabular-nums",
              r.tone ? TONE[r.tone] : "text-ink",
            )}
          >
            {r.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Losses as bars with money at the end: one row per measure, the bar's
 * length relative to the largest in the group. A percentage next to a
 * dong amount is the pairing that gives a loss its weight.
 */
export interface LossBarRow {
  label: string;
  fraction: number;
  amount: string;
  note?: string;
  color: string;
}

export function LossBars({ rows, locale }: { rows: LossBarRow[]; locale: string }) {
  const max = Math.max(...rows.map((r) => Math.abs(r.fraction)), 1e-9);
  return (
    <ul className="space-y-3 rounded-lg border border-border bg-background p-4 shadow-sm">
      {rows.map((r) => {
        const pct = Math.abs(r.fraction);
        return (
          <li key={r.label}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-ink">
                {r.label}
                {r.note && <span className="ml-2 text-xs text-dim">{r.note}</span>}
              </span>
              <span className="figure shrink-0 font-semibold">
                −{fmtPercent(pct, locale, 1)}
                <span className="ml-2 font-normal text-dim">{r.amount}</span>
              </span>
            </div>
            <div className="mt-1.5 h-3 overflow-hidden rounded-sm bg-surface">
              <div
                className="h-full rounded-sm"
                style={{ width: `${(pct / max) * 100}%`, backgroundColor: r.color }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
