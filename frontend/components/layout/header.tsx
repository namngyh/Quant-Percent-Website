"use client";

import { useEffect, useState } from "react";
import {
  AnimatePresence,
  motion,
  useReducedMotion,
  useScroll,
  useSpring,
} from "framer-motion";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { ArrowUpRight, Menu, X } from "lucide-react";
import { Link, usePathname } from "@/i18n/navigation";
import { LanguageSwitcher } from "@/components/layout/language-switcher";
import {
  NavDropdown,
  NavDropdownExternal,
  NavDropdownLink,
} from "@/components/layout/nav-dropdown";
import { AuthNav } from "@/components/auth/auth-nav";
import { Brand } from "@/components/brand";
import { cn } from "@/lib/utils";
import { useHydrated } from "@/lib/use-hydrated";
import { TERMINAL_ENTRY } from "@/lib/terminal";

/*
 * The bar holds two links and two menus instead of six links, grouped by what a
 * visitor came to do: read today's market, read the research behind it, join
 * the members' articles, or use a tool. "About" lives in the footer beside
 * "Contact", and stays in the mobile drawer where length costs nothing.
 */
const MARKET = { key: "market", href: "/market-intelligence" } as const;

const RESEARCH = [
  { key: "models", href: "/models" },
  { key: "performance", href: "/performance" },
] as const;

// Articles are written, voted on and discussed by members, so they sit on the
// bar as the community rather than inside the team's own research.
const COMMUNITY = { key: "community", href: "/articles" } as const;

const TOOLS = [{ key: "portfolio", href: "/quant-portfolio" }] as const;

const ABOUT = { key: "about", href: "/about" } as const;

