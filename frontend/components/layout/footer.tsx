import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { Brand } from "@/components/brand";

const NAV_LINKS = [
  { key: "market", href: "/market-intelligence" },
  { key: "models", href: "/models" },
  { key: "performance", href: "/performance" },
  { key: "about", href: "/about" },
  { key: "contact", href: "/contact" },
] as const;

export async function Footer() {
  const t = await getTranslations("footer");
  const tNav = await getTranslations("nav");
  const tCommon = await getTranslations("common");

  return (
    <footer className="border-t-4 border-brand bg-foreground text-background">
      <div className="container-qp py-14">
        <div className="grid gap-10 desk:grid-cols-[1.4fr_1fr_1fr]">
          <div>
            <Brand />
            <p className="mt-3 text-[15px] text-white/75">{t("tagline")}</p>
            <p className="figure mt-2 text-[13px] text-white/50">{t("philosophy")}</p>
          </div>
          <nav aria-label={t("nav")}>
            <p className="eyebrow text-brand-soft">{t("nav")}</p>
            <ul className="mt-4 space-y-2.5">
              {NAV_LINKS.map((l) => (
                <li key={l.key}>
                  <Link
                    href={l.href}
                    className="text-[13px] text-white/55 transition-colors hover:text-white"
                  >
                    {tNav(l.key)}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <nav aria-label={t("legalNav")}>
            <p className="eyebrow text-signal-soft">{t("legalNav")}</p>
            <ul className="mt-4 space-y-2.5">
              <li>
                <Link
                  href="/legal"
                  className="text-[13px] text-white/55 transition-colors hover:text-white"
                >
                  {t("legal")}
                </Link>
              </li>
              <li>
                <Link
                  href="/privacy"
                  className="text-[13px] text-white/55 transition-colors hover:text-white"
                >
                  {t("privacy")}
                </Link>
              </li>
              <li>
                <Link
                  href="/system-status"
                  className="text-[13px] text-white/55 transition-colors hover:text-white"
                >
                  {t("systemStatus")}
                </Link>
              </li>
            </ul>
          </nav>
        </div>

        <div className="mt-12 border-t border-white/15 pt-8">
          <p className="max-w-3xl text-xs leading-relaxed text-white/45">
            {t("disclaimer")}
          </p>
          <p className="mt-3 max-w-3xl text-xs leading-relaxed text-white/45">
            {tCommon("mockNotice")}
          </p>
          <p className="mt-6 text-xs text-white/45">
            {t("copyright", { year: new Date().getFullYear() })}
          </p>
        </div>
      </div>
    </footer>
  );
}
