"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { EChartsCoreOption } from "echarts/core";
import { EChart, CHART } from "@/components/charts/echart";
import { InfoTip } from "@/components/info-tip";
import type { PortfolioNetwork } from "@/lib/api/types";
import { fmtPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * The portfolio drawn on DynamicGraph's VN30 dependency map.
 *
 * Held names are full colour with a dark ring; the rest of the index is
 * faded so the eye reads the holdings against the structure rather than the
 * structure itself. The list beside it says the same thing in words: how
 * much of the book sits in each community, which is the number the
 * correlation figures above only imply.
 *
 * Same palette and force settings as the model page's own map, so the two
 * agree about which community is which colour.
 */

const COMMUNITY_COLORS = [
  "#3a72c4",
  "#ad7519",
  "#158f66",
  "#8a4fbd",
  "#c0433a",
  "#3f7d8c",
  "#8a5a44",
  "#5b6b7a",
  "#9a6f2c",
];

const color = (community: number) =>
  COMMUNITY_COLORS[community % COMMUNITY_COLORS.length];

export function PortfolioNetwork({ network: n }: { network: PortfolioNetwork }) {
  const t = useTranslations("portfolio.network");
  const locale = useLocale();

  const option = useMemo<EChartsCoreOption>(() => {
    const maxStrength = Math.max(...n.nodes.map((x) => x.strength), 0.01);
    const data = n.nodes.map((node) => ({
      id: node.id,
      name: node.id,
      value: node.strength,
      held: node.in_portfolio,
      weight: node.weight,
      community: node.community,
      riskScore: node.risk_score,
      symbolSize: node.in_portfolio
        ? 30 + (node.weight ?? 0) * 40
        : 18 + (node.strength / maxStrength) * 14,
      itemStyle: node.in_portfolio
        ? { color: color(node.community), borderColor: CHART.ink, borderWidth: 3, opacity: 1 }
        : { color: color(node.community), borderColor: "#ffffff", borderWidth: 1.5, opacity: 0.32 },
      label: {
        show: true,
        position: "inside",
        color: "#ffffff",
        fontFamily: CHART.mono,
        fontSize: node.in_portfolio ? 11 : 9,
        fontWeight: node.in_portfolio ? 700 : 500,
        opacity: node.in_portfolio ? 1 : 0.7,
      },
    }));
    const held = new Set(n.covered);
    const links = n.edges.map((e) => {
      const between = held.has(e.source) && held.has(e.target);
      const touches = held.has(e.source) || held.has(e.target);
      const positive = e.signed_weight >= 0;
      return {
        source: e.source,
        target: e.target,
        value: e.weight,
        signed: e.signed_weight,
        lineStyle: {
          color: positive ? CHART.brand : CHART.negative,
          width: between ? 2 + e.weight * 6 : touches ? 1 + e.weight * 3 : 0.6,
          opacity: between ? 0.85 : touches ? 0.35 : 0.06,
          type: positive ? "solid" : "dashed",
          curveness: 0.05,
        },
      };
    });
    return {
      animationDuration: 700,
      legend: { show: false },
      tooltip: {
        trigger: "item",
        confine: true,
        formatter: (p: { dataType?: string; data?: Record<string, unknown> }) => {
          if (p.dataType === "edge") {
            const d = p.data as { source: string; target: string; signed: number };
            return `<b>${d.source} ↔ ${d.target}</b><br/>${
              d.signed >= 0 ? t("together") : t("opposite")
            }: ${fmtPercent(Math.abs(d.signed), locale)}`;
          }
          const d = p.data as {
            name: string;
            held: boolean;
            weight: number | null;
            community: number;
            riskScore: number;
          };
          return [
            `<b>${d.name}</b>`,
            d.held && d.weight !== null
              ? `${t("weightLabel")}: ${fmtPercent(d.weight, locale)}`
              : t("notHeld"),
            `${t("communityLabel")} ${d.community + 1}`,
            `${t("riskLabel")}: ${Math.round(d.riskScore * 100)}/100`,
          ].join("<br/>");
        },
      },
      series: [
        {
          type: "graph",
          layout: "force",
          data,
          links,
          roam: true,
          draggable: false,
          force: { repulsion: 420, gravity: 0.05, edgeLength: [90, 200], friction: 0.62 },
          emphasis: { focus: "adjacency", lineStyle: { opacity: 0.9 } },
          blur: { itemStyle: { opacity: 0.12 }, lineStyle: { opacity: 0.02 } },
        },
      ],
    };
  }, [n, locale, t]);

  const top = n.communities.find((c) => c.held.length > 0);
  const multi = n.communities.filter((c) => c.held.length > 0);

  return (
    <section aria-labelledby="pf-network">
      <h2 id="pf-network" className="title-md inline-flex items-center gap-2">
        {t("heading")}
        <InfoTip
          wide
          text={[
            t("lead"),
            t("source", { window: n.window }),
            ...(n.stress_label ? [t("stress", { label: t(`stressLabel.${n.stress_label}`) })] : []),
          ]}
        />
      </h2>

      {top && top.held.length >= 2 && (
        <p className="mt-5 max-w-4xl border-l-4 border-signal bg-signal-soft px-5 py-4 leading-relaxed text-ink">
          {t("standout", {
            share: fmtPercent(top.portfolio_weight, locale, 0),
            count: top.held.length,
            members: top.held.join(", "),
            community: top.id + 1,
          })}
        </p>
      )}

      <div className="mt-6 grid gap-6 desk:grid-cols-[3fr_2fr]">
        <div className="min-w-0 overflow-hidden rounded-lg border border-border bg-background shadow-sm">
          <div className="flex flex-wrap gap-x-5 gap-y-2 border-b border-border px-4 py-3 text-xs text-dim">
            <span className="inline-flex items-center gap-2">
              <span className="h-3 w-3 rounded-full border-2 border-ink bg-brand" />
              {t("legendHeld")}
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-brand/30" />
              {t("legendOther")}
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="h-0.5 w-5 bg-brand" />
              {t("together")}
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="w-5 border-t-2 border-dashed border-negative" />
              {t("opposite")}
            </span>
          </div>
          <EChart option={option} ariaLabel={t("heading")} className="h-[26rem] bg-surface/35" />
        </div>

        <div className="rounded-lg border border-border bg-background p-5 shadow-sm">
          <h3 className="text-base font-semibold">{t("communitiesTitle")}</h3>
          <ul className="mt-3 divide-y divide-border/70">
            {multi.map((c) => (
              <li key={c.id} className="flex items-start justify-between gap-4 py-2.5 text-sm">
                <span className="inline-flex items-start gap-2">
                  <span
                    className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: color(c.id) }}
                  />
                  <span>
                    <span className="figure font-medium">{c.held.join(", ")}</span>
                    <span className="block text-xs text-dim">
                      {t("communityWith", {
                        community: c.id + 1,
                        others: c.members.filter((m) => !c.held.includes(m)).join(", ") || "—",
                      })}
                    </span>
                  </span>
                </span>
                <span className="figure shrink-0">{fmtPercent(c.portfolio_weight, locale, 0)}</span>
              </li>
            ))}
          </ul>
          <p className={cn("mt-4 text-xs leading-relaxed text-dim")}>
            {n.uncovered.length > 0
              ? t("uncovered", {
                  symbols: n.uncovered.join(", "),
                  share: fmtPercent(1 - n.covered_weight, locale, 0),
                })
              : t("allCovered")}
          </p>
        </div>
      </div>
    </section>
  );
}
