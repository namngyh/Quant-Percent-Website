import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Reveal } from "@/components/reveal";
import { LiveBoard } from "@/components/home/live-board";
import { PercentMark } from "@/components/percent-mark";
import { MarketPulse } from "@/components/home/market-pulse";
import { PerformancePreview } from "@/components/home/performance-preview";
import { PortfolioInvite } from "@/components/home/portfolio-invite";
import { ModusComparison } from "@/components/home/modus-comparison";
import {
  ByTheNumbers,
  HomeCta,
  ResearchSystems,
} from "@/components/home/sections";

export const dynamic = "force-dynamic";

export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("home.hero");

  return (
    <main>
      {/*
        Hero. Asymmetric split rather than a centred block: the argument reads
        down the left, the evidence sits to its right. A visitor sees a real
        quote with a real timestamp without scrolling, which is the fastest
        way to show this is a working system and not a brochure.
      */}
      <section className="relative overflow-hidden bg-foreground text-background">
        {/* Faint measurement grid — the surface a reading is taken on. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              "linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)",
            backgroundSize: "72px 72px",
          }}
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-1/4 top-0 h-full w-2/3 opacity-40"
          style={{
            background:
              "radial-gradient(ellipse at 60% 40%, rgba(58,114,196,0.35), transparent 65%)",
          }}
        />
        {/*
          The brand mark at display size, cropped by the section edge. It is
          the logo rather than an abstract flourish, so the identity registers
          before a visitor reads a word — and cropping it keeps it a texture
          instead of a second thing competing with the headline.
        */}
        <PercentMark className="pointer-events-none absolute -left-24 -top-16 hidden h-[26rem] w-[26rem] text-white/[0.055] desk:block" />
        <div className="container-qp relative py-20 desk:py-28">
          <div className="grid items-center gap-14 desk:grid-cols-[1.1fr_0.9fr] desk:gap-16">
            <div className="border-l-2 border-brand/70 pl-6 desk:pl-8">
              <Reveal>
                <h1 className="title-xl text-background">{t("title")}</h1>
              </Reveal>
              <Reveal delay={0.15}>
                <p className="mt-7 max-w-xl text-lg leading-relaxed text-white/70">
                  {t("description")}
                </p>
              </Reveal>
              <Reveal delay={0.3}>
                <div className="mt-10 flex flex-wrap gap-3">
                  <Button
                    asChild
                    className="bg-background text-foreground hover:bg-white/90"
                  >
                    <Link href="/market-intelligence">{t("primaryCta")}</Link>
                  </Button>
                  <Button
                    asChild
                    variant="ghost"
                    className="border border-white/20 text-white/85 hover:bg-white/10 hover:text-white"
                  >
                    <Link href="/models">{t("secondaryCta")}</Link>
                  </Button>
                </div>
              </Reveal>
            </div>
            <Reveal delay={0.2}>
              <LiveBoard />
            </Reveal>
          </div>
        </div>
      </section>

      {/* Full market state, below the fold (§7.3) */}
      <MarketPulse />

      {/* Model Modus is the flagship system, so its 2024-2026 record and the
          year-by-year breakdown behind it come before the supporting material
          rather than after it. */}
      <PerformancePreview />

      {/* The same record set against the index Modus trades. */}
      <ModusComparison />

      {/* The one thing a visitor can run against their own holdings. */}
      <PortfolioInvite />

      {/* By the numbers (§7.4) */}
      <ByTheNumbers />

      {/* Research systems (§7.5) */}
      <ResearchSystems />

      {/* CTA (§7.8) */}
      <HomeCta />
    </main>
  );
}
