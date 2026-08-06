"use client";

import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";
import nodesSource from "@/public/research/dynamic-graph-nodes.json";
import { CHART, EChart } from "@/components/charts/echart";
import { fmtPercent } from "@/lib/format";

/**
 * Two views of the same 30 stocks, beside the ranking table.
 *
 * Left: influence against risk. A scatter answers "which central names are
 * also under pressure" in one look — the pair of columns in the table cannot,
 * because reading two sorted orders against each other is work.
 *
 * Right: how the network groups stocks. The model finds clusters from price
 * behaviour, not from sector labels, so showing the sector mix inside each
 * cluster says something a sector breakdown cannot.
 */

const COPY = {
  vi: {
    scatterTitle: "Ảnh hưởng so với rủi ro",
    scatterLead:
      "Mỗi điểm là một cổ phiếu. Càng sang phải càng nằm ở trung tâm mạng lưới; càng lên cao càng chịu nhiều áp lực. Góc trên bên phải là nhóm vừa trung tâm vừa rủi ro.",
    xAxis: "Mức ảnh hưởng",
    yAxis: "Điểm rủi ro",
    clusterTitle: "Các nhóm cổ phiếu mô hình tìm ra",
    clusterLead:
      "Mô hình nhóm cổ phiếu theo cách chúng biến động cùng nhau, không theo ngành. Cột cho biết mỗi nhóm có bao nhiêu mã.",
    stocks: "cổ phiếu",
  },
  en: {
    scatterTitle: "Influence against risk",
    scatterLead:
      "Each point is a stock. Further right means more central to the network; higher means more pressure. The top right is both central and stressed.",
    xAxis: "Influence",
    yAxis: "Risk score",
    clusterTitle: "Clusters the model found",
    clusterLead:
      "The model groups stocks by how they move together, not by sector. Bars show how many names fall in each group.",
    stocks: "stocks",
  },
} as const;

export function NetworkClusters({ locale }: { locale: "vi" | "en" }) {
  const t = COPY[locale];

  const scatterOption = useMemo<EChartsCoreOption>(
    () => ({
      grid: { left: 8, right: 20, top: 30, bottom: 40, containLabel: true },
      xAxis: {
        type: "value",
        name: t.xAxis,
        nameLocation: "middle",
        nameGap: 30,
        nameTextStyle: { color: CHART.dim, fontSize: 12 },
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: { color: CHART.dim },
        splitLine: { lineStyle: { color: CHART.surface } },
      },
      yAxis: {
        type: "value",
        // Named on the left edge rather than above the plot, where an axis
        // name collides with the series label. `nameRotate` keeps it reading
        // along the axis it describes.
        name: t.yAxis,
        nameLocation: "middle",
        nameRotate: 90,
        nameGap: 46,
        nameTextStyle: { color: CHART.dim, fontSize: 12 },
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: {
          color: CHART.dim,
          formatter: (v: number) => `${Math.round(v * 100)}%`,
        },
        splitLine: { lineStyle: { color: CHART.surface } },
      },
      legend: { show: false },
      tooltip: {
        trigger: "item",
        formatter: (p: { data: [number, number, string, string] }) =>
          `<b>${p.data[2]}</b><br/>${p.data[3]}<br/>${t.xAxis}: ${p.data[0].toFixed(2)}<br/>${t.yAxis}: ${Math.round(p.data[1] * 100)}%`,
      },
      series: [
        {
          type: "scatter",
          symbolSize: 13,
          data: nodesSource.map((n) => [
            n.eigenvector_centrality,
            n.risk_score,
            n.label,
            n.sector,
          ]),
          itemStyle: {
            color: CHART.brand,
            opacity: 0.85,
            // A 2px ring keeps overlapping points readable.
            borderColor: "#ffffff",
            borderWidth: 2,
          },
          // Label only the extremes; a name on every point is unreadable.
          label: {
            show: true,
            position: "top",
            color: CHART.ink,
            fontFamily: CHART.mono,
            fontSize: 11,
            formatter: (p: { data: [number, number, string] }) =>
              p.data[0] > 0.28 || p.data[1] > 0.62 ? p.data[2] : "",
          },
        },
      ],
    }),
    [t]
  );

  const clusters = useMemo(() => {
    const byCluster = new Map<number, string[]>();
    for (const n of nodesSource) {
      byCluster.set(n.community, [...(byCluster.get(n.community) ?? []), n.label]);
    }
    return [...byCluster.entries()]
      .map(([id, members]) => ({ id, members }))
      .sort((a, b) => b.members.length - a.members.length);
  }, []);

  return (
    <section className="mt-14">
      <div className="grid gap-8 desk:grid-cols-2">
        <div className="qp-panel p-5">
          <h3 className="text-sm font-medium">{t.scatterTitle}</h3>
          <p className="mt-1 text-xs leading-relaxed text-dim">
            {t.scatterLead}
          </p>
          <EChart
            option={scatterOption}
            ariaLabel={t.scatterTitle}
            className="mt-4 h-96"
          />
        </div>

        <div className="qp-panel p-5">
          <h3 className="text-sm font-medium">{t.clusterTitle}</h3>
          <p className="mt-1 text-xs leading-relaxed text-dim">
            {t.clusterLead}
          </p>
          <ul className="mt-5 space-y-4">
            {clusters.map((c, i) => (
              <li key={c.id}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="figure text-xs uppercase tracking-[0.06em] text-dim">
                    {locale === "vi" ? "Nhóm" : "Cluster"} {c.id + 1}
                  </span>
                  <span className="figure text-xs text-dim">
                    {c.members.length} {t.stocks} ·{" "}
                    {fmtPercent(c.members.length / nodesSource.length, locale)}
                  </span>
                </div>
                <div
                  aria-hidden="true"
                  className="mt-1.5 h-2 rounded-full"
                  style={{
                    width: `${(c.members.length / nodesSource.length) * 100}%`,
                    backgroundColor: CHART.series[i % CHART.series.length],
                  }}
                />
                <p className="figure mt-2 text-[11px] leading-relaxed text-dim">
                  {c.members.join(" · ")}
                </p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
