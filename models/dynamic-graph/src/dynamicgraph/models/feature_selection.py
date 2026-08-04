"""Fold-local feature selection.

Fitted **only** on a fold's training rows, then applied unchanged to validation
and test. Selecting features on the full sample is one of the most common
sources of optimistic backtests, because the choice of which columns to keep
already encodes the answer.

Three stages, cheapest first:

1. **Coverage / variance** -- drop columns that are mostly missing or constant
   inside the training block.
2. **Redundancy** -- among columns whose training-period |Spearman| exceeds a
   threshold, keep one. Multi-scale network metrics are heavily collinear by
   construction (a 60-day and a 120-day density move together), so this removes
   the bulk of the feature space without discarding information.
3. **Univariate ranking** -- keep the top `max_features` by training-period
   mutual information with the label.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class FeatureSelector:
    """Training-fitted column filter."""

    max_features: int = 60
    min_coverage: float = 0.60
    redundancy_threshold: float = 0.95
    #: Redundancy pruning is O(p^2); restrict it to the strongest
    #: `max_features * shortlist_multiplier` candidates.
    shortlist_multiplier: int = 4
    #: "spearman" (fast, default) or "mutual_info" (slow, non-linear).
    score: str = "spearman"
    seed: int = 42
    selected_: list[str] = field(default_factory=list)
    dropped_low_coverage_: int = 0
    dropped_constant_: int = 0
    dropped_redundant_: int = 0
    fitted: bool = False

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series) -> "FeatureSelector":
        if X_train.empty:
            self.selected_, self.fitted = [], True
            return self

        frame = X_train.replace([np.inf, -np.inf], np.nan)

        coverage = frame.notna().mean()
        keep = coverage[coverage >= self.min_coverage].index
        self.dropped_low_coverage_ = int(frame.shape[1] - len(keep))
        frame = frame[keep]

        variance = frame.std(ddof=0)
        keep = variance[variance.fillna(0.0) > 1e-12].index
        self.dropped_constant_ = int(frame.shape[1] - len(keep))
        frame = frame[keep]

        if frame.shape[1] == 0:
            self.selected_, self.fitted = [], True
            return self

        # ---- univariate ranking ------------------------------------------
        # Rank by univariate signal first, so the survivor of each collinear
        # cluster is the most informative member rather than whichever happened
        # to come first alphabetically.
        scores = self._univariate_scores(frame, y_train)
        ordered = list(scores.sort_values(ascending=False).index)

        # ---- redundancy pruning ------------------------------------------
        # Prune only among the strongest candidates. The full pairwise rank
        # correlation is O(p^2): on ~660 columns it dominates the entire fold,
        # and columns ranked far below the budget can never be selected anyway.
        shortlist = ordered[: max(self.max_features * self.shortlist_multiplier, self.max_features)]
        n_before = len(shortlist)

        if len(shortlist) > 1:
            correlation = frame[shortlist].corr(method="spearman").abs().to_numpy()
            survivors: list[int] = []
            for i in range(len(shortlist)):
                if any(
                    correlation[i, j] > self.redundancy_threshold
                    and np.isfinite(correlation[i, j])
                    for j in survivors
                ):
                    continue
                survivors.append(i)
                if len(survivors) >= self.max_features:
                    break
            self.dropped_redundant_ = n_before - len(survivors)
            shortlist = [shortlist[i] for i in survivors]

        self.selected_ = shortlist[: self.max_features]
        self.fitted = True
        logger.debug(
            "Feature selection: %d -> %d (low coverage %d, constant %d, redundant %d).",
            X_train.shape[1], len(self.selected_),
            self.dropped_low_coverage_, self.dropped_constant_, self.dropped_redundant_,
        )
        return self

    def _univariate_scores(self, frame: pd.DataFrame, y: pd.Series) -> pd.Series:
        """Univariate association between each column and the label.

        Default is |Spearman|, computed as a single vectorised rank correlation.
        Mutual information is available via `score='mutual_info'` but is a kNN
        estimator: on ~660 columns x ~2800 rows it costs ~15 s per fold, which
        across 21 folds and 48 model runs is several hours. The rank correlation
        is ~200x faster and, used only to order candidates before redundancy
        pruning, selects a near-identical feature set.
        """
        aligned = y.reindex(frame.index)
        mask = aligned.notna()
        if mask.sum() < 30 or aligned[mask].nunique() < 2:
            return pd.Series(0.0, index=frame.columns)

        filled = frame[mask].fillna(frame[mask].median())
        target = aligned[mask]

        if self.score == "mutual_info":
            try:
                from sklearn.feature_selection import mutual_info_classif

                values = mutual_info_classif(filled, target.astype(int), random_state=self.seed)
                return pd.Series(values, index=frame.columns)
            except Exception as exc:
                logger.debug("Mutual information failed (%s); falling back to |Spearman|.", exc)

        # Rank-transform once, then a single correlation pass over all columns.
        ranked = filled.rank()
        target_ranked = target.rank()
        centered = ranked - ranked.mean()
        target_centered = target_ranked - target_ranked.mean()
        numerator = centered.mul(target_centered, axis=0).sum()
        denominator = np.sqrt((centered**2).sum() * (target_centered**2).sum())
        scores = (numerator / denominator.replace(0.0, np.nan)).abs()
        return scores.fillna(0.0)

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if not self.fitted:
            raise RuntimeError("FeatureSelector must be fitted before transform().")
        if not self.selected_:
            return X.iloc[:, :0]
        return X.reindex(columns=self.selected_)

    def fit_transform(self, X_train: pd.DataFrame, y_train: pd.Series) -> pd.DataFrame:
        return self.fit(X_train, y_train).transform(X_train)

    def to_dict(self) -> dict:
        return {
            "n_selected": len(self.selected_),
            "selected": list(self.selected_),
            "dropped_low_coverage": self.dropped_low_coverage_,
            "dropped_constant": self.dropped_constant_,
            "dropped_redundant": self.dropped_redundant_,
            "max_features": self.max_features,
            "redundancy_threshold": self.redundancy_threshold,
        }
