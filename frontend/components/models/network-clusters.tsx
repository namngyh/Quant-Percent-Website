"use client";

import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { DataState } from "@/components/states/data-state";
import { useNetworkSnapshot } from "@/lib/api/network";
import { CHART, EChart } from "@/components/charts/echart";
import { fmtPercent } from "@/lib/format";
import { sectorLabel } from "@/lib/sectors";

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
      "Mỗi điểm là một cổ phiếu. Trục ngang là thứ hạng ảnh hưởng trong mạng lưới, càng sang phải càng nằm ở trung tâm; càng lên cao càng chịu nhiều áp lực. Góc trên bên phải là nhóm vừa trung tâm vừa rủi ro. Rê chuột vào một điểm để xem chỉ số gốc.",
    xAxis: "Thứ hạng ảnh hưởng",
    xRaw: "Chỉ số ảnh hưởng",
    yAxis: "Điểm rủi ro",
    clusterTitle: "Các nhóm cổ phiếu mô hình tìm ra",
    clusterLead:
      "Mô hình nhóm cổ phiếu theo cách chúng biến động cùng nhau, không theo ngành. Cột cho biết mỗi nhóm có bao nhiêu mã.",
    stocks: "cổ phiếu",
  },
  en: {
    scatterTitle: "Influence against risk",
    scatterLead:
      "Each point is a stock. The horizontal axis is influence rank within the network, so further right means more central; higher means more pressure. The top right is both central and stressed. Hover a point for the underlying score.",
    xAxis: "Influence rank",
    xRaw: "Influence score",
    yAxis: "Risk score",
    clusterTitle: "Clusters the model found",
    clusterLead:
      "The model groups stocks by how they move together, not by sector. Bars show how many names fall in each group.",
    stocks: "stocks",
  },
} as const;

