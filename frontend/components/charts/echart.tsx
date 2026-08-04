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

/** Restrained base style shared by every chart (spec §15). */
const BASE: EChartsCoreOption = {
  color: ["#087f78", "#d97706", "#0d1110", "#16805d", "#c64032", "#65706d"],
  animationDuration: 760,
  animationDurationUpdate: 420,
  animationEasing: "cubicOut",
  animationEasingUpdate: "cubicOut",
  textStyle: { fontFamily: MONO, color: "#65706d", fontSize: 11 },
  grid: { left: 8, right: 8, top: 24, bottom: 8, containLabel: true },
  tooltip: {
    trigger: "axis",
    backgroundColor: "#ffffff",
    borderColor: "#dfe7e5",
    borderWidth: 1,
    borderRadius: 2,
    padding: [8, 10],
    textStyle: { color: "#0d1110", fontFamily: MONO, fontSize: 11 },
    extraCssText: "box-shadow:0 8px 24px rgba(13,17,16,0.08);",
  },
  legend: {
    top: 0,
    left: 0,
    itemWidth: 14,
    itemHeight: 2,
    icon: "rect",
    textStyle: { color: "#65706d", fontFamily: MONO, fontSize: 11 },
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
      className={cn("chart-canvas h-72 w-full", className)}
    />
  );
}

/** Palette + shared constants for option builders. */
export const CHART = {
  ink: "#0d1110",
  dim: "#65706d",
  faint: "#9caaa6",
  lightgray: "#cfdbd8",
  border: "#dfe7e5",
  surface: "#edf3f1",
  brand: "#087f78",
  brandDark: "#075f5a",
  brandSoft: "#dff4f1",
  signal: "#d97706",
  signalDark: "#995108",
  signalSoft: "#fff1d6",
  positive: "#16805d",
  negative: "#c64032",
  mono: MONO,
};
