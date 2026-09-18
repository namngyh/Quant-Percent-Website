/** Locale-aware number/date formatting for figures (always render with .figure/mono). */

const localeTag = (locale: string) => (locale === "vi" ? "vi-VN" : "en-US");

export function fmtNumber(
  value: number,
  locale: string,
  opts: Intl.NumberFormatOptions = {}
) {
  return new Intl.NumberFormat(localeTag(locale), {
    maximumFractionDigits: 2,
    ...opts,
  }).format(value);
}

export function fmtPrice(value: number, locale: string) {
  return fmtNumber(value, locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function fmtPercent(value: number, locale: string, digits = 1) {
  return new Intl.NumberFormat(localeTag(locale), {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

/** Signed percent with explicit symbol so color is never the only signal. */
export function fmtSignedPercent(value: number, locale: string, digits = 2) {
  const sign = value > 0 ? "+" : "";
  return sign + fmtPercent(value, locale, digits);
}

export function fmtDate(iso: string, locale: string) {
  return new Intl.DateTimeFormat(localeTag(locale), {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(iso));
}

export function fmtDateTime(iso: string, locale: string) {
  return new Intl.DateTimeFormat(localeTag(locale), {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

/**
 * Dong in millions ("tr") and billions ("tỷ"), because 563.240.000 does not
 * read at a glance. The unit suffixes are the Vietnamese ones in both
 * locales: an English reader of a VN portfolio still sees prices in dong.
 */
export function fmtVnd(value: number, locale: string) {
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) {
    return `${fmtNumber(value / 1_000_000_000, locale, { maximumFractionDigits: 2 })} tỷ`;
  }
  if (abs >= 1_000_000) {
    return `${fmtNumber(value / 1_000_000, locale, { maximumFractionDigits: 1 })} tr`;
  }
  return fmtNumber(value, locale, { maximumFractionDigits: 0 });
}

/** Direction symbol so meaning is never carried by color alone. */
export function directionSymbol(value: number) {
  if (value > 0) return "▲";
  if (value < 0) return "▼";
  return "•";
}
