import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { Brand } from "@/components/brand";

const NAV_LINKS = [
  { key: "market", href: "/market-intelligence" },
  { key: "models", href: "/models" },
  { key: "performance", href: "/performance" },
  { key: "portfolio", href: "/quant-portfolio" },
  { key: "about", href: "/about" },
] as const;

/*
  "Liên hệ" used to sit in the header nav. It lives here now, alongside the
  two channels that go with it — feedback, which needs an account, and the
  open call for people who want to build with us. Grouping the three under
  one heading is what let the header drop a label.
*/
const CONNECT_LINKS = [
  { key: "contactLink", href: "/contact" },
  { key: "feedbackLink", href: "/feedback" },
  { key: "joinLink", href: "/join" },
] as const;

export async function Footer() {
  const t = await getTranslations("footer");
  const tNav = await getTranslations("nav");
  const tCommon = await getTranslations("common");

  return (
    /*
      The footer was a navy slab closing a white page. It is now the same
      white family as everything above it, held apart by a tinted surface and
      a single hairline — which is what keeps the site reading as one sheet
      rather than as a page with a lid on it. The brand anchor the heavy navy
      rule used to provide is carried by the gradient hairline instead.
    */
    <footer className="border-t border-border bg-surface">
      <div aria-hidden="true" className="h-[3px] bg-accent" />
      <div className="container-qp py-16">
        <div className="grid gap-12 desk:grid-cols-[1.3fr_1fr_1fr_1.1fr]">
          <div>
            <Brand />
            {/* One brand line, nothing beneath it. */}
            <p className="mt-4 max-w-sm text-[15px] leading-relaxed text-dim">
              {t("tagline")}
            </p>
          </div>
          <nav aria-label={t("nav")}>
            <p className="eyebrow">{t("nav")}</p>
            <ul className="mt-5 space-y-3">
              {NAV_LINKS.map((l) => (
                <li key={l.key}>
                  <Link
                    href={l.href}
                    className="text-[13px] text-dim transition-colors hover:text-brand-strong"
                  >
                    {tNav(l.key)}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <nav aria-label={t("legalNav")}>
            <p className="eyebrow">{t("legalNav")}</p>
            <ul className="mt-5 space-y-3">
              <li>
                <Link
                  href="/legal"
                  className="text-[13px] text-dim transition-colors hover:text-brand-strong"
                >
                  {t("legal")}
                </Link>
              </li>
              <li>
                <Link
                  href="/privacy"
                  className="text-[13px] text-dim transition-colors hover:text-brand-strong"
                >
                  {t("privacy")}
                </Link>
              </li>
              <li>
                <Link
                  href="/system-status"
                  className="text-[13px] text-dim transition-colors hover:text-brand-strong"
                >
                  {t("systemStatus")}
                </Link>
              </li>
            </ul>
          </nav>
          <nav aria-label={t("connectNav")}>
            <p className="eyebrow">{t("connectNav")}</p>
            <ul className="mt-5 space-y-3">
              {CONNECT_LINKS.map((l) => (
                <li key={l.key}>
                  <Link
                    href={l.href}
                    className="text-[13px] text-dim transition-colors hover:text-brand-strong"
                  >
                    {t(l.key)}
                  </Link>
                </li>
              ))}
              <li>
                <a
                  href={`mailto:${t("contactEmail")}`}
                  className="text-[13px] text-dim transition-colors hover:text-brand-strong"
                >
                  {t("contactEmail")}
                </a>
              </li>
            </ul>
          </nav>
        </div>

        <div className="mt-14 border-t border-border pt-8">
          <p className="max-w-3xl text-xs leading-relaxed text-dim">
            {t("disclaimer")}
          </p>
          <p className="mt-3 max-w-3xl text-xs leading-relaxed text-dim">
            {tCommon("mockNotice")}
          </p>
          <p className="mt-6 text-xs text-dim">
            {t("copyright", { year: new Date().getFullYear() })}
          </p>
        </div>
      </div>
    </footer>
  );
}
