/**
 * Performance reports published on /performance.
 *
 * Every entry is ONE evaluation run with a single, clearly-labeled result
 * type (spec §10.1). Result types are never blended. The numbers behind
 * these reports are real research output extracted from the Model-Modus
 * project into `config/performance/*.json`; nothing here is simulated for
 * display purposes.
 */

export type ResultType =
  | "backtest"
  | "out_of_sample"
  | "walk_forward"
  | "paper_trading"
  | "live";

/** Which extracted dataset backs the report. */
export type ReportDataset = "validation" | "walkForward" | "multiseed";

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
  /** Benchmark series was not exported with the runs. This is stated, not invented. */
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

/** Shared caveats. Every published run predates the 2026-07-04 fill fix. */
const COMMON_CAVEATS: LocalizedList = {
  vi: [
    "Kết quả mô phỏng trên dữ liệu lịch sử. Hệ thống chưa được đưa vào giao dịch thật.",
    "Số liệu chạy trên phương pháp mô phỏng khớp lệnh trước ngày 04/07/2026. Phương pháp hiện tại xử lý thận trọng hơn với các phiên mở cửa vượt mức dừng lỗ; vì phương pháp cũ có thể cho kết quả thuận lợi hơn, báo cáo đang được chạy lại theo chuẩn hiện tại.",
    "Lợi nhuận công bố chưa trừ chi phí giao dịch. Ảnh hưởng của chi phí được trình bày riêng trong báo cáo chạy nhiều lần.",
    "Tỷ lệ phần trăm được tính trên mức vốn giả định 1.000 điểm chỉ số, tương đương 100.000.000 VND theo mệnh giá 100.000 VND mỗi điểm. Mức giảm từ đỉnh được tính trên đường tăng trưởng vốn.",
  ],
  en: [
    "Simulated results on historical data. The system has not been put into live trading.",
    "These figures ran under the order-fill method used before 4 July 2026. The current method treats sessions that open beyond a stop level more conservatively; because the earlier method can read more favourably, the reports are being rerun to the current standard.",
    "Published profit does not include transaction costs. A separate 50-run report shows how costs affect the result.",
    "Percentages use an assumed starting value of 1,000 index points, equal to 100,000,000 VND at 100,000 VND per point. The largest decline is measured from the highest previous portfolio value.",
  ],
};

function withCommon(extra: LocalizedList): LocalizedList {
  return {
    vi: [...extra.vi, ...COMMON_CAVEATS.vi],
    en: [...extra.en, ...COMMON_CAVEATS.en],
  };
}

