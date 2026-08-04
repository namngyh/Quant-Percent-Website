# DynamicGraph - Out-of-Sample Evaluation

_Generated 2026-07-26T03:32:26+07:00_

## 1. Protocol

- Split: **purged_walk_forward** (chronological; no shuffling anywhere in the codebase)
- Initial training: 756 trading days (expanding)
- Validation: 126 days | Test step: 63 days
- Purge: 40 days | Embargo: 5 days

Fitted on training rows only: imputation, scaling, feature selection, target quantile thresholds, graphical-lasso alpha and stress-score standardisation. Fitted on validation only: probability calibration and the decision threshold. Test rows are predicted once and never revisited.

- Feature selection: at most 60 column(s) per fold, chosen on that fold's training block by coverage, univariate |Spearman| against the label, and redundancy pruning at |Spearman| > 0.95.
- Hyperparameter tuning: **DISABLED**. Every model below uses fixed default hyperparameters. Run `scripts/compare_tuning.py` to check whether tuning changes the conclusion before treating any negative result as settled.

### Folds

|   fold_id |   n_train |   n_validation |   n_test | train_start   | train_end   | validation_start   | validation_end   | test_start   | test_end   |   purge_days |   embargo_days | expanding_window   |   max_horizon |
|----------:|----------:|---------------:|---------:|:--------------|:------------|:-------------------|:-----------------|:-------------|:-----------|-------------:|---------------:|:-------------------|--------------:|
|         0 |       756 |            126 |       63 | 2012-02-06    | 2015-02-13  | 2015-04-21         | 2015-10-20       | 2015-12-16   | 2016-03-21 |           40 |              5 | True               |            40 |
|         1 |       882 |            126 |       63 | 2012-02-06    | 2015-08-24  | 2015-10-21         | 2016-04-22       | 2016-06-22   | 2016-09-19 |           40 |              5 | True               |            40 |
|         2 |      1008 |            126 |       63 | 2012-02-06    | 2016-02-25  | 2016-04-25         | 2016-10-20       | 2016-12-16   | 2017-03-22 |           40 |              5 | True               |            40 |
|         3 |      1134 |            126 |       63 | 2012-02-06    | 2016-08-24  | 2016-10-21         | 2017-04-25       | 2017-06-23   | 2017-09-20 |           40 |              5 | True               |            40 |
|         4 |      1260 |            126 |       63 | 2012-02-06    | 2017-02-27  | 2017-04-26         | 2017-10-23       | 2017-12-19   | 2018-03-27 |           40 |              5 | True               |            40 |
|         5 |      1386 |            126 |       63 | 2012-02-06    | 2017-08-25  | 2017-10-24         | 2018-05-02       | 2018-06-28   | 2018-09-25 |           40 |              5 | True               |            40 |
|         6 |      1512 |            126 |       63 | 2012-02-06    | 2018-03-02  | 2018-05-03         | 2018-10-26       | 2018-12-24   | 2019-03-29 |           40 |              5 | True               |            40 |
|         7 |      1638 |            126 |       63 | 2012-02-06    | 2018-08-30  | 2018-10-29         | 2019-05-07       | 2019-07-03   | 2019-09-30 |           40 |              5 | True               |            40 |
|         8 |      1764 |            126 |       63 | 2012-02-06    | 2019-03-06  | 2019-05-08         | 2019-10-31       | 2019-12-27   | 2020-04-01 |           40 |              5 | True               |            40 |
|         9 |      1890 |            126 |       63 | 2012-02-06    | 2019-09-05  | 2019-11-01         | 2020-05-07       | 2020-07-03   | 2020-09-30 |           40 |              5 | True               |            40 |
|        10 |      2016 |            126 |       63 | 2012-02-06    | 2020-03-09  | 2020-05-08         | 2020-11-02       | 2020-12-29   | 2021-04-02 |           40 |              5 | True               |            40 |
|        11 |      2142 |            126 |       63 | 2012-02-06    | 2020-09-07  | 2020-11-03         | 2021-05-10       | 2021-07-06   | 2021-10-04 |           40 |              5 | True               |            40 |
|        12 |      2268 |            126 |       63 | 2012-02-06    | 2021-03-10  | 2021-05-11         | 2021-11-04       | 2021-12-31   | 2022-04-06 |           40 |              5 | True               |            40 |
|        13 |      2394 |            126 |       63 | 2012-02-06    | 2021-09-09  | 2021-11-05         | 2022-05-12       | 2022-07-08   | 2022-10-06 |           40 |              5 | True               |            40 |
|        14 |      2520 |            126 |       63 | 2012-02-06    | 2022-03-14  | 2022-05-13         | 2022-11-08       | 2023-01-05   | 2023-04-10 |           40 |              5 | True               |            40 |
|        15 |      2646 |            126 |       63 | 2012-02-06    | 2022-09-13  | 2022-11-09         | 2023-05-16       | 2023-07-12   | 2023-10-10 |           40 |              5 | True               |            40 |
|        16 |      2772 |            126 |       63 | 2012-02-06    | 2023-03-16  | 2023-05-17         | 2023-11-10       | 2024-01-09   | 2024-04-11 |           40 |              5 | True               |            40 |
|        17 |      2898 |            126 |       63 | 2012-02-06    | 2023-09-15  | 2023-11-13         | 2024-05-20       | 2024-07-16   | 2024-10-14 |           40 |              5 | True               |            40 |
|        18 |      3024 |            126 |       63 | 2012-02-06    | 2024-03-19  | 2024-05-21         | 2024-11-14       | 2025-01-13   | 2025-04-17 |           40 |              5 | True               |            40 |
|        19 |      3150 |            126 |       63 | 2012-02-06    | 2024-09-19  | 2024-11-15         | 2025-05-23       | 2025-07-21   | 2025-10-17 |           40 |              5 | True               |            40 |

