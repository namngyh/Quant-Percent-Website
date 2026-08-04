# DynamicGraph - Ablation Study

_Generated 2026-07-26T03:32:26+07:00_

Every variant uses the same folds, model, calibration and threshold procedure. Only the feature space changes, so differences are attributable to the removed feature family.

## 1. Variant results

| variant                   |   n_features_candidate |   n_features |    n |   base_rate |   brier |   brier_skill_score |   brier_vs_market_only |   auroc |   auprc |   auprc_lift_over_base |     mcc |   recall_stress |   precision_stress |   false_alarms_per_year |
|:--------------------------|-----------------------:|-------------:|-----:|------------:|--------:|--------------------:|-----------------------:|--------:|--------:|-----------------------:|--------:|----------------:|-------------------:|------------------------:|
| residual_return_graph     |                    330 |           60 | 1323 |      0.1338 |  0.1417 |             -0.2224 |                -0.0468 |  0.5153 |  0.1551 |                 1.1592 | -0.0033 |          0.1751 |             0.1314 |                 39.0476 |
| graph_only                |                    664 |           60 | 1323 |      0.1338 |  0.1563 |             -0.3491 |                -0.0321 |  0.4166 |  0.1188 |                 0.888  | -0.0794 |          0.1808 |             0.0894 |                 62.0952 |
| multi_scale               |                    664 |           60 | 1323 |      0.1338 |  0.1563 |             -0.3491 |                -0.0321 |  0.4166 |  0.1188 |                 0.888  | -0.0794 |          0.1808 |             0.0894 |                 62.0952 |
| single_scale_120          |                    132 |           60 | 1323 |      0.1338 |  0.1647 |             -0.4214 |                -0.0237 |  0.4801 |  0.1266 |                 0.9463 | -0.0942 |          0.1582 |             0.0802 |                 61.1429 |
| correlation_graph         |                    132 |           60 | 1323 |      0.1338 |  0.1672 |             -0.4428 |                -0.0212 |  0.3891 |  0.1065 |                 0.7963 | -0.1126 |          0.1299 |             0.0682 |                 59.8095 |
| partial_correlation_graph |                    528 |           60 | 1323 |      0.1338 |  0.1781 |             -0.5366 |                -0.0103 |  0.3872 |  0.106  |                 0.7923 | -0.1344 |          0.1977 |             0.0731 |                 84.5714 |
| raw_return_graph          |                    330 |           60 | 1323 |      0.1338 |  0.1785 |             -0.5403 |                -0.0099 |  0.3158 |  0.0935 |                 0.6992 | -0.1665 |          0.0678 |             0.036  |                 61.1429 |
| no_community_features     |                    550 |           60 | 1323 |      0.1338 |  0.1788 |             -0.5431 |                -0.0096 |  0.4501 |  0.1205 |                 0.9004 |  0.0214 |          0.3729 |             0.1438 |                 74.8571 |
| no_centrality_features    |                    610 |           60 | 1323 |      0.1338 |  0.1838 |             -0.5864 |                -0.0046 |  0.4261 |  0.1173 |                 0.8767 | -0.0636 |          0.1469 |             0.0922 |                 48.7619 |
| market_plus_graph         |                    700 |           60 | 1323 |      0.1338 |  0.1874 |             -0.617  |                -0.001  |  0.418  |  0.113  |                 0.8446 | -0.0384 |          0.3616 |             0.1181 |                 91.0476 |
| market_only               |                     36 |           36 | 1323 |      0.1338 |  0.1884 |             -0.6258 |                 0      |  0.4032 |  0.1109 |                 0.8286 | -0.0387 |          0.1525 |             0.1067 |                 43.0476 |
| single_scale_60           |                    264 |           60 | 1323 |      0.1338 |  0.1912 |             -0.6499 |                 0.0028 |  0.4559 |  0.1162 |                 0.8688 | -0.1007 |          0.1921 |             0.0827 |                 71.8095 |
| no_spectral_features      |                    550 |           60 | 1323 |      0.1338 |  0.2015 |             -0.7387 |                 0.0131 |  0.4136 |  0.1135 |                 0.8486 | -0.1283 |          0.096  |             0.0548 |                 55.8095 |

`brier_vs_market_only` is negative when the variant beats the market-only baseline. `brier_skill_score` is measured against a constant forecast at the realised base rate; a negative value means the variant is worse than quoting the historical frequency, however it ranks against the other variants.

## 2. Marginal contribution of each feature family

`brier_degradation` > 0 means removing the family made out-of-sample predictions worse, i.e. the family carried information.

| removed_group   |   brier_without |   brier_with_all |   brier_degradation |   auprc_without |   auprc_with_all |   auprc_degradation |   n_features |
|:----------------|----------------:|-----------------:|--------------------:|----------------:|-----------------:|--------------------:|-------------:|
| spectral        |          0.2015 |           0.1874 |              0.0141 |          0.1135 |            0.113 |             -0.0005 |           60 |
| centrality      |          0.1838 |           0.1874 |             -0.0035 |          0.1173 |            0.113 |             -0.0043 |           60 |
| community       |          0.1788 |           0.1874 |             -0.0086 |          0.1205 |            0.113 |             -0.0075 |           60 |

## 3. Interpretation guardrails

- Ablation deltas are point estimates on a single horizon and model. They are indicative, not decisive; the paired bootstrap in the OOS report is the formal test.
- A variant that wins here but not in the paired comparison has not been shown to help.
