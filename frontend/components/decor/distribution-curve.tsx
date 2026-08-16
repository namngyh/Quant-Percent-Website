import { cn } from "@/lib/utils";

/**
 * A normal density with its lower tail shaded, as a faint mark behind the hero.
 *
 * This is what is left of a larger set — a field of equations, a histogram,
 * candles, simulated paths, a scatter, a drawdown profile and a correlation
 * matrix all lived here at one point. Layered together they were noise: each
 * was faint on its own, but five overlapping textures behind a headline is
 * clutter, and they were positioned by eyeballing percentages rather than
 * against any grid. One figure, in one place, is the version that works.
 *
 * The tail is cut at −1.645σ, the 5% quantile — the same threshold the
 * portfolio tool reports as its 95% loss level, so the shape is the picture
 * behind a number the site actually publishes rather than a generic bell.
 *
 * It draws in `currentColor` and is inert: `aria-hidden`, no pointer events,
 * nothing selectable.
 */
export function DistributionCurve({ className }: { className?: string }) {
  const W = 320;
  const H = 150;
  const SPAN = 3.4; // plotted from -3.4σ to +3.4σ
  const STEPS = 90;
  const VAR_Z = -1.645;

  const x = (z: number) => ((z + SPAN) / (2 * SPAN)) * W;
  const y = (z: number) => H - Math.exp(-(z * z) / 2) * (H - 8);

  const points = Array.from({ length: STEPS + 1 }, (_, i) => {
    const z = -SPAN + (i / STEPS) * 2 * SPAN;
    return `${x(z).toFixed(2)},${y(z).toFixed(2)}`;
  });

  const tail = Array.from({ length: 31 }, (_, i) => {
    const z = -SPAN + (i / 30) * (VAR_Z + SPAN);
    return `${x(z).toFixed(2)},${y(z).toFixed(2)}`;
  });

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={cn("pointer-events-none select-none", className)}
      fill="none"
      aria-hidden="true"
    >
      <line x1="0" y1={H} x2={W} y2={H} stroke="currentColor" strokeWidth="1" />
      {/* The 5% tail, filled */}
      <polygon
        points={`${x(-SPAN).toFixed(2)},${H} ${tail.join(" ")} ${x(VAR_Z).toFixed(2)},${H}`}
        fill="currentColor"
        opacity="0.5"
      />
      {/* The quantile marker */}
      <line
        x1={x(VAR_Z).toFixed(2)}
        y1={y(VAR_Z).toFixed(2)}
        x2={x(VAR_Z).toFixed(2)}
        y2={H}
        stroke="currentColor"
        strokeWidth="1"
        strokeDasharray="3 3"
      />
      <polyline
        points={points.join(" ")}
        stroke="currentColor"
        strokeWidth="1.75"
      />
    </svg>
  );
}
