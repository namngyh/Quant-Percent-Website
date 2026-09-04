/**
 * Model catalogue (spec §24): models are added or hidden here, never
 * hard-coded in components. Localized copy lives alongside metadata so a
 * new model is a single entry in this file.
 */

export type ModelCategory =
  | "forecasting"
  | "regime"
  | "trading_system"
  | "ranking"
  | "volatility"
  | "risk";

export type ModelStatus = "active" | "paper_trading" | "experimental" | "archived";

type Localized = { vi: string; en: string };
type LocalizedList = { vi: string[]; en: string[] };

export interface ModelConfig {
  slug: string;
  name: string;
  code: string;
  markets: string[];
  category: ModelCategory;
  status: ModelStatus;
  visibility: "public" | "hidden";
  /**
   * Who can open the model's outputs. Set "members" to require sign-in.
   * the card is blurred behind a lock and the detail page is gated.
   * This is the single switch for deciding which models stay previewable.
   */
  access: "public" | "members";
  featured: boolean;
  version: string;
  updatedAt?: string;
  sparkline?: number[];
  sparklineLabel?: Localized;
  /**
   * How the card figure should be read.
   *
   * Present means `sparkline` holds one value per entry in `horizons`, and the
   * card draws a labelled bar per horizon against this scale. Absent means the
   * values are a sequence over time and keep the trend line — the only case
   * where a line without an axis says something true.
   */
  sparklineScale?: {
    min: number;
    max: number;
    suffix?: string;
    /** The level the metric is meant to reach, marked with a hairline. */
    reference?: number;
    referenceLabel?: Localized;
  };
  horizons: number[];
  show_performance: boolean;
  show_forecast: boolean;
  show_internal_signal: false; // Never true because internal signals are not published.
  strategySlug?: string;
  tagline: Localized;
  keyOutput: Localized;
  /**
   * Layer-level architecture for flagship systems. Names the techniques
   * used, never the parameters, weights or entry logic (spec §9.2).
   */
  architecture?: { title: Localized; text: Localized }[];
  description: {
    objective: Localized;
    intuition: Localized;
    modelType: Localized;
    validation: Localized;
    outputs: LocalizedList;
    limitations: LocalizedList;
  };
}

/** Fields needed to render a catalogue card. The production API returns this
 * subset from `web.models`; full descriptions are fetched on the detail page. */
export type ModelCardData = Pick<
  ModelConfig,
  | "slug"
  | "name"
  | "code"
  | "markets"
  | "category"
  | "status"
  | "access"
  | "featured"
  | "version"
  | "updatedAt"
  | "sparkline"
  | "sparklineLabel"
  | "sparklineScale"
  | "horizons"
  | "tagline"
  | "keyOutput"
>;

