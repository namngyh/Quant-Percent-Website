"use client";

import { useEffect, useRef, useState } from "react";
import { useInView, useReducedMotion } from "framer-motion";
import { useHydrated } from "@/lib/use-hydrated";

/**
 * A number that counts up when it scrolls into view.
 *
 * `format` is what makes this usable for the figures on this site rather than
 * only for whole counts. The headline metrics are percentages and ratios that
 * have to be written the way the reader's locale writes them — "-8,9%" in
 * Vietnamese, "-8.9%" in English — so the caller passes the same formatter it
 * would have used for the static value and this animates the number underneath
 * it. Formatting here instead would mean reimplementing `Intl` badly.
 *
 * Under `prefers-reduced-motion` it renders the final value on the first paint
 * and never animates. It also starts from the final value on the server, so
 * the figure is correct in the HTML for anything reading the page without
 * running scripts.
 */
export function MetricCounter({
  value,
  format,
  className,
}: {
  value: number;
  format?: (v: number) => string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const reduced = useReducedMotion();
  const hydrated = useHydrated();
  const shouldReduce = hydrated && reduced;
  const render = format ?? ((v: number) => String(Math.round(v)));

  /*
   * What is stored is progress from 0 to 1, not the number on screen, and the
   * displayed figure is derived from it.
   *
   * Holding the figure itself meant seeding it with the real value for the
   * server, then resetting it to zero the moment the element scrolled into
   * view — a write to state in the effect body, and one frame where the
   * finished number was painted before the count-up snapped it back to zero.
   * Deriving it means the run begins at zero in the very same render that
   * flips `running` true, so there is nothing to reset and nothing to flash.
   */
  const [progress, setProgress] = useState(0);
  const running = inView && !shouldReduce;
  const shown = running ? value * progress : value;

  useEffect(() => {
    if (!running) return;
    const duration = 1100;
    let raf = 0;
    let start = 0;
    const tick = (now: number) => {
      if (!start) start = now;
      const p = Math.min(1, (now - start) / duration);
      // Cubic ease-out: fast enough to feel responsive, and it settles rather
      // than stopping dead on the final digit.
      setProgress(1 - Math.pow(1 - p, 3));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [running]);

  return (
    <span ref={ref} className={className}>
      {render(shown)}
    </span>
  );
}
