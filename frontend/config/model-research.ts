export type ResearchLocale = "vi" | "en";

type Localized<T = string> = Record<ResearchLocale, T>;

export interface ResearchMetric {
  label: Localized;
  value: Localized;
  note: Localized;
}

export interface ResearchChartSeries {
  name: Localized;
  data: number[];
  type?: "line" | "bar";
  color: string;
  stack?: string;
  /**
   * The level this series was supposed to reach, drawn as a dashed line in the
   * series colour. Use this rather than `baseline` when each series is judged
   * against a different target — a single shared line would flatter whichever
   * series has the higher one.
   */
  target?: number;
}

/**
 * A shaded range between two boundaries, one pair of values per category.
 *
 * Simulation output is a distribution, not a line. Drawing the quantiles as
 * separate lines makes a reader trace which one belongs to which; shading the
 * space between them says "the outcome lands in here" in one glance.
 */
export interface ResearchBand {
  name: Localized;
  lower: number[];
  upper: number[];
  color: string;
  /** Fill strength, 0 to 1. Nest bands by giving the inner one more. */
  opacity?: number;
}

export interface ResearchChart {
  id: string;
  title: Localized;
  note: Localized;
  categories: string[];
  series: ResearchChartSeries[];
  bands?: ResearchBand[];
  valueSuffix?: string;
  minimum?: number;
  maximum?: number;
  baseline?: number;
  /** Label for the horizontal axis, printed under it when the categories are
   *  not self-explanatory. */
  xAxisLabel?: Localized;
  /** Draw every nth category label. Use on a long axis where every tick
   *  would overlap its neighbour. */
  categoryLabelInterval?: number;
}

export interface ModelResearchProfile {
  slug: string;
  artifactDate: string;
  verdict: {
    eyebrow: Localized;
    title: Localized;
    body: Localized;
  };
  metrics: ResearchMetric[];
  method: Localized<string[]>;
  findings: Localized<string[]>;
  charts: ResearchChart[];
  visual?: {
    src: string;
    alt: Localized;
    caption: Localized;
  };
  provenance: Localized;
}

