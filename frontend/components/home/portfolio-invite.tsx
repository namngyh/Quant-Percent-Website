import { getTranslations } from "next-intl/server";
import { ArrowRight, ListChecks, PieChart, ShieldAlert } from "lucide-react";
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
 */
export async function PortfolioInvite() {
  const t = await getTranslations("home.portfolio");

  const steps = [
    { icon: ListChecks, key: "step1" },
    { icon: PieChart, key: "step2" },
    { icon: ShieldAlert, key: "step3" },
  ] as const;

  return (
    <section className="border-t border-border bg-surface/60">
      <div className="container-qp section-pad">
        <div className="grid gap-12 desk:grid-cols-[1.1fr_1fr] desk:items-center">
          <div>
            <p className="eyebrow">{t("eyebrow")}</p>
            <h2 className="title-lg mt-4">{t("title")}</h2>
            <p className="mt-5 max-w-xl leading-relaxed text-ink">
              {t("description")}
            </p>

            <blockquote className="mt-6 max-w-xl border-l-4 border-signal bg-background px-5 py-4 leading-relaxed text-ink shadow-sm">
              {t("example")}
            </blockquote>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Button asChild>
                <Link href="/quant-portfolio">
                  {t("cta")}
                  <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
                </Link>
              </Button>
              <span className="text-sm text-dim">{t("noSignup")}</span>
            </div>
          </div>

          <ol className="space-y-5">
            {steps.map(({ icon: Icon, key }, index) => (
              <li
                key={key}
                className="flex gap-4 rounded-lg border border-border bg-background p-5 shadow-sm"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
                  <Icon className="h-5 w-5" aria-hidden="true" />
                </span>
                <div>
                  <p className="font-semibold">
                    <span className="figure mr-2 text-dim">{index + 1}</span>
                    {t(`${key}.title`)}
                  </p>
                  <p className="mt-1.5 text-sm leading-relaxed text-dim">
                    {t(`${key}.body`)}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
