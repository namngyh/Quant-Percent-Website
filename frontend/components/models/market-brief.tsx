"use client";

import { useLocale, useTranslations } from "next-intl";
import { DataState } from "@/components/states/data-state";
import { InfoTip } from "@/components/info-tip";
import { useApi } from "@/lib/api/fetcher";
import { useNetworkSnapshot } from "@/lib/api/network";
import type { ForecastRecord, Quote, RiskDashboard } from "@/lib/api/types";
import { fmtNumber, fmtPercent, fmtPrice, fmtSignedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * What the models say about the market today, in one row.
 *
 * Four models used to mean four pages, and answering "so what is the market
 * doing?" meant opening all four and holding the answers in your head. Each
 * page is written for someone studying that model; nobody arrives wanting to
 * study a model. They arrive wanting to know where the index might go, how
 * much it could fall, and whether the market is behaving normally.
 *
 * So the tiles are ordered by that question, not by model. Which model
 * produced each number is named underneath rather than made the heading —
 * useful for anyone who wants to follow it, invisible to anyone who does not.
 *
 * The panel reports the models it could not reach instead of hiding them. A
 * market summary missing a quarter of its evidence, presented as if whole, is
 * worse than one that says which quarter is missing.
 */

const COPY = {
  vi: {
    heading: "Thị trường hôm nay",
    lead: "Bốn mô hình chạy độc lập sau mỗi phiên. Đây là những gì chúng nói, gộp lại một chỗ.",
    index: "VN-Index",
    indexNote: "phiên gần nhất",
    forecast: "Dự báo 20 phiên",
    forecastNote: "mô hình dự báo phân bố",
    forecastTip:
      "Mức thay đổi mô hình cho là có khả năng nhất sau 20 phiên, kèm khả năng chỉ số tăng. Không phải cam kết.",
    risk: "Mức rủi ro",
    riskNote: "mô hình mô phỏng rủi ro",
    riskTip:
      "Ngưỡng lỗ 95%: trong 95 trên 100 kịch bản mô phỏng, mức lỗ không vượt quá con số này. Không phải mức lỗ tối đa.",
    network: "Cấu trúc thị trường",
    networkNote: "mô hình mạng lưới liên kết",
    networkTip:
      "Điểm càng cao nghĩa là các cổ phiếu càng biến động cùng nhau, tức khả năng đa dạng hóa giảm. Không phải xác suất thị trường đi xuống.",
    chanceUp: "khả năng tăng",
    var95: "ngưỡng lỗ 95%",
    unavailable: "Chưa có dữ liệu",
    missing: "Chưa lấy được: {names}.",
    asOf: "Dữ liệu đến",
  },
  en: {
    heading: "The market today",
    lead: "Four models run independently after each session. This is what they say, in one place.",
    index: "VN-Index",
    indexNote: "latest session",
    forecast: "20-session forecast",
    forecastNote: "distribution forecast model",
    forecastTip:
      "The change the model considers most likely over 20 sessions, with the chance the index rises. Not a commitment.",
    risk: "Risk level",
    riskNote: "risk simulation model",
    riskTip:
      "95% loss threshold: in 95 of 100 simulated scenarios the loss stays within this figure. It is not a maximum loss.",
    network: "Market structure",
    networkNote: "relationship network model",
    networkTip:
      "A higher score means stocks move together more closely, so diversification may be weaker. It is not the probability of a decline.",
    chanceUp: "chance of rising",
    var95: "95% loss threshold",
    unavailable: "No data yet",
    missing: "Could not reach: {names}.",
    asOf: "Data through",
  },
} as const;

/** Risk grades carry a colour; everything else stays neutral on purpose. */
const RISK_TONE: Record<string, string> = {
  low: "text-positive",
  moderate: "text-ink",
  elevated: "text-signal-dark",
  high: "text-negative",
};

function Tile({
  label,
  note,
  tip,
  value,
  detail,
  tone,
  missing,
  missingLabel,
}: {
  label: string;
  note: string;
  tip?: string;
  value?: string;
  detail?: string;
  tone?: string;
  missing?: boolean;
  missingLabel: string;
}) {
  return (
    <div className="bg-background p-5">
      <div className="flex items-center gap-1.5">
        <p className="text-xs text-dim">{label}</p>
        {tip && <InfoTip text={tip} />}
      </div>
      {missing ? (
        <p className="figure mt-2 text-2xl font-medium text-dim">
          {missingLabel}
        </p>
      ) : (
        <>
          <p className={cn("figure mt-2 text-2xl font-medium", tone)}>{value}</p>
          {detail && (
            <p className="figure mt-1 text-sm text-dim">{detail}</p>
          )}
        </>
      )}
      <p className="mt-2.5 text-[11px] leading-snug text-dim">{note}</p>
    </div>
  );
}

export function MarketBrief() {
  const locale = useLocale() as "vi" | "en";
  const t = COPY[locale];
  // The models emit machine labels — "elevated", "high_stress". Printing
  // them raw leaves a Vietnamese reader to guess at English keys.
  const tc = useTranslations("common");

  const quote = useApi<Quote>("/api/v1/market/VNINDEX/quote");
  const forecast = useApi<{ records: ForecastRecord[] }>(
    "/api/v1/models/msdp/latest?symbol=VNINDEX",
  );
  const risk = useApi<RiskDashboard>("/api/v1/market/risk?symbol=VNINDEX");
  const network = useNetworkSnapshot();

  // The 20-session horizon is the one every model here reports on, so the
  // tiles compare like with like rather than whichever horizon each happens
  // to lead with.
  const h20 = forecast.data?.records.find((r) => r.horizon === 20);
  const risky = risk.data;
  const net = network.data;

  const loading =
    quote.isLoading && forecast.isLoading && risk.isLoading && network.isLoading;

  // Whichever data date the panel actually has. They come from separate
  // models, so the oldest one is what the row as a whole is good for.
  const dates = [
    quote.data?.data_as_of,
    h20?.data_as_of,
    risky?.data_as_of,
    net?.as_of_date,
  ]
    .filter(Boolean)
    .map((d) => String(d).slice(0, 10))
    .sort();
  const asOf = dates[0];

  const absent = [
    !quote.data && t.index,
    !h20 && t.forecast,
    !risky && t.risk,
    !net && t.network,
  ].filter(Boolean) as string[];

  return (
    <section aria-labelledby="market-brief">
      <h2 id="market-brief" className="title-md">
        {t.heading}
      </h2>
      <p className="mt-3 max-w-3xl leading-relaxed text-ink">{t.lead}</p>

      <DataState loading={loading} reserve="min-h-[9rem]" className="mt-6">
        <dl className="grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-4">
          <Tile
            label={t.index}
            note={t.indexNote}
            missing={!quote.data}
            missingLabel={t.unavailable}
            value={quote.data ? fmtPrice(quote.data.price, locale) : undefined}
            detail={
              quote.data
                ? fmtSignedPercent(quote.data.change_percent / 100, locale)
                : undefined
            }
            tone={
              quote.data && quote.data.change_percent < 0
                ? "text-negative"
                : "text-positive"
            }
          />
          <Tile
            label={t.forecast}
            note={t.forecastNote}
            tip={t.forecastTip}
            missing={!h20}
            missingLabel={t.unavailable}
            value={h20 ? fmtSignedPercent(h20.forecast_return, locale) : undefined}
            detail={
              h20
                ? `${fmtPercent(h20.probability_up, locale)} ${t.chanceUp}`
                : undefined
            }
          />
          <Tile
            label={t.risk}
            note={t.riskNote}
            tip={t.riskTip}
            missing={!risky}
            missingLabel={t.unavailable}
            value={risky ? tc(`riskState.${risky.risk_state}`) : undefined}
            detail={
              risky?.var_95 != null
                ? `${t.var95} ${fmtPercent(risky.var_95, locale)}`
                : undefined
            }
            tone={risky ? RISK_TONE[risky.risk_state] : undefined}
          />
          <Tile
            label={t.network}
            note={t.networkNote}
            tip={t.networkTip}
            missing={!net}
            missingLabel={t.unavailable}
            value={net ? tc(`networkState.${net.stress_label}`) : undefined}
            detail={
              net
                ? `${fmtNumber(net.stress_score, locale, { maximumFractionDigits: 1 })}/100`
                : undefined
            }
          />
        </dl>

        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-dim">
          {asOf && (
            <span className="figure">
              {t.asOf} {asOf}
            </span>
          )}
          {absent.length > 0 && (
            <span>{t.missing.replace("{names}", absent.join(", "))}</span>
          )}
        </div>
      </DataState>
    </section>
  );
}
