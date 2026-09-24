import { getTranslations } from "next-intl/server";
import { ArrowUpRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Reveal } from "@/components/reveal";
import { TERMINAL_ENTRY } from "@/lib/terminal";

/*
 * An illustrative equity curve for the mock window. Fixed points rather than
 * generated ones, so the server and the client draw the same line and the
 * picture never changes between visits. It is a drawing of what the Terminal
 * shows, not a result, and it carries no numbers that could be read as one
 * beyond the three labelled placeholders below.
 */
const CURVE = [
  62, 60, 63, 58, 61, 57, 55, 58, 54, 50, 52, 48, 51, 46, 43, 47, 42, 39, 41, 36, 33, 35, 30,
  32, 27, 24, 26, 22, 19, 21, 17,
];
const CANDLES = [
  [70, 64, 72, 61], [64, 66, 69, 62], [66, 60, 67, 58], [60, 63, 65, 57], [63, 58, 64, 55],
  [58, 55, 60, 52], [55, 57, 59, 51], [57, 52, 58, 49], [52, 49, 54, 46], [49, 51, 53, 45],
  [51, 46, 52, 43], [46, 44, 48, 40], [44, 47, 49, 41], [47, 42, 48, 39], [42, 38, 44, 35],
  [38, 40, 42, 34], [40, 36, 41, 33], [36, 33, 38, 30],
];

/** What QP Terminal is for, with a drawn window of it and the way in. */
export async function TerminalShowcase() {
  const t = await getTranslations("home.terminal");
  const tHero = await getTranslations("home.hero");
  const features = t.raw("features") as string[];

  const path = CURVE.map((y, i) => `${i === 0 ? "M" : "L"}${(i / (CURVE.length - 1)) * 300},${y}`).join(" ");

  return (
    <section className="relative overflow-hidden border-b border-border bg-background">
      <div aria-hidden="true" className="numeral-clip">
        <span className="section-numeral">04</span>
      </div>
      <div className="container-qp section-pad relative">
        <div className="grid items-center gap-14 desk:grid-cols-[1fr_1.05fr] desk:gap-20">
          <div>
            <p className="eyebrow">
              <span className="tick text-accent/60">04</span>
              {t("eyebrow")}
            </p>
            <h2 className="title-lg mt-5">{t("title")}</h2>
            <p className="mt-6 text-lg leading-relaxed text-dim">{t("description")}</p>
            <ul className="mt-8 space-y-3.5">
              {features.map((feature) => (
                <li key={feature} className="flex gap-3 text-[15px] leading-relaxed text-ink">
                  <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand-strong">
                    <Check className="size-3.5" aria-hidden="true" />
                  </span>
                  {feature}
                </li>
              ))}
            </ul>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Button asChild>
                <a href={TERMINAL_ENTRY} target="_blank" rel="noopener noreferrer">
                  {t("cta")}
                  <ArrowUpRight className="ml-1 size-4" aria-hidden="true" />
                  <span className="sr-only">({tHero("opensNewTab")})</span>
                </a>
              </Button>
              <span className="text-sm text-dim">{t("note")}</span>
            </div>
          </div>

          {/* A drawn window, not a screenshot: it cannot go stale when the
              Terminal's interface changes, and it stays sharp at any size. */}
          <Reveal delay={0.1}>
            <div
              aria-hidden="true"
              className="overflow-hidden rounded-xl border border-border bg-[#0f1b2a] shadow-[var(--shadow-md)]"
            >
              <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3">
                <span className="size-2.5 rounded-full bg-white/20" />
                <span className="size-2.5 rounded-full bg-white/20" />
                <span className="size-2.5 rounded-full bg-white/20" />
                <span className="ml-3 truncate font-mono text-[12px] text-white/60">
                  {t("mockTitle")}
                </span>
              </div>
              <div className="p-5">
                <svg viewBox="0 0 300 80" className="h-40 w-full" preserveAspectRatio="none">
                  {CANDLES.map(([open, close, high, low], i) => {
                    const x = 8 + i * 16;
                    const up = close < open; // SVG y grows downward
                    const color = up ? "#4ade80" : "#f87171";
                    return (
                      <g key={i}>
                        <line x1={x} x2={x} y1={low} y2={high} stroke={color} strokeWidth="1" />
                        <rect
                          x={x - 4}
                          width="8"
                          y={Math.min(open, close)}
                          height={Math.max(1.5, Math.abs(open - close))}
                          fill={color}
                        />
                      </g>
                    );
                  })}
                </svg>
                <svg viewBox="0 0 300 80" className="mt-3 h-20 w-full" preserveAspectRatio="none">
                  <path d={`${path} L300,80 L0,80 Z`} fill="rgb(96 165 250 / 0.14)" />
                  <path d={path} fill="none" stroke="#60a5fa" strokeWidth="2" vectorEffect="non-scaling-stroke" />
                </svg>
                <div className="mt-4 grid grid-cols-3 gap-3 border-t border-white/10 pt-4">
                  {[
                    [t("mockReturn"), "—"],
                    [t("mockDrawdown"), "—"],
                    [t("mockTrades"), "—"],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <p className="text-[11px] uppercase tracking-[0.08em] text-white/50">{label}</p>
                      <p className="mt-1 font-mono text-lg text-white/80">{value}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
