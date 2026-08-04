import { getTranslations } from "next-intl/server";
import { Info } from "lucide-react";

/**
 * Short legal / mock-data disclosure strip shown on model, market and
 * performance pages (spec §14, §20).
 */
export async function DisclosureBanner({
  variant = "legal",
}: {
  variant?: "legal" | "mock";
}) {
  const t = await getTranslations(variant === "legal" ? "footer" : "common");
  return (
    <div
      className={
        variant === "mock"
          ? "border-b border-brand/20 bg-brand-soft/55"
          : "border-b border-signal/20 bg-signal-soft/60"
      }
    >
      <div className="container-qp flex items-start gap-2 py-2.5">
        <Info
          className={`mt-0.5 size-3.5 shrink-0 ${
            variant === "mock" ? "text-brand" : "text-signal-strong"
          }`}
          aria-hidden="true"
        />
        <p className="text-[11.5px] leading-snug text-dim">
          {variant === "legal" ? t("disclaimer") : t("mockNotice")}
        </p>
      </div>
    </div>
  );
}
