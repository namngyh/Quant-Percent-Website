"use client";

import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { EChart, CHART } from "@/components/charts/echart";
import nodesSource from "@/public/research/dynamic-graph-nodes.json";
import edgesSource from "@/public/research/dynamic-graph-edges.json";

type Locale = "vi" | "en";

type SourceEdge = (typeof edgesSource)[number];

type GraphNode = {
  id: string;
  name: string;
  category: number;
  symbolSize: number;
  value: number;
  sector: string;
  degree: number;
  riskScore: number;
  itemStyle: { color: string; borderColor: string; borderWidth: number };
};

type GraphEdge = {
  source: string;
  target: string;
  value: number;
  signedWeight: number;
  relation: "positive" | "negative";
  lineStyle: {
    color: string;
    width: number;
    opacity: number;
    type: "solid" | "dashed";
  };
};

const COMMUNITY_COLORS = [
  "#087f78",
  "#d97706",
  "#3168a6",
  "#9a5bb5",
  "#c64032",
  "#16805d",
  "#8a5a44",
];

const copy = {
  vi: {
    hover: "Trỏ hoặc chạm vào một mã để xem các liên kết trực tiếp",
    positive: "Cùng chiều",
    negative: "Ngược chiều",
    strength: "Mức liên hệ",
    connections: "Liên kết trực tiếp",
    sector: "Nhóm ngành",
    risk: "Điểm rủi ro",
    more: "liên kết khác",
    aria:
      "Mạng liên hệ giữa 30 cổ phiếu. Trỏ vào một mã để làm nổi bật các liên kết trực tiếp.",
  },
  en: {
    hover: "Hover over or tap a ticker to reveal its direct links",
    positive: "Moves together",
    negative: "Moves oppositely",
    strength: "Relationship strength",
    connections: "Direct links",
    sector: "Sector",
    risk: "Risk score",
    more: "more links",
    aria:
      "Relationship network among 30 stocks. Hover over a ticker to highlight its direct links.",
  },
} satisfies Record<Locale, Record<string, string>>;

