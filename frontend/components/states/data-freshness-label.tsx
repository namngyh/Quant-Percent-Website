"use client";

import { useLocale, useTranslations } from "next-intl";
import type { Freshness } from "@/lib/api/types";
import { fmtDateTime } from "@/lib/format";

/**
 * Timestamp rendered under every data block (spec §20). Market data is
 * mock and says so; performance reports carry real research output and
 * pass `illustrative={false}`.
 */
export function DataFreshnessLabel({
  freshness,
  modelVersion,
  illustrative = true,
}: {
  freshness: Freshness;
  modelVersion?: string;
  illustrative?: boolean;
}) {
  const t = useTranslations("common");
  const locale = useLocale();
  return (
    <p className="figure mt-3 text-[11px] leading-relaxed text-dim">
      {t("freshness.dataAsOf")}: {fmtDateTime(freshness.data_as_of, locale)}
      {" · "}
      {t("freshness.generatedAt")}: {fmtDateTime(freshness.generated_at, locale)}
      {freshness.delay_minutes > 0 && (
        <> · {t("freshness.delayedBy", { minutes: freshness.delay_minutes })}</>
      )}
      {modelVersion && (
        <>
          {" · "}
          {t("freshness.modelVersion")}: {modelVersion}
        </>
      )}
      {" · "}
      <span className="uppercase tracking-[0.08em]">
        {illustrative ? t("illustrative") : t("researchOutput")}
      </span>
    </p>
  );
}
