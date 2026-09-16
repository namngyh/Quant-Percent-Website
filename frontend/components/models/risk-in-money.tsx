"use client";

import { useState } from "react";
import { useLocale } from "next-intl";
import { DataState } from "@/components/states/data-state";
import { InfoTip } from "@/components/info-tip";
import { useApi } from "@/lib/api/fetcher";
import type { RiskDashboard } from "@/lib/api/types";
import { fmtPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * The risk model's percentages, expressed in money.
 *
 * "VaR 95% = -9.19%" is precise and almost unreadable. A reader deciding
 * whether they can live with that has to convert it against their own
 * position in their head, and most will skim past instead. The same figure
 * as "you could be down 9.2 million on 100 million" is the same claim with
 * the arithmetic done, and it is the arithmetic that makes it land.
 *
 * The amounts are round reference sizes rather than a free-text field. The
 * point is to give the percentage a scale a reader recognises, not to invite
 * anyone to type in their real position — this is a market-wide simulation
 * of the index, not advice about a portfolio, and a field asking "how much
 * do you have" would imply otherwise.
 */

const AMOUNTS = [50_000_000, 100_000_000, 500_000_000, 1_000_000_000];

const COPY = {
  vi: {
    title: "Những con số này nghĩa là bao nhiêu tiền",
    lead: "Chọn một mức vốn tham chiếu để thấy các tỷ lệ trên quy ra tiền. Đây là mô phỏng cho chỉ số VN-Index, không phải tính toán cho danh mục của bạn.",
    amount: "Mức vốn tham chiếu",
    var95: "Có thể mất tới",
    var95Note: "trong 95 trên 100 kịch bản mô phỏng, mức lỗ không vượt quá đây",
    es95: "Nếu rơi vào 5% kịch bản xấu nhất",
    es95Note: "mức lỗ trung bình của riêng nhóm kịch bản đó",
    current: "Đang giảm so với đỉnh",
    currentNote: "khoảng cách từ đỉnh gần nhất tới hiện tại",
    million: "triệu",
    billion: "tỷ",
    caveat:
      "Các con số là kết quả mô phỏng trên biến động quá khứ, không phải mức lỗ tối đa và không phải cam kết. Thị trường có thể giảm sâu hơn mọi kịch bản mô hình sinh ra.",
  },
  en: {
    title: "What these figures mean in money",
    lead: "Pick a reference amount to see the percentages above as cash. This simulates the VN-Index itself, not your portfolio.",
    amount: "Reference amount",
    var95: "Could be down as much as",
    var95Note: "in 95 of 100 simulated paths the loss stays within this",
    es95: "If it lands in the worst 5 of 100",
    es95Note: "the average loss across only those paths",
    current: "Currently below the peak by",
    currentNote: "distance from the most recent high to today",
    million: "million",
    billion: "billion",
    caveat:
      "These come from simulating past volatility. They are not a maximum loss and not a commitment — the market can fall further than any path the model produced.",
  },
} as const;

/** Vietnamese reads large sums in triệu and tỷ, not in raw digits. */
function money(value: number, locale: "vi" | "en") {
  const t = COPY[locale];
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) {
    const n = abs / 1_000_000_000;
    return `${n.toLocaleString(locale, { maximumFractionDigits: 2 })} ${t.billion}`;
  }
  const n = abs / 1_000_000;
  return `${n.toLocaleString(locale, { maximumFractionDigits: 1 })} ${t.million}`;
}

export function RiskInMoney() {
  const locale = useLocale() as "vi" | "en";
  const t = COPY[locale];
  const [amount, setAmount] = useState(AMOUNTS[1]);
  const { data, error, isLoading, mutate } = useApi<RiskDashboard>(
    "/api/v1/market/risk?symbol=VNINDEX",
  );

  const rows = data
    ? [
        {
          key: "var",
          label: t.var95,
          note: t.var95Note,
          rate: data.var_95,
        },
        {
          key: "es",
          label: t.es95,
          note: t.es95Note,
          rate: data.es_95,
        },
        {
          key: "now",
          label: t.current,
          note: t.currentNote,
          rate: data.current_drawdown,
        },
      ].filter((r) => r.rate != null)
    : [];

  return (
    <section aria-labelledby="risk-money">
      <h2 id="risk-money" className="title-md">
        {t.title}
      </h2>
      <p className="mt-3 max-w-3xl leading-relaxed text-dim">{t.lead}</p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-xs text-dim">{t.amount}</span>
        {AMOUNTS.map((a) => (
          <button
            key={a}
            type="button"
            onClick={() => setAmount(a)}
            aria-pressed={amount === a}
            className={cn(
              "figure rounded-full border px-3.5 py-1.5 text-[12px] font-medium transition-colors",
              amount === a
                ? "border-brand bg-brand text-white"
                : "border-border text-dim hover:border-brand hover:text-brand",
            )}
          >
            {money(a, locale)}
          </button>
        ))}
      </div>

      <DataState
        className="mt-4"
        loading={isLoading}
        error={error}
        onRetry={() => mutate()}
        empty={Boolean(data) && rows.length === 0}
        reserve="min-h-[10rem]"
      >
        <dl className="grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-3">
          {rows.map((r) => (
            <div key={r.key} className="bg-background p-5">
              <dt className="flex items-center gap-1.5 text-xs text-dim">
                {r.label}
                <InfoTip text={r.note} />
              </dt>
              <dd className="figure mt-2 text-2xl font-medium text-negative">
                −{money((r.rate as number) * amount, locale)}
              </dd>
              <p className="figure mt-1 text-sm text-dim">
                {fmtPercent(r.rate as number, locale)}
              </p>
            </div>
          ))}
        </dl>

        <p className="mt-3 max-w-3xl border-l-2 border-lightgray pl-4 text-xs leading-relaxed text-dim">
          {t.caveat}
        </p>
      </DataState>
    </section>
  );
}
