"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";

// ECharts is heavy and most articles carry no chart; load it only for those
// that do.
const EChart = dynamic(
  () => import("@/components/charts/echart").then((m) => m.EChart),
  { ssr: false, loading: () => <div className="chart-canvas h-80 w-full" /> }
);

const MAX_SOURCE = 50_000;

/*
 * Keys an author may not set. ECharts inserts tooltip `formatter` strings and
 * `extraCssText` into the page as HTML, so either would let an article run
 * script in a reader's session. The tooltip is also forced into rich-text
 * mode, which draws on the canvas and never touches innerHTML at all.
 */
const BLOCKED = new Set([
  "formatter",
  "extraCssText",
  "renderMode",
  "appendTo",
  "appendToBody",
  "className",
  "__proto__",
  "constructor",
  "prototype",
]);

function clean(value: unknown, depth = 0): unknown {
  if (depth > 20) return undefined;
  if (Array.isArray(value)) return value.map((v) => clean(v, depth + 1));
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, v] of Object.entries(value)) {
      if (!BLOCKED.has(key)) out[key] = clean(v, depth + 1);
    }
    return out;
  }
  return value;
}

function parse(
  source: string
): { caption: string | null; option: EChartsCoreOption } | null {
  if (source.length > MAX_SOURCE) return null;
  try {
    const raw = JSON.parse(source) as unknown;
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    const option = clean(raw) as Record<string, unknown>;
    const tooltip =
      option.tooltip && typeof option.tooltip === "object" ? option.tooltip : {};
    // The title is lifted out and drawn as a caption: inside the canvas it
    // collides with the legend, and as HTML it is real text a reader can
    // select and a screen reader can find.
    const { title, ...rest } = option;
    const text = (Array.isArray(title) ? title[0] : title) as { text?: unknown } | undefined;
    return {
      caption: typeof text?.text === "string" ? text.text : null,
      option: {
        ...rest,
        tooltip: { trigger: "axis", ...tooltip, renderMode: "richText" },
      },
    };
  } catch {
    return null;
  }
}

/**
 * A ```chart block in an article: an ECharts option written as JSON.
 * A broken block says so in place instead of taking the article down.
 */
export function ArticleChart({ source }: { source: string }) {
  const t = useTranslations("articles");
  const parsed = useMemo(() => parse(source), [source]);

  if (!parsed) {
    return (
      <p
        role="note"
        className="my-6 rounded-lg border border-dashed border-border bg-surface px-4 py-3 text-sm text-dim"
      >
        {t("editor.chartError")}
      </p>
    );
  }

  return (
    <figure className="my-8">
      {parsed.caption && (
        <figcaption className="mb-3 text-center text-[15px] font-semibold text-foreground">
          {parsed.caption}
        </figcaption>
      )}
      <EChart
        option={parsed.option}
        className="h-80"
        ariaLabel={parsed.caption ?? t("chartLabel")}
      />
    </figure>
  );
}