export const MODEL_RESEARCH: Record<string, ModelResearchProfile> = {
  "raemf-mc": {
    slug: "raemf-mc",
    artifactDate: "2026-08-06",
    verdict: {
      eyebrow: { vi: "Kết quả chính", en: "Main result" },
      title: {
        vi: "Mô hình ước lượng phạm vi kết quả tốt hơn, nhưng độ tin cậy chưa đồng đều giữa các thời hạn.",
        en: "The model estimates the range of outcomes better, but its reliability is uneven across periods.",
      },
      body: {
        vi: "Phiên bản M2 dự báo phạm vi kết quả tốt hơn phiên bản chỉ đưa ra một giá trị. Ở thời hạn 60 phiên, phạm vi 95% đạt đúng mục tiêu; nhưng ở thời hạn 40 phiên, kết quả thực tế rơi ra ngoài nhiều hơn hẳn mức mong đợi. Vì độ tin cậy chưa ổn định giữa các thời hạn, Quant Percent chỉ công bố M2 như một kết quả nghiên cứu, chưa dùng làm phiên bản mặc định.",
        en: "M2 estimates possible outcomes better than the version that gives a single value. At the 60-session period its 95% range meets the target, but at 40 sessions actual outcomes fall outside far more often than expected. Because that reliability is not consistent across periods, Quant Percent presents M2 as research, not as the default model.",
      },
    },
    metrics: [
      {
        label: { vi: "Dữ liệu", en: "Dataset" },
        value: { vi: "6.324 phiên", en: "6,324 sessions" },
        note: {
          vi: "VN-Index, 28/07/2000–06/08/2026",
          en: "VN-Index, 28 Jul 2000–6 Aug 2026",
        },
      },
      {
        label: { vi: "Dữ liệu dùng để kiểm tra", en: "Data used for testing" },
        value: { vi: "1.880–1.892", en: "1,880–1,892" },
        note: {
          vi: "mốc dự báo cho mỗi thời hạn",
          en: "test points for each forecast period",
        },
      },
      {
        label: { vi: "Tỷ lệ dự báo đúng tăng/giảm", en: "Correct up-or-down forecasts" },
        value: { vi: "53,8–58,5%", en: "53.8–58.5%" },
        note: {
          vi: "cao nhất ở thời hạn 40 phiên",
          en: "highest at the 40-session period",
        },
      },
      {
        label: { vi: "Kết quả nằm trong phạm vi 95%", en: "Actual outcomes inside the 95% range" },
        value: { vi: "82,8–95,0%", en: "82.8–95.0%" },
        note: {
          vi: "chỉ thời hạn 60 phiên đạt mục tiêu 95%",
          en: "only the 60-session period reaches the 95% target",
        },
      },
    ],
    method: {
      vi: [
        "Mô hình xác định thị trường đang tăng, đi ngang, giảm hay căng thẳng chỉ bằng thông tin đã có tại thời điểm dự báo.",
        "Một thành phần ước lượng mức biến động; một thành phần khác ước lượng khả năng của từng trạng thái thị trường.",
        "Phương pháp Bayes biến phân được dùng để tạo ra nhiều kết quả có thể xảy ra, thay vì chỉ đưa ra một con số.",
        "Mô hình được kiểm tra ba lần theo thứ tự thời gian. Các vùng dữ liệu có thể chồng lấn được loại bỏ để tránh nhìn trước tương lai.",
      ],
      en: [
        "The model describes the market as rising, sideways, falling or stressed using only information available at the time.",
        "One component estimates volatility while another estimates the chance of each market condition.",
        "Variational Bayes creates a range of possible returns rather than a single number.",
        "The model is tested three times in date order, with overlapping data removed to prevent looking into the future.",
      ],
    },
    findings: {
      vi: [
        "Cả 9 lần chạy cho ba thời hạn 20, 40 và 60 phiên đều hoàn tất ổn định.",
        "Mô hình còn nhận biết kém các giai đoạn thị trường giảm. Xác suất trạng thái không nên được xem là tín hiệu mua bán.",
        "Dự báo tạo ngày 06/08/2026 chưa đến đủ thời hạn để so sánh với thực tế, nên không được dùng để chứng minh hiệu quả.",
      ],
      en: [
        "All nine runs across the 20, 40 and 60-session periods completed reliably.",
        "The model still struggles to identify falling markets. Market-state probabilities are not trading signals.",
        "Forecasts issued on 6 Aug 2026 have not reached their full periods and are not used as performance evidence.",
      ],
    },
    charts: [
      {
        id: "raemf-coverage",
        title: {
          vi: "Kết quả thực tế có nằm trong phạm vi dự báo không?",
          en: "Did actual outcomes stay inside the forecast range?",
        },
        note: {
          vi: "Nếu phạm vi được công bố là 90% hoặc 95%, tỷ lệ thực tế cũng nên gần mức đó. Kết quả thấp hơn cho thấy phạm vi dự báo còn quá hẹp.",
          en: "A range labelled 90% or 95% should contain actual outcomes at about that rate. Lower results show that the range is too narrow.",
        },
        categories: ["20", "40", "60"],
        valueSuffix: "%",
        minimum: 70,
        maximum: 100,
        series: [
          {
            name: { vi: "Phạm vi dự báo 90%", en: "90% interval" },
            data: [86.75, 74.94, 92.32],
            type: "bar",
            color: "#3a72c4",
            target: 90,
          },
          {
            name: { vi: "Phạm vi dự báo 95%", en: "95% interval" },
            data: [92.6, 82.77, 95.0],
            type: "bar",
            color: "#ad7519",
            target: 95,
          },
        ],
      },
      {
        id: "raemf-regimes",
        title: {
          vi: "Mô hình nhìn nhận thị trường ngày 06/08/2026 ra sao?",
          en: "How did the model view the market on 6 Aug 2026?",
        },
        note: {
          vi: "Không trạng thái nào có xác suất vượt trội, nên kết quả được xếp là “không chắc chắn”. Biểu đồ chỉ mô tả thị trường, không phải khuyến nghị mua bán.",
          en: "Probabilities are dispersed and the system labels the result uncertain. This is a state description, not a trading recommendation.",
        },
        categories: ["20", "40", "60"],
        valueSuffix: "%",
        minimum: 0,
        maximum: 100,
        series: [
          {
            name: { vi: "Tăng", en: "Bull" },
            data: [22.68, 20.26, 19.45],
            type: "bar",
            color: "#14795a",
            stack: "regime",
          },
          {
            name: { vi: "Đi ngang", en: "Sideway" },
            data: [29.54, 35.69, 36.8],
            type: "bar",
            color: "#94a3b8",
            stack: "regime",
          },
          {
            name: { vi: "Giảm", en: "Bear" },
            data: [24.57, 25.28, 23.0],
            type: "bar",
            color: "#ad7519",
            stack: "regime",
          },
          {
            name: { vi: "Căng thẳng", en: "Stress" },
            data: [23.21, 18.77, 20.75],
            type: "bar",
            color: "#a93b32",
            stack: "regime",
          },
        ],
      },
      {
        id: "raemf-fan",
        title: {
          vi: "Mô phỏng Monte Carlo: kết quả rơi vào đâu theo từng phiên?",
          en: "Monte Carlo simulation: where do outcomes land session by session?",
        },
        note: {
          vi: "Dải màu là nửa giữa của 1.200 đường mô phỏng, đường liền là trung vị. Chỉ vẽ nửa giữa vì phần đuôi của phân bố còn rất rộng — đây cũng là lý do mô hình vẫn ở trạng thái nghiên cứu. Mô phỏng chạy trên dữ liệu đến 13/07/2026, không phải dự báo hiện hành.",
          en: "The shaded area is the middle half of 1,200 simulated paths and the line is the median. Only the middle half is drawn because the tails of this distribution are very wide — which is why the model stays in research. Simulated on data to 13 Jul 2026; this is not a current forecast.",
        },
        categories: ["0", "4", "8", "12", "16", "20", "24", "28", "32", "36", "40", "44", "48", "52", "56", "60"],
        valueSuffix: "%",
        minimum: -8,
        maximum: 14,
        baseline: 0,
        xAxisLabel: { vi: "Số phiên kể từ ngày mô phỏng", en: "Sessions from the simulation date" },
        bands: [
          {
            name: { vi: "Nửa giữa của các kịch bản", en: "Middle half of scenarios" },
            lower: [0, -0.71, -0.91, -1.12, -1.21, -1.4, -1.54, -2.19, -2.07, -2.63, -2.91, -3.0, -3.77, -5.22, -5.5, -6.56],
            upper: [0, 1.06, 1.75, 2.31, 3.04, 3.72, 4.37, 4.57, 5.7, 6.46, 7.0, 8.2, 9.48, 10.0, 10.27, 11.62],
            color: "#3a72c4",
            opacity: 0.16,
          },
        ],
        series: [
          {
            name: { vi: "Trung vị", en: "Median" },
            data: [0, 0.16, 0.47, 0.46, 0.79, 1.17, 1.15, 1.15, 1.46, 1.68, 1.78, 1.92, 2.14, 2.0, 2.1, 2.25],
            type: "line",
            color: "#3a72c4",
          },
        ],
      },
      {
        id: "raemf-drawdown",
        title: {
          vi: "Khả năng giảm từ đỉnh trong từng thời hạn",
          en: "Chance of a decline from a peak, by period",
        },
        note: {
          vi: "Mỗi cột là khả năng VN-Index giảm quá mức tương ứng so với đỉnh trong thời hạn đó. Nhìn càng xa, khả năng gặp một đợt giảm càng cao. Mô phỏng chạy trên dữ liệu đến 13/07/2026.",
          en: "Each bar is the chance that VN-Index falls beyond that level from a previous peak within the period. The further out, the more likely a decline is met. Simulated on data to 13 Jul 2026.",
        },
        categories: ["20", "40", "60"],
        valueSuffix: "%",
        minimum: 0,
        maximum: 80,
        xAxisLabel: { vi: "Số phiên", en: "Sessions ahead" },
        series: [
          {
            name: { vi: "Giảm từ 5%", en: "Fall of 5% or more" },
            data: [36.17, 60.74, 72.85],
            type: "bar",
            color: "#94a3b8",
          },
          {
            name: { vi: "Giảm từ 10%", en: "Fall of 10% or more" },
            data: [20.24, 40.44, 53.86],
            type: "bar",
            color: "#ad7519",
          },
          {
            name: { vi: "Giảm từ 15%", en: "Fall of 15% or more" },
            data: [16.05, 30.98, 42.38],
            type: "bar",
            color: "#c2603f",
          },
          {
            name: { vi: "Giảm từ 20%", en: "Fall of 20% or more" },
            data: [13.14, 27.44, 37.57],
            type: "bar",
            color: "#a93b32",
          },
        ],
      },
    ],
    provenance: {
      vi: "Số liệu được trích trực tiếp từ tệp kết quả của lần chạy nghiên cứu ghi nhận ở trên, không nhập lại bằng tay.",
      en: "Figures are read directly from the result files of the recorded research run, not re-entered by hand.",
    },
  },
  "rarf-fhe": {
    slug: "rarf-fhe",
    artifactDate: "2026-08-06",
    verdict: {
      eyebrow: { vi: "Kết quả chính", en: "Main result" },
      title: {
        vi: "Hệ thống kiểm soát rủi ro hoạt động tốt, nhưng mô hình học máy chưa dự báo tốt hơn cách đơn giản.",
        en: "The risk controls work, but machine learning has not beaten a simple forecast.",
      },
      body: {
        vi: "Ở thời hạn chính 20 phiên, hệ thống nhận thấy mô hình học máy không tốt hơn cách dự báo cơ sở nên tự động quay về phương án đơn giản hơn. Cơ chế này giúp tránh sử dụng một mô hình chưa đủ tốt. Sau khi hiệu chỉnh, khoảng dự báo đáng tin cậy hơn nhưng cũng rộng hơn.",
        en: "For the main 20-session period, the system found that machine learning was not better and switched to a simpler forecast. This safeguard avoids relying on a model that has not proved its value. After adjustment, the forecast range was more reliable but also wider.",
      },
    },
    metrics: [
      {
        label: { vi: "Dữ liệu", en: "Dataset" },
        value: { vi: "6.324 phiên", en: "6,324 sessions" },
        note: {
          vi: "VN-Index, 28/07/2000–06/08/2026",
          en: "VN-Index, 28 Jul 2000–6 Aug 2026",
        },
      },
      {
        label: { vi: "Tiêu chí đã đạt", en: "Checks passed" },
        value: { vi: "6/9", en: "6/9" },
        note: {
          vi: "tiêu chí kiểm tra; bản A0 vẫn được giữ",
          en: "6 of 9 checks passed; the safer version was kept",
        },
      },
      {
        label: {
          vi: "Kết quả nằm trong phạm vi 95%",
          en: "Actual outcomes inside the 95% range",
        },
        value: { vi: "95,19%", en: "95.19%" },
        note: {
          vi: "sau hiệu chỉnh, từ mức 85,99%",
          en: "after adjustment, up from 85.99%",
        },
      },
      {
        label: { vi: "Mô phỏng gần nhất", en: "Latest simulation" },
        value: { vi: "40.000", en: "40,000" },
        note: {
          vi: "kịch bản giá cho thời hạn 20 phiên",
          en: "price paths over 20 sessions",
        },
      },
    ],
    method: {
      vi: [
        "Hệ thống xác định trạng thái và mức biến động của thị trường chỉ bằng dữ liệu đã có tại thời điểm dự báo.",
        "Mô hình rừng ngẫu nhiên (Random Forest) dự báo cho sáu thời hạn và luôn được so sánh với một cách dự báo cơ sở đơn giản.",
        "Một bước hiệu chỉnh thống kê giúp phạm vi dự báo phản ánh sát hơn mức độ không chắc chắn thực tế.",
        "Hàng chục nghìn kịch bản được mô phỏng để ước lượng khả năng thua lỗ lớn và mức giảm từ đỉnh.",
      ],
      en: [
        "The system identifies the market state and expected volatility using only information available at the forecast date.",
        "A Random Forest makes forecasts for six time periods and is always compared with a simple reference method.",
        "A statistical adjustment helps the forecast range reflect real-world uncertainty more closely.",
        "Tens of thousands of scenarios estimate the chance of a large loss and a decline from a previous peak.",
      ],
    },
    findings: {
      vi: [
        "Sai số tăng khi thời hạn dài hơn. Biểu đồ thể hiện kết quả của cách dự báo cơ sở được hệ thống chọn, không phải thành tích riêng của Random Forest.",
        "Mô phỏng ngày 06/08/2026 ước tính khả năng VN-Index giảm hơn 5% từ đỉnh trong 20 phiên là 74,40%. Đây là xác suất mô phỏng, không phải điều chắc chắn xảy ra.",
        "Kết quả dựa trên giả định các biến động từng xảy ra trong quá khứ vẫn còn hữu ích cho tương lai. Độ chính xác có thể giảm khi thị trường thay đổi mạnh.",
      ],
      en: [
        "Forecast error increases over longer periods. The chart shows the simple method selected by the system, not the Random Forest on its own.",
        "The 6 Aug 2026 simulation estimated a 74.40% chance that VN-Index would fall more than 5% from a peak within 20 sessions. This is a simulated probability, not a certainty.",
        "The result assumes that past market movements remain useful for understanding the future. Accuracy may fall when the market changes sharply.",
      ],
    },
    charts: [
      {
        id: "rarf-rmse",
        title: {
          vi: "Sai số dự báo tăng thế nào khi nhìn xa hơn?",
          en: "How does forecast error grow over longer periods?",
        },
        note: {
          vi: "Đơn vị là phần trăm thay đổi của VN-Index. Ở thời hạn chính, hệ thống chọn cách dự báo cơ sở vì Random Forest chưa cho kết quả tốt hơn.",
          en: "Values are percentage changes in VN-Index. For the main period, the system selected the simple reference method because the Random Forest was not better.",
        },
        categories: ["1", "5", "10", "20", "40", "60"],
        valueSuffix: "%",
        minimum: 0,
        series: [
          {
            name: { vi: "Sai số dự báo (RMSE)", en: "Forecast error (RMSE)" },
            data: [1.24, 2.86, 4.05, 5.79, 8.19, 9.88],
            type: "line",
            color: "#3a72c4",
          },
        ],
      },
      {
        id: "rarf-drawdown",
        title: {
          vi: "Khả năng giảm từ đỉnh trong mô phỏng gần nhất",
          en: "What was the chance of a decline from a peak in the latest simulation?",
        },
        note: {
          vi: "Mỗi cột cho biết khả năng VN-Index giảm quá một ngưỡng nhất định so với đỉnh, trong 5, 10 hoặc 20 phiên kể từ ngày 06/08/2026.",
          en: "Each bar shows the chance that VN-Index falls beyond a stated level from a previous peak within 5, 10 or 20 sessions from 6 Aug 2026.",
        },
        categories: ["3%", "5%", "7%", "10%", "15%"],
        valueSuffix: "%",
        minimum: 0,
        series: [
          {
            name: { vi: "Trong 5 phiên", en: "Within 5 sessions" },
            data: [45.42, 21.98, 9.45, 2.3, 0.17],
            type: "bar",
            color: "#94a3b8",
          },
          {
            name: { vi: "Trong 10 phiên", en: "Within 10 sessions" },
            data: [73.3, 46.43, 26.94, 10.44, 1.42],
            type: "bar",
            color: "#ad7519",
          },
          {
            name: { vi: "Trong 20 phiên", en: "Within 20 sessions" },
            data: [93.24, 74.4, 53.39, 29.5, 8.28],
            type: "bar",
            color: "#a93b32",
          },
        ],
      },
      {
        id: "rarf-coverage",
        title: {
          vi: "Khoảng dự báo có đáng tin ở mọi thời hạn không?",
          en: "Is the forecast range trustworthy at every horizon?",
        },
        note: {
          vi: "Một khoảng dự báo 90% đúng nghĩa phải chứa kết quả thực tế khoảng 90 lần trên 100. Trước bước hiệu chỉnh, tỷ lệ này tụt mạnh khi nhìn xa hơn: ở 60 phiên chỉ còn 28%. Sau hiệu chỉnh, cả sáu thời hạn đều bám sát mức 90%. Đo trên toàn bộ giai đoạn kiểm tra.",
          en: "A genuine 90% interval should contain the actual outcome about 90 times in 100. Before calibration the rate falls away with the horizon — at 60 sessions only 28% — and after it, all six horizons sit close to 90%. Measured across the whole test period.",
        },
        categories: ["1", "5", "10", "20", "40", "60"],
        valueSuffix: "%",
        minimum: 0,
        maximum: 100,
        baseline: 90,
        xAxisLabel: { vi: "Số phiên", en: "Sessions ahead" },
        series: [
          {
            name: { vi: "Trước hiệu chỉnh", en: "Before calibration" },
            data: [90.09, 74.35, 71.22, 78.51, 74.87, 28.46],
            type: "bar",
            color: "#94a3b8",
          },
          {
            name: { vi: "Sau hiệu chỉnh", en: "After calibration" },
            data: [89.84, 92.06, 91.28, 91.46, 92.69, 89.14],
            type: "bar",
            color: "#14795a",
          },
        ],
      },
    ],
    provenance: {
      vi: "Số liệu được trích trực tiếp từ tệp kết quả của lần chạy nghiên cứu ghi nhận ở trên, không nhập lại bằng tay.",
      en: "Figures are read directly from the result files of the recorded research run, not re-entered by hand.",
    },
  },
  "dynamic-graph": {
    slug: "dynamic-graph",
    // Full publication run on 2026-08-06. The stress classifiers still run
    // as part of that pipeline, but their output is not published: the page
    // presents market structure only.
    artifactDate: "2026-08-06",
    verdict: {
      eyebrow: { vi: "Kết quả chính", en: "Main result" },
      title: {
        vi: "Hữu ích để xem các cổ phiếu VN30 đang liên kết với nhau ra sao, nhưng không dùng để dự báo giá.",
        en: "Useful for seeing how VN30 stocks move together, but not for predicting prices.",
      },
      body: {
        vi: "DynamicGraph cho biết cổ phiếu nào thường biến động cùng nhau và mức độ thị trường đang tập trung vào một số nhóm cổ phiếu. Đây là công cụ quan sát cấu trúc thị trường: nó không đưa ra dự báo giá và không phải tín hiệu mua bán.",
        en: "DynamicGraph shows which stocks often move together and whether the market is becoming concentrated in a few groups. It is a tool for observing market structure: it does not forecast prices and is not a buy or sell signal.",
      },
    },
    metrics: [
      {
        label: { vi: "Phạm vi", en: "Coverage" },
        value: { vi: "29 cổ phiếu", en: "29 stocks" },
        note: {
          vi: "rổ VN30 sau đảo rổ; TCX chưa đủ lịch sử giá",
          en: "VN30 after the rebalance; TCX lacks price history",
        },
      },
      {
        label: { vi: "Điểm căng thẳng", en: "Stress score" },
        value: { vi: "77,04/100", en: "77.04/100" },
        note: {
          vi: "ngày 06/08/2026, trạng thái căng thẳng trên mức bình thường",
          en: "6 Aug 2026, elevated stress state",
        },
      },
      {
        label: { vi: "So với lịch sử", en: "Compared with history" },
        value: { vi: "86,22%", en: "86.22%" },
        note: {
          vi: "so với lịch sử có sẵn",
          en: "relative to available history",
        },
      },
      {
        label: { vi: "Dữ liệu dùng để kiểm tra", en: "Test data" },
        value: { vi: "1.323 ngày", en: "1,323 days" },
        note: {
          vi: "20 lần chia theo thời gian, có khoảng cách chống nhìn trước",
          en: "20 time-based tests, with gaps to prevent looking ahead",
        },
      },
    ],
    method: {
      vi: [
        "Trước tiên, mô hình loại bớt ảnh hưởng chung của toàn thị trường để tập trung vào mối liên hệ riêng giữa từng cặp cổ phiếu.",
        "Dữ liệu 60 phiên gần nhất được dùng để tạo một bản đồ: cổ phiếu là các điểm, mối liên hệ đủ mạnh là các đường nối.",
        "Từ bản đồ này, mô hình đo cổ phiếu nào có nhiều ảnh hưởng trong mạng, nhóm nào đang liên kết chặt và mức căng thẳng chung.",
        "Khi kiểm tra theo thời gian, mọi phép tính chỉ dùng dữ liệu có trước ngày đánh giá để tránh nhìn trước tương lai.",
      ],
      en: [
        "The model first removes some of the broad market effect so it can focus on the relationship between each pair of stocks.",
        "The latest 60 sessions are used to build a map: stocks are points and sufficiently strong relationships are connecting lines.",
        "The map is used to measure which stocks are highly connected, which groups move closely together and how concentrated the market is.",
        "Every time-based test uses only information available before the evaluation date.",
      ],
    },
    findings: {
      vi: [
        "Ngày 06/08/2026, VIC, VHM và GAS là ba cổ phiếu có mức liên kết cao nhất trong mạng. Liên kết cao không có nghĩa giá sẽ tăng.",
        "Trong thử nghiệm phân bổ, cách ưu tiên giảm biến động đạt mức biến động năm 15,63%, thấp hơn mức 19,72% của danh mục chia đều. Tuy nhiên, riêng kỹ thuật Graphical Lasso chưa cho thấy lợi ích rõ ràng: 15,65% so với 15,70% của cách ước lượng thông thường.",
        "Thử nghiệm dùng danh sách VN30 hiện tại cho cả dữ liệu quá khứ, nên có thể bỏ sót các cổ phiếu từng bị loại khỏi VN30. Kết quả chưa thể xem là một chiến lược có thể giao dịch thực tế.",
      ],
      en: [
        "VIC, VHM and GAS were the three most connected stocks in the network on 6 Aug 2026. Being highly connected does not mean their prices will rise.",
        "In the allocation test, the approach focused on reducing fluctuations recorded 15.63% annual volatility, compared with 19.72% for an equally weighted portfolio. The Graphical Lasso technique did not show a clear additional benefit: 15.65% against 15.70% for the ordinary estimator.",
        "The test applies today's VN30 list to past data, so it may omit stocks that previously left the index. The result should not be treated as a ready-to-trade strategy.",
      ],
    },
    charts: [
      {
        id: "dynamic-stress",
        title: {
          vi: "Mức liên kết và căng thẳng của VN30 gần đây",
          en: "Recent connection and stress level in VN30",
        },
        note: {
          vi: "Mỗi điểm là một phiên giao dịch. Điểm cao cho thấy các cổ phiếu đang liên kết chặt hơn hoặc khả năng đa dạng hóa đang giảm. Đây không phải xác suất thị trường đi xuống.",
          en: "Each point is one trading session. A high score means stocks are more tightly connected or diversification may be weaker. It is not the probability of a market decline.",
        },
        categories: [
          "22/07",
          "23/07",
          "24/07",
          "27/07",
          "28/07",
          "29/07",
          "30/07",
          "31/07",
          "03/08",
          "04/08",
          "05/08",
          "06/08",
        ],
        valueSuffix: "/100",
        minimum: 70,
        maximum: 92,
        series: [
          {
            name: { vi: "Điểm căng thẳng", en: "Stress score" },
            data: [
              86.71, 81.66, 84.68, 83.79, 80.31, 81.9, 84.36, 76.22, 79.0,
              82.09, 81.52, 77.04,
            ],
            type: "line",
            color: "#ad7519",
          },
        ],
      },
    ],
    visual: {
      src: "/research/dynamic-graph-network.png",
      alt: {
        vi: "Bản đồ mối liên hệ mới nhất giữa các cổ phiếu VN30",
        en: "Latest map of relationships among VN30 stocks",
      },
      caption: {
        vi: "Mỗi vòng tròn là một cổ phiếu, mỗi đường nối thể hiện hai cổ phiếu có mối liên hệ đáng chú ý sau khi đã loại bớt ảnh hưởng chung của thị trường. Mối liên hệ không có nghĩa một cổ phiếu gây ra biến động ở cổ phiếu khác.",
        en: "Each circle is a stock. Each line marks a notable relationship after reducing the broad market effect. A connection does not mean that one stock causes another to move.",
      },
    },
    provenance: {
      vi: "Toàn bộ số liệu trên trang này đến từ một lần chạy đầy đủ trên dữ liệu đến ngày 06/08/2026: bản đồ liên kết, bảng xếp hạng và điểm căng thẳng. Số liệu được trích trực tiếp từ tệp kết quả, không nhập lại bằng tay.",
      en: "Every figure on this page comes from a single full run on data through 6 Aug 2026: the relationship map, the ranking table and the stress score. All figures are read directly from the result files, not re-entered by hand.",
    },
  },
  msdp: {
    slug: "msdp",
    // The forecast below is re-run daily. The validation figures are not:
    // they come from the recorded training run and only change when the model
    // is retrained, which the provenance note states outright.
    artifactDate: "2026-08-06",
    verdict: {
      eyebrow: { vi: "Kết quả chính", en: "Main result" },
      title: {
        vi: "Hữu ích để ước lượng phạm vi và rủi ro, nhưng chưa dự báo một con số tốt hơn các cách đơn giản.",
        en: "Useful for estimating a range and risk, but not yet better at predicting one number.",
      },
      body: {
        vi: "Causa cho kết quả tốt hơn ở một số phép đo, nhưng khi kiểm tra độ ổn định, chưa thể khẳng định sai số dự báo trung bình tốt hơn các cách đơn giản. Bằng chứng rõ hơn chỉ xuất hiện ở một vài trường hợp: dự báo 5 phiên, phạm vi kết quả 20 phiên và khả năng tăng trong 5 phiên.",
        en: "Causa performs better on several measures, but stability checks do not yet show that its average forecast error is clearly lower than simple methods. Stronger evidence appears only in a few cases: the 5-session forecast, the 20-session outcome range and the chance of a rise over 5 sessions.",
      },
    },
    metrics: [
      {
        label: { vi: "Dữ liệu kiểm tra cuối", en: "Final test data" },
        value: { vi: "830 mốc", en: "830 test points" },
        note: {
          vi: "không dùng để điều chỉnh mô hình",
          en: "not used to adjust the model",
        },
      },
      {
        label: { vi: "Số phương án đã thử", en: "Settings tried" },
        value: { vi: "50 lần", en: "50 trials" },
        note: {
          vi: "4 lần chia dữ liệu theo thời gian",
          en: "4 time-based data splits",
        },
      },
      {
        label: { vi: "Độ ổn định", en: "Stability" },
        value: { vi: "3 lần chạy", en: "3 runs" },
        note: {
          vi: "1.000 lần lấy mẫu lại để kiểm tra",
          en: "1,000 repeated samples for stability checks",
        },
      },
      {
        label: {
          vi: "Kết quả nằm trong phạm vi dự báo",
          en: "Actual outcomes inside the forecast range",
        },
        value: { vi: "88,0–90,2%", en: "88.0–90.2%" },
        note: {
          vi: "so với mục tiêu 90%",
          en: "compared with the 90% target",
        },
      },
    ],
    method: {
      vi: [
        "Bốn thành phần cùng quan sát thị trường ở góc nhìn ngắn hạn, trung hạn, dài hạn và mức biến động.",
        "Với mỗi thời hạn 5, 20 hoặc 60 phiên, mô hình tự chọn mức đóng góp của từng thành phần.",
        "Kết quả gồm khả năng tăng, phạm vi lợi suất có thể xảy ra, mức giảm từ đỉnh và mức biến động dự kiến.",
        "Một bước hiệu chỉnh thống kê giúp phạm vi dự báo sát thực tế hơn. Bộ dữ liệu kiểm tra cuối không được dùng để điều chỉnh mô hình.",
      ],
      en: [
        "Four components examine the market from short-term, medium-term, long-term and volatility perspectives.",
        "For each period of 5, 20 or 60 sessions, the model decides how much each component should contribute.",
        "Results include the chance of a rise, a possible return range, the decline from a previous peak and expected volatility.",
        "A statistical adjustment makes the forecast range more realistic. The final test data is kept separate from model adjustments.",
      ],
    },
    findings: {
      vi: [
        "Cách mô hình tự chia trọng số chỉ tốt hơn nhẹ so với việc chia đều cho bốn thành phần.",
        "Phạm vi dự báo rộng lên nhanh khi nhìn xa hơn. Điều này thể hiện mức độ không chắc chắn, không phải xác suất mô hình dự báo đúng.",
        "Quá trình huấn luyện lại và kiểm tra đầy đủ trước khi vận hành chưa hoàn tất. Kết quả hiện vẫn ở giai đoạn nghiên cứu.",
      ],
      en: [
        "The model's automatic weighting was only slightly better than giving equal weight to all four components.",
        "The forecast range widens quickly over longer periods. This shows uncertainty; it is not the probability that the forecast is correct.",
        "The full retraining and final operational checks are not complete. The current result remains at the research stage.",
      ],
    },
    charts: [
      {
        id: "msdp-coverage",
        title: {
          vi: "Hiệu chỉnh có giúp phạm vi dự báo đáng tin hơn không?",
          en: "Did adjustment make the forecast range more reliable?",
        },
        note: {
          vi: "Sau hiệu chỉnh, tỷ lệ kết quả thực tế nằm trong phạm vi dự báo gần mục tiêu 90% hơn. Đổi lại, phạm vi dự báo rộng hơn.",
          en: "After adjustment, the share of actual outcomes inside the forecast range moved closer to the 90% target. The trade-off is a wider range.",
        },
        categories: ["5", "20", "60"],
        valueSuffix: "%",
        minimum: 80,
        maximum: 95,
        baseline: 90,
        series: [
          {
            name: { vi: "Trước hiệu chỉnh", en: "Before adjustment" },
            data: [87.83, 86.75, 86.14],
            type: "bar",
            color: "#94a3b8",
          },
          {
            name: { vi: "Sau hiệu chỉnh", en: "After adjustment" },
            data: [90.24, 88.55, 87.95],
            type: "bar",
            color: "#3a72c4",
          },
        ],
      },
      {
        id: "msdp-latest",
        title: {
          vi: "VN-Index có thể tăng hoặc giảm bao nhiêu từ ngày 06/08/2026?",
          en: "How far could VN-Index rise or fall from 6 Aug 2026?",
        },
        note: {
          vi: "Đường giữa là kết quả ở trung tâm; hai đường ngoài là phạm vi sau hiệu chỉnh. Ba điểm chỉ thể hiện kết quả ở từng thời hạn, không phải đường đi tương lai của VN-Index.",
          en: "The middle line is the central result and the outer lines show the adjusted range. These are results for separate time periods, not a predicted future path for VN-Index.",
        },
        categories: ["5", "20", "60"],
        valueSuffix: "%",
        minimum: -30,
        maximum: 20,
        baseline: 0,
        // Read from the 2026-08-06 inference: the outer lines are
        // `calibrated_interval`, matching the "sau hiệu chỉnh" wording in the
        // note, and the centre is the median of `return_quantiles`.
        series: [
          {
            name: { vi: "Mức thấp của phạm vi", en: "Lower end of range" },
            data: [-7.41, -15.15, -27.23],
            type: "line",
            color: "#c0433a",
          },
          {
            // The centre line is the forecast itself, so it takes the brand
            // colour. The two edges previously sat one shade apart on the same
            // green and could not be told from each other in the legend.
            name: { vi: "Kết quả ở trung tâm", en: "Central result" },
            data: [-1.78, -4.22, -7.5],
            type: "line",
            color: "#3a72c4",
          },
          {
            name: { vi: "Mức cao của phạm vi", en: "Upper end of range" },
            data: [3.99, 7.4, 15.15],
            type: "line",
            color: "#158f66",
          },
        ],
      },
    ],
    provenance: {
      vi: "Phần dự báo được tính lại trên dữ liệu đến ngày 06/08/2026. Các số liệu kiểm tra phía trên đến từ lần huấn luyện và kiểm định gần nhất; chúng chỉ thay đổi khi mô hình được huấn luyện lại, nên không cập nhật theo ngày. Mọi số liệu được trích trực tiếp từ tệp kết quả, không nhập lại bằng tay.",
      en: "The forecast is recomputed on data through 6 Aug 2026. The test results above come from the most recent training and validation run; they change only when the model is retrained and so are not updated daily. All figures are read directly from the result files, not re-entered by hand.",
    },
  },
};

export const getModelResearch = (slug: string) => MODEL_RESEARCH[slug];