function formatPercent(value: number, locale: Locale) {
  return Math.abs(value).toLocaleString(locale, {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

function buildOption(locale: Locale): EChartsCoreOption {
  const text = copy[locale];
  const maxStrength = Math.max(...nodesSource.map((node) => node.strength));
  const graphNodes: GraphNode[] = nodesSource.map((node) => ({
    id: node.id,
    name: node.label,
    category: node.community,
    symbolSize: 23 + (node.strength / maxStrength) * 21,
    value: node.strength,
    sector: node.sector,
    degree: node.degree,
    riskScore: node.risk_score,
    itemStyle: {
      color: COMMUNITY_COLORS[node.community % COMMUNITY_COLORS.length],
      borderColor: "#ffffff",
      borderWidth: 2,
    },
  }));

  const graphEdges: GraphEdge[] = edgesSource.map((edge) => {
    const positive = edge.signed_weight >= 0;
    return {
      source: edge.source,
      target: edge.target,
      value: edge.absolute_weight,
      signedWeight: edge.signed_weight,
      relation: positive ? "positive" : "negative",
      lineStyle: {
        color: positive ? CHART.brand : CHART.negative,
        width: 1 + edge.absolute_weight * 5,
        opacity: 0.045,
        type: positive ? "solid" : "dashed",
      },
    };
  });

  const edgesByNode = new Map<string, Array<SourceEdge>>();
  for (const edge of edgesSource) {
    edgesByNode.set(edge.source, [...(edgesByNode.get(edge.source) ?? []), edge]);
    edgesByNode.set(edge.target, [...(edgesByNode.get(edge.target) ?? []), edge]);
  }

  return {
    animationDuration: 850,
    animationDurationUpdate: 280,
    legend: { show: false },
    tooltip: {
      trigger: "item",
      confine: true,
      enterable: false,
      padding: [10, 12],
      formatter: (params: {
        dataType?: "node" | "edge";
        data?: GraphNode | GraphEdge;
      }) => {
        if (params.dataType === "edge") {
          const edge = params.data as GraphEdge;
          const relation =
            edge.relation === "positive" ? text.positive : text.negative;
          const color =
            edge.relation === "positive" ? CHART.brand : CHART.negative;
          return [
            `<strong>${edge.source} ↔ ${edge.target}</strong>`,
            `<span style="color:${color}">●</span> ${relation}`,
            `${text.strength}: ${formatPercent(edge.signedWeight, locale)}`,
          ].join("<br/>");
        }

        const node = params.data as GraphNode;
        const links = [...(edgesByNode.get(node.id) ?? [])].sort(
          (a, b) => b.absolute_weight - a.absolute_weight
        );
        const visible = links.slice(0, 7);
        const rows = visible.map((edge) => {
          const neighbor = edge.source === node.id ? edge.target : edge.source;
          const positive = edge.signed_weight >= 0;
          const color = positive ? CHART.brand : CHART.negative;
          const relation = positive ? text.positive : text.negative;
          return `<div style="display:flex;justify-content:space-between;gap:18px;margin-top:5px">
            <span><b>${neighbor}</b> <span style="color:${color}">${relation}</span></span>
            <span>${formatPercent(edge.signed_weight, locale)}</span>
          </div>`;
        });
        const remaining =
          links.length > visible.length
            ? `<div style="margin-top:6px;color:${CHART.dim}">+${links.length - visible.length} ${text.more}</div>`
            : "";

        return [
          `<strong style="font-size:13px">${node.name}</strong>`,
          `<div style="color:${CHART.dim};margin-top:3px">${text.sector}: ${node.sector}</div>`,
          `<div style="color:${CHART.dim}">${text.risk}: ${(node.riskScore * 100).toFixed(0)}/100</div>`,
          `<div style="border-top:1px solid ${CHART.border};margin-top:8px;padding-top:7px"><b>${text.connections}: ${links.length}</b></div>`,
          ...rows,
          remaining,
        ].join("");
      },
    },
    series: [
      {
        type: "graph",
        layout: "force",
        data: graphNodes,
        links: graphEdges,
        categories: COMMUNITY_COLORS.map((color, index) => ({
          name: String(index + 1),
          itemStyle: { color },
        })),
        roam: true,
        draggable: false,
        cursor: "pointer",
        force: {
          repulsion: 470,
          gravity: 0.045,
          edgeLength: [105, 215],
          friction: 0.62,
          layoutAnimation: true,
        },
        label: {
          show: true,
          position: "inside",
          color: "#ffffff",
          fontFamily: CHART.mono,
          fontSize: 10,
          fontWeight: 700,
        },
        lineStyle: {
          opacity: 0.045,
          curveness: 0.04,
        },
        emphasis: {
          focus: "adjacency",
          scale: 1.18,
          label: { show: true, fontSize: 12 },
          itemStyle: {
            borderColor: CHART.ink,
            borderWidth: 2,
            shadowBlur: 12,
            shadowColor: "rgba(13,17,16,0.2)",
          },
          lineStyle: {
            opacity: 0.92,
          },
        },
        blur: {
          itemStyle: { opacity: 0.16 },
          label: { opacity: 0.14 },
          lineStyle: { opacity: 0.015 },
        },
      },
    ],
  };
}

export function DynamicNetwork({ locale }: { locale: Locale }) {
  const option = useMemo(() => buildOption(locale), [locale]);
  const text = copy[locale];

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-border px-5 py-4">
        <p className="text-sm font-medium text-ink">{text.hover}</p>
        <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-dim">
          <span className="inline-flex items-center gap-2">
            <span className="h-0.5 w-5 bg-brand" aria-hidden="true" />
            {text.positive}
          </span>
          <span className="inline-flex items-center gap-2">
            <span
              className="w-5 border-t-2 border-dashed border-negative"
              aria-hidden="true"
            />
            {text.negative}
          </span>
        </div>
      </div>
      <EChart
        option={option}
        ariaLabel={text.aria}
        className="h-[32rem] bg-surface/35 sm:h-[38rem]"
      />
    </div>
  );
}
