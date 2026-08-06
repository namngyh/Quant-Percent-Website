"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { apiRequest, ApiError } from "@/lib/api/fetcher";
import { PortfolioAnalysisSchema } from "@/lib/api/types";
import type { PortfolioAnalysis, PortfolioRequestPayload } from "@/lib/api/types";
import { PortfolioForm } from "@/components/portfolio/portfolio-form";
import { PortfolioResult } from "@/components/portfolio/portfolio-result";

/**
 * Holds the entered portfolio and its analysis.
 *
 * The holdings never leave this component except in the body of the analyse
 * request, and nothing is written to storage: a position list is the kind of
 * data a reader should be able to try out without leaving a trace.
 */
export function PortfolioWorkspace() {
  const t = useTranslations("portfolio");
  const [result, setResult] = useState<PortfolioAnalysis | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function analyse(payload: PortfolioRequestPayload) {
    setPending(true);
    setError(null);
    try {
      const raw = await apiRequest<unknown>("/api/v1/portfolio/analyze", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const parsed = PortfolioAnalysisSchema.safeParse(raw);
      if (!parsed.success) {
        // A contract mismatch is a bug, not a user error. Say so plainly
        // rather than rendering a half-populated panel.
        setError(t("errors.contract"));
        return;
      }
      setResult(parsed.data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setError(t("errors.notAnalysable"));
      } else if (err instanceof ApiError && err.status === 404) {
        setError(t("errors.unknownSymbol"));
      } else {
        setError(t("errors.generic"));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <PortfolioForm onSubmit={analyse} pending={pending} />
      {error && (
        <p
          role="alert"
          className="mt-6 border-l-4 border-negative bg-surface px-5 py-4 text-sm leading-relaxed text-ink"
        >
          {error}
        </p>
      )}
      {result && <PortfolioResult data={result} />}
    </>
  );
}
