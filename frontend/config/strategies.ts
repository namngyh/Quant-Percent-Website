/**
 * Performance reports published on /performance.
 *
 * Every entry is ONE evaluation run with a single, clearly-labeled result
 * type (spec §10.1). Result types are never blended. The numbers behind
 * these reports are real research output extracted from the Model-Modus
 * project into `config/performance/*.json`; nothing here is simulated for
 * display purposes.
 *
 * The three reports that preceded this one came from the older `mlforquant`
 * checkout and all ran under the order-fill method used before 2026-07-04.
 * They were removed rather than left alongside: publishing four runs of the
 * same system, from two codebases and two fill methods, on one page makes it
 * impossible to say which number is the result.
 */

export type ResultType =
  | "backtest"
  | "out_of_sample"
  | "walk_forward"
  | "paper_trading"
  | "live";

/** Which extracted dataset backs the report. */
export type ReportDataset = "modus2024_2025";

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
    slug: "vn30f1m-modus-2024-2025",
    // The period and the test method are stated in the facts beneath the
    // heading; repeating them in the title made it a sentence rather than a
    // name.
    name: {
      vi: "Model Modus",
      en: "Model Modus",
    },
    systemSlug: "model-modus",
    dataset: "modus2024_2025",
    resultType: "out_of_sample",
    asset: "VN30F1M",
    timeframe: "5 phút",
    benchmark: {
      vi: "VN-Index, tính trên cùng khoảng thời gian từ dữ liệu đóng cửa hằng ngày",
      en: "VN-Index, over the same window, from daily closing data",
    },
    periodStart: "2024-01-02",
    periodEnd: "2025-12-31",
    feesNote: {
      vi: "Chưa trừ phí giao dịch (cấu hình tham chiếu: phí + thuế 0,4 điểm/vòng lệnh)",
      en: "Before transaction fees (reference: 0.4 points in fees and tax per completed trade)",
    },
    slippageNote: {
      vi: "Chưa trừ chênh lệch giá khi khớp lệnh (mức tham chiếu: 0,2 điểm mỗi chiều). Lệnh giả định khớp tại giá đóng nến.",
      en: "Before the difference between expected and executed price (reference: 0.2 points per side). Orders are assumed to fill at the candle close.",
    },
    splitNote: {
      vi: "Mô hình học từ 2018–2023 rồi được đóng băng. Năm 2024 dùng để chốt các tham số vào/ra lệnh; năm 2025 chưa từng được dùng cho bất kỳ khâu nào trước khi chấm điểm.",
      en: "The model learned from 2018–2023 and was then frozen. 2024 was used to settle the entry and exit settings; 2025 was never used for anything before scoring.",
    },
    modelVersion: "systemModus-1.3",
    codeVersion: "systemModus-ver_1.3",
    seedNote: {
      vi: "Một lần chạy, seed 433444",
      en: "One run, seed 433444",
    },
    summary: {
      vi: "Hai năm đầy đủ trên hợp đồng tương lai VN30F1M, khung 5 phút, với mô hình đã đóng băng trước khi chạm vào dữ liệu kiểm tra.",
      en: "Two complete years on the VN30F1M futures contract at a 5-minute timeframe, with the model frozen before it touched the test data.",
    },
    caveats: {
      vi: [
        "Kết quả mô phỏng trên dữ liệu lịch sử. Hệ thống chưa được đưa vào giao dịch thật.",
        "Năm 2024 đã được dùng để hiệu chỉnh chính mô hình này, nên số của năm đó lạc quan hơn năm 2025 là điều tự nhiên.",
        "Kết quả đến từ một lần chạy, nên chưa cho biết mô hình có ổn định khi chạy lại hay không.",
        "Lợi nhuận công bố chưa trừ phí, thuế và chênh lệch giá khi khớp lệnh.",
        "Mức sụt giảm sâu nhất là mức của năm tệ hơn trong hai năm, đo riêng trong từng năm — hai năm được chấm tách biệt, không nối thành một đường vốn liên tục.",
        "Tỷ lệ phần trăm được tính trên mức vốn giả định 1.000 điểm chỉ số, tương đương 100.000.000 VND theo mệnh giá 100.000 VND mỗi điểm.",
      ],
      en: [
        "Simulated results on historical data. The system has not been put into live trading.",
        "2024 was used to tune this very model, so its figures reading better than 2025 is expected.",
        "This result comes from one run, so it does not show whether repeated runs would be stable.",
        "Published profit is before fees, tax and the difference between expected and executed price.",
        "The deepest decline shown is the worse of the two years, each measured within its own year — the two years were scored separately, not chained into one continuous equity curve.",
        "Percentages use an assumed starting value of 1,000 index points, equal to 100,000,000 VND at 100,000 VND per point.",
      ],
    },
  },
];

export const getStrategy = (slug: string) =>
  STRATEGIES.find((s) => s.slug === slug);

export const strategiesForSystem = (systemSlug: string) =>
  STRATEGIES.filter((s) => s.systemSlug === systemSlug);

export const FEATURED_STRATEGY = "vn30f1m-modus-2024-2025";