export const MODELS: ModelConfig[] = [
  {
    slug: "raemf-mc",
    name: "RAEMF-VB-MC",
    code: "QP-F01",
    markets: ["VNINDEX"],
    category: "forecasting",
    status: "experimental",
    visibility: "public",
    access: "public",
    featured: true,
    version: "0.3.0",
    updatedAt: "2026-08-06T00:00:00.000Z",
    sparkline: [53.84, 58.47, 53.85],
    sparklineLabel: {
      vi: "Tỷ lệ dự báo đúng tăng/giảm, theo số phiên",
      en: "Correct up-or-down calls, by sessions ahead",
    },
    sparklineScale: {
      min: 40,
      max: 70,
      suffix: "%",
      reference: 50,
      referenceLabel: {
        vi: "Vạch đứng là mức 50% — ngang với đoán ngẫu nhiên.",
        en: "The tick marks 50% — the level of a coin flip.",
      },
    },
    horizons: [20, 40, 60],
    show_performance: false,
    show_forecast: false,
    show_internal_signal: false,
    tagline: {
      vi: "Ước lượng VN-Index có thể tăng hoặc giảm trong phạm vi nào ở 20, 40 và 60 phiên.",
      en: "Estimates how far the VN-Index could rise or fall over 20, 40 and 60 sessions.",
    },
    keyOutput: {
      vi: "Phạm vi tăng giảm và rủi ro cho 20, 40 và 60 phiên",
      en: "Possible returns and risks over 20, 40 and 60 sessions",
    },
    description: {
      objective: {
        vi: "Ước lượng VN-Index có thể tăng hoặc giảm trong phạm vi nào sau 20, 40 và 60 phiên, đồng thời đo khả năng xảy ra các mức thua lỗ.",
        en: "Estimate how far VN-Index could rise or fall over 20, 40 and 60 sessions, including the chance of different loss levels.",
      },
      intuition: {
        vi: "Quan hệ giữa các biến thị trường có thể thay đổi theo từng giai đoạn. Mô hình vì vậy sử dụng trạng thái thị trường như một phần bối cảnh của dự báo.",
        en: "Relationships between market variables can change over time. The model therefore uses market state as part of the forecast context.",
      },
      modelType: {
        vi: "Kết hợp mô hình nhận biết trạng thái thị trường với nhiều kịch bản mô phỏng để tạo ra một phạm vi kết quả thay vì chỉ một con số.",
        en: "The system combines models that recognise market states with many simulated scenarios, producing a range of possible outcomes instead of one number.",
      },
      validation: {
        vi: "Kiểm tra lần lượt theo thời gian trên dữ liệu chưa dùng để xây dựng mô hình; so sánh với cách dự báo đơn giản và đo xem kết quả thực tế có nằm trong phạm vi đã dự báo hay không.",
        en: "The model is tested in time order on data not used to build it, compared with a simple forecast and checked against actual outcomes.",
      },
      outputs: {
        vi: ["Kết quả ở trung tâm cho từng thời hạn", "Phạm vi dự báo 95%", "Khả năng tăng hoặc giảm", "Khả năng của từng trạng thái thị trường", "Mức biến động dự kiến"],
        en: ["Central result for each period", "95% forecast range", "Chance of a rise or fall", "Chance of each market state", "Expected volatility"],
      },
      limitations: {
        vi: ["Không thể dự đoán đầy đủ các sự kiện bất ngờ bên ngoài thị trường", "Sai số có thể tăng ở thời hạn dài", "Kết quả phụ thuộc vào chất lượng dữ liệu đầu vào"],
        en: ["Cannot fully anticipate unexpected external events", "Errors may grow over longer periods", "Results depend on input data quality"],
      },
    },
  },
  {
    slug: "rarf-fhe",
    name: "RARF-FHE",
    code: "QP-F02",
    markets: ["VNINDEX", "VN30"],
    category: "forecasting",
    status: "experimental",
    visibility: "public",
    access: "public",
    featured: true,
    version: "1.0.0",
    updatedAt: "2026-08-06T00:00:00.000Z",
    sparkline: [1.24, 2.86, 4.05, 5.79, 8.19, 9.88],
    sparklineLabel: {
      vi: "Sai số dự báo, theo số phiên",
      en: "Forecast error, by sessions ahead",
    },
    sparklineScale: {
      min: 0,
      max: 12,
      suffix: "%",
      referenceLabel: {
        vi: "Sai số càng thấp càng tốt.",
        en: "Lower error is better.",
      },
    },
    horizons: [1, 5, 10, 20, 40, 60],
    show_performance: false,
    show_forecast: false,
    show_internal_signal: false,
    tagline: {
      vi: "Dự báo VN-Index, tự chuyển về phương án đơn giản khi mô hình học máy chưa đủ tốt.",
      en: "Forecasts the VN-Index and falls back to a simple method when machine learning is not good enough.",
    },
    keyOutput: {
      vi: "Phạm vi dự báo và khả năng giảm từ đỉnh của VN-Index",
      en: "Forecast ranges and chances of a decline from peak",
    },
    description: {
      objective: {
        vi: "Dự báo VN-Index theo nhiều thời hạn, đồng thời ước lượng phạm vi kết quả và khả năng giảm từ đỉnh.",
        en: "Forecast VN-Index over several periods, including a possible range and the chance of a decline from a previous peak.",
      },
      intuition: {
        vi: "Việc theo dõi mức đóng góp của từng nhóm dữ liệu giúp người đọc hiểu cơ sở của dự báo. Mức đóng góp không đồng nghĩa với quan hệ nhân quả.",
        en: "Tracking each factor group's contribution helps readers understand the basis of a forecast. Contribution does not imply causation.",
      },
      modelType: {
        vi: "Mô hình rừng ngẫu nhiên (Random Forest) được so sánh với một cách dự báo cơ sở. Hệ thống tự dùng phương án đơn giản nếu học máy chưa tốt hơn.",
        en: "A Random Forest is compared with a simple reference forecast. The system automatically uses the simpler option when machine learning is not better.",
      },
      validation: {
        vi: "Dữ liệu được chia đúng theo thời gian. Mô hình chỉ học từ quá khứ rồi mới được thử trên giai đoạn tiếp theo.",
        en: "Data is divided in time order. The model learns only from the past and is then tested on the following period.",
      },
      outputs: {
        vi: ["Dự báo theo từng thời hạn", "Phạm vi kết quả", "Khả năng giảm từ đỉnh", "Trạng thái thị trường"],
        en: ["Forecast for each period", "Possible outcome range", "Chance of a decline from peak", "Market state"],
      },
      limitations: {
        vi: ["Giải thích ở mức nhóm đặc trưng, không phải quan hệ nhân quả", "Nhạy với thay đổi cấu trúc thị trường"],
        en: ["Explanations are at factor-group level, not causal", "Sensitive to structural market changes"],
      },
    },
  },
  {
    slug: "dynamic-graph",
    name: "DynamicGraph",
    code: "QP-R02",
    markets: ["VN30"],
    category: "risk",
    status: "experimental",
    visibility: "public",
    access: "public",
    featured: true,
    version: "0.1.0",
    updatedAt: "2026-08-06T00:00:00.000Z",
    sparkline: [
      86.71, 81.66, 84.68, 83.79, 80.31, 81.9, 84.36, 76.22, 79.0,
      82.09, 81.52, 77.04,
    ],
    sparklineLabel: {
      vi: "Mức liên kết giữa các cổ phiếu gần đây",
      en: "Recent connection level among stocks",
    },
    horizons: [],
    show_performance: false,
    show_forecast: false,
    show_internal_signal: false,
    tagline: {
      vi: "Cho biết các cổ phiếu VN30 đang liên kết với nhau ra sao và khi nào khả năng đa dạng hóa suy giảm.",
      en: "Shows how VN30 stocks move together and when diversification may weaken.",
    },
    keyOutput: {
      vi: "Bản đồ liên kết cổ phiếu và mức căng thẳng của VN30",
      en: "Stock connection map and VN30 stress level",
    },
    description: {
      objective: {
        vi: "Mô tả cấu trúc phụ thuộc biến đổi theo thời gian giữa các cổ phiếu VN30 sau khi loại ảnh hưởng chung của thị trường.",
        en: "Describe time-varying dependence among VN30 stocks after removing their shared market component.",
      },
      intuition: {
        vi: "Khi nhiều cổ phiếu liên kết chặt hơn, khả năng đa dạng hóa có thể suy giảm. Mạng giúp quan sát hiện tượng này nhưng không cho biết giá sẽ tăng hay giảm.",
        en: "When stocks become more tightly connected, diversification may weaken. The network observes this structure but does not predict price direction.",
      },
      modelType: {
        vi: "Mạng tương quan riêng phần 60 phiên, ước lượng bằng Ledoit–Wolf và Graphical Lasso, kèm chỉ số độ trung tâm và cộng đồng.",
        en: "A 60-session relationship map, using established statistical methods to identify strongly connected stocks and groups.",
      },
      validation: {
        vi: "Mô hình được kiểm tra 20 lần theo thứ tự thời gian, có khoảng cách giữa dữ liệu học và dữ liệu kiểm tra để tránh nhìn trước.",
        en: "The model was tested 20 times in chronological order, with gaps between learning and test data to prevent looking ahead.",
      },
      outputs: {
        vi: ["Mạng phụ thuộc VN30", "Điểm căng thẳng cấu trúc", "Độ trung tâm của từng cổ phiếu", "Cụm cổ phiếu liên kết"],
        en: ["VN30 dependency network", "Structural stress score", "Stock centrality", "Dependency communities"],
      },
      limitations: {
        vi: ["Không dự báo giá và không chứng minh quan hệ nguyên nhân–kết quả", "Dùng danh sách VN30 hiện tại cho cả dữ liệu quá khứ nên có thể bỏ sót các cổ phiếu đã bị loại"],
        en: ["Does not forecast price or establish causality", "Uses the current VN30 list historically and therefore has survivorship bias"],
      },
    },
  },
  {
    slug: "msdp",
    name: "MSDP",
    code: "QP-F03",
    markets: ["VNINDEX"],
    category: "forecasting",
    status: "experimental",
    visibility: "public",
    access: "public",
    featured: true,
    version: "0.1.0",
    updatedAt: "2026-08-06T00:00:00.000Z",
    sparkline: [90.24, 88.55, 87.95],
    sparklineLabel: {
      vi: "Độ tin cậy của phạm vi dự báo, theo số phiên",
      en: "Reliability of the forecast range, by sessions ahead",
    },
    sparklineScale: {
      min: 80,
      max: 100,
      suffix: "%",
      reference: 90,
      referenceLabel: {
        vi: "Vạch đứng là mức 90% cần đạt.",
        en: "The tick marks the 90% target.",
      },
    },
    horizons: [5, 20, 60],
    show_performance: false,
    show_forecast: true,
    show_internal_signal: false,
    tagline: {
      vi: "Ước lượng phạm vi tăng giảm, mức giảm từ đỉnh và biến động của VN-Index ở nhiều thời hạn.",
      en: "Estimates possible VN-Index returns, declines from peak and volatility over several periods.",
    },
    keyOutput: {
      vi: "Khả năng tăng, phạm vi kết quả và rủi ro giảm giá",
      en: "Chance of rising, possible outcomes and downside risk",
    },
    description: {
      objective: {
        vi: "Ước lượng phạm vi VN-Index có thể tăng hoặc giảm sau 5, 20 và 60 phiên thay vì chỉ đưa ra một con số.",
        en: "Estimate how far VN-Index could rise or fall over 5, 20 and 60 sessions instead of giving only one number.",
      },
      intuition: {
        vi: "Nhịp ngắn, trung, dài và biến động có thể chứa thông tin khác nhau. Mô hình học cách phối hợp bốn góc nhìn riêng cho từng thời hạn.",
        en: "Short, medium, long and volatility views can carry different information. The model learns a separate mix for each horizon.",
      },
      modelType: {
        vi: "Bốn thành phần quan sát thị trường ở các khoảng thời gian khác nhau. Kết quả được hiệu chỉnh để phạm vi dự báo sát thực tế hơn.",
        en: "Four components observe the market over different periods. The result is adjusted so the forecast range better matches real outcomes.",
      },
      validation: {
        vi: "Dữ liệu được chia theo thời gian thành phần xây dựng, hiệu chỉnh và kiểm tra. Mô hình được thử với 50 phương án, chạy lại 3 lần và lấy mẫu lại 1.000 lần để đo độ ổn định.",
        en: "Data is divided in time order for building, adjusting and testing. The model tried 50 settings, was run three times and checked with 1,000 repeated samples.",
      },
      outputs: {
        vi: ["Phạm vi tăng hoặc giảm", "Khả năng VN-Index tăng", "Mức giảm từ đỉnh có thể xảy ra", "Mức biến động dự kiến", "Mức đóng góp của bốn thành phần"],
        en: ["Possible rise or fall range", "Chance that VN-Index rises", "Possible decline from peak", "Expected volatility", "Contribution of four components"],
      },
      limitations: {
        vi: ["Chưa chứng minh được ưu thế dự báo điểm", "Khoảng dự báo dài hạn rất rộng", "Quy trình huấn luyện lại production và hiệu chỉnh OOF chưa hoàn tất"],
        en: ["Not yet proven better at predicting one number", "Long-term forecast ranges are very wide", "Full retraining and final operational checks are incomplete"],
      },
    },
  },
  {
    slug: "model-modus",
    name: "Model Modus",
    code: "QP-T01",
    markets: ["VN30F1M"],
    category: "trading_system",
    // Frozen and validated, but not yet in paper trading. The research
    // project still has open validation gates before deployment.
    status: "experimental",
    visibility: "public",
    access: "public",
    featured: false,
    version: "2.1.0",
    horizons: [1],
    show_performance: true,
    show_forecast: false,
    show_internal_signal: false,
    strategySlug: "vn30f1m-walk-forward",
    tagline: {
      vi: "Hệ thống giao dịch có quy tắc cho hợp đồng tương lai VN30F1M, hiện mới được thử nghiệm trên dữ liệu quá khứ.",
      en: "A rule-based VN30F1M futures system currently tested only on historical data.",
    },
    keyOutput: {
      vi: "Kết quả của ba lần thử nghiệm độc lập",
      en: "Results from three independent tests",
    },
    description: {
      objective: {
        vi: "Giao dịch có hệ thống hợp đồng tương lai VN30F1M trong ngày với quản trị rủi ro thích ứng.",
        en: "Systematic intraday trading of VN30F1M futures with adaptive risk management.",
      },
      intuition: {
        vi: "Hệ thống sử dụng cùng một bộ quy tắc để xử lý dữ liệu và quản trị rủi ro, nhằm giảm sự thiếu nhất quán trong quyết định giao dịch.",
        en: "The system applies the same rules to data processing and risk management to reduce inconsistency in trading decisions.",
      },
      modelType: {
        vi: "Hệ thống gồm ba phần chính: đọc tín hiệu thị trường, quyết định giao dịch và kiểm soát rủi ro. Quy tắc mua bán chi tiết không được công khai.",
        en: "The system has three main parts: reading market signals, making trade decisions and controlling risk. Detailed trading rules are not published.",
      },
      validation: {
        vi: "Hệ thống được thử trên các năm dữ liệu chưa dùng để xây dựng mô hình và được chạy lại 50 lần để xem kết quả có ổn định hay không. Mô phỏng có tính đến giá mở cửa vượt mức dừng lỗ, phiên ATC, ngày đáo hạn và chi phí giao dịch.",
        en: "The system was tested on years not used to build the model and run 50 times to check stability. The simulation includes opening prices beyond stop levels, ATC sessions, expiry days and transaction costs.",
      },
      outputs: {
        vi: ["Đường tăng trưởng vốn", "Mức giảm từ đỉnh", "Phân bố lợi nhuận từng lệnh", "Chỉ số rủi ro", "Ảnh hưởng của chi phí giao dịch"],
        en: ["Portfolio value over time", "Decline from peak", "Profit or loss for each trade", "Risk measures", "Effect of transaction costs"],
      },
      // Left empty on purpose. The first item restated the disclosure policy
      // the architecture section already carries, and the third described
      // work in progress inside the research team. That the system is tested
      // on historical data only is stated in the tagline and by the status
      // badge, so nothing factual is lost by omitting the list here.
      limitations: { vi: [], en: [] },
    },
    // Layer names and purposes only. Techniques, lookback windows, state
    // counts and timeframes are deliberately absent: publishing them would
    // amount to publishing the model.
    architecture: [
      {
        title: { vi: "Tầng tín hiệu", en: "Signal layer" },
        text: {
          vi: "Nhiều nhóm chỉ báo độc lập cùng quan sát thị trường ở các khía cạnh khác nhau. Việc kết hợp nhiều góc nhìn giúp hệ thống ít phụ thuộc vào một cách đọc thị trường duy nhất.",
          en: "Several independent indicator groups observe the market from different angles. Combining multiple views reduces the system's dependence on any single reading of the market.",
        },
      },
      {
        title: { vi: "Tầng ra quyết định", en: "Decision layer" },
        text: {
          vi: "Một mô hình học máy tổng hợp các tín hiệu thành quyết định vào hoặc thoát lệnh, kèm mức độ tin cậy. Lệnh chỉ được thực hiện khi mức tin cậy vượt ngưỡng đã đặt trước.",
          en: "A machine-learning model consolidates the signals into entry and exit decisions with an associated confidence level. A trade is taken only when that confidence clears a predefined threshold.",
        },
      },
      {
        title: { vi: "Nhận diện trạng thái thị trường", en: "Market regime detection" },
        text: {
          vi: "Hệ thống phân loại điều kiện thị trường hiện tại và điều chỉnh cách hành xử theo từng trạng thái. Cùng một tín hiệu có thể dẫn tới quyết định khác nhau tùy bối cảnh thị trường.",
          en: "The system classifies prevailing market conditions and adjusts its behaviour accordingly. The same signal can lead to a different decision depending on the market context.",
        },
      },
      {
        title: { vi: "Quản trị rủi ro thích ứng", en: "Adaptive risk management" },
        text: {
          vi: "Mức dừng lỗ được nới hoặc thu hẹp theo mức biến động dự kiến: thị trường biến động mạnh thì khoảng dừng rộng hơn để tránh bị dừng sớm bởi nhiễu giá.",
          en: "Stop levels widen or tighten with expected volatility: a more volatile market gets more room, so a position is not closed early by ordinary price noise.",
        },
      },
      {
        title: { vi: "Mô phỏng khớp lệnh thận trọng", en: "Conservative execution simulation" },
        text: {
          vi: "Mô phỏng giả định khớp lệnh ở mức bất lợi khi thị trường mở cửa vượt qua mức dừng, xử lý riêng lệnh phát sinh trong phiên ATC, tất toán vào ngày đáo hạn và tính đầy đủ chi phí giao dịch.",
          en: "The simulation assumes an unfavourable fill when the market opens beyond a stop level, handles orders arising in the ATC session separately, settles positions on expiry days and applies full transaction costs.",
        },
      },
      {
        title: { vi: "Không nhìn trước tương lai", en: "Anti-leakage discipline" },
        text: {
          vi: "Mọi thành phần học từ dữ liệu chỉ được thấy dữ liệu có trước thời điểm huấn luyện. Bộ dữ liệu kiểm tra cuối cùng được niêm phong và chỉ mở đúng một lần.",
          en: "Every component that learns from data sees only data preceding the training cutoff. The final test set is sealed and opened exactly once.",
        },
      },
    ],
  },
  {
    slug: "vn30-equity-intelligence",
    name: "VN30 Equity Intelligence",
    code: "QP-R01",
    markets: ["VN30"],
    category: "ranking",
    status: "active",
    visibility: "public",
    access: "public",
    featured: false,
    version: "1.1.0",
    horizons: [5, 20],
    show_performance: false,
    show_forecast: true,
    show_internal_signal: false,
    tagline: {
      vi: "So sánh các cổ phiếu VN30 theo xu hướng, mức biến động và rủi ro.",
      en: "Compares VN30 stocks by trend, volatility and risk.",
    },
    keyOutput: {
      vi: "Thứ hạng và mức rủi ro của 30 cổ phiếu VN30",
      en: "Rankings and risk levels for 30 VN30 stocks",
    },
    description: {
      objective: {
        vi: "Xếp hạng tương đối các cổ phiếu VN30 dựa trên tổ hợp định giá, trạng thái kỹ thuật, rủi ro và trạng thái của nhóm ngành.",
        en: "Relative ranking of VN30 stocks by a composite of valuation, technical state, risk and sector regime.",
      },
      intuition: {
        vi: "So sánh các cổ phiếu trong cùng rổ giúp thể hiện vị trí tương đối của từng mã. Kết quả xếp hạng không phải dự báo giá hay khuyến nghị mua bán.",
        en: "Comparing stocks within the same basket shows each stock's relative position. The ranking is neither a price forecast nor a trading recommendation.",
      },
      modelType: {
        vi: "Mô hình xếp hạng đa yếu tố, chuẩn hóa các cổ phiếu tại cùng một thời điểm và điều chỉnh theo trạng thái thị trường.",
        en: "A multi-factor ranking model with cross-sectional normalization and regime adjustment.",
      },
      validation: {
        vi: "Đánh giá độ ổn định của thứ hạng và khả năng phân biệt tương đối trên dữ liệu chưa dùng để huấn luyện.",
        en: "Rank-stability evaluation and out-of-sample relative information coefficients over time.",
      },
      outputs: {
        vi: ["Xếp hạng hằng ngày", "Mức định giá tương đối", "Trạng thái kỹ thuật", "Điểm rủi ro", "Trạng thái nhóm ngành"],
        en: ["Daily rankings", "Relative valuation", "Technical state", "Risk score", "Sector regime"],
      },
      limitations: {
        vi: ["Thứ hạng chỉ mang tính tương đối, không phải khuyến nghị mua bán", "Phạm vi hiện chỉ gồm các cổ phiếu trong rổ VN30"],
        en: ["Rankings are relative, not trade recommendations", "Coverage limited to the VN30 basket"],
      },
    },
  },
  {
    slug: "regime-hmm",
    name: "Regime HMM",
    code: "QP-S01",
    markets: ["VNINDEX", "VN30", "VN30F1M"],
    category: "regime",
    status: "active",
    visibility: "public",
    access: "members",
    featured: false,
    version: "1.4.1",
    horizons: [1],
    show_performance: false,
    show_forecast: true,
    show_internal_signal: false,
    tagline: {
      vi: "Nhận biết thị trường đang tăng, giảm, đi ngang hay biến động mạnh.",
      en: "Real-time market state detection with Hidden Markov models.",
    },
    keyOutput: {
      vi: "Khả năng xảy ra của từng trạng thái thị trường",
      en: "Regime probabilities for the main indices",
    },
    description: {
      objective: {
        vi: "Nhận biết thị trường đang tăng, giảm, đi ngang hay biến động mạnh, đồng thời ước lượng khả năng trạng thái thay đổi.",
        en: "Classify the market into statistical states (bullish, bearish, sideways, turbulent) with transition probabilities.",
      },
      intuition: {
        vi: "Trạng thái thị trường cung cấp một lớp bối cảnh để các mô hình khác điều chỉnh cách diễn giải dữ liệu.",
        en: "Other models need context before acting. Market state provides that context.",
      },
      modelType: {
        vi: "Mô hình Markov ẩn dùng mức tăng giảm và biến động để nhận biết trạng thái thị trường.",
        en: "Hidden Markov model over return and volatility features.",
      },
      validation: {
        vi: "Đánh giá độ ổn định của phân loại và độ trễ khi nhận diện thay đổi trạng thái trên dữ liệu chưa dùng để huấn luyện.",
        en: "Classification stability and out-of-sample transition detection latency.",
      },
      outputs: {
        vi: ["Trạng thái hiện tại", "Xác suất từng trạng thái", "Khả năng chuyển từ trạng thái này sang trạng thái khác"],
        en: ["Current regime", "Per-regime probabilities", "Transition matrix"],
      },
      limitations: {
        vi: ["Nhận diện có độ trễ tự nhiên", "Số trạng thái là lựa chọn mô hình hóa"],
        en: ["Detection has inherent lag", "The number of states is a modeling choice"],
      },
    },
  },
  {
    slug: "vol-garch",
    name: "Volatility GARCH",
    code: "QP-V01",
    markets: ["VNINDEX", "VN30F1M"],
    category: "volatility",
    status: "active",
    visibility: "public",
    access: "members",
    featured: false,
    version: "1.0.5",
    horizons: [1, 5],
    show_performance: false,
    show_forecast: true,
    show_internal_signal: false,
    tagline: {
      vi: "Ước lượng giá có thể dao động mạnh đến mức nào trong 1–5 phiên tới.",
      en: "Conditional volatility forecasting for indices and derivatives.",
    },
    keyOutput: {
      vi: "Mức biến động dự kiến trong 1–5 phiên",
      en: "1–5 day volatility forecasts",
    },
    description: {
      objective: {
        vi: "Ước lượng mức biến động trong 1 và 5 ngày để hỗ trợ xây dựng khoảng dự báo và đánh giá rủi ro.",
        en: "Estimate and forecast conditional volatility to feed forecast intervals and risk management.",
      },
      intuition: {
        vi: "Mức biến động thường tập trung theo từng giai đoạn: sau một phiên biến động mạnh, các phiên tiếp theo cũng có thể tiếp tục biến động mạnh. Mô hình khai thác đặc điểm này.",
        en: "Volatility often clusters over time: large moves can be followed by further large moves. The model uses this observed pattern.",
      },
      modelType: {
        vi: "Mô hình GARCH học từ việc các giai đoạn biến động mạnh thường xuất hiện gần nhau.",
        en: "GARCH-family models with fat-tailed distributions.",
      },
      validation: {
        vi: "Kiểm tra trên giai đoạn dữ liệu mới bằng một thước đo chuyên dùng cho dự báo biến động (QLIKE).",
        en: "Out-of-sample evaluation with volatility-specific loss functions (QLIKE).",
      },
      outputs: {
        vi: ["Biến động dự báo theo từng thời hạn", "Khoảng biến động ước tính", "Trạng thái biến động"],
        en: ["Per-horizon volatility forecasts", "Volatility bands", "Volatility state"],
      },
      limitations: {
        vi: ["Không dự báo được cú sốc biến động đột ngột", "Giả định cấu trúc có thể bị vi phạm"],
        en: ["Cannot anticipate sudden volatility shocks", "Structural assumptions can be violated"],
      },
    },
  },
  {
    slug: "mc-risk-engine",
    name: "MC Risk Engine",
    code: "QP-K01",
    markets: ["VNINDEX", "VN30", "VN30F1M"],
    category: "risk",
    status: "active",
    visibility: "public",
    access: "members",
    featured: false,
    version: "1.3.0",
    horizons: [20],
    show_performance: false,
    show_forecast: false,
    show_internal_signal: false,
    tagline: {
      vi: "Mô phỏng nhiều tình huống để ước lượng khả năng thua lỗ và mức giảm từ đỉnh.",
      en: "Estimating risk and future drawdowns through simulation.",
    },
    keyOutput: {
      vi: "Ngưỡng lỗ ước tính và mức giảm có thể xảy ra",
      en: "VaR, Expected Shortfall and drawdown distributions",
    },
    description: {
      objective: {
        vi: "Ước lượng ngưỡng lỗ VaR, tổn thất kỳ vọng, mức giảm từ đỉnh và kết quả trong các kịch bản thị trường bất lợi.",
        en: "Estimate VaR, Expected Shortfall, drawdown distributions and stress scenarios for the systematic book.",
      },
      intuition: {
        vi: "Một giá trị trung bình không phản ánh đầy đủ các trường hợp xấu. Mô hình vì vậy đánh giá cả phạm vi kết quả và xác suất của từng mức tổn thất.",
        en: "A single average does not describe adverse cases. The model therefore estimates a range of outcomes and the probability of different loss levels.",
      },
      modelType: {
        vi: "Tạo nhiều kịch bản ngẫu nhiên (Monte Carlo) và lấy mẫu lại dữ liệu cũ để kiểm tra độ ổn định của kết quả.",
        en: "Monte Carlo and bootstrap over regime-conditioned return distributions.",
      },
      validation: {
        vi: "Đối chiếu ngưỡng VaR với dữ liệu thực tế và kiểm tra tỷ lệ kết quả nằm trong phạm vi đã ước lượng.",
        en: "VaR backtesting (violation rates) and percentile coverage checks.",
      },
      outputs: {
        vi: ["VaR và tổn thất kỳ vọng theo mức tin cậy", "Phân bố mức giảm từ đỉnh", "Kịch bản thị trường bất lợi"],
        en: ["VaR and ES by confidence level", "Drawdown distributions", "Stress scenarios"],
      },
      limitations: {
        vi: ["Kết quả phụ thuộc vào cách mô hình giả định các mức tăng giảm có thể xảy ra", "Những tình huống chưa từng xảy ra trong quá khứ có thể không được phản ánh"],
        en: ["Dependent on distributional assumptions", "Historical scenarios do not cover all futures"],
      },
    },
  },
  {
    slug: "market-breadth",
    name: "Market Breadth Monitor",
    code: "QP-X01",
    markets: ["VN30"],
    category: "regime",
    status: "experimental",
    visibility: "public",
    access: "members",
    featured: false,
    version: "0.3.0",
    horizons: [5],
    show_performance: false,
    show_forecast: false,
    show_internal_signal: false,
    tagline: {
      vi: "Cho biết một xu hướng đang được nhiều hay chỉ một vài cổ phiếu VN30 hỗ trợ.",
      en: "Measuring market breadth through co-movement of constituent stocks.",
    },
    keyOutput: {
      vi: "Mức độ tham gia của các cổ phiếu và cảnh báo lệch xu hướng",
      en: "Breadth and divergence indices (experimental)",
    },
    description: {
      objective: {
        vi: "Phát hiện khi chỉ số vẫn tăng nhưng ngày càng ít cổ phiếu cùng tăng, dấu hiệu xu hướng có thể đang yếu đi.",
        en: "Detect internal trend weakening early through the breadth of constituent participation.",
      },
      intuition: {
        vi: "Chỉ số có thể tăng nhờ một vài cổ phiếu lớn trong khi phần còn lại đã yếu đi. Sự lệch nhau này đáng để theo dõi.",
        en: "An index can rise while most stocks are already weakening. That difference can carry useful information.",
      },
      modelType: {
        vi: "Tổ hợp các chỉ số đo mức độ tham gia của cổ phiếu, được chuẩn hóa tại cùng một thời điểm. Mô hình đang thử nghiệm.",
        en: "A composite of cross-sectionally normalized breadth measures (experimental).",
      },
      validation: {
        vi: "Ý tưởng vẫn đang được kiểm tra; chưa có kết quả hoàn chỉnh trên một giai đoạn dữ liệu mới.",
        en: "In hypothesis-testing stage; no complete out-of-sample results yet.",
      },
      outputs: {
        vi: ["Chỉ số độ rộng", "Cảnh báo phân kỳ"],
        en: ["Breadth index", "Divergence alerts"],
      },
      limitations: {
        vi: ["Mô hình đang thử nghiệm. Kết quả chưa được kiểm tra đầy đủ"],
        en: ["Experimental model. Results have not yet been fully tested"],
      },
    },
  },
  {
    slug: "sector-rotation",
    name: "Sector Rotation Model",
    code: "QP-X02",
    markets: ["VN30"],
    category: "ranking",
    status: "experimental",
    visibility: "public",
    access: "members",
    featured: false,
    version: "0.2.1",
    horizons: [20],
    show_performance: false,
    show_forecast: false,
    show_internal_signal: false,
    tagline: {
      vi: "Theo dõi luân chuyển dòng tiền giữa các nhóm ngành.",
      en: "Tracking capital rotation across sector groups.",
    },
    keyOutput: {
      vi: "Xếp hạng nhóm ngành theo sức mạnh giá (thử nghiệm)",
      en: "Sector momentum rankings (experimental)",
    },
    description: {
      objective: {
        vi: "Nhận diện chu kỳ luân chuyển giữa các nhóm ngành trong rổ VN30.",
        en: "Identify rotation cycles across sector groups within the VN30 basket.",
      },
      intuition: {
        vi: "Tiền có thể chuyển từ nhóm ngành đang yếu sang nhóm đang mạnh. Theo dõi sự thay đổi này giúp hiểu nhóm nào đang dẫn dắt thị trường.",
        en: "Capital rarely leaves the market at once. It moves between sectors, which can reveal changes in market structure.",
      },
      modelType: {
        vi: "Mô hình động lượng tương đối giữa nhóm ngành (đang thử nghiệm).",
        en: "Relative momentum model across sector groups (experimental).",
      },
      validation: {
        vi: "Đang thử trên dữ liệu quá khứ; chưa có kết quả để công bố.",
        en: "Under historical validation; no published results.",
      },
      outputs: {
        vi: ["Xếp hạng ngành", "Trạng thái luân chuyển"],
        en: ["Sector rankings", "Rotation state"],
      },
      limitations: {
        vi: ["Mô hình đang thử nghiệm. Kết quả chưa được kiểm tra đầy đủ", "VN30 có ít cổ phiếu trong một số nhóm ngành nên việc so sánh còn hạn chế"],
        en: ["Experimental model. Results have not yet been fully tested", "Sector granularity within VN30 is limited"],
      },
    },
  },
  {
    slug: "liquidity-flow",
    name: "Liquidity Flow",
    code: "QP-X03",
    markets: ["VNINDEX"],
    category: "regime",
    status: "archived",
    visibility: "public",
    access: "members",
    featured: false,
    version: "0.9.0",
    horizons: [5],
    show_performance: false,
    show_forecast: false,
    show_internal_signal: false,
    tagline: {
      vi: "Nghiên cứu cũ về mối liên hệ giữa khối lượng giao dịch và giá, hiện không còn cập nhật.",
      en: "Early research on liquidity flows (archived).",
    },
    keyOutput: {
      vi: "Không còn cập nhật",
      en: "No longer updated",
    },
    description: {
      objective: {
        vi: "Tìm hiểu liệu thay đổi về khối lượng và khả năng mua bán có xuất hiện trước biến động giá ngắn hạn hay không.",
        en: "Studied the relationship between trading liquidity and short-term returns.",
      },
      intuition: {
        vi: "Trong một số giai đoạn, thanh khoản thay đổi trước giá. Tuy nhiên, giả thuyết này không cho kết quả đủ ổn định trên dữ liệu chưa dùng để xây dựng mô hình.",
        en: "Liquidity sometimes shifts before price. Tests showed that this idea was not stable enough on new data.",
      },
      modelType: {
        vi: "Mô hình thống kê sử dụng các chỉ số về khối lượng và khả năng mua bán. Nghiên cứu đã được lưu trữ.",
        en: "Regression models over liquidity features (archived).",
      },
      validation: {
        vi: "Không vượt qua yêu cầu về độ ổn định trên dữ liệu chưa dùng để xây dựng mô hình, nên đã được lưu trữ để tham chiếu.",
        en: "Did not pass stability tests on new data. Archived for reference.",
      },
      outputs: {
        vi: ["Không còn công bố đầu ra"],
        en: ["No outputs are published"],
      },
      limitations: {
        vi: ["Mô hình đã dừng cập nhật từ khi lưu trữ"],
        en: ["The model has not been updated since archival"],
      },
    },
  },
];

export const publicModels = () => MODELS.filter((m) => m.visibility === "public");
export const featuredModels = () => publicModels().filter((m) => m.featured);
export const getModel = (slug: string) =>
  MODELS.find((m) => m.slug === slug && m.visibility === "public");

/** True when the model's outputs are only shown to signed-in members. */
export const requiresAuth = (model: Pick<ModelConfig, "access">) =>
  model.access === "members";
export const memberModelCount = () =>
  publicModels().filter(requiresAuth).length;
export const previewModelCount = () =>
  publicModels().filter((m) => !requiresAuth(m)).length;

/** Counts used by the "by the numbers" section are derived, never hard-coded. */
export const modelCount = () => MODELS.length;