export function Header() {
  const t = useTranslations("nav");
  const pathname = usePathname();
  /*
   * What is stored is the route the drawer was opened on, not a boolean, and
   * "open" is derived by comparing it with the current route.
   *
   * Every link inside the drawer closes it on click, but browser back and
   * forward change the route without one, which would leave the panel covering
   * the page it navigated to. Deriving the flag closes it on any navigation at
   * all, including ones this component never hears about — and it does so
   * during render, where an effect that called setState would cost a second
   * render pass for every route change.
   */
  const [openedAt, setOpenedAt] = useState<string | null>(null);
  const open = openedAt !== null && openedAt === pathname;
  const close = () => setOpenedAt(null);
  const isActive = (href: string) => pathname.startsWith(href);

  const [scrolled, setScrolled] = useState(false);
  const hydrated = useHydrated();
  const reduced = useReducedMotion();
  const animate = !(hydrated && reduced);
  const { scrollYProgress } = useScroll();
  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 160,
    damping: 28,
    mass: 0.3,
  });

  // Lock body scroll while the drawer is open (links close it on click)
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  // Escape closes it, for anyone on a tablet with a keyboard attached.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenedAt(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 12);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  return (
    /*
      The drawer is a sibling of <header>, not a child of it, and that is load
      bearing rather than tidiness.

      An element with `backdrop-filter` becomes the containing block for every
      `position: fixed` descendant. The header carries a backdrop blur once the
      page is scrolled, so a fixed drawer nested inside it resolved
      `top: 4rem; bottom: 0` against the header's own 64px box and laid out at
      exactly zero height. The button toggled, the icon flipped to ✕, and
      nothing appeared — the menu was unusable on every scrolled page.

      Sibling placement is the fix that survives future styling: any filter,
      transform or `will-change` added to the header later would reintroduce the
      same trap, and none of them can reach a node outside it.
    */
    <>
      {/* The border and the shadow are held in the class list rather than in a
          `[data-scrolled]` CSS rule, because Tailwind's utilities layer sits
          after the components layer — `border-border` in the markup would
          always beat a `border-color` set on `.site-header`, and the header
          would keep its rule at rest no matter what the stylesheet said. */}
      <header
        className={cn(
          "site-header sticky top-0 z-50 border-b",
          // Translucent only when it is actually over page content. With the
          // drawer open the bar sits above an opaque white panel, and letting
          // the scrolled page blur through it left smudges of the old page
          // hanging over a clean menu.
          scrolled && !open
            ? "border-border bg-background/82 shadow-[var(--shadow-sm)] backdrop-blur-md"
            : "border-transparent bg-background",
          open && "border-border"
        )}
        data-scrolled={scrolled}
      >
        <div className="container-qp flex h-16 items-center justify-between gap-6">
          {/* `data-home-brand` is the landing target the opening sequence
              measures. Keep it on whichever element carries the lockup. */}
          <Link
            href="/"
            aria-label="Quant Percent"
            data-home-brand
            className="brand-link shrink-0"
          >
            <Brand priority />
          </Link>

          {/*
              Two groups: the section pills sit shoulder to shoulder because
              they are one control, and the Terminal, account and language
              controls are pushed off with real space because they are not.

              The bar used to carry six Vietnamese labels, a divider, two
              account links and a VI / EN pair — close to 1000px beside the
              brand, which kept the drawer on screen up to 1180px. With the
              sections folded into two menus, the account links into one
              control and the language pair into one button, it fits at the
              site-wide `desk` (980px), English labels included.
          */}
          <nav className="hidden items-center gap-5 desk:flex" aria-label="Main">
            <span className="flex items-center gap-0.5">
              <BarLink href={MARKET.href} active={isActive(MARKET.href)}>
                {t("marketShort")}
              </BarLink>

              <NavDropdown
                label={t("research")}
                active={RESEARCH.some((item) => isActive(item.href))}
              >
                {RESEARCH.map((item) => (
                  <NavDropdownLink
                    key={item.key}
                    href={item.href}
                    active={isActive(item.href)}
                  >
                    {t(item.key)}
                  </NavDropdownLink>
                ))}
              </NavDropdown>

              <BarLink href={COMMUNITY.href} active={isActive(COMMUNITY.href)}>
                {t(COMMUNITY.key)}
              </BarLink>

              <NavDropdown
                label={t("tools")}
                active={TOOLS.some((item) => isActive(item.href))}
              >
                {TOOLS.map((item) => (
                  <NavDropdownLink
                    key={item.key}
                    href={item.href}
                    active={isActive(item.href)}
                  >
                    {t(item.key)}
                  </NavDropdownLink>
                ))}
                <NavDropdownExternal
                  href={TERMINAL_ENTRY}
                  hint={t("terminalHint")}
                  newTabLabel={t("opensNewTab")}
                >
                  {t("terminal")}
                </NavDropdownExternal>
              </NavDropdown>
            </span>

            <span className="flex items-center gap-3">
              {/* The Terminal is the one product here people return to daily,
                  so it gets a direct button as well as its place in Tools. */}
              <a
                href={TERMINAL_ENTRY}
                target="_blank"
                rel="noopener noreferrer"
                title={t("terminalHint")}
                className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-border px-3.5 py-1.5 text-[13px] font-medium text-brand-strong transition-colors hover:border-brand hover:bg-brand-soft"
              >
                {t("terminal")}
                <ArrowUpRight aria-hidden="true" className="size-3.5" />
                <span className="sr-only">({t("opensNewTab")})</span>
              </a>
              <AuthNav />
              <LanguageSwitcher variant="compact" />
            </span>
          </nav>

          <button
            type="button"
            className="rounded-full p-2.5 transition-colors hover:bg-surface-2 desk:hidden"
            aria-label={open ? t("closeMenu") : t("openMenu")}
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpenedAt(open ? null : pathname)}
          >
            {open ? <X className="size-6" /> : <Menu className="size-6" />}
          </button>
        </div>

        <motion.div
          aria-hidden="true"
          className="absolute inset-x-0 bottom-0 h-0.5 origin-left bg-accent"
          style={{ scaleX: animate ? smoothProgress : scrollYProgress }}
        />
      </header>

      {/* Full-screen mobile drawer (§6). It starts below the header rather than
          under it, so a lower z-index than the bar is correct — the two never
          overlap, and the ✕ that closes the drawer has to stay on top. */}
      <AnimatePresence>
        {open && (
          <motion.nav
            id="mobile-nav"
            className="fixed inset-x-0 bottom-0 top-16 z-40 flex flex-col overflow-y-auto overscroll-contain bg-background desk:hidden"
            aria-label="Mobile"
            initial={animate ? { opacity: 0, y: -10 } : false}
            animate={{ opacity: 1, y: 0 }}
            exit={animate ? { opacity: 0, y: -8 } : undefined}
            transition={{ duration: animate ? 0.24 : 0 }}
          >
            <div className="container-qp flex flex-1 flex-col py-6">
              {/* The drawer has the room the bar lacks, so the menus open flat
                  here, each under its own small heading. */}
              <DrawerLink href="/" onClick={close}>
                {t("home")}
              </DrawerLink>
              <DrawerLink href={MARKET.href} onClick={close}>
                {t(MARKET.key)}
              </DrawerLink>
              {/* Up here with the other ungrouped pages: placed after Tools it
                  read as one of the tools. */}
              <DrawerLink href={ABOUT.href} onClick={close}>
                {t(ABOUT.key)}
              </DrawerLink>
              <DrawerHeading>{t("research")}</DrawerHeading>
              {RESEARCH.map((item) => (
                <DrawerLink key={item.key} href={item.href} onClick={close}>
                  {t(item.key)}
                </DrawerLink>
              ))}
              <DrawerHeading>{t(COMMUNITY.key)}</DrawerHeading>
              <DrawerLink href={COMMUNITY.href} onClick={close}>
                {t("articles")}
              </DrawerLink>
              <DrawerHeading>{t("tools")}</DrawerHeading>
              {TOOLS.map((item) => (
                <DrawerLink key={item.key} href={item.href} onClick={close}>
                  {t(item.key)}
                </DrawerLink>
              ))}
              <a
                href={TERMINAL_ENTRY}
                target="_blank"
                rel="noopener noreferrer"
                onClick={close}
                className={cn(drawerLinkClass, "inline-flex items-center gap-2")}
              >
                {t("terminal")}
                <ArrowUpRight aria-hidden="true" className="size-5" />
                <span className="sr-only">({t("opensNewTab")})</span>
              </a>
              <AuthNav variant="mobile" onNavigate={close} />
              <div className="py-6">
                <LanguageSwitcher />
              </div>
            </div>
          </motion.nav>
        )}
      </AnimatePresence>
    </>
  );
}

function BarLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        // `whitespace-nowrap` so a label can never split across two lines
        // inside its own pill.
        "nav-link whitespace-nowrap text-[13px] font-medium",
        active ? "text-brand-strong" : "text-ink hover:text-brand-strong"
      )}
    >
      {children}
    </Link>
  );
}

const drawerLinkClass =
  "border-b border-border py-5 text-xl font-medium tracking-normal transition-[color,padding] duration-200 hover:pl-2 hover:text-brand";

function DrawerLink({
  href,
  onClick,
  children,
}: {
  href: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Link href={href} onClick={onClick} className={drawerLinkClass}>
      {children}
    </Link>
  );
}

function DrawerHeading({ children }: { children: ReactNode }) {
  return (
    <p className="pb-1 pt-7 text-[12px] font-medium uppercase tracking-[0.12em] text-dim">
      {children}
    </p>
  );
}
