"""Documented compact search domains used by laptop experiments."""

EBM_SPACE = {
    "learning_rate": [0.015, 0.025, 0.03, 0.04],
    "max_rounds": [30, 50, 80],
    "max_bins": [64, 96],
    "min_samples_leaf": [2, 5, 10],
    "interactions": [0],
    "outer_bags": [2],
}

XGBOOST_SPACE = {"max_depth": [2, 3], "learning_rate": [0.03, 0.05]}
RANDOM_FOREST_SPACE = {"max_depth": [5, 6, 8], "n_estimators": [160, 240]}
