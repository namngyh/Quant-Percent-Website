import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Reveal } from "@/components/reveal";
import { LiveBoard } from "@/components/home/live-board";
import { WeAre } from "@/components/home/we-are";
import { PercentMark } from "@/components/percent-mark";
import { DistributionCurve } from "@/components/decor/distribution-curve";
import { ArrowUpRight } from "lucide-react";
import { PortfolioInvite } from "@/components/home/portfolio-invite";
import { ProductTrio } from "@/components/home/product-trio";
import { CommunityLatest } from "@/components/home/community-latest";
import { TerminalShowcase } from "@/components/home/terminal-showcase";
import { HomeCta, ResearchSystems } from "@/components/home/sections";
import { TERMINAL_ENTRY } from "@/lib/terminal";

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

        It used to be a navy slab. White is the better ground for the same
        argument: the opening sequence draws back two white panels, so a dark
        hero meant the site's first frame was a hole opening in the shutter,
        and the live board — the one thing here that has to look like an
        instrument — had to fight a dark surround to stay legible. On white the
        shutter simply dissolves into the page.
      */}
      {/*
        The hero and the ticker together are the first screen, so they are
        measured together: this wrapper is exactly the viewport minus the 4rem
        header, the hero grows to fill whatever the ticker does not take, and
        the band lands on the fold as the bottom edge of the opening.

        Sizing the hero alone in `vh` was what let the dark Modus section show
        through underneath — the hero was capped at 82vh, and 82vh plus a header
        plus a ticker is less than a screen, so the next section always got the
        remainder. `svh` rather than `vh` because on a phone `vh` measures the
        viewport with the browser's toolbars retracted, which is not the height
        the page is first painted at.
      */}
      <div className="flex min-h-[calc(100svh-4rem)] flex-col">
      <section className="relative flex flex-1 overflow-hidden bg-background">
        <div aria-hidden="true" className="hero-grid" />
        {/*
          The brand mark at display size, cropped by the section edge. It is
          the logo rather than an abstract flourish, so the identity registers
          before a visitor reads a word — and cropping it keeps it a texture
          instead of a second thing competing with the headline. It drifts, on
          a slow period.

          A field of equations and seven small figures were layered in here over
          several passes, and the accumulation was the problem: each layer was
          faint on its own, but five of them behind a headline is noise, and
          they were placed by eyeballing percentages rather than against any
          grid, so the composition was unbalanced as well as busy. What is left
          is the measurement grid, this mark, and the density curve below —
          three things, each anchored to an edge.
        */}
        <PercentMark className="float pointer-events-none absolute -left-28 -top-20 hidden h-[30rem] w-[30rem] text-accent/[0.06] desk:block" />

        {/* The one figure that came back: a return distribution with its 5%
            tail shaded, low and to the right. It is the picture behind every
            loss figure the site publishes. */}
        <DistributionCurve className="pointer-events-none absolute -bottom-12 right-[-4rem] hidden h-[24rem] w-[48rem] text-accent/[0.055] desk:block" />
        <div className="container-qp relative flex w-full items-center py-24 desk:py-28">
          <div className="grid w-full items-center gap-14 desk:grid-cols-[1.05fr_0.95fr] desk:gap-20">
            <div>
              <Reveal>
                <p className="eyebrow">{t("eyebrow")}</p>
              </Reveal>
              <Reveal delay={0.08}>
                {/* The accent lands on the second clause only, so the sentence
                    keeps one stressed phrase rather than being one colour end
                    to end. */}
                <h1 className="title-xl mt-7 text-foreground">
                  {t("titleLead")}{" "}
                  <span className="accent-text">{t("titleAccent")}</span>
                </h1>
              </Reveal>
              <Reveal delay={0.16}>
                {/* One line, not a paragraph. What replaced it said the same
                    thing twice over three sentences, and a visitor deciding
                    whether to keep reading does not read the third. */}
                <p className="mt-8 max-w-lg text-xl leading-relaxed text-dim">
                  {t("description")}
                </p>
              </Reveal>
              <Reveal delay={0.24}>
                <div className="mt-11 flex flex-wrap gap-3">
                  <Button asChild>
                    <Link href="/quant-portfolio">{t("primaryCta")}</Link>
                  </Button>
                  <Button asChild variant="outline">
                    <a href={TERMINAL_ENTRY} target="_blank" rel="noopener noreferrer">
                      {t("secondaryCta")}
                      <ArrowUpRight className="ml-1 size-4" aria-hidden="true" />
                      <span className="sr-only">({t("opensNewTab")})</span>
                    </a>
                  </Button>
                </div>
              </Reveal>
            </div>
            {/* `qp-intro-reveal` is driven by the opening sequence in CSS, so
                the board resolves as the mark docks into the header. On a
                repeat visit the class does nothing and the scroll reveal runs
                on its own. */}
            <div className="qp-intro-reveal">
              <Reveal delay={0.2}>
                {/* The line sits above the board rather than beside the
                    headline: the left column is one continuous argument, and
                    dropping a second, differently-shaped statement into it
                    would interrupt that. Here it introduces the instrument. */}
                <WeAre />
                <div className="mt-5">
                  <LiveBoard />
                </div>
              </Reveal>
            </div>
          </div>
        </div>
      </section>

      {/* Live quotes, scrolling. The one thing on the page that moves by
          itself without being decoration — every figure in it is real. It is
          inside the first-screen wrapper so it closes the fold rather than
          starting the scroll. */}
      </div>

      {/*
        Built around what a visitor can do here rather than what the team
        reports: the community, the portfolio tool and QP Terminal, then the
        research behind them.

        Two sections left in this pass. The market pulse went with the retired
        market-intelligence page. The Modus comparison is sealed while the
        system is re-examined, and a sealed panel on the homepage asked a
        first-time visitor to look at something they were not allowed to see;
        it stays in components/home/modus-comparison.tsx for when the seal
        lifts.
      */}

      {/* All three at a glance, for anyone who stops reading here. */}
      <ProductTrio />

      {/* The newest articles: proof the community is alive. */}
      <CommunityLatest locale={locale} />

      {/* The one thing a visitor can run against their own holdings. */}
      <PortfolioInvite />

      <TerminalShowcase />

      <ResearchSystems />

      <HomeCta />
    </main>
  );
}
