import { getTranslations } from "next-intl/server";
import { ArrowRight, ArrowUpRight, MessagesSquare, PieChart, TerminalSquare } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Reveal } from "@/components/reveal";
import { TERMINAL_ENTRY } from "@/lib/terminal";

interface Product {
  key: "community" | "portfolio" | "terminal";
  href: string;
  icon: LucideIcon;
  external?: boolean;
  isNew?: boolean;
}

/*
 * The three things a visitor can actually do here, side by side, straight
 * after the hero. Each gets a fuller section further down; this row exists so
 * someone who only reads the first two screens still leaves knowing all three.
 *
 * The Terminal opens in a new tab (it lives on its own subdomain, and a
 * member works in it for a long session), so its card says so.
 */
const PRODUCTS: Product[] = [
  { key: "community", href: "/articles", icon: MessagesSquare, isNew: true },
  { key: "portfolio", href: "/quant-portfolio", icon: PieChart },
  { key: "terminal", href: TERMINAL_ENTRY, icon: TerminalSquare, external: true, isNew: true },
];

export async function ProductTrio() {
  const t = await getTranslations("home.products");
  const tHero = await getTranslations("home.hero");

  return (
    <section className="tint relative overflow-hidden border-b border-border">
      <div aria-hidden="true" className="numeral-clip">
        <span className="section-numeral">01</span>
      </div>
      <div className="container-qp section-pad relative">
        <p className="eyebrow">
          <span className="tick text-accent/60">01</span>
          {t("eyebrow")}
        </p>
        <h2 className="title-lg mt-5">{t("title")}</h2>

        <ul className="mt-12 grid gap-5 desk:grid-cols-3">
          {PRODUCTS.map((p, i) => {
            const Icon = p.icon;
            const Arrow = p.external ? ArrowUpRight : ArrowRight;
            const label = (
              <>
                {t(`${p.key}.cta`)}
                <Arrow className="size-4" aria-hidden="true" />
                {p.external && <span className="sr-only">({tHero("opensNewTab")})</span>}
              </>
            );
            const linkClass =
              "arrow-link mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-brand after:absolute after:inset-0 after:content-['']";
            return (
              <li key={p.key}>
                <Reveal index={i} className="h-full">
                  <article className="glow-card relative flex h-full flex-col p-7">
                    <div className="flex items-center justify-between">
                      <span className="flex size-12 items-center justify-center rounded-xl bg-brand-soft text-brand-strong">
                        <Icon className="size-6" aria-hidden="true" />
                      </span>
                      {p.isNew && (
                        <span className="rounded-full bg-accent px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-white">
                          {t("new")}
                        </span>
                      )}
                    </div>
                    <h3 className="mt-6 text-xl font-semibold">{t(`${p.key}.title`)}</h3>
                    <p className="mt-3 flex-1 text-[15px] leading-relaxed text-dim">
                      {t(`${p.key}.text`)}
                    </p>
                    {/* The link's box covers the card, so the whole card is
                        the target without nesting interactive elements. */}
                    {p.external ? (
                      <a href={p.href} target="_blank" rel="noopener noreferrer" className={linkClass}>
                        {label}
                      </a>
                    ) : (
                      <Link href={p.href} className={linkClass}>
                        {label}
                      </Link>
                    )}
                  </article>
                </Reveal>
              </li>
            );
          })}
        </ul>
        <p className="mt-6 text-sm text-dim">{t("membersNote")}</p>
      </div>
    </section>
  );
}
