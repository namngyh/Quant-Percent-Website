"use client";

import { useLocale, useTranslations } from "next-intl";
import type { Freshness } from "@/lib/api/types";
import { fmtDateTime } from "@/lib/format";

/**
 * Timestamp rendered under every data block (spec §20).
 *
 * The "illustrative" tag used to default to true, from when the market
 * section was placeholder data. It is not any more — quotes, history and
 * freshness all come from the ingestion feed — so the default now follows
 * the data mode and only says "illustrative" when the site really is serving
 * mock data. A live figure labelled as an illustration understates real work;
 * the reverse would be worse.
 */
const MOCK_MODE = process.env.NEXT_PUBLIC_DATA_MODE === "mock";

export function DataFreshnessLabel({
  freshness,
  modelVersion,
  illustrative = MOCK_MODE,
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
