/**
 * Performance reports published on /performance.
 *
 * Every entry is ONE evaluation run with a single, clearly-labeled result
 * type (spec §10.1). Result types are never blended. The numbers behind
 * these reports are real research output extracted from the Model-Modus
 * project into `config/performance/*.json`; nothing here is simulated for
 * display purposes.
 *
 * As of the 2026-08-13 extraction there is one report. The three that
 * preceded it — a 2024 validation on seed 31, an anchored walk-forward on
 * seed 100, and a 50-seed cost study — all ran on code from before
 * 2026-07-04 and were superseded by the frozen brain below. They were removed
 * rather than left up beside it: publishing four runs of the same system on
 * different code revisions invites a reader to pick the flattering one.
 */

export type ResultType =
  | "backtest"
  | "out_of_sample"
  | "walk_forward"
  | "paper_trading"
  | "live";

/** Which extracted dataset backs the report. */
export type ReportDataset = "frozenBrain";

type Localized = { vi: string; en: string };
type LocalizedList = { vi: string[]; en: string[] };

export interface StrategyConfig {
  slug: string;
  name: Localized;
  /** Model whose validation this report is. */
  systemSlug: string;
  dataset: ReportDataset;
  resultType: ResultType;
  asset: string;
  timeframe: string;
  benchmark: Localized;
  periodStart: string;
  periodEnd: string;
  feesNote: Localized;
  slippageNote: Localized;
  splitNote: Localized;
  modelVersion: string;
  /** Code revision that produced the numbers. See caveats. */
  codeVersion: string;
  seedNote: Localized;
  summary: Localized;
  /** Scope limits shown at the top of the detail page (spec §14). */
  caveats: LocalizedList;
}

export const STRATEGIES: StrategyConfig[] = [
  {
    slug: "vn30f1m-frozen-brain",
    // The period and the test method are stated in the facts beneath the
    // heading; repeating them in the title made it a sentence rather than a
    // name.
    name: {
      vi: "Model Modus",
      en: "Model Modus",
    },
    systemSlug: "model-modus",
    dataset: "frozenBrain",
    // The model was closed before 2024 began and never reopened. 2024 tuned
    // the inference settings, 2025 and 2026 were untouched until scoring.
    resultType: "out_of_sample",
    asset: "VN30F1M",
    timeframe: "5 phút",
    benchmark: {
      vi: "VN-Index, tính trên cùng khoảng thời gian từ dữ liệu đóng cửa hằng ngày",
      en: "VN-Index, over the same window, from daily closing data",
    },
    periodStart: "2024-01-02",
    periodEnd: "2026-08-03",
    feesNote: {
      vi: "Chưa trừ phí giao dịch (cấu hình tham chiếu: phí + thuế 0,4 điểm/vòng lệnh)",
      en: "Before transaction fees (reference: 0.4 points in fees and tax per completed trade)",
    },
    slippageNote: {
      vi: "Chưa trừ chênh lệch giá khi khớp lệnh (mức tham chiếu: 0,2 điểm mỗi chiều). Lệnh giả định khớp tại giá đóng nến.",
      en: "Before the difference between expected and executed price (reference: 0.2 points per side). Orders are assumed to fill at the candle close.",
    },
    splitNote: {
      vi: "Mô hình học từ 2018–2023 rồi được đóng băng. Năm 2024 dùng để chốt các tham số vào/ra lệnh, nên con số 2024 lạc quan hơn thực tế. Năm 2025 và 2026 chưa từng được dùng cho bất kỳ khâu nào trước khi chấm điểm.",
      en: "The model learned from 2018–2023 and was then frozen. 2024 was used to settle the entry and exit settings, so its figures read more favourably than reality. 2025 and 2026 were never used for anything before scoring.",
    },
    modelVersion: "brain-2026-07-08",
    codeVersion: "2026-07-08",
    seedNote: { vi: "Một lần chạy, seed 42", en: "One run, seed 42" },
    summary: {
      vi: "Một mô hình đã đóng băng, chấm lại trên ba năm: 2024 là năm hiệu chỉnh, 2025 và 2026 là dữ liệu mô hình chưa từng thấy.",
      en: "One frozen model scored across three years: 2024 was the tuning year, 2025 and 2026 were data the model had never seen.",
    },
    caveats: {
      vi: [
        "Kết quả mô phỏng trên dữ liệu lịch sử. Hệ thống chưa được đưa vào giao dịch thật.",
        "Năm 2024 đã được dùng để hiệu chỉnh chính mô hình này, nên số của 2024 lạc quan hơn 2025–2026 là điều tự nhiên. Hai năm sau mới là bài kiểm tra thật.",
        "Năm 2026 mới chạy tới 03/08/2026, khoảng 0,52 năm giao dịch. Mọi chỉ số niên hóa của năm này (lợi nhuận/năm, Sharpe, Sortino, Calmar) đã được nhân lên theo tỷ lệ, không so trực tiếp với 2024 và 2025 được. Đọc lợi nhuận thô, số lệnh và Profit Factor trước.",
        "Đây là số của một lần chạy duy nhất (seed 42), không phải phân phối nhiều lần chạy. Nó chưa cho biết kết quả ổn định đến đâu nếu chạy lại với hạt giống khác.",
        "Lợi nhuận công bố chưa trừ phí, thuế và chênh lệch giá khi khớp lệnh.",
        "Mức sụt giảm sâu nhất là mức của một năm tệ nhất trong ba năm, đo riêng trong từng năm — ba năm được chấm tách biệt, không nối thành một đường vốn liên tục.",
        "Tỷ lệ phần trăm được tính trên mức vốn giả định 1.000 điểm chỉ số, tương đương 100.000.000 VND theo mệnh giá 100.000 VND mỗi điểm.",
      ],
      en: [
        "Simulated results on historical data. The system has not been put into live trading.",
        "2024 was used to tune this very model, so its figures reading better than 2025–2026 is expected. The two later years are the real test.",
        "2026 runs only to 3 August 2026, about 0.52 of a trading year. Every annualised figure for that year (return per year, Sharpe, Sortino, Calmar) has been scaled up accordingly and cannot be compared directly with 2024 or 2025. Read the raw profit, the trade count and the profit factor first.",
        "These are the figures of a single run (seed 42), not a distribution across runs. They do not show how stable the result would be under a different seed.",
        "Published profit is before fees, tax and the difference between expected and executed price.",
        "The deepest decline shown is the worst of the three years, each measured within its own year — the three years were scored separately, not chained into one continuous equity curve.",
        "Percentages use an assumed starting value of 1,000 index points, equal to 100,000,000 VND at 100,000 VND per point.",
      ],
    },
  },
];

export const getStrategy = (slug: string) =>
  STRATEGIES.find((s) => s.slug === slug);

export const strategiesForSystem = (systemSlug: string) =>
  STRATEGIES.filter((s) => s.systemSlug === systemSlug);

export const FEATURED_STRATEGY = "vn30f1m-frozen-brain";
