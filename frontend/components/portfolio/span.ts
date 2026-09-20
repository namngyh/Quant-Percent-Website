"use client";

import { useTranslations } from "next-intl";

/**
 * How long a run of sessions is, in words a reader uses: "1 năm", not
 * "251 phiên". A trading year is ~252 sessions and a month ~21.
 */
export function useSpanLabel(): (sessions: number) => string {
  const t = useTranslations("portfolio.span");
  return (sessions: number) => {
    const months = Math.round(sessions / 21);
    if (months >= 11) return t("year");
    if (months >= 1) return t("months", { n: months });
    return t("sessions", { n: sessions });
  };
}
