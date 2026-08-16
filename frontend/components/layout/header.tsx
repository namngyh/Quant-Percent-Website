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
import { Menu, X } from "lucide-react";
import { Link, usePathname } from "@/i18n/navigation";
import { LanguageSwitcher } from "@/components/layout/language-switcher";
import { AuthNav } from "@/components/auth/auth-nav";
import { Brand } from "@/components/brand";
import { cn } from "@/lib/utils";
import { useHydrated } from "@/lib/use-hydrated";

const NAV_ITEMS = [
  { key: "market", href: "/market-intelligence" },
  { key: "models", href: "/models" },
  { key: "performance", href: "/performance" },
  { key: "portfolio", href: "/quant-portfolio" },
  { key: "about", href: "/about" },
] as const;

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
              Two groups, not one row: the pills sit shoulder to shoulder
              because they are one control, and the account and language
              controls are pushed off with real space because they are not.

              The breakpoint here is 1180px, not the site-wide `desk` (980px).
              Six Vietnamese labels, a divider, two account links and the
              language switcher need about 1070px beside the brand; below that
              the pills were wrapping onto two lines each and the bar read as
              broken. `desk` still governs the page layout — only the choice
              between this nav and the drawer moves, and the drawer covers the
              gap perfectly well.
          */}
          <nav
            className="hidden items-center gap-3 min-[1180px]:flex"
            aria-label="Main"
          >
            <span className="flex items-center gap-0.5">
              {[...NAV_ITEMS, { key: "contact", href: "/contact" } as const].map(
                (item) => {
                  const active = pathname.startsWith(item.href);
                  return (
                    <Link
                      key={item.key}
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        // `whitespace-nowrap` so a label can never split
                        // across two lines inside its own pill.
                        "nav-link whitespace-nowrap text-[13px] font-medium",
                        active
                          ? "text-brand-strong"
                          : "text-ink hover:text-brand-strong"
                      )}
                    >
                      {t(item.key)}
                    </Link>
                  );
                }
              )}
            </span>
            <span aria-hidden="true" className="h-5 w-px bg-border" />
            <AuthNav />
            <LanguageSwitcher />
          </nav>

          <button
            type="button"
            className="rounded-full p-2.5 transition-colors hover:bg-surface-2 min-[1180px]:hidden"
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
            className="fixed inset-x-0 bottom-0 top-16 z-40 flex flex-col overflow-y-auto overscroll-contain bg-background min-[1180px]:hidden"
            aria-label="Mobile"
            initial={animate ? { opacity: 0, y: -10 } : false}
            animate={{ opacity: 1, y: 0 }}
            exit={animate ? { opacity: 0, y: -8 } : undefined}
            transition={{ duration: animate ? 0.24 : 0 }}
          >
            <div className="container-qp flex flex-1 flex-col py-6">
              {[{ key: "home", href: "/" } as const, ...NAV_ITEMS].map((item) => (
                <Link
                  key={item.key}
                  href={item.href}
                  onClick={close}
                  className="border-b border-border py-5 text-xl font-medium tracking-normal transition-[color,padding] duration-200 hover:pl-2 hover:text-brand"
                >
                  {t(item.key)}
                </Link>
              ))}
              <Link
                href="/contact"
                onClick={close}
                className="border-b border-border py-5 text-xl font-medium tracking-normal transition-[color,padding] duration-200 hover:pl-2 hover:text-brand"
              >
                {t("contact")}
              </Link>
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
