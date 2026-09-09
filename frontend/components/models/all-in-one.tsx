"use client";

import { useLocale } from "next-intl";
import { Link } from "@/i18n/navigation";
import { MarketBrief } from "@/components/models/market-brief";
import { CurrentOutput, ForecastChart } from "@/components/models/model-output";
import { ForecastFan } from "@/components/models/forecast-fan";
import { RiskProfile } from "@/components/models/risk-profile";
import { DynamicNetwork } from "@/components/models/dynamic-network";
import { NetworkRanking } from "@/components/models/network-ranking";
import { NetworkClusters } from "@/components/models/network-clusters";

/**
 * The four models on one page, arranged by question rather than by model.
 *
 * Splitting them across four pages made sense while each was a research
 * write-up. It stopped making sense once they started publishing daily,
 * because a reader who wants to know what the market is doing had to open
 * four pages and assemble the answer themselves — and three of the four
 * pages open with methodology, which is the wrong thing to read first.
 *
 * The order here follows what someone actually asks: where might the index
 * go, how far could it fall, is the market behaving normally. Each section
 * names the model behind it and links to its full write-up, so the depth is
 * still one click away for anyone who wants it.
 *
 * Every panel fetches on its own and reports its own failure. One model being
 * down leaves a labelled gap rather than an empty page.
 */

const COPY = {
  vi: {
    forecastTitle: "Chỉ số có thể đi tới đâu",
    forecastLead:
      "Mô hình ước lượng một phạm vi kết quả cho từng thời hạn, không phải một con số duy nhất. Phạm vi rộng ra khi nhìn xa hơn là biểu hiện của mức không chắc chắn.",
    riskTitle: "Có thể mất bao nhiêu",
    riskLead:
      "Mô hình mô phỏng hàng chục nghìn kịch bản giá để ước lượng khả năng xảy ra từng mức sụt giảm. Đây là xác suất mô phỏng, không phải điều chắc chắn.",
    networkTitle: "Thị trường đang vận hành ra sao",
    networkLead:
      "Mô hình đo các cổ phiếu VN30 đang biến động cùng nhau chặt tới đâu. Liên kết càng chặt thì đa dạng hóa càng ít tác dụng — đây là mô tả cấu trúc, không phải dự báo giá.",
    deep: "Xem báo cáo nghiên cứu đầy đủ",
    by: "Mô hình",
  },
  en: {
    forecastTitle: "Where the index could go",
    forecastLead:
      "The model estimates a range of outcomes for each period rather than a single number. A range that widens with the horizon is the model reporting its own uncertainty.",
    riskTitle: "How much could be lost",
    riskLead:
      "The model simulates tens of thousands of price paths to estimate how likely each size of fall is. These are simulated probabilities, not certainties.",
    networkTitle: "How the market is behaving",
    networkLead:
      "The model measures how tightly VN30 stocks move together. Tighter links mean diversification helps less — this describes structure, it does not forecast prices.",
    deep: "Read the full research report",
    by: "Model",
  },
} as const;

function SectionHead({
  title,
  lead,
  model,
  slug,
  locale,
}: {
  title: string;
  lead: string;
  model: string;
  slug: string;
  locale: "vi" | "en";
}) {
  const t = COPY[locale];
  return (
    <div className="max-w-3xl">
      <p className="figure text-xs uppercase tracking-[0.08em] text-brand">
        {t.by} · {model}
      </p>
      <h2 className="title-md mt-2">{title}</h2>
      <p className="mt-3 leading-relaxed text-ink">{lead}</p>
      <Link
        href={`/models/${slug}`}
        className="arrow-link mt-4 inline-flex items-center gap-2 text-[13px] font-medium text-brand underline-offset-4 hover:text-brand-strong hover:underline"
      >
        {t.deep}{" "}
        <span aria-hidden="true" data-arrow>
          →
        </span>
      </Link>
    </div>
  );
}

export function AllInOne({ names }: { names: Record<string, string> }) {
  const locale = useLocale() as "vi" | "en";
  const t = COPY[locale];

  return (
    <div className="space-y-16 desk:space-y-20">
      <MarketBrief />

      <section aria-labelledby="aio-forecast">
        <SectionHead
          title={t.forecastTitle}
          lead={t.forecastLead}
          model={names.msdp ?? "MSDP"}
          slug="msdp"
          locale={locale}
        />
        <div className="mt-8 space-y-10">
          <CurrentOutput modelSlug="msdp" symbol="VNINDEX" />
          <ForecastChart modelSlug="msdp" symbol="VNINDEX" />
          <ForecastFan slug="msdp" symbol="VNINDEX" locale={locale} />
        </div>
      </section>

      <section aria-labelledby="aio-risk" className="border-t border-border pt-16">
        <SectionHead
          title={t.riskTitle}
          lead={t.riskLead}
          model={names["rarf-fhe"] ?? "RARF-FHE"}
          slug="rarf-fhe"
          locale={locale}
        />
        <div className="mt-8">
          <RiskProfile locale={locale} />
        </div>
      </section>

      <section
        aria-labelledby="aio-network"
        className="border-t border-border pt-16"
      >
        <SectionHead
          title={t.networkTitle}
          lead={t.networkLead}
          model={names["dynamic-graph"] ?? "DynamicGraph"}
          slug="dynamic-graph"
          locale={locale}
        />
        <div className="mt-8 space-y-10">
          <NetworkRanking locale={locale} />
          <NetworkClusters locale={locale} />
          <div className="overflow-hidden rounded-lg border border-border bg-background shadow-sm">
            <DynamicNetwork locale={locale} />
          </div>
        </div>
      </section>
    </div>
  );
}
