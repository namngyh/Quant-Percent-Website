import type { Metadata } from "next";
import { routing } from "@/i18n/routing";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://quantpercent.com";

/** hreflang alternates + canonical for a localized route (spec §23). */
export function localeAlternates(
  locale: string,
  path: string
): Metadata["alternates"] {
  const clean = path === "/" ? "" : path;
  return {
    canonical: `${SITE_URL}/${locale}${clean}`,
    languages: Object.fromEntries(
      routing.locales.map((l) => [l, `${SITE_URL}/${l}${clean}`])
    ),
  };
}

export { SITE_URL };
