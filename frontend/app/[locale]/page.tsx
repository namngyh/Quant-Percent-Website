import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Reveal } from "@/components/reveal";
import { HeroAnimation } from "@/components/home/hero-animation";
import { MarketPulse } from "@/components/home/market-pulse";
import { PerformancePreview } from "@/components/home/performance-preview";
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
      {/* Hero (§7.1–7.2) */}
      <section className="relative overflow-hidden">
        <HeroAnimation />
        <div className="container-qp relative flex min-h-[calc(100vh-4rem)] flex-col justify-center py-24">
          <div className="hero-accent pl-6 desk:pl-8">
            <Reveal>
              <h1 className="title-xl max-w-full desk:max-w-[48vw] xl:max-w-[44rem]">
                {t("title")}
              </h1>
            </Reveal>
            <Reveal delay={0.15}>
              <p className="mt-7 max-w-xl text-lg leading-relaxed text-ink">
                {t("description")}
              </p>
            </Reveal>
            <Reveal delay={0.3}>
              <div className="mt-10 flex flex-wrap gap-3">
                <Button asChild>
                  <Link href="/market-intelligence">{t("primaryCta")}</Link>
                </Button>
                <Button asChild variant="ghost">
                  <Link href="/models">{t("secondaryCta")}</Link>
                </Button>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* Market pulse (§7.3) */}
      <MarketPulse />

      {/* By the numbers (§7.4) */}
      <ByTheNumbers />

      {/* Research systems (§7.5) */}
      <ResearchSystems />

      {/* Performance preview (§7.7) */}
      <PerformancePreview />

      {/* CTA (§7.8) */}
      <HomeCta />
    </main>
  );
}