function InfluenceScatter({ locale }: { locale: "vi" | "en" }) {
  const t = COPY[locale];
  const { data, error, isLoading, mutate } = useNetworkSnapshot();
  const nodesSource = useMemo(() => data?.nodes ?? [], [data]);

  // Influence plotted as a rank, not as the raw centrality score.
  //
  // Eigenvector centrality is severely skewed: two names sit above 0.5 while
  // the other twenty-eight are packed into the first tenth of the axis. On
  // the raw scale most of the market was a vertical smear against the left
  // edge with the tickers printed over each other, and no amount of label
  // nudging separates points that genuinely share a coordinate.
  //
  // Ranking spreads them evenly across the width. "Further right is more
  // central" — the only claim the panel makes about this axis — survives the
  // change intact. What is lost is the size of the gap between neighbours,
  // so the tooltip carries the underlying score for anyone who wants it.
  const points = useMemo(() => {
    const order = [...nodesSource].sort(
      (a, b) => a.eigenvector_centrality - b.eigenvector_centrality,
    );
    const last = Math.max(order.length - 1, 1);
    return order.map((node, i) => ({ rank: (i / last) * 100, node }));
  }, [nodesSource]);

  // Which points get a name. A fixed count per axis tells the same story —
  // the most central names, the most pressured ones — without the answer
  // depending on how tightly one corner happens to be packed today. The
  // tooltip names every point on hover regardless.
  const named = useMemo(() => {
    const by = (key: "eigenvector_centrality" | "risk_score", n: number) =>
      [...nodesSource]
        .sort((a, b) => b[key] - a[key])
        .slice(0, n)
        .map((x) => x.label);
    return new Set([
      ...by("eigenvector_centrality", 5),
      ...by("risk_score", 4),
    ]);
  }, [nodesSource]);

  const scatterOption = useMemo<EChartsCoreOption>(
    () => ({
      grid: { left: 8, right: 34, top: 30, bottom: 40, containLabel: true },
      xAxis: {
        type: "value",
        name: t.xAxis,
        nameLocation: "middle",
        nameGap: 30,
        nameTextStyle: { color: CHART.dim, fontSize: 12 },
        // Pinned to the full rank range so the axis reads the same every day
        // and its two ends mean "least central" and "most central" rather
        // than whatever today's extremes happen to be.
        min: 0,
        max: 100,
        axisLine: { lineStyle: { color: CHART.border } },
        axisLabel: { color: CHART.dim, formatter: (v: number) => `${v}%` },
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
        formatter: (p: { data: [number, number, string, string, number] }) =>
          `<b>${p.data[2]}</b><br/>${p.data[3]}<br/>${t.xAxis}: ${Math.round(p.data[0])}%<br/>${t.xRaw}: ${p.data[4].toFixed(3)}<br/>${t.yAxis}: ${Math.round(p.data[1] * 100)}%`,
      },
      series: [
        {
          type: "scatter",
          symbolSize: 16,
          data: points.map(({ rank, node }) => [
            rank,
            node.risk_score,
            node.label,
            sectorLabel(node.sector, locale),
            node.eigenvector_centrality,
          ]),
          itemStyle: {
            color: CHART.brand,
            opacity: 0.85,
            // A 2px ring keeps overlapping points readable.
            borderColor: "#ffffff",
            borderWidth: 2,
          },
          label: {
            show: true,
            position: "top",
            color: CHART.ink,
            fontFamily: CHART.mono,
            fontSize: 12,
            formatter: (p: { data: [number, number, string] }) =>
              named.has(p.data[2]) ? p.data[2] : "",
          },
          // `moveOverlap` nudges colliding labels apart before
          // `hideOverlap` drops any that still cannot fit — two points at
          // nearly the same coordinates keep both names instead of losing
          // one of them.
          labelLayout: { moveOverlap: "shiftY", hideOverlap: true },
        },
      ],
    }),
    // `locale` is read directly now that sector names are translated for the
    // tooltip, so switching language has to rebuild the option — `t` alone no
    // longer covers everything locale-dependent in here.
    [t, locale, points, named]
  );

  return (
    <section className="mt-14 flex flex-col">
      <h3 className="text-sm font-medium">{t.scatterTitle}</h3>
      <p className="mt-1 text-xs leading-relaxed text-dim">{t.scatterLead}</p>
      <DataState
        className="mt-4 flex flex-1 flex-col"
        loading={isLoading}
        error={error}
        onRetry={() => mutate()}
        empty={Boolean(data) && nodesSource.length === 0}
        reserve="min-h-[26rem]"
      >
        {/* The chart takes whatever height the row gives it. Beside a taller
            neighbour that turns blank card into plot area, which is also the
            cheapest way to hold crowded points apart. */}
        <EChart
          option={scatterOption}
          ariaLabel={t.scatterTitle}
          className="qp-panel h-auto min-h-[36rem] flex-1 p-3"
        />
      </DataState>
    </section>
  );
}

/**
 * How the network groups the same stocks.
 *
 * The model finds these clusters from price behaviour, not from sector
 * labels, so which names fall together says something a sector breakdown
 * cannot. It reads as a list rather than a chart because the only quantity
 * involved is how many names are in each group.
 */
function ClusterBreakdown({ locale }: { locale: "vi" | "en" }) {
  const t = COPY[locale];
  const { data, error, isLoading, mutate } = useNetworkSnapshot();
  const nodesSource = useMemo(() => data?.nodes ?? [], [data]);

  const clusters = useMemo(() => {
    const byCluster = new Map<number, string[]>();
    for (const n of nodesSource) {
      byCluster.set(n.community, [...(byCluster.get(n.community) ?? []), n.label]);
    }
    return [...byCluster.entries()]
      .map(([id, members]) => ({ id, members }))
      .sort((a, b) => b.members.length - a.members.length);
  }, [nodesSource]);

  return (
    <section className="mt-14">
      <h3 className="text-sm font-medium">{t.clusterTitle}</h3>
      <p className="mt-1 text-xs leading-relaxed text-dim">{t.clusterLead}</p>
      <DataState
        className="mt-4"
        loading={isLoading}
        error={error}
        onRetry={() => mutate()}
        empty={Boolean(data) && nodesSource.length === 0}
        reserve="min-h-[26rem]"
      >
        <ul className="qp-panel space-y-4 p-5">
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
      </DataState>
    </section>
  );
}

export { ClusterBreakdown, InfluenceScatter };