## 2. Out-of-sample metrics

| target         |   horizon | feature_set   | model                  |    n |   base_rate |   brier |   brier_skill_score |   auroc |   auprc |     mcc |   recall_stress |   precision_stress |   false_alarms_per_year |   expected_calibration_error |   calibration_slope |
|:---------------|----------:|:--------------|:-----------------------|-----:|------------:|--------:|--------------------:|--------:|--------:|--------:|----------------:|-------------------:|------------------------:|-----------------------------:|--------------------:|
| stress_q10_5d  |         5 | graph         | naive_frequency        | 1323 |      0.1149 |  0.1052 |             -0.0348 |  0.5439 |  0.1281 | -0.016  |          0.4539 |             0.1095 |                106.857  |                       0.0784 |              0.2846 |
| stress_q10_5d  |         5 | market        | naive_frequency        | 1323 |      0.1149 |  0.1052 |             -0.0349 |  0.5439 |  0.1281 | -0.016  |          0.4539 |             0.1095 |                106.857  |                       0.0784 |              0.2839 |
| stress_q10_5d  |         5 | combined      | naive_frequency        | 1323 |      0.1149 |  0.1052 |             -0.0349 |  0.5439 |  0.1281 | -0.016  |          0.4539 |             0.1095 |                106.857  |                       0.0784 |              0.2839 |
| stress_q10_5d  |         5 | combined      | random_forest          | 1323 |      0.1149 |  0.1141 |             -0.1216 |  0.5884 |  0.1582 |  0.0875 |          0.5526 |             0.1469 |                 92.9524 |                       0.0903 |              0.2251 |
| stress_q10_5d  |         5 | graph         | hist_gradient_boosting | 1323 |      0.1149 |  0.1145 |             -0.1258 |  0.4968 |  0.1126 | -0.038  |          0.2895 |             0.098  |                 77.1429 |                       0.0961 |             -0.0317 |
| stress_q10_5d  |         5 | graph         | random_forest          | 1323 |      0.1149 |  0.1154 |             -0.1348 |  0.5796 |  0.1615 |  0.025  |          0.5132 |             0.1232 |                105.714  |                       0.0939 |              0.0081 |
| stress_q10_5d  |         5 | combined      | hist_gradient_boosting | 1323 |      0.1149 |  0.1228 |             -0.2079 |  0.393  |  0.0913 | -0.0911 |          0.1842 |             0.0705 |                 70.2857 |                       0.1148 |             -0.0768 |
| stress_q10_5d  |         5 | market        | random_forest          | 1323 |      0.1149 |  0.1313 |             -0.2913 |  0.6235 |  0.1436 |  0.1416 |          0.6908 |             0.1606 |                104.571  |                       0.1043 |              0.2693 |
| stress_q10_5d  |         5 | combined      | logistic_elasticnet    | 1323 |      0.1149 |  0.1379 |             -0.3565 |  0.5796 |  0.1663 |  0.0803 |          0.5263 |             0.1452 |                 89.7143 |                       0.0963 |              0.1258 |
| stress_q10_5d  |         5 | graph         | logistic_elasticnet    | 1323 |      0.1149 |  0.1419 |             -0.3958 |  0.5872 |  0.1347 |  0.111  |          0.6776 |             0.1486 |                112.381  |                       0.0961 |              0.0351 |
| stress_q10_5d  |         5 | market        | hist_gradient_boosting | 1323 |      0.1149 |  0.145  |             -0.4261 |  0.4756 |  0.1134 |  0.0141 |          0.5592 |             0.119  |                119.809  |                       0.1312 |             -0.0828 |
| stress_q10_5d  |         5 | combined      | logistic_l2            | 1323 |      0.1149 |  0.1453 |             -0.4288 |  0.5815 |  0.1757 |  0.1088 |          0.4605 |             0.1655 |                 67.2381 |                       0.1047 |              0.0551 |
| stress_q10_5d  |         5 | market        | logistic_elasticnet    | 1323 |      0.1149 |  0.1558 |             -0.5317 |  0.5786 |  0.1337 |  0.0718 |          0.6053 |             0.1375 |                109.905  |                       0.134  |              0.1326 |
| stress_q10_5d  |         5 | market        | logistic_l2            | 1323 |      0.1149 |  0.1584 |             -0.5573 |  0.5642 |  0.1318 |  0.0065 |          0.5132 |             0.1169 |                112.191  |                       0.1448 |              0.0642 |
| stress_q10_5d  |         5 | graph         | logistic_l2            | 1323 |      0.1149 |  0.1676 |             -0.6486 |  0.6096 |  0.1461 |  0.1114 |          0.6908 |             0.1479 |                115.238  |                       0.1241 |              0.0342 |
| stress_q10_10d |        10 | graph         | naive_frequency        | 1323 |      0.1126 |  0.1099 |             -0.1    |  0.4856 |  0.1136 | -0.0189 |          0.2617 |             0.1032 |                 64.5714 |                       0.0925 |             -0.1183 |
| stress_q10_10d |        10 | market        | naive_frequency        | 1323 |      0.1126 |  0.1099 |             -0.1    |  0.5029 |  0.1168 | -0.0189 |          0.2617 |             0.1032 |                 64.5714 |                       0.0828 |             -0.1167 |
| stress_q10_10d |        10 | combined      | naive_frequency        | 1323 |      0.1126 |  0.1099 |             -0.1    |  0.5029 |  0.1168 | -0.0189 |          0.2617 |             0.1032 |                 64.5714 |                       0.0828 |             -0.1167 |
| stress_q10_10d |        10 | graph         | hist_gradient_boosting | 1323 |      0.1126 |  0.1354 |             -0.3552 |  0.5281 |  0.1133 |  0.015  |          0.2886 |             0.1204 |                 59.8095 |                       0.1021 |              0.0392 |
| stress_q10_10d |        10 | graph         | logistic_elasticnet    | 1323 |      0.1126 |  0.1379 |             -0.3798 |  0.58   |  0.2496 |  0.0671 |          0.5101 |             0.1377 |                 90.6667 |                       0.1266 |              0.2535 |
| stress_q10_10d |        10 | market        | hist_gradient_boosting | 1323 |      0.1126 |  0.1448 |             -0.4488 |  0.4151 |  0.1004 |  0.0001 |          0.3826 |             0.1126 |                 85.5238 |                       0.1512 |             -0.171  |
| stress_q10_10d |        10 | combined      | hist_gradient_boosting | 1323 |      0.1126 |  0.1482 |             -0.4829 |  0.4684 |  0.1014 |  0.0148 |          0.3758 |             0.1189 |                 79.0476 |                       0.1272 |             -0.0613 |
| stress_q10_10d |        10 | combined      | logistic_elasticnet    | 1323 |      0.1126 |  0.1499 |             -0.4999 |  0.6121 |  0.2234 |  0.1406 |          0.6174 |             0.1646 |                 88.9524 |                       0.1351 |              0.1753 |
| stress_q10_10d |        10 | combined      | random_forest          | 1323 |      0.1126 |  0.1547 |             -0.5476 |  0.5046 |  0.1245 | -0.0101 |          0.2483 |             0.1072 |                 58.6667 |                       0.1644 |              0.0189 |
| stress_q10_10d |        10 | graph         | random_forest          | 1323 |      0.1126 |  0.156  |             -0.5605 |  0.5306 |  0.1183 | -0.017  |          0.2886 |             0.1046 |                 70.0952 |                       0.1472 |              0.0433 |
| stress_q10_10d |        10 | graph         | logistic_l2            | 1323 |      0.1126 |  0.1565 |             -0.5658 |  0.5686 |  0.1803 |  0.0545 |          0.4094 |             0.1368 |                 73.3333 |                       0.1497 |              0.1309 |
| stress_q10_10d |        10 | combined      | logistic_l2            | 1323 |      0.1126 |  0.1784 |             -0.7854 |  0.6513 |  0.1746 |  0.0655 |          0.349  |             0.1469 |                 57.5238 |                       0.1555 |              0.1095 |
| stress_q10_10d |        10 | market        | logistic_elasticnet    | 1323 |      0.1126 |  0.1793 |             -0.7942 |  0.4817 |  0.1145 | -0.0661 |          0.3221 |             0.0878 |                 95.0476 |                       0.1806 |             -0.0454 |
| stress_q10_10d |        10 | market        | random_forest          | 1323 |      0.1126 |  0.18   |             -0.8006 |  0.4226 |  0.0909 | -0.0789 |          0.2685 |             0.0805 |                 87.0476 |                       0.1929 |             -0.0541 |
| stress_q10_10d |        10 | market        | logistic_l2            | 1323 |      0.1126 |  0.1995 |             -0.9962 |  0.4373 |  0.1028 | -0.1004 |          0.2819 |             0.0754 |                 98.0952 |                       0.2179 |             -0.0601 |
| stress_q10_20d |        20 | graph         | naive_frequency        | 1323 |      0.1338 |  0.1299 |             -0.1212 |  0.4616 |  0.1287 |  0.0253 |          0.2655 |             0.1492 |                 51.0476 |                       0.1246 |             -0.189  |
| stress_q10_20d |        20 | market        | naive_frequency        | 1323 |      0.1338 |  0.1299 |             -0.1213 |  0.4798 |  0.1317 |  0.0253 |          0.2655 |             0.1492 |                 51.0476 |                       0.1258 |             -0.1882 |
| stress_q10_20d |        20 | combined      | naive_frequency        | 1323 |      0.1338 |  0.1299 |             -0.1213 |  0.4798 |  0.1317 |  0.0253 |          0.2655 |             0.1492 |                 51.0476 |                       0.1258 |             -0.1882 |
| stress_q10_20d |        20 | graph         | hist_gradient_boosting | 1323 |      0.1338 |  0.1563 |             -0.3491 |  0.4166 |  0.1188 | -0.0794 |          0.1808 |             0.0894 |                 62.0952 |                       0.151  |             -0.1441 |
| stress_q10_20d |        20 | graph         | random_forest          | 1323 |      0.1338 |  0.1651 |             -0.4247 |  0.5381 |  0.1544 |  0.0023 |          0.3898 |             0.1348 |                 84.381  |                       0.1514 |              0.0277 |
| stress_q10_20d |        20 | combined      | logistic_elasticnet    | 1323 |      0.1338 |  0.1726 |             -0.489  |  0.5309 |  0.1606 | -0.0142 |          0.2768 |             0.1263 |                 64.5714 |                       0.1727 |             -0.0085 |
| stress_q10_20d |        20 | combined      | logistic_l2            | 1323 |      0.1338 |  0.1764 |             -0.5225 |  0.4971 |  0.1649 | -0.0352 |          0.2373 |             0.1144 |                 61.9048 |                       0.1879 |             -0.0083 |
| stress_q10_20d |        20 | combined      | hist_gradient_boosting | 1323 |      0.1338 |  0.1874 |             -0.617  |  0.418  |  0.113  | -0.0384 |          0.3616 |             0.1181 |                 91.0476 |                       0.1714 |             -0.146  |
| stress_q10_20d |        20 | combined      | random_forest          | 1323 |      0.1338 |  0.1875 |             -0.6182 |  0.4978 |  0.1661 | -0.0161 |          0.4181 |             0.1276 |                 96.381  |                       0.2272 |              0.0628 |
| stress_q10_20d |        20 | market        | hist_gradient_boosting | 1323 |      0.1338 |  0.1884 |             -0.6258 |  0.4032 |  0.1109 | -0.0387 |          0.1525 |             0.1067 |                 43.0476 |                       0.1873 |             -0.0622 |
| stress_q10_20d |        20 | graph         | logistic_elasticnet    | 1323 |      0.1338 |  0.2288 |             -0.9742 |  0.4565 |  0.1495 | -0.0424 |          0.3051 |             0.1144 |                 79.619  |                       0.2474 |             -0.0474 |
| stress_q10_20d |        20 | market        | random_forest          | 1323 |      0.1338 |  0.2322 |             -1.0036 |  0.347  |  0.1074 | -0.0659 |          0.2486 |             0.1016 |                 74.0952 |                       0.2686 |             -0.1454 |
| stress_q10_20d |        20 | graph         | logistic_l2            | 1323 |      0.1338 |  0.2458 |             -1.1213 |  0.4526 |  0.1501 | -0.0085 |          0.3277 |             0.1298 |                 74.0952 |                       0.2626 |             -0.0274 |
| stress_q10_20d |        20 | market        | logistic_l2            | 1323 |      0.1338 |  0.2739 |             -1.3635 |  0.3053 |  0.1099 | -0.1688 |          0.1977 |             0.0647 |                 96.381  |                       0.2817 |             -0.1386 |
| stress_q10_20d |        20 | market        | logistic_elasticnet    | 1323 |      0.1338 |  0.289  |             -1.4941 |  0.3493 |  0.1017 | -0.1602 |          0.1582 |             0.06   |                 83.619  |                       0.2867 |             -0.1299 |
| stress_q10_40d |        40 | graph         | naive_frequency        | 1323 |      0.1738 |  0.1696 |             -0.1807 |  0.4008 |  0.1641 | -0.1531 |          0.0261 |             0.0317 |                 34.8571 |                       0.1975 |             -0.3162 |
| stress_q10_40d |        40 | market        | naive_frequency        | 1323 |      0.1738 |  0.1696 |             -0.1812 |  0.4608 |  0.1754 | -0.1531 |          0.0261 |             0.0317 |                 34.8571 |                       0.1879 |             -0.3127 |
| stress_q10_40d |        40 | combined      | naive_frequency        | 1323 |      0.1738 |  0.1696 |             -0.1812 |  0.4608 |  0.1754 | -0.1531 |          0.0261 |             0.0317 |                 34.8571 |                       0.1879 |             -0.3127 |
| stress_q10_40d |        40 | graph         | random_forest          | 1323 |      0.1738 |  0.2147 |             -0.495  |  0.502  |  0.1725 | -0.047  |          0.3652 |             0.1527 |                 88.7619 |                       0.2215 |              0.0782 |
| stress_q10_40d |        40 | combined      | random_forest          | 1323 |      0.1738 |  0.2396 |             -0.6683 |  0.4848 |  0.1658 | -0.045  |          0.2565 |             0.1479 |                 64.7619 |                       0.2458 |              0.0235 |
| stress_q10_40d |        40 | graph         | hist_gradient_boosting | 1323 |      0.1738 |  0.2431 |             -0.6926 |  0.4912 |  0.1633 | -0.0445 |          0.2217 |             0.1457 |                 56.9524 |                       0.2421 |              0.0125 |
| stress_q10_40d |        40 | graph         | logistic_elasticnet    | 1323 |      0.1738 |  0.2635 |             -0.8348 |  0.5694 |  0.1978 |  0.1446 |          0.5478 |             0.2418 |                 75.2381 |                       0.2498 |              0.0366 |
| stress_q10_40d |        40 | graph         | logistic_l2            | 1323 |      0.1738 |  0.2742 |             -0.909  |  0.5972 |  0.214  |  0.0521 |          0.3696 |             0.2029 |                 63.619  |                       0.2647 |              0.042  |
| stress_q10_40d |        40 | market        | hist_gradient_boosting | 1323 |      0.1738 |  0.2844 |             -0.9801 |  0.2691 |  0.1174 | -0.1698 |          0.1043 |             0.0676 |                 63.0476 |                       0.3034 |             -0.1746 |
| stress_q10_40d |        40 | combined      | hist_gradient_boosting | 1323 |      0.1738 |  0.3017 |             -1.1009 |  0.4024 |  0.145  | -0.2144 |          0.0522 |             0.0354 |                 62.2857 |                       0.3036 |             -0.0281 |
| stress_q10_40d |        40 | market        | random_forest          | 1323 |      0.1738 |  0.3046 |             -1.121  |  0.2997 |  0.1262 | -0.0611 |          0.2348 |             0.1381 |                 64.1905 |                       0.3512 |             -0.1323 |
| stress_q10_40d |        40 | combined      | logistic_l2            | 1323 |      0.1738 |  0.3559 |             -1.4782 |  0.4787 |  0.1747 | -0.1026 |          0.2652 |             0.1235 |                 82.4762 |                       0.3446 |             -0.0112 |
| stress_q10_40d |        40 | combined      | logistic_elasticnet    | 1323 |      0.1738 |  0.3562 |             -1.4799 |  0.4893 |  0.1624 | -0.0971 |          0.2739 |             0.1265 |                 82.8571 |                       0.3479 |              0.0023 |
| stress_q10_40d |        40 | market        | logistic_elasticnet    | 1323 |      0.1738 |  0.373  |             -1.5968 |  0.3448 |  0.1296 | -0.181  |          0.2087 |             0.0902 |                 92.1905 |                       0.3943 |             -0.1172 |
| stress_q10_40d |        40 | market        | logistic_l2            | 1323 |      0.1738 |  0.4081 |             -1.8418 |  0.3285 |  0.1238 | -0.1638 |          0.2348 |             0.0994 |                 93.1429 |                       0.4073 |             -0.1316 |

