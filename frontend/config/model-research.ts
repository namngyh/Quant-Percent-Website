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
}

export interface ResearchChart {
  id: string;
  title: Localized;
  note: Localized;
  categories: string[];
  series: ResearchChartSeries[];
  valueSuffix?: string;
  minimum?: number;
  maximum?: number;
  baseline?: number;
}

export interface ModelResearchProfile {
  slug: string;
  repoUrl: string;
  sourceCommit: string;
  artifactDate: string;
  runId?: string;
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
    repoUrl:
      "https://github.com/namngyh/RAEMF-MC-Regime-Aware-Explainable-Multi-Horizon-Forecasting-with-Monte-Carlo-",
    sourceCommit: "c9c3f9082dd09cd3a23d4e62a5b80992d483fcf0",
    artifactDate: "2026-07-25",
    verdict: {
      eyebrow: { vi: "Kết quả chính", en: "Main result" },
      title: {
        vi: "Mô hình ước lượng phạm vi kết quả tốt hơn, nhưng vẫn đánh giá rủi ro thấp hơn thực tế.",
        en: "The model estimates the range of outcomes better, but still understates real-world risk.",
      },
      body: {
        vi: "Phiên bản M2 dự báo phạm vi kết quả tốt hơn phiên bản chỉ đưa ra một giá trị. Tuy nhiên, phạm vi này vẫn còn hẹp: kết quả thực tế rơi ra ngoài nhiều hơn mức mong đợi và rủi ro thua lỗ lớn bị đánh giá thấp. Vì vậy, Quant Percent chỉ công bố M2 như một kết quả nghiên cứu, chưa dùng làm phiên bản mặc định.",
        en: "M2 estimates possible outcomes better than the version that gives a single value. Its forecast range is still too narrow: actual outcomes fall outside more often than expected and large losses are understated. Quant Percent therefore presents M2 as research, not as the default model.",
      },
    },
    metrics: [
      {
        label: { vi: "Dữ liệu", en: "Dataset" },
        value: { vi: "6.306 phiên", en: "6,306 sessions" },
        note: {
          vi: "VN-Index, 28/07/2000–13/07/2026",
          en: "VN-Index, 28 Jul 2000–13 Jul 2026",
        },
      },
      {
        label: { vi: "Dữ liệu dùng để kiểm tra", en: "Data used for testing" },
        value: { vi: "1.874–1.886", en: "1,874–1,886" },
        note: {
          vi: "mốc dự báo cho mỗi thời hạn",
          en: "test points for each forecast period",
        },
      },
      {
        label: { vi: "Tỷ lệ dự báo đúng tăng/giảm", en: "Correct up-or-down forecasts" },
        value: { vi: "54,6–64,6%", en: "54.6–64.6%" },
        note: {
          vi: "tăng dần từ 20 đến 60 phiên",
          en: "from 20 to 60 sessions",
        },
      },
      {
        label: { vi: "Kết quả nằm trong phạm vi 95%", en: "Actual outcomes inside the 95% range" },
        value: { vi: "86,2–87,1%", en: "86.2–87.1%" },
        note: {
          vi: "thấp hơn mục tiêu 95%",
          en: "below the nominal 95% target",
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
        "Dự báo tạo ngày 13/07/2026 chưa đến đủ thời hạn để so sánh với thực tế, nên không được dùng để chứng minh hiệu quả.",
      ],
      en: [
        "All nine runs across the 20, 40 and 60-session periods completed reliably.",
        "The model still struggles to identify falling markets. Market-state probabilities are not trading signals.",
        "Forecasts issued on 13 Jul 2026 have not reached their full periods and are not used as performance evidence.",
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
            data: [79.11, 80.73, 81.66],
            type: "bar",
            color: "#087f78",
          },
          {
            name: { vi: "Phạm vi dự báo 95%", en: "95% interval" },
            data: [86.23, 87.07, 87.07],
            type: "bar",
            color: "#d97706",
          },
        ],
      },
      {
        id: "raemf-regimes",
        title: {
          vi: "Mô hình nhìn nhận thị trường ngày 13/07/2026 ra sao?",
          en: "How did the model view the market on 13 Jul 2026?",
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
            data: [21.96, 23.27, 23.66],
            type: "bar",
            color: "#16805d",
            stack: "regime",
          },
          {
            name: { vi: "Đi ngang", en: "Sideway" },
            data: [22.65, 19.08, 22.28],
            type: "bar",
            color: "#9caaa6",
            stack: "regime",
          },
          {
            name: { vi: "Giảm", en: "Bear" },
            data: [23.9, 22.49, 18.22],
            type: "bar",
            color: "#d97706",
            stack: "regime",
          },
          {
            name: { vi: "Căng thẳng", en: "Stress" },
            data: [31.49, 35.16, 35.85],
            type: "bar",
            color: "#c64032",
            stack: "regime",
          },
        ],
      },
    ],
    provenance: {
      vi: "Số liệu lấy từ báo cáo và các tệp kết quả trong repo tại phiên bản mã nguồn nêu trên. Website chưa tự chạy lại toàn bộ quá trình xây dựng mô hình.",
      en: "Figures come from the report and result files in the repository at the cited code version. The website has not independently rerun the full model-building process.",
    },
  },
  "rarf-fhe": {
    slug: "rarf-fhe",
    repoUrl:
      "https://github.com/namngyh/RARF-FHE-Regime-Aware-Random-Forest-Forecasting-Hybrid-Engine",
    sourceCommit: "6215511c84f02b356135d959883459c8e8f565fe",
    artifactDate: "2026-07-15",
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
        value: { vi: "6.306 phiên", en: "6,306 sessions" },
        note: {
          vi: "VN-Index, 28/07/2000–13/07/2026",
          en: "VN-Index, 28 Jul 2000–13 Jul 2026",
        },
      },
      {
        label: { vi: "Tiêu chí đã đạt", en: "Checks passed" },
        value: { vi: "7/9", en: "7/9" },
        note: {
          vi: "tiêu chí kiểm tra; bản A0 vẫn được giữ",
          en: "7 of 9 checks passed; the safer version was kept",
        },
      },
      {
        label: {
          vi: "Kết quả nằm trong phạm vi 95%",
          en: "Actual outcomes inside the 95% range",
        },
        value: { vi: "95,26%", en: "95.26%" },
        note: {
          vi: "sau hiệu chỉnh, từ mức 86,29%",
          en: "after adjustment, up from 86.29%",
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
        "Mô phỏng ngày 13/07/2026 ước tính khả năng VN-Index giảm hơn 5% từ đỉnh trong 20 phiên là 35,03%. Đây là xác suất mô phỏng, không phải điều chắc chắn xảy ra.",
        "Kết quả dựa trên giả định các biến động từng xảy ra trong quá khứ vẫn còn hữu ích cho tương lai. Độ chính xác có thể giảm khi thị trường thay đổi mạnh.",
      ],
      en: [
        "Forecast error increases over longer periods. The chart shows the simple method selected by the system, not the Random Forest on its own.",
        "The 13 Jul 2026 simulation estimated a 35.03% chance that VN-Index would fall more than 5% from a peak within 20 sessions. This is a simulated probability, not a certainty.",
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
            data: [1.23, 2.82, 3.99, 5.73, 8.17, 9.84],
            type: "line",
            color: "#087f78",
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
          vi: "Mỗi cột cho biết khả năng VN-Index giảm quá một ngưỡng nhất định so với đỉnh, trong 5, 10 hoặc 20 phiên kể từ ngày 13/07/2026.",
          en: "Each bar shows the chance that VN-Index falls beyond a stated level from a previous peak within 5, 10 or 20 sessions from 13 Jul 2026.",
        },
        categories: ["3%", "5%", "7%", "10%", "15%"],
        valueSuffix: "%",
        minimum: 0,
        series: [
          {
            name: { vi: "Trong 5 phiên", en: "Within 5 sessions" },
            data: [17.72, 4.2, 0.79, 0.02, 0],
            type: "bar",
            color: "#9caaa6",
          },
          {
            name: { vi: "Trong 10 phiên", en: "Within 10 sessions" },
            data: [39.22, 14.2, 4.32, 0.5, 0.01],
            type: "bar",
            color: "#d97706",
          },
          {
            name: { vi: "Trong 20 phiên", en: "Within 20 sessions" },
            data: [67.81, 35.03, 15.87, 3.78, 0.19],
            type: "bar",
            color: "#c64032",
          },
        ],
      },
    ],
    provenance: {
      vi: "Số liệu lấy từ báo cáo và các bảng kết quả trong repo tại phiên bản mã nguồn nêu trên. Website chưa tự chạy lại toàn bộ quá trình xây dựng mô hình.",
      en: "Figures come from the reports and result tables in the repository at the cited code version. The website has not independently rerun the full model-building process.",
    },
  },
  "dynamic-graph": {
    slug: "dynamic-graph",
    repoUrl: "https://github.com/namngyh/Dynamic-Graph",
    sourceCommit: "bde76b714b05fed4b3ff1becdf420ad0e390844d",
    artifactDate: "2026-07-29",
    verdict: {
      eyebrow: { vi: "Kết quả chính", en: "Main result" },
      title: {
        vi: "Hữu ích để xem các cổ phiếu VN30 đang liên kết với nhau ra sao, nhưng không dùng để dự báo giá.",
        en: "Useful for seeing how VN30 stocks move together, but not for predicting prices.",
      },
      body: {
        vi: "DynamicGraph cho biết cổ phiếu nào thường biến động cùng nhau và mức độ thị trường đang tập trung vào một số nhóm cổ phiếu. Khi được thử trên dữ liệu mới, phần dự báo căng thẳng không tốt hơn cách dùng tần suất lịch sử. Vì vậy, công cụ này chỉ dùng để quan sát cấu trúc thị trường, không đưa ra dự báo giá hay tín hiệu mua bán.",
        en: "DynamicGraph shows which stocks often move together and whether the market is becoming concentrated in a few groups. On newer test data, its stress forecast was not better than a simple method based on historical frequency. The website therefore uses it only to observe market structure, not to predict prices or give buy and sell signals.",
      },
    },
    metrics: [
      {
        label: { vi: "Phạm vi", en: "Coverage" },
        value: { vi: "30 cổ phiếu", en: "30 stocks" },
        note: {
          vi: "danh sách VN30 hiện tại, cộng chỉ số VN30",
          en: "current VN30 constituents plus the VN30 index",
        },
      },
      {
        label: { vi: "Điểm căng thẳng", en: "Stress score" },
        value: { vi: "84,62/100", en: "84.62/100" },
        note: {
          vi: "ngày 24/07/2026, trạng thái căng thẳng cao",
          en: "24 Jul 2026, high-stress state",
        },
      },
      {
        label: { vi: "So với lịch sử", en: "Compared with history" },
        value: { vi: "92,82%", en: "92.82%" },
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
        "Ngày 24/07/2026, VIC, FPT và VHM là ba cổ phiếu có mức liên kết cao nhất trong mạng. Liên kết cao không có nghĩa giá sẽ tăng.",
        "Trong thử nghiệm phân bổ, cách ưu tiên giảm biến động đạt mức biến động năm 16,44%, thấp hơn mức 20,34% của danh mục chia đều. Tuy nhiên, riêng kỹ thuật Graphical Lasso chưa cho thấy lợi ích rõ ràng.",
        "Thử nghiệm dùng danh sách VN30 hiện tại cho cả dữ liệu quá khứ, nên có thể bỏ sót các cổ phiếu từng bị loại khỏi VN30. Kết quả chưa thể xem là một chiến lược có thể giao dịch thực tế.",
      ],
      en: [
        "VIC, FPT and VHM were the three most connected stocks in the network on 24 Jul 2026. Being highly connected does not mean their prices will rise.",
        "In the allocation test, the approach focused on reducing fluctuations recorded 16.44% annual volatility, compared with 20.34% for an equally weighted portfolio. The Graphical Lasso technique did not show a clear additional benefit.",
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
          vi: "Điểm cao cho thấy các cổ phiếu đang liên kết chặt hơn hoặc khả năng đa dạng hóa đang giảm. Đây không phải xác suất thị trường đi xuống.",
          en: "A high score means stocks are more tightly connected or diversification may be weaker. It is not the probability of a market decline.",
        },
        categories: [
          "09/07",
          "10/07",
          "13/07",
          "14/07",
          "15/07",
          "16/07",
          "17/07",
          "20/07",
          "21/07",
          "22/07",
          "23/07",
          "24/07",
        ],
        valueSuffix: "/100",
        minimum: 70,
        maximum: 100,
        series: [
          {
            name: { vi: "Điểm căng thẳng", en: "Stress score" },
            data: [
              82.47, 80.37, 83.83, 81.72, 86.08, 83.77, 83.5, 86.24, 83.35,
              85.35, 80.71, 84.62,
            ],
            type: "line",
            color: "#d97706",
          },
        ],
      },
      {
        id: "dynamic-skill",
        title: {
          vi: "Phần dự báo có tốt hơn cách đơn giản không?",
          en: "Did the forecast beat a simple method?",
        },
        note: {
          vi: "Mức trên 0% mới tốt hơn cách dự báo dựa trên tần suất lịch sử. Tất cả thời hạn đều dưới 0%, nên phần này chưa đủ tốt để sử dụng như một sản phẩm dự báo.",
          en: "Only values above 0% would beat a forecast based on historical frequency. Every period is below 0%, so this part is not presented as a forecasting product.",
        },
        categories: ["5", "10", "20", "40"],
        valueSuffix: "%",
        minimum: -75,
        maximum: 5,
        baseline: 0,
        series: [
          {
            name: {
              vi: "Mức cải thiện so với cách đơn giản",
              en: "Improvement over the simple method",
            },
            data: [-12.16, -54.76, -61.82, -66.83],
            type: "bar",
            color: "#c64032",
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
      vi: "Số liệu lấy từ báo cáo và các tệp kết quả trong repo tại phiên bản mã nguồn nêu trên. Website chưa tự chạy lại toàn bộ quá trình xây dựng mô hình.",
      en: "Figures come from the reports and result files in the repository at the cited code version. The website has not independently rerun the full model-building process.",
    },
  },
  msdp: {
    slug: "msdp",
    repoUrl:
      "https://github.com/namngyh/MSDP-Multi-Scale-Distributional-Predictor-for-VN-Index",
    sourceCommit: "8c359449bb018b0ab13255c0f3e0c3a761b814a0",
    artifactDate: "2026-07-22",
    runId: "20260722_154609_gpu",
    verdict: {
      eyebrow: { vi: "Kết quả chính", en: "Main result" },
      title: {
        vi: "Hữu ích để ước lượng phạm vi và rủi ro, nhưng chưa dự báo một con số tốt hơn các cách đơn giản.",
        en: "Useful for estimating a range and risk, but not yet better at predicting one number.",
      },
      body: {
        vi: "MSDP cho kết quả tốt hơn ở một số phép đo, nhưng khi kiểm tra độ ổn định, chưa thể khẳng định sai số dự báo trung bình tốt hơn các cách đơn giản. Bằng chứng rõ hơn chỉ xuất hiện ở một vài trường hợp: dự báo 5 phiên, phạm vi kết quả 20 phiên và khả năng tăng trong 5 phiên.",
        en: "MSDP performs better on several measures, but stability checks do not yet show that its average forecast error is clearly lower than simple methods. Stronger evidence appears only in a few cases: the 5-session forecast, the 20-session outcome range and the chance of a rise over 5 sessions.",
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
            color: "#9caaa6",
          },
          {
            name: { vi: "Sau hiệu chỉnh", en: "After adjustment" },
            data: [90.24, 88.55, 87.95],
            type: "bar",
            color: "#087f78",
          },
        ],
      },
      {
        id: "msdp-latest",
        title: {
          vi: "VN-Index có thể tăng hoặc giảm bao nhiêu từ ngày 13/07/2026?",
          en: "How far could VN-Index rise or fall from 13 Jul 2026?",
        },
        note: {
          vi: "Đường giữa là kết quả ở trung tâm; hai đường ngoài là phạm vi sau hiệu chỉnh. Ba điểm chỉ thể hiện kết quả ở từng thời hạn, không phải đường đi tương lai của VN-Index.",
          en: "The middle line is the central result and the outer lines show the adjusted range. These are results for separate time periods, not a predicted future path for VN-Index.",
        },
        categories: ["5", "20", "60"],
        valueSuffix: "%",
        minimum: -25,
        maximum: 25,
        baseline: 0,
        series: [
          {
            name: { vi: "Mức thấp của phạm vi", en: "Lower end of range" },
            data: [-5.93, -11.88, -21.19],
            type: "line",
            color: "#c64032",
          },
          {
            name: { vi: "Kết quả ở trung tâm", en: "Central result" },
            data: [-0.5, -0.96, -1.56],
            type: "line",
            color: "#0d1110",
          },
          {
            name: { vi: "Mức cao của phạm vi", en: "Upper end of range" },
            data: [4.03, 9.68, 18.74],
            type: "line",
            color: "#16805d",
          },
        ],
      },
    ],
    provenance: {
      vi: "Số liệu lấy từ lần chạy GPU ngày 22/07/2026 và các tệp kết quả trong repo tại phiên bản mã nguồn nêu trên. Báo cáo thử nhanh cũ không được dùng. Website chưa tự chạy lại toàn bộ quá trình xây dựng mô hình.",
      en: "Figures come from the completed GPU test and result files in the repository at the cited code version. An older quick test was excluded. The website has not independently rerun the full model-building process.",
    },
  },
};

export const getModelResearch = (slug: string) => MODEL_RESEARCH[slug];
