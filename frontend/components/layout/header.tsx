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
  { key: "about", href: "/about" },
] as const;

export function Header() {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
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

  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 12);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  return (
    <header
      className="site-header sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur-sm"
      data-scrolled={scrolled}
    >
      <div className="container-qp flex h-16 items-center justify-between gap-6">
        <Link
          href="/"
          aria-label="Quant Percent"
          className="brand-link shrink-0"
        >
          <Brand priority />
        </Link>

        <nav className="hidden items-center gap-7 desk:flex" aria-label="Main">
          {NAV_ITEMS.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.key}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "nav-link text-[13px] font-medium tracking-[0.02em] transition-colors",
                  active ? "text-brand" : "text-dim hover:text-brand"
                )}
              >
                {t(item.key)}
              </Link>
            );
          })}
          <Link
            href="/contact"
            className={cn(
              "nav-link text-[13px] font-medium tracking-[0.02em] transition-colors",
              pathname.startsWith("/contact")
                ? "text-brand"
                : "text-dim hover:text-brand"
            )}
          >
            {t("contact")}
          </Link>
          <AuthNav />
          <LanguageSwitcher />
        </nav>

        <button
          type="button"
          className="rounded-md p-2 transition-colors hover:bg-surface desk:hidden"
          aria-label={open ? t("closeMenu") : t("openMenu")}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X className="size-6" /> : <Menu className="size-6" />}
        </button>
      </div>

      {/* Full-screen mobile drawer (§6) */}
      <AnimatePresence>
        {open && (
          <motion.nav
            className="fixed inset-x-0 bottom-0 top-16 z-50 flex flex-col overflow-y-auto bg-background desk:hidden"
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
                  onClick={() => setOpen(false)}
                  className="border-b border-border py-5 text-xl font-medium tracking-normal transition-[color,padding] duration-200 hover:pl-2 hover:text-brand"
                >
                  {t(item.key)}
                </Link>
              ))}
              <Link
                href="/contact"
                onClick={() => setOpen(false)}
                className="border-b border-border py-5 text-xl font-medium tracking-normal transition-[color,padding] duration-200 hover:pl-2 hover:text-brand"
              >
                {t("contact")}
              </Link>
              <AuthNav variant="mobile" onNavigate={() => setOpen(false)} />
              <div className="py-6">
                <LanguageSwitcher />
              </div>
            </div>
          </motion.nav>
        )}
      </AnimatePresence>
      <motion.div
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 h-0.5 origin-left bg-brand"
        style={{ scaleX: animate ? smoothProgress : scrollYProgress }}
      />
    </header>
  );
}
