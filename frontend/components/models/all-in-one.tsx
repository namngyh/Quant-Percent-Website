"use client";

import { useLocale } from "next-intl";
import { MarketBrief } from "@/components/models/market-brief";
import { CurrentOutput, ForecastChart } from "@/components/models/model-output";
import { ForecastFan } from "@/components/models/forecast-fan";
import { RiskInMoney } from "@/components/models/risk-in-money";
import { RiskProfile } from "@/components/models/risk-profile";
import { RaemfRiskTable } from "@/components/models/raemf-risk-table";
import { DynamicNetwork } from "@/components/models/dynamic-network";
import { NetworkRanking } from "@/components/models/network-ranking";
import {
  ClusterBreakdown,
  InfluenceScatter,
} from "@/components/models/network-clusters";
import { cn } from "@/lib/utils";

/**
 * The four models on one page, laid out to be looked at rather than read.
 *
 * The first version put a heading, a lead paragraph and a link above every
 * section — three blocks of prose before the reader reaches a number,
 * repeated eight times. The second cut the prose but left every panel at full
 * width, so the page became one tall column: eight blocks stacked down the
 * middle, and comparing any two of them meant scrolling between them.
 *
 * This one runs across. A three-column grid takes the panels that are
 * naturally compact — a column of horizons, a three-bar range, a network map —
 * and sets them beside the wide one they belong with, so each row is a pair
 * that answers one question and the page is five rows instead of nine blocks.
 */

/** Column spans, only from the desktop breakpoint; narrower screens stack. */
const SPAN: Record<number, string> = {
  1: "",
  2: "desk:col-span-2",
  3: "desk:col-span-3",
};

/**
 * One panel in the grid, tagged with the model behind it.
 *
 * The tag is deliberately the smallest thing on the panel, and it is a label
 * rather than a link: this page is the whole story now. It used to link out
 * to a per-model report, which split the reader's attention across four
 * pages for the sake of a question — "which model made this?" — that the
 * tag already answers.
 */
function Panel({
  model,
  cols = 1,
  children,
}: {
  model: string;
  cols?: 1 | 2 | 3;
  children: React.ReactNode;
}) {
  return (
    <section
      // Several of these components carry their own top margin, which is what
      // separates them when they are stacked on a model's detail page. Here
      // the grid owns the spacing, and an inherited margin would drop one
      // half of a row below the other.
      //
      // A column flex with the child stretched: the grid already makes both
      // halves of a row the same height, and this passes that height down so
      // a chart that wants to grow (the scatter) can take it. Block content is
      // unaffected — it just sits at the top of a slightly taller box.
      className={cn(
        "flex min-w-0 flex-col [&>section]:mt-0! [&>section]:flex-1",
        SPAN[cols],
      )}
    >
      <p className="figure mb-2 text-[11px] uppercase tracking-[0.08em] text-dim">
        {model}
      </p>
      {children}
    </section>
  );
}

export function AllInOne({ names }: { names: Record<string, string> }) {
  const locale = useLocale() as "vi" | "en";
  const msdp = names.msdp ?? "MSDP";
  const rarf = names["rarf-fhe"] ?? "RARF-FHE";
  const graph = names["dynamic-graph"] ?? "DynamicGraph";
  const raemf = names["raemf-mc"] ?? "Tempus VNI";

  return (
    <div className="space-y-12">
      <MarketBrief />

      {/* Each row reads left to right: the compact panel states the numbers,
          the wide one beside it shows them. */}
      <div className="grid gap-x-8 gap-y-14 desk:grid-cols-3">
        <Panel model={msdp}>
          <CurrentOutput modelSlug="msdp" symbol="VNINDEX" />
        </Panel>
        {/* The forecast is what a reader comes for, so it takes two thirds of
            the row — enough width for the interval to visibly open out. */}
        <Panel model={msdp} cols={2}>
          <ForecastChart modelSlug="msdp" symbol="VNINDEX" />
        </Panel>

        {/* Two answers to "how bad could it get", side by side: the forecast
            range by horizon, and the chance of a fall of a given size. */}
        <Panel model={msdp}>
          <ForecastFan slug="msdp" symbol="VNINDEX" locale={locale} />
        </Panel>
        <Panel model={rarf} cols={2}>
          <RiskProfile locale={locale} />
        </Panel>

        {/* The same risk figures with the arithmetic done. Full width: three
            money cards across read at a glance, stacked they read as a list. */}
        <Panel model={rarf} cols={3}>
          <RiskInMoney />
        </Panel>

        {/* The fourth model's table, present and sealed. Leaving it off the
            page would hide that a model is under review; showing its current
            figures would publish numbers that fail a basic sanity check. */}
        <Panel model={raemf} cols={3}>
          <RaemfRiskTable />
        </Panel>

        {/* The map is a force layout: it pushes its nodes apart until it runs
            out of canvas, and in a third of a row the outer ones fall off the
            edge. It is also the one view here worth looking at whole. */}
        <Panel model={graph} cols={3}>
          <div className="overflow-hidden rounded-lg border border-border bg-background shadow-sm">
            <DynamicNetwork locale={locale} />
          </div>
        </Panel>

        {/* The groups the model found, beside where those stocks sit. The
            scatter needs the wide half: thirty tickers in a narrow box print
            over each other however the points are spread. */}
        <Panel model={graph}>
          <ClusterBreakdown locale={locale} />
        </Panel>
        <Panel model={graph} cols={2}>
          <InfluenceScatter locale={locale} />
        </Panel>

        {/* Eight columns of figures; anything narrower scrolls sideways. */}
        <Panel model={graph} cols={3}>
          <NetworkRanking locale={locale} />
        </Panel>
      </div>
    </div>
  );
}