**Reading the table.** `brier_skill_score` compares against a constant base-rate forecast: 0 means no better than predicting the unconditional frequency, negative means worse. `auprc` should be compared to `base_rate`, not to 0.5. `calibration_slope` of 1 is perfect; below 1 means over-confident.

## 3. Does the graph add out-of-sample value?

**Verdict: `mixed`**

Some settings improved significantly and others did not. The evidence does not support a general claim that graph features help.

- Paired comparisons run: 20
- Significant Brier improvements: 4
- Significant AUPRC improvements: 3
- Mean Brier difference (challenger - market-only): -0.02595

Significance uses a **paired moving-block bootstrap** on identical resampled blocks, which controls for the shared market environment. An i.i.d. bootstrap would materially overstate significance on daily data.

### Absolute skill (against a constant base-rate forecast)

- **No configuration beat a constant base-rate forecast.** The best Brier skill score across 48 configuration(s) was -0.1216.
- No configuration beat a constant forecast at the realised base rate. Any relative improvement below is an improvement over a poorly calibrated baseline, not evidence of usable forecasting skill.

This is the more important of the two results. The relative comparison above shows that graph features improve on the market-only feature set; the absolute result shows that neither is currently good enough to forecast VN30 stress at these horizons. Treat DynamicGraph's structural output as the deliverable and the probabilities as diagnostic.

