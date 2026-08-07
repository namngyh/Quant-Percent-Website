import { cn } from "@/lib/utils";

/**
 * The headline number of a model card, drawn to scale.
 *
 * What this replaces was a bare polyline through three or six points with no
 * axis and no labels. Two things were wrong with it. The line implied time,
 * but the points are horizons — 20, 40 and 60 sessions ahead — so it drew a
 * trend that does not exist. And it rescaled itself to its own min and max, so
 * 53.8 / 58.5 / 53.9 became a mountain when the real spread is under five
 * points on a nought-to-hundred metric.
 *
 * A labelled bar per horizon fixes both. The bar length is measured against a
 * stated scale, the horizon is written next to it, and where the metric has a
 * level it is supposed to reach, that level is marked. A reader learns what
 * the model does from the card rather than from a shape.
 */

export interface MetricBar {
  /** Row label — the horizon, in the reader's language. */
  label: string;
  value: number;
}

export function MetricStrip({
  bars,
  suffix = "",
  /** Lower and upper end of the drawn scale. */
  min,
  max,
  /** The level the metric is supposed to reach, marked with a hairline. */
  reference,
  referenceLabel,
  locale,
  className,
}: {
  bars: MetricBar[];
  suffix?: string;
  min: number;
  max: number;
  reference?: number;
  referenceLabel?: string;
  locale: "vi" | "en";
  className?: string;
}) {
  const span = max - min || 1;
  const pos = (v: number) => ((v - min) / span) * 100;

  return (
    <div className={cn("space-y-1.5", className)}>
      {bars.map((bar) => (
        <div key={bar.label} className="grid grid-cols-[3.4rem_1fr_3.2rem] items-center gap-2">
          <span className="figure text-[10px] text-dim">{bar.label}</span>
          <span className="relative block h-2.5 rounded-sm bg-surface">
            <span
              className="absolute inset-y-0 left-0 rounded-sm bg-brand"
              style={{ width: `${Math.max(2, Math.min(100, pos(bar.value)))}%` }}
            />
            {reference !== undefined && (
              // The mark usually falls inside a filled bar, so it is drawn
              // over the fill and stands taller than it — a hairline the same
              // darkness as the bar would disappear into it.
              <span
                aria-hidden="true"
                className="absolute inset-y-[-3px] w-[1.5px] bg-ink"
                style={{ left: `${Math.min(100, Math.max(0, pos(reference)))}%` }}
              />
            )}
          </span>
          <span className="figure text-right text-[11px] font-medium tabular-nums">
            {bar.value.toLocaleString(locale, { maximumFractionDigits: 1 })}
            {suffix}
          </span>
        </div>
      ))}
      {referenceLabel && (
        <p className="pt-0.5 text-[10px] leading-snug text-dim">{referenceLabel}</p>
      )}
    </div>
  );
}
