"use client";

import { useMemo, useState } from "react";
import { useLocale } from "next-intl";
import nodesSource from "@/public/research/dynamic-graph-nodes.json";
import { InfoTip } from "@/components/info-tip";
import { fmtPercent, fmtSignedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

type Node = (typeof nodesSource)[number];
type SortKey =
  | "rank"
  | "strength"
  | "eigenvector_centrality"
  | "risk_score"
  | "return_20d"
  | "volatility_20d"
  | "current_drawdown";

/**
 * VN30 ranked by position in the estimated dependence network.
 *
 * This ranks on what DynamicGraph actually measures — how tightly a stock is
 * tied to the rest of the index, and how exposed it currently is — which is
 * the layer its own validation supports. It is deliberately NOT a forecast
 * table: the model publishes no per-stock direction or probability, and
 * dressing centrality up as "likely to rise" would invent a claim the
 * research does not make.
 */

const COPY = {
  vi: {
    title: "Xếp hạng cổ phiếu VN30 theo mạng lưới liên kết",
    lead: "30 cổ phiếu VN30 xếp theo mức độ gắn kết với phần còn lại của rổ. Đây không phải dự báo giá — bảng cho biết cổ phiếu nào nằm ở trung tâm cấu trúc thị trường và cổ phiếu nào đang chịu áp lực.",
    rank: "Hạng",
    ticker: "Mã",
    sector: "Ngành",
    cluster: "Nhóm",
    influence: "Mức ảnh hưởng",
    influenceTip:
      "Cổ phiếu càng ở trung tâm mạng lưới thì biến động của nó càng đi cùng nhiều mã khác. Không phải chỉ báo mua bán.",
    risk: "Điểm rủi ro",
    riskTip:
      "Tổng hợp từ biến động, mức giảm từ đỉnh và rủi ro của các mã liên kết. Càng cao càng nhiều áp lực.",
    return20: "Lợi suất 20 phiên",
    vol: "Biến động",
    volTip: "Mức dao động giá trong 20 phiên gần nhất, quy theo năm.",
    drawdown: "Giảm từ đỉnh",
    drawdownTip: "Mức giảm so với đỉnh gần nhất của chính cổ phiếu đó.",
    sortBy: "Sắp xếp theo",
    showAll: "Xem đủ 30 mã",
    showTop: "Thu gọn còn 10 mã",
    basket:
      "Rổ VN30 sau kỳ đảo rổ ngày 03/08/2026 (PLX và TPB rời rổ; MCH và TCX vào rổ). Bảng hiện {count} mã: TCX chưa đủ một năm dữ liệu giá nên chưa đưa vào ước lượng mạng lưới được, và sẽ xuất hiện khi tích luỹ đủ lịch sử.",
    note: "Số liệu trích từ lần chạy nghiên cứu gần nhất. Cấu trúc mạng lưới được kiểm chứng ổn định giữa các phiên; tầng dự báo căng thẳng của mô hình chưa đạt và không được công bố.",
  },
  en: {
    title: "VN30 ranked by network position",
    lead: "The 30 VN30 constituents ranked by how tightly each moves with the rest of the basket. This is not a price forecast — it shows which stocks sit at the centre of the market's structure and which are under pressure.",
    rank: "Rank",
    ticker: "Ticker",
    sector: "Sector",
    cluster: "Cluster",
    influence: "Influence",
    influenceTip:
      "The more central a stock, the more its moves coincide with the rest of the index. Not a trading signal.",
    risk: "Risk score",
    riskTip:
      "Combines volatility, drawdown and the risk of connected names. Higher means more pressure.",
    return20: "20-day return",
    vol: "Volatility",
    volTip: "Price variability over the last 20 sessions, annualised.",
    drawdown: "Drawdown",
    drawdownTip: "Fall from the stock's own recent peak.",
    sortBy: "Sort by",
    showAll: "Show all 30",
    showTop: "Show top 10",
    basket:
      "VN30 after the 3 August 2026 rebalance (PLX and TPB out; MCH and TCX in). The table shows {count} names: TCX does not yet have a year of price history, so it cannot enter the network estimate and will appear once it does.",
    note: "Figures come from the most recent research run. The network structure is validated as stable between sessions; the model's stress-forecasting layer did not pass and is not published.",
  },
} as const;

export function NetworkRanking({
  locale,
  asOf,
}: {
  locale: "vi" | "en";
  /** Date of the research run these rows came from. */
  asOf?: string;
}) {
  const t = COPY[locale];
  const uiLocale = useLocale();
  const [sortKey, setSortKey] = useState<SortKey>("rank");
  const [expanded, setExpanded] = useState(false);

  const maxStrength = useMemo(
    () => Math.max(...nodesSource.map((n) => n.strength)),
    []
  );

  const rows = useMemo(() => {
    const sorted = [...nodesSource].sort((a, b) => {
      if (sortKey === "rank") return a.rank - b.rank;
      // Everything else reads best largest-first; drawdown is negative, so
      // sorting ascending puts the deepest fall on top.
      if (sortKey === "current_drawdown" || sortKey === "return_20d") {
        return a[sortKey] - b[sortKey];
      }
      return b[sortKey] - a[sortKey];
    });
    return expanded ? sorted : sorted.slice(0, 10);
  }, [sortKey, expanded]);

  const columns: { key: SortKey; label: string; tip?: string }[] = [
    { key: "eigenvector_centrality", label: t.influence, tip: t.influenceTip },
    { key: "risk_score", label: t.risk, tip: t.riskTip },
    { key: "return_20d", label: t.return20 },
    { key: "volatility_20d", label: t.vol, tip: t.volTip },
    { key: "current_drawdown", label: t.drawdown, tip: t.drawdownTip },
  ];

  return (
    <section aria-labelledby="network-ranking" className="mt-14">
      <h2 id="network-ranking" className="title-md">
        {t.title}
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-ink">{t.lead}</p>

      {/* A reader who follows the index will count the rows. Say which basket
          this is and why it is short of thirty, so a deliberate exclusion is
          not read as a missing row. */}
      <p className="mt-3 max-w-3xl rounded-lg border border-border bg-surface px-4 py-3 text-xs leading-relaxed text-dim">
        {t.basket.replace("{count}", String(nodesSource.length))}
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <span className="text-xs text-dim">{t.sortBy}:</span>
        {[{ key: "rank" as SortKey, label: t.rank }, ...columns].map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={() => setSortKey(c.key)}
            aria-pressed={sortKey === c.key}
            className={cn(
              "rounded-full border px-3 py-1.5 text-xs transition-colors",
              sortKey === c.key
                ? "border-brand bg-brand text-background"
                : "border-border text-dim hover:border-brand hover:text-brand"
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="mt-5 overflow-x-auto rounded-lg border border-border shadow-sm">
        <table className="w-full min-w-[820px] text-[13px]">
          <thead>
            <tr className="border-b border-border bg-surface text-left">
              <th scope="col" className="px-4 py-3 font-medium text-dim">
                {t.rank}
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-dim">
                {t.ticker}
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-dim">
                {t.sector}
              </th>
              {columns.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  aria-sort={sortKey === c.key ? "descending" : undefined}
                  className="px-4 py-3 text-right font-medium text-dim"
                >
                  <span className="inline-flex items-center gap-1.5">
                    {c.label}
                    {c.tip && <InfoTip text={c.tip} />}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((n: Node) => (
              <tr key={n.id} className="border-b border-border last:border-0">
                <td className="figure px-4 py-3 text-dim">{n.rank}</td>
                <td className="figure px-4 py-3 font-semibold">{n.label}</td>
                <td className="px-4 py-3 text-dim">{n.sector}</td>

                {/* Influence carries a bar as well as a number: the ordering
                    is the point, and a bar reads faster than four decimals. */}
                <td className="px-4 py-3">
                  <span className="flex items-center justify-end gap-2">
                    <span
                      aria-hidden="true"
                      className="h-1.5 rounded-full bg-brand/70"
                      style={{
                        width: `${Math.max(4, (n.strength / maxStrength) * 72)}px`,
                      }}
                    />
                    <span className="figure w-12 text-right tabular-nums">
                      {n.eigenvector_centrality.toFixed(2)}
                    </span>
                  </span>
                </td>

                <td className="figure px-4 py-3 text-right tabular-nums">
                  {fmtPercent(n.risk_score, uiLocale)}
                </td>
                <td
                  className={cn(
                    "figure px-4 py-3 text-right tabular-nums",
                    n.return_20d > 0 && "text-positive",
                    n.return_20d < 0 && "text-negative"
                  )}
                >
                  {fmtSignedPercent(n.return_20d, uiLocale)}
                </td>
                <td className="figure px-4 py-3 text-right tabular-nums">
                  {fmtPercent(n.volatility_20d, uiLocale)}
                </td>
                <td className="figure px-4 py-3 text-right tabular-nums text-negative">
                  {fmtPercent(n.current_drawdown, uiLocale)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-[13px] font-medium text-brand hover:text-brand-strong"
        >
          {expanded ? t.showTop : t.showAll}
        </button>
      </div>

      <p className="mt-3 max-w-3xl text-xs leading-relaxed text-dim">
        {asOf && (
          <span className="figure">
            {locale === "vi" ? "Dữ liệu đến" : "Data through"} {asOf} ·{" "}
          </span>
        )}
        {t.note}
      </p>
    </section>
  );
}
