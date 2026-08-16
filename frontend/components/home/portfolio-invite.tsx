import { getTranslations } from "next-intl/server";
import { ArrowRight } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";

/**
 * Invites a visitor to run their own portfolio through the analysis.
 *
 * The pitch is the one thing the tool does that a broker statement does not:
 * it separates how much money is in a position from how much of the risk that
 * position carries. Everything else on the page is about Quant Percent's own
 * research; this is the part a reader can point at their own holdings.
 *
 * No sign-up, and it says so — asking for an account before showing any value
 * is what makes this kind of tool go unused.
 *
 * A three-step "how it works" list used to sit beside this, one card per step
 * with an icon. It described the tool to people who had not decided to use it
 * yet, which is the wrong moment: the single real result below does that job
 * in one line, and the tool's own page explains itself to anyone who arrives.
 * Centred, because with the list gone there is no second column to balance.
 */
export async function PortfolioInvite() {
  const t = await getTranslations("home.portfolio");

  return (
    /* Tinted. The Modus report now ends on a white section of its own — the
       half its chart panel hangs into — so this one has to take the other
       surface or the two would run together with only a hairline between. */
    <section className="tint relative overflow-hidden border-y border-border">
      <div aria-hidden="true" className="numeral-clip">
        <span className="section-numeral">02</span>
      </div>
      <div className="container-qp section-pad relative">
        <div className="mx-auto max-w-3xl text-center">
          <p className="eyebrow">
            <span className="tick text-accent/60">02</span>
            {t("eyebrow")}
          </p>
          <h2 className="title-lg mt-5">{t("title")}</h2>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-dim">
            {t("description")}
          </p>

          {/* A real figure the tool produced, not an illustration. It is the
              only sentence here that proves the thing works. */}
          <blockquote className="glow-card mx-auto mt-10 max-w-2xl px-7 py-6 text-lg leading-relaxed text-foreground">
            {t("example")}
          </blockquote>

          <div className="mt-10 flex flex-col items-center gap-4">
            <Button asChild>
              <Link href="/quant-portfolio">
                {t("cta")}
                <ArrowRight className="ml-1 h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
            <span className="text-sm text-dim">{t("noSignup")}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