### Paired comparisons

| target         | model                  | challenger   |   brier_baseline |   brier_challenger |   brier_difference |   brier_ci_lower |   brier_ci_upper | brier_significant   |   auprc_difference | auprc_significant   |
|:---------------|:-----------------------|:-------------|-----------------:|-------------------:|-------------------:|-----------------:|-----------------:|:--------------------|-------------------:|:--------------------|
| stress_q10_5d  | naive_frequency        | graph        |           0.1052 |             0.1052 |            -0      |          -0      |           0      | False               |             0      | False               |
| stress_q10_5d  | naive_frequency        | combined     |           0.1052 |             0.1052 |             0      |           0      |           0      | False               |             0      | False               |
| stress_q10_5d  | logistic_elasticnet    | graph        |           0.1558 |             0.1419 |            -0.0138 |          -0.0348 |           0.0068 | False               |             0.001  | False               |
| stress_q10_5d  | logistic_elasticnet    | combined     |           0.1558 |             0.1379 |            -0.0178 |          -0.0396 |           0.0046 | False               |             0.0326 | False               |
| stress_q10_5d  | logistic_l2            | graph        |           0.1584 |             0.1676 |             0.0093 |          -0.0258 |           0.0489 | False               |             0.0142 | False               |
| stress_q10_5d  | logistic_l2            | combined     |           0.1584 |             0.1453 |            -0.0131 |          -0.0426 |           0.0147 | False               |             0.0439 | False               |
| stress_q10_5d  | random_forest          | graph        |           0.1313 |             0.1154 |            -0.0159 |          -0.0402 |           0.0045 | False               |             0.0179 | False               |
| stress_q10_5d  | random_forest          | combined     |           0.1313 |             0.1141 |            -0.0173 |          -0.0412 |           0.0012 | False               |             0.0146 | False               |
| stress_q10_5d  | hist_gradient_boosting | graph        |           0.145  |             0.1145 |            -0.0305 |          -0.057  |          -0.0121 | True                |            -0.0008 | False               |
| stress_q10_5d  | hist_gradient_boosting | combined     |           0.145  |             0.1228 |            -0.0222 |          -0.0471 |          -0.0033 | True                |            -0.0221 | False               |
| stress_q10_10d | naive_frequency        | graph        |           0.1099 |             0.1099 |            -0      |          -0.0001 |           0.0001 | False               |            -0.0032 | False               |
| stress_q10_10d | naive_frequency        | combined     |           0.1099 |             0.1099 |             0      |           0      |           0      | False               |             0      | False               |
| stress_q10_10d | logistic_elasticnet    | graph        |           0.1793 |             0.1379 |            -0.0414 |          -0.0886 |          -0.0014 | True                |             0.1351 | False               |
| stress_q10_10d | logistic_elasticnet    | combined     |           0.1793 |             0.1499 |            -0.0294 |          -0.0793 |           0.0104 | False               |             0.1089 | False               |
| stress_q10_10d | logistic_l2            | graph        |           0.1995 |             0.1565 |            -0.043  |          -0.1028 |           0.0034 | False               |             0.0775 | False               |
| stress_q10_10d | logistic_l2            | combined     |           0.1995 |             0.1784 |            -0.0211 |          -0.0776 |           0.0301 | False               |             0.0718 | True                |
| stress_q10_10d | random_forest          | graph        |           0.18   |             0.156  |            -0.024  |          -0.0709 |           0.0234 | False               |             0.0275 | False               |
| stress_q10_10d | random_forest          | combined     |           0.18   |             0.1547 |            -0.0253 |          -0.0687 |           0.0135 | False               |             0.0337 | False               |
| stress_q10_10d | hist_gradient_boosting | graph        |           0.1448 |             0.1354 |            -0.0094 |          -0.0459 |           0.0276 | False               |             0.013  | False               |
| stress_q10_10d | hist_gradient_boosting | combined     |           0.1448 |             0.1482 |             0.0034 |          -0.0323 |           0.0393 | False               |             0.001  | False               |
| stress_q10_20d | naive_frequency        | graph        |           0.1299 |             0.1299 |            -0      |          -0.0001 |           0      | False               |            -0.003  | False               |
| stress_q10_20d | naive_frequency        | combined     |           0.1299 |             0.1299 |             0      |           0      |           0      | False               |             0      | False               |
| stress_q10_20d | logistic_elasticnet    | graph        |           0.289  |             0.2288 |            -0.0603 |          -0.1203 |          -0.0088 | True                |             0.0477 | False               |
| stress_q10_20d | logistic_elasticnet    | combined     |           0.289  |             0.1726 |            -0.1165 |          -0.1924 |          -0.0601 | True                |             0.0589 | False               |
| stress_q10_20d | logistic_l2            | graph        |           0.2739 |             0.2458 |            -0.0281 |          -0.0785 |           0.0234 | False               |             0.0402 | False               |
| stress_q10_20d | logistic_l2            | combined     |           0.2739 |             0.1764 |            -0.0975 |          -0.179  |          -0.0277 | True                |             0.055  | False               |
| stress_q10_20d | random_forest          | graph        |           0.2322 |             0.1651 |            -0.0671 |          -0.1318 |          -0.0158 | True                |             0.047  | False               |
| stress_q10_20d | random_forest          | combined     |           0.2322 |             0.1875 |            -0.0447 |          -0.1089 |           0.0097 | False               |             0.0587 | False               |
| stress_q10_20d | hist_gradient_boosting | graph        |           0.1884 |             0.1563 |            -0.0321 |          -0.0758 |           0.0061 | False               |             0.0079 | False               |
| stress_q10_20d | hist_gradient_boosting | combined     |           0.1884 |             0.1874 |            -0.001  |          -0.0448 |           0.0397 | False               |             0.0021 | False               |
| stress_q10_40d | naive_frequency        | graph        |           0.1696 |             0.1696 |            -0.0001 |          -0.0002 |           0      | False               |            -0.0114 | False               |
| stress_q10_40d | naive_frequency        | combined     |           0.1696 |             0.1696 |             0      |           0      |           0      | False               |             0      | False               |
| stress_q10_40d | logistic_elasticnet    | graph        |           0.373  |             0.2635 |            -0.1094 |          -0.1824 |          -0.0358 | True                |             0.0682 | False               |
| stress_q10_40d | logistic_elasticnet    | combined     |           0.373  |             0.3562 |            -0.0168 |          -0.0916 |           0.0535 | False               |             0.0328 | False               |
| stress_q10_40d | logistic_l2            | graph        |           0.4081 |             0.2742 |            -0.134  |          -0.2196 |          -0.0495 | True                |             0.0902 | True                |
| stress_q10_40d | logistic_l2            | combined     |           0.4081 |             0.3559 |            -0.0522 |          -0.1425 |           0.025  | False               |             0.0551 | True                |
| stress_q10_40d | random_forest          | graph        |           0.3046 |             0.2147 |            -0.0899 |          -0.1515 |          -0.022  | True                |             0.0463 | True                |
| stress_q10_40d | random_forest          | combined     |           0.3046 |             0.2396 |            -0.065  |          -0.12   |          -0.0078 | True                |             0.0396 | True                |
| stress_q10_40d | hist_gradient_boosting | graph        |           0.2844 |             0.2431 |            -0.0413 |          -0.1154 |           0.0332 | False               |             0.0459 | True                |
| stress_q10_40d | hist_gradient_boosting | combined     |           0.2844 |             0.3017 |             0.0174 |          -0.0433 |           0.0803 | False               |             0.0276 | False               |

