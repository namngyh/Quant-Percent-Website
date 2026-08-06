"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import {
  BarChart,
  CandlestickChart,
  GraphChart,
  HeatmapChart,
  LineChart,
  ScatterChart,
} from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";
import { cn } from "@/lib/utils";

echarts.use([
  LineChart,
  BarChart,
  CandlestickChart,
  GraphChart,
  HeatmapChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkAreaComponent,
  DataZoomComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

const MONO = "IBM Plex Mono, ui-monospace, monospace";

/**
 * Categorical series in fixed order. Checked with the palette validator:
 * inside the lightness band, above the chroma floor, worst adjacent pair
 * ΔE 8.2 under protanopia and 17.2 for normal vision, all at 3:1 contrast.
 * Assign in order and never cycle — a colour belongs to a series, not to a
 * position in a sorted list.
 */
const SERIES = ["#3a72c4", "#ad7519", "#158f66", "#8a4fbd", "#c0433a"];

/** Restrained base style shared by every chart (spec §15). */
const BASE: EChartsCoreOption = {
  color: SERIES,
  animationDuration: 760,
  animationDurationUpdate: 420,
  animationEasing: "cubicOut",
  animationEasingUpdate: "cubicOut",
  // 12px rather than 11: these charts are read by people who do not stare at
  // dashboards all day, and axis labels were the first thing to go illegible.
  textStyle: { fontFamily: MONO, color: "#64748b", fontSize: 12 },
  grid: { left: 8, right: 12, top: 28, bottom: 8, containLabel: true },
  tooltip: {
    trigger: "axis",
    backgroundColor: "#ffffff",
    borderColor: "#e2e8f0",
    borderWidth: 1,
    borderRadius: 6,
    padding: [10, 12],
    textStyle: { color: "#0f1b2a", fontFamily: MONO, fontSize: 12 },
    extraCssText: "box-shadow:0 10px 30px rgba(15,27,42,0.10);",
    axisPointer: { lineStyle: { color: "#cbd5e1", width: 1 } },
  },
  legend: {
    top: 0,
    left: 0,
    itemWidth: 16,
    itemHeight: 3,
    itemGap: 18,
    icon: "roundRect",
    textStyle: { color: "#24344a", fontFamily: MONO, fontSize: 12 },
  },
};

export function EChart({
  option,
  className,
  ariaLabel,
}: {
  option: EChartsCoreOption;
  className?: string;
  ariaLabel: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const optionRef = useRef(option);
  useEffect(() => {
    optionRef.current = option;
  });

  // Lazily init when scrolled into view; keep main thread light (§22)
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let revealFrame = 0;

    const init = () => {
      if (chartRef.current) return;
      const chart = echarts.init(el, undefined, { renderer: "canvas" });
      chart.setOption({
        ...BASE,
        ...(reduced ? { animation: false } : {}),
        ...optionRef.current,
      });
      chartRef.current = chart;
      revealFrame = window.requestAnimationFrame(() => {
        el.dataset.chartReady = "true";
      });
    };

    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          init();
          io.disconnect();
        }
      },
      { rootMargin: "120px" }
    );
    io.observe(el);

    // Initialize shortly after mount if a background tab suspends observers.
    const fallback = window.setTimeout(init, 1500);

    const ro = new ResizeObserver(() => chartRef.current?.resize());
    ro.observe(el);

    return () => {
      window.clearTimeout(fallback);
      window.cancelAnimationFrame(revealFrame);
      delete el.dataset.chartReady;
      io.disconnect();
      ro.disconnect();
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  // Update options when data changes
  useEffect(() => {
    chartRef.current?.setOption({ ...BASE, ...option }, { notMerge: true });
  }, [option]);

  return (
    <div
      ref={ref}
      role="img"
      aria-label={ariaLabel}
      // Taller by default: these carry the argument on the page, and at 18rem
      // the equity curves were compressed to the point of being decorative.
      className={cn("chart-canvas h-96 w-full", className)}
    />
  );
}

/** Palette + shared constants for option builders. */
export const CHART = {
  ink: "#0f1b2a",
  dim: "#64748b",
  faint: "#94a3b8",
  lightgray: "#cbd5e1",
  border: "#e2e8f0",
  surface: "#eef2f7",
  brand: "#3a72c4",
  brandDark: "#2c579a",
  brandSoft: "#e7eef5",
  signal: "#ad7519",
  signalDark: "#8a5d14",
  signalSoft: "#f7efdf",
  // Status colours, reserved. Never reused as an extra categorical series.
  positive: "#14795a",
  negative: "#a93b32",
  series: SERIES,
  mono: MONO,
};