export const STRATEGIES: StrategyConfig[] = [
  {
    slug: "vn30f1m-validation-2024",
    name: {
      vi: "Model Modus: Thử nghiệm năm 2024",
      en: "Model Modus: 2024 Test",
    },
    systemSlug: "model-modus",
    dataset: "validation",
    resultType: "out_of_sample",
    asset: "VN30F1M",
    timeframe: "5 phút",
    benchmark: {
      vi: "Chưa có dữ liệu của phương án đầu tư dùng để so sánh",
      en: "No comparison investment data was available",
    },
    periodStart: "2024-01-02",
    periodEnd: "2024-12-31",
    feesNote: {
      vi: "Chưa trừ phí giao dịch (cấu hình tham chiếu: phí + thuế 0,4 điểm/vòng lệnh)",
      en: "Before transaction fees (reference: 0.4 points in fees and tax per completed trade)",
    },
    slippageNote: {
      vi: "Chưa trừ chênh lệch giá khi khớp lệnh (mức tham chiếu: 0,2 điểm mỗi chiều)",
      en: "Before the difference between expected and executed price (reference: 0.2 points per side)",
    },
    splitNote: {
      vi: "Mô hình chỉ học từ dữ liệu 2018–2023. Dữ liệu năm 2024 được giữ riêng để kiểm tra sau khi mô hình đã hoàn tất.",
      en: "The model learned only from 2018–2023 data. The year 2024 was kept separate for the final test.",
    },
    modelVersion: "brain-2026-07-02",
    codeVersion: "pre-2026-07-04",
    seedNote: { vi: "Một lần chạy", en: "One run" },
    summary: {
      vi: "Lần đầu Model Modus được thử trên một năm dữ liệu hoàn toàn chưa dùng để xây dựng hoặc điều chỉnh mô hình.",
      en: "The first test of Model Modus on a full year of data that was not used to build or adjust the model.",
    },
    caveats: withCommon({
      vi: ["Kết quả chỉ đến từ một lần chạy, nên chưa cho biết mô hình có ổn định khi chạy lại hay không."],
      en: ["This result comes from one run, so it does not show whether repeated runs would be stable."],
    }),
  },
  {
    slug: "vn30f1m-walk-forward",
    // The period and the test method are stated in the facts beneath the
    // heading; repeating them in the title made it a sentence rather than a
    // name.
    name: {
      vi: "Model Modus",
      en: "Model Modus",
    },
    systemSlug: "model-modus",
    dataset: "walkForward",
    resultType: "walk_forward",
    asset: "VN30F1M",
    timeframe: "5 phút",
    benchmark: {
      vi: "Chưa có dữ liệu của phương án đầu tư dùng để so sánh",
      en: "No comparison investment data was available",
    },
    periodStart: "2024-01-02",
    periodEnd: "2026-06-30",
    feesNote: {
      vi: "Chưa trừ phí giao dịch (cấu hình tham chiếu: phí + thuế 0,4 điểm/vòng lệnh)",
      en: "Before transaction fees (reference: 0.4 points in fees and tax per completed trade)",
    },
    slippageNote: {
      vi: "Chưa trừ chênh lệch giá khi khớp lệnh (mức tham chiếu: 0,2 điểm mỗi chiều)",
      en: "Before the difference between expected and executed price (reference: 0.2 points per side)",
    },
    splitNote: {
      vi: "Mỗi năm được kiểm tra riêng. Mô hình chỉ học từ dữ liệu năm 2018 đến hết năm liền trước, sau đó mới được thử trên năm kế tiếp. Cách làm này mô phỏng đúng tình huống không biết trước tương lai.",
      en: "Each year is tested separately. The model learns from 2018 through the previous year, then is tested on the next year. This mirrors a situation where future data is not available.",
    },
    modelVersion: "brain-2026-07-02",
    codeVersion: "pre-2026-07-04",
    seedNote: { vi: "Một lần chạy (mã 100)", en: "One run (code 100)" },
    summary: {
      vi: "Thử nghiệm trên ba năm liên tiếp. Ở mỗi năm, mô hình chỉ được biết dữ liệu của những năm trước.",
      en: "A test over three consecutive years. For each year, the model only knew data from earlier years.",
    },
    caveats: withCommon({
      vi: [
        "Giai đoạn năm 2026 chỉ có dữ liệu đến 30/06/2026, gồm 13 lệnh và cho kết quả âm. Số lệnh này chưa đủ để đưa ra kết luận.",
        "Kết quả chung của ba giai đoạn chịu ảnh hưởng lớn từ năm 2025, vì vậy không nên được hiểu là mức lợi suất kỳ vọng hằng năm.",
      ],
      en: [
        "The 2026 period covers only half a year, through 30 June 2026. It contains 13 trades and a negative result, which is too little evidence for a conclusion.",
        "The combined figure is dominated by 2025; it should not be read as an expected annual return.",
      ],
    }),
  },
  {
    slug: "vn30f1m-multiseed-test",
    name: {
      vi: "Model Modus: Thử nghiệm 2025–2026 (50 lần chạy)",
      en: "Model Modus: 2025–2026 Test (50 runs)",
    },
    systemSlug: "model-modus",
    dataset: "multiseed",
    resultType: "backtest",
    asset: "VN30F1M",
    timeframe: "5 phút",
    benchmark: {
      vi: "Chưa có dữ liệu của phương án đầu tư dùng để so sánh",
      en: "No comparison investment data was available",
    },
    periodStart: "2025-01-02",
    periodEnd: "2026-06-30",
    feesNote: {
      vi: "Kết quả gốc chưa trừ phí; bảng độ nhạy đo ở các mức 0,0–0,5 điểm/lệnh",
      en: "Main figures exclude fees; the cost table shows levels from 0.0 to 0.5 points per trade",
    },
    slippageNote: {
      vi: "Chênh lệch giá khi khớp lệnh được tính chung trong bảng ảnh hưởng của chi phí",
      en: "The difference between expected and executed price is included in the same cost table",
    },
    splitNote: {
      vi: "Mô hình học từ dữ liệu 2018–2024. Dữ liệu 2025–2026 chỉ được mở để kiểm tra một lần sau khi mô hình đã ngừng điều chỉnh vào ngày 02/07/2026.",
      en: "The model learned from 2018–2024 data. The 2025–2026 data was used once for testing after model adjustments stopped on 2 July 2026.",
    },
    modelVersion: "brain-2026-07-02",
    codeVersion: "pre-2026-07-04",
    seedNote: { vi: "50 lần chạy", en: "50 runs" },
    summary: {
      vi: "So sánh 50 lần chạy trên cùng bộ dữ liệu để xem kết quả có ổn định hay không, đồng thời đo ảnh hưởng của chi phí giao dịch.",
      en: "A comparison of 50 runs on the same test data to see whether results are stable and how transaction costs affect them.",
    },
    caveats: withCommon({
      vi: [
        "Bộ dữ liệu kiểm tra chỉ được sử dụng một lần. Nếu tiếp tục xem kết quả để điều chỉnh mô hình, lần kiểm tra này sẽ không còn độc lập.",
        "Hướng giao dịch chưa ổn định giữa các lần chạy: 45/50 lần nghiêng về mua và 5/50 lần nghiêng về bán. Nhóm nghiên cứu đang thử cách kết hợp nhiều lần chạy.",
        "Giai đoạn đánh giá chỉ dài 1,4 năm và bao gồm nửa năm 2026 khuyết dữ liệu.",
      ],
      en: [
        "The test data was used once. Repeatedly checking it while adjusting the model would make the test less independent.",
        "Trade direction is not stable across runs: 45 of 50 favour buying and 5 favour selling. The research team is testing a way to combine multiple runs.",
        "The evaluation window is only 1.4 years and includes a half-complete 2026.",
      ],
    }),
  },
];

export const getStrategy = (slug: string) =>
  STRATEGIES.find((s) => s.slug === slug);

/** Every published validation run of one model. */
export const strategiesForSystem = (systemSlug: string) =>
  STRATEGIES.filter((s) => s.systemSlug === systemSlug);

export const strategyCount = () => STRATEGIES.length;

/** Report shown on the home page and the VN30F1M market tab. */
export const FEATURED_STRATEGY = "vn30f1m-walk-forward";
