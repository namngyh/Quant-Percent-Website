# Báo cáo thực nghiệm RAEMF-MC

## Tóm tắt
Báo cáo này ghi lại một lần chạy laptop mode trên dữ liệu `data.csv`. Kết quả là ngoài mẫu theo thứ tự thời gian và không dùng tập test để lựa chọn tham số.

## Mô hình tốt nhất theo Brier score
| horizon | model | brier | macro_f1 | balanced_accuracy |
| --- | --- | --- | --- | --- |
| 20 | XGBoost | 0.7283 | 0.3332 | 0.3372 |
| 40 | RAEMF-MC | 0.7246 | 0.2591 | 0.2733 |
| 60 | Random Forest | 0.7397 | 0.2301 | 0.2289 |

## Metric chính
| model | horizon | macro_f1 | balanced_accuracy | brier | log_loss | recall_bear | recall_stress |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MACD | 20 | 0.2245 | 0.2340 | 1.2270 | 2.3501 | 0.2000 | 0.0547 |
| RAEMF-MC | 20 | 0.3026 | 0.3223 | 0.7423 | 1.3707 | 0.2593 | 0.3383 |
| XGBoost | 20 | 0.3332 | 0.3372 | 0.7283 | 1.3444 | 0.1185 | 0.3383 |
| Random Forest | 20 | 0.3546 | 0.3652 | 0.7320 | 1.3516 | 0.0963 | 0.4129 |
| MACD | 40 | 0.1917 | 0.2014 | 1.2779 | 2.4436 | 0.1474 | 0.0311 |
| RAEMF-MC | 40 | 0.2591 | 0.2733 | 0.7246 | 1.3255 | 0.0526 | 0.4222 |
| XGBoost | 40 | 0.2683 | 0.2687 | 0.7275 | 1.3379 | 0.0316 | 0.2756 |
| Random Forest | 40 | 0.2822 | 0.2884 | 0.7320 | 1.3506 | 0.1053 | 0.0978 |
| MACD | 60 | 0.2096 | 0.2392 | 1.2348 | 2.3644 | 0.2571 | 0.0130 |
| RAEMF-MC | 60 | 0.2075 | 0.2333 | 0.7864 | 1.4336 | 0.1714 | 0.3810 |
| XGBoost | 60 | 0.2393 | 0.2507 | 0.7417 | 1.3584 | 0.0286 | 0.3810 |
| Random Forest | 60 | 0.2301 | 0.2289 | 0.7397 | 1.3595 | 0.0143 | 0.1861 |

## Bootstrap chênh lệch metric
Chênh lệch âm của Brier hoặc log loss nghĩa là RAEMF-MC thấp hơn benchmark trên metric mất mát đó.
| horizon | benchmark | metric | mean_diff | ci_low | ci_high |
| --- | --- | --- | --- | --- | --- |
| 20 | XGBoost | brier | 0.0140 | -0.0054 | 0.0263 |
| 20 | XGBoost | log_loss | 0.0263 | -0.0088 | 0.0470 |
| 20 | Random Forest | brier | 0.0102 | -0.0086 | 0.0266 |
| 20 | Random Forest | log_loss | 0.0191 | -0.0174 | 0.0512 |
| 20 | MACD | brier | -0.4848 | -0.5797 | -0.3947 |
| 20 | MACD | log_loss | -0.9795 | -1.1548 | -0.8121 |
| 40 | XGBoost | brier | -0.0029 | -0.0255 | 0.0154 |
| 40 | XGBoost | log_loss | -0.0123 | -0.0518 | 0.0235 |
| 40 | Random Forest | brier | -0.0074 | -0.0353 | 0.0148 |
| 40 | Random Forest | log_loss | -0.0250 | -0.0759 | 0.0249 |
| 40 | MACD | brier | -0.5533 | -0.6408 | -0.4527 |
| 40 | MACD | log_loss | -1.1181 | -1.2724 | -0.9257 |
| 60 | XGBoost | brier | 0.0448 | 0.0133 | 0.0697 |
| 60 | XGBoost | log_loss | 0.0752 | 0.0183 | 0.1146 |
| 60 | Random Forest | brier | 0.0468 | 0.0077 | 0.0774 |
| 60 | Random Forest | log_loss | 0.0741 | -0.0012 | 0.1340 |
| 60 | MACD | brier | -0.4483 | -0.5598 | -0.3510 |
| 60 | MACD | log_loss | -0.9307 | -1.1378 | -0.7574 |

## Dự báo mới nhất
```json
{
  "as_of_date": "2026-07-01",
  "last_close": 1865.37,
  "horizons": {
    "20": {
      "probabilities": {
        "Bull": 0.1418633071332986,
        "Sideway": 0.25935881959416385,
        "Bear": 0.3605209328507657,
        "Stress": 0.2382569404217719
      },
      "predicted_class": "Bear",
      "confidence": "Uncertain",
      "market_filter": "Uncertain"
    },
    "40": {
      "probabilities": {
        "Bull": 0.302917708294685,
        "Sideway": 0.18539009350995633,
        "Bear": 0.25806874995062756,
        "Stress": 0.2536234482447311
      },
      "predicted_class": "Bull",
      "confidence": "Uncertain",
      "market_filter": "Uncertain"
    },
    "60": {
      "probabilities": {
        "Bull": 0.30904599463325,
        "Sideway": 0.301103974930659,
        "Bear": 0.076360610244674,
        "Stress": 0.313489420191417
      },
      "predicted_class": "Stress",
      "confidence": "Low",
      "market_filter": "Uncertain"
    }
  },
  "note": "Không phải lời khuyên đầu tư."
}
```

## Diễn giải trung lập
Nếu khoảng tin cậy bootstrap của chênh lệch metric còn chứa 0, báo cáo không kết luận RAEMF-MC vượt trội ổn định. Recall của Bear và Stress được trình bày riêng vì mất cân bằng lớp có thể làm accuracy đánh lừa.

## Giới hạn
Dữ liệu chỉ gồm lịch sử VN-Index trong `data.csv`, không có biến vĩ mô, market breadth hoặc dữ liệu thành phần chỉ số. Backtest là minh họa exposure sau một ngày trễ, không phải khuyến nghị đầu tư.