## 4. Cross-sectional node ranking

A different question from the market-level model: can the network *order* the 30 constituents by forward risk-adjusted return? Three nested feature sets isolate the network's contribution.

| feature_set          | model   |   horizon |   n_dates |   ic_ic_mean |   ic_ic_std |   ic_ic_ir |   ic_ic_t_stat |   ic_ic_positive_rate |   long_short_spread |   long_short_spread_t |   mean_turnover |   cost_adjusted_spread_annualized |   ic_mean_vs_node_only |
|:---------------------|:--------|----------:|----------:|-------------:|------------:|-----------:|---------------:|----------------------:|--------------------:|----------------------:|----------------:|----------------------------------:|-----------------------:|
| node                 | ridge   |        20 |      1323 |       0.1029 |      0.2436 |     6.7049 |        15.3629 |                0.6712 |              0.0844 |               14.5892 |          0.2872 |                            1.0454 |                 0      |
| node_plus_centrality | ridge   |        20 |      1323 |       0.0599 |      0.2353 |     4.039  |         9.2546 |                0.5911 |              0.0452 |                8.2079 |          0.3237 |                            0.5492 |                -0.043  |
| node_plus_neighbor   | ridge   |        20 |      1323 |       0.0493 |      0.2318 |     3.3786 |         7.7412 |                0.5911 |              0.0374 |                6.7037 |          0.3339 |                            0.45   |                -0.0536 |

**Verdict: `no_improvement`**

Network features did not improve cross-sectional ordering over per-stock features. Centrality describes structural position, not expected return.

Rank IC and long-short spreads are evaluation devices. They demonstrate ordering ability, not a causal effect and not a tradable strategy.

A mean rank IC is only meaningful relative to its own standard error; the `ic_ic_t_stat` column is the quantity to read, not the IC alone.

## 5. Caveats

- Overlapping h-day labels mean the effective sample is closer to `n/h` than `n`; the reported `effective_sample_size` reflects this.
- Stress events are rare and clustered, so a handful of episodes drives most of the measured skill. Event-level detection metrics are reported alongside day-level ones for exactly this reason.
- The universe carries survivorship bias unless `liquidity_proxy` was used; see the data audit report.
