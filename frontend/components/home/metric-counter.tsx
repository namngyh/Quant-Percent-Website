"use client";

import { useEffect, useRef, useState } from "react";
import { useInView, useReducedMotion } from "framer-motion";
import { useHydrated } from "@/lib/use-hydrated";

/** Count-up number that renders the final value directly under reduced motion. */
export function MetricCounter({
  value,
  className,
  suffix = "",
}: {
  value: number;
  className?: string;
  suffix?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const reduced = useReducedMotion();
  const hydrated = useHydrated();
  const shouldReduce = hydrated && reduced;
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (shouldReduce || !inView) return;
    const duration = 1200;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(Math.round(value * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, shouldReduce, value]);

  return (
    <span ref={ref} className={className}>
      {shouldReduce ? value : display}
      {suffix}
    </span>
  );
}
