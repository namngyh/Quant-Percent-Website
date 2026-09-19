"use client";

import { useLocale } from "next-intl";
import { InfoTip } from "@/components/info-tip";
import { Sealed } from "@/components/sealed";

/**
 * The Monte Carlo risk table for the regime model — sealed.
 *
 * The model's current output fails a check anyone can apply: it puts the
 * 95% one-month loss threshold above 100% of the index, and the model's own
 * caveats say the tail estimates are not yet reliable (the fitted degrees of
 * freedom leave the kurtosis infinite). A refit is in progress. Until it
 * finishes and passes review there is no honest number to put here.
 *
 * So this shows the table's shape and nothing else: which horizons, which
 * thresholds, what each one means. A reader learns what the model will
 * publish and sees plainly that it is withheld for now. No cell carries a
 * figure — not the broken ones dimmed, not zeros, not estimates. The seal
 * says why.
 */

const HORIZONS = [1, 5, 20] as const;

const COPY = {
  vi: {
    title: "Bảng ngưỡng rủi ro theo mô phỏng",
    lead: "Các ngưỡng lỗ và mức sụt giảm tối đa ở từng thời hạn, mô phỏng Monte Carlo trên phân bố có đuôi nặng và chuyển trạng thái.",
    horizon: "Thời hạn",
    sessions: "phiên",
    columns: [
      { key: "var95", label: "VaR 95%", tip: "Trong 95 trên 100 kịch bản, mức lỗ không vượt quá ngưỡng này." },
      { key: "cvar95", label: "CVaR 95%", tip: "Mức lỗ trung bình của riêng 5% kịch bản xấu nhất." },
      { key: "var99", label: "VaR 99%", tip: "Trong 99 trên 100 kịch bản, mức lỗ không vượt quá ngưỡng này." },
      { key: "cvar99", label: "CVaR 99%", tip: "Mức lỗ trung bình của riêng 1% kịch bản xấu nhất." },
      { key: "mdd50", label: "Sụt giảm tối đa (trung vị)", tip: "Mức giảm sâu nhất từ đỉnh trong kỳ, ở kịch bản giữa." },
      { key: "mdd95", label: "Sụt giảm tối đa (p95)", tip: "Mức giảm sâu nhất từ đỉnh trong kỳ, ở kịch bản xấu thứ 5 trên 100." },
    ],
    sealTitle: "Niêm phong",
    sealNote:
      "Tempus VNI đang được hiệu chuẩn lại. Kết quả hiện tại chưa qua kiểm định nội bộ, bảng tạm đóng cho tới khi có bản đạt chuẩn.",
  },
  en: {
    title: "Simulated risk thresholds",
    lead: "Loss thresholds and maximum drawdown by horizon, from Monte Carlo paths with heavy tails and regime switching.",
    horizon: "Horizon",
    sessions: "sessions",
    columns: [
      { key: "var95", label: "VaR 95%", tip: "In 95 of 100 paths the loss stays within this threshold." },
      { key: "cvar95", label: "CVaR 95%", tip: "Average loss across only the worst 5 of 100 paths." },
      { key: "var99", label: "VaR 99%", tip: "In 99 of 100 paths the loss stays within this threshold." },
      { key: "cvar99", label: "CVaR 99%", tip: "Average loss across only the worst 1 of 100 paths." },
      { key: "mdd50", label: "Max drawdown (median)", tip: "Deepest peak-to-trough fall within the period, on the middle path." },
      { key: "mdd95", label: "Max drawdown (p95)", tip: "Deepest peak-to-trough fall within the period, on the 5th-worst path in 100." },
    ],
    sealTitle: "Sealed",
    sealNote:
      "Tempus VNI is being recalibrated. Its current output has not passed internal review, so this table is closed until a version does.",
  },
} as const;

export function RaemfRiskTable() {
  const locale = useLocale() as "vi" | "en";
  const t = COPY[locale];

  return (
    <section aria-labelledby="raemf-risk">
      <h2 id="raemf-risk" className="title-md">
        {t.title}
      </h2>
      <p className="mt-3 max-w-3xl leading-relaxed text-dim">{t.lead}</p>

      <Sealed title={t.sealTitle} note={t.sealNote} className="mt-5">
        <div className="overflow-x-auto rounded-lg border border-border shadow-sm">
          <table className="w-full min-w-[720px] text-[13px]">
            <thead>
              <tr className="bg-surface text-left text-xs text-dim">
                <th scope="col" className="px-4 py-3 font-medium">
                  {t.horizon}
                </th>
                {t.columns.map((c) => (
                  <th key={c.key} scope="col" className="px-4 py-3 font-medium">
                    <span className="inline-flex items-center gap-1.5">
                      {c.label}
                      <InfoTip text={c.tip} />
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {HORIZONS.map((h) => (
                <tr key={h} className="border-t border-border">
                  <th scope="row" className="figure px-4 py-3.5 text-left font-medium">
                    {h} {t.sessions}
                  </th>
                  {t.columns.map((c) => (
                    <td key={c.key} className="figure px-4 py-3.5 text-dim">
                      —
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Sealed>
    </section>
  );
}
