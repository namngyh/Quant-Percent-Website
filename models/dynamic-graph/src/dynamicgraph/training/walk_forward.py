"""Purged walk-forward evaluation.

Per fold, in this order and no other:

  1. slice train / validation / test by position (chronological, purged);
  2. fit the target QUANTILE threshold on training rows only;
  3. fit imputation + scaling inside the estimator pipeline on training rows only;
  4. optionally tune hyperparameters on the validation block;
  5. refit on train, calibrate on validation, pick the decision threshold on
     validation;
  6. predict the test block once and store it.

Nothing fitted in steps 2-5 ever sees a test row. The stored OOS predictions are
the only thing the reporting layer is allowed to consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from dynamicgraph.evaluation.classification import classification_metrics
from dynamicgraph.features.targets import label_by_train_quantile
from dynamicgraph.logging_config import get_logger
from dynamicgraph.models.baselines import ModelSpec, sample_weights_from_labels
from dynamicgraph.models.calibration import CalibratedModel, calibrate, optimize_threshold
from dynamicgraph.models.feature_selection import FeatureSelector
from dynamicgraph.training.purging import assert_no_overlap, effective_sample_size
from dynamicgraph.training.splits import Fold

logger = get_logger(__name__)


@dataclass
class WalkForwardResult:
    """OOS predictions and per-fold diagnostics for one (model, feature set, horizon)."""

    model_name: str
    feature_set: str
    horizon: int
    target_name: str
    predictions: pd.DataFrame = field(default_factory=pd.DataFrame)
    fold_metrics: pd.DataFrame = field(default_factory=pd.DataFrame)
    thresholds: dict[int, float] = field(default_factory=dict)
    calibration_methods: dict[int, str] = field(default_factory=dict)
    target_thresholds: dict[int, float] = field(default_factory=dict)
    hyperparameters: dict[int, dict[str, Any]] = field(default_factory=dict)
    #: Columns kept per fold by the training-fitted selector.
    selected_features: dict[int, list[str]] = field(default_factory=dict)
    feature_names: list[str] = field(default_factory=list)
    n_features: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.target_name}__{self.feature_set}__{self.model_name}"

    @property
    def n_features_selected(self) -> float:
        """Mean number of columns actually used, after fold-local selection.

        `n_features` is the size of the candidate space; this is what the model
        saw. Reporting only the former overstates model complexity several-fold.
        """
        if not self.selected_features:
            return float(self.n_features)
        return float(np.mean([len(v) for v in self.selected_features.values()]))

    def oos_metrics(self, threshold: float | None = None) -> dict[str, Any]:
        if self.predictions.empty:
            return {"n": 0, "note": "no predictions"}
        threshold = threshold if threshold is not None else float(
            np.median(list(self.thresholds.values())) if self.thresholds else 0.5
        )
        metrics = classification_metrics(
            self.predictions["y_true"].to_numpy(),
            self.predictions["probability"].to_numpy(),
            threshold=threshold,
            n_days=len(self.predictions),
        )
        metrics.update(
            {
                "model": self.model_name,
                "feature_set": self.feature_set,
                "horizon": self.horizon,
                "target": self.target_name,
                "n_folds": int(self.predictions["fold"].nunique()),
                "n_features_candidate": self.n_features,
                "n_features": self.n_features_selected,
                "effective_sample_size": effective_sample_size(len(self.predictions), self.horizon),
            }
        )
        return metrics


def _slice(frame: pd.DataFrame, positions: np.ndarray, index: pd.DatetimeIndex) -> pd.DataFrame:
    return frame.reindex(index[positions])


def run_walk_forward(
    features: pd.DataFrame,
    target_values: pd.Series,
    folds: list[Fold],
    model_spec: ModelSpec,
    config: Any,
    horizon: int,
    target_name: str,
    feature_set: str = "combined",
    quantile: float | None = None,
    absolute_labels: pd.Series | None = None,
    tuner: Callable[..., dict[str, Any]] | None = None,
) -> WalkForwardResult:
    """Run one model over all folds and collect the OOS predictions.

    Exactly one of `quantile` (fit the label threshold on training rows) or
    `absolute_labels` (pre-computed fixed-threshold labels) must be supplied.
    """
    if (quantile is None) == (absolute_labels is None):
        raise ValueError("Supply exactly one of `quantile` or `absolute_labels`.")

    index = folds[0].index
    features = features.reindex(index)
    target_values = target_values.reindex(index)

    result = WalkForwardResult(
        model_name=model_spec.name,
        feature_set=feature_set,
        horizon=horizon,
        target_name=target_name,
        feature_names=list(features.columns),
        n_features=features.shape[1],
    )

    seed = int(config.project.seed)
    calibration_method = str(config.models.calibration_method)
    threshold_objective = str(config.evaluation.decision_threshold_objective)
    min_positive_train = int(config.training.min_positive_train)
    max_features = int(getattr(config.training, "max_features", 0) or 0)

    prediction_rows: list[pd.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []

    for fold in folds:
        train_positions = fold.train_positions
        validation_positions = fold.validation_positions
        test_positions = fold.test_positions

        assert_no_overlap(train_positions, test_positions, horizon, fold.embargo_days)
        assert_no_overlap(train_positions, validation_positions, horizon, fold.embargo_days)

        # ---- labels: quantile fitted on TRAINING rows only --------------
        if quantile is not None:
            train_mask = pd.Series(False, index=index)
            train_mask.iloc[train_positions] = True
            try:
                labels, label_threshold = label_by_train_quantile(
                    target_values, train_mask, quantile, direction="lower"
                )
            except ValueError as exc:
                logger.warning("Fold %d: %s", fold.fold_id, exc)
                continue
            result.target_thresholds[fold.fold_id] = label_threshold
        else:
            labels = absolute_labels.reindex(index)
            label_threshold = np.nan

        X_train = _slice(features, train_positions, index)
        y_train = labels.reindex(index[train_positions])
        X_validation = _slice(features, validation_positions, index)
        y_validation = labels.reindex(index[validation_positions])
        X_test = _slice(features, test_positions, index)
        y_test = labels.reindex(index[test_positions])

        train_ok = y_train.notna() & X_train.notna().any(axis=1)
        X_train, y_train = X_train[train_ok], y_train[train_ok]
        validation_ok = y_validation.notna() & X_validation.notna().any(axis=1)
        X_validation, y_validation = X_validation[validation_ok], y_validation[validation_ok]
        test_ok = y_test.notna() & X_test.notna().any(axis=1)
        X_test_used, y_test_used = X_test[test_ok], y_test[test_ok]

        n_positive = int(y_train.sum())
        if len(X_train) < 100 or n_positive < min_positive_train or len(X_test_used) < 5:
            logger.debug(
                "Fold %d skipped (%s): n_train=%d, positives=%d, n_test=%d.",
                fold.fold_id, model_spec.name, len(X_train), n_positive, len(X_test_used),
            )
            continue

        # ---- feature selection, fitted on TRAINING rows only -------------
        if max_features and X_train.shape[1] > max_features:
            selector = FeatureSelector(
                max_features=max_features,
                redundancy_threshold=float(config.training.feature_redundancy_threshold),
                seed=seed,
            ).fit(X_train, y_train)
            if selector.selected_:
                X_train = selector.transform(X_train)
                X_validation = selector.transform(X_validation)
                X_test_used = selector.transform(X_test_used)
                result.selected_features[fold.fold_id] = list(selector.selected_)

        # ---- optional tuning on the validation block --------------------
        params: dict[str, Any] = {}
        if tuner is not None and model_spec.search_space:
            try:
                params = tuner(
                    model_spec=model_spec,
                    X_train=X_train, y_train=y_train,
                    X_validation=X_validation, y_validation=y_validation,
                    seed=seed,
                )
                result.hyperparameters[fold.fold_id] = params
            except Exception as exc:
                logger.warning("Tuning failed on fold %d (%s); using defaults.", fold.fold_id, exc)

        estimator = model_spec.build(params, seed=seed)
        weights = sample_weights_from_labels(y_train.to_numpy(), config.models.class_weight)
        try:
            if weights is not None and _accepts_sample_weight(estimator):
                estimator.fit(X_train, y_train, model__sample_weight=weights)
            else:
                estimator.fit(X_train, y_train)
        except Exception as exc:
            logger.warning("Fold %d: %s failed to fit (%s); skipping.", fold.fold_id, model_spec.name, exc)
            continue

        # ---- calibrate + choose the threshold, both on VALIDATION -------
        if len(X_validation) >= 20 and y_validation.notna().sum() >= 20:
            calibrated = calibrate(
                estimator, X_validation, y_validation.to_numpy(),
                method=calibration_method, feature_names=list(features.columns),
            )
            validation_probabilities = calibrated.predict_proba(X_validation)
            threshold, threshold_info = optimize_threshold(
                validation_probabilities,
                y_validation.to_numpy(),
                objective=threshold_objective,
                fixed=float(config.evaluation.fixed_threshold),
            )
        else:
            calibrated = CalibratedModel(estimator=estimator, method="none")
            threshold = float(config.evaluation.fixed_threshold)
            threshold_info = {"note": "validation block too small"}

        calibrated.decision_threshold = threshold
        result.thresholds[fold.fold_id] = threshold
        result.calibration_methods[fold.fold_id] = calibrated.method

        # ---- predict the test block ONCE --------------------------------
        probabilities = calibrated.predict_proba(X_test_used)
        prediction_rows.append(
            pd.DataFrame(
                {
                    "date": X_test_used.index,
                    "fold": fold.fold_id,
                    "probability": probabilities,
                    "y_true": y_test_used.to_numpy(),
                    "threshold": threshold,
                    "model": model_spec.name,
                    "feature_set": feature_set,
                    "horizon": horizon,
                    "target": target_name,
                }
            )
        )

        fold_metrics = classification_metrics(
            y_test_used.to_numpy(), probabilities, threshold=threshold, n_days=len(y_test_used)
        )
        fold_metrics.update(
            {
                "fold": fold.fold_id,
                "n_train": len(X_train),
                "n_train_positive": n_positive,
                "n_validation": len(X_validation),
                "n_features_selected": int(X_train.shape[1]),
                "calibration": calibrated.method,
                "label_threshold": label_threshold,
                "train_end": str(fold.train_dates.max().date()),
                "test_start": str(fold.test_dates.min().date()),
                "test_end": str(fold.test_dates.max().date()),
                **{f"threshold_{k}": v for k, v in threshold_info.items()},
            }
        )
        fold_rows.append(fold_metrics)

    if prediction_rows:
        result.predictions = (
            pd.concat(prediction_rows, ignore_index=True).sort_values("date").reset_index(drop=True)
        )
    result.fold_metrics = pd.DataFrame(fold_rows)
    if result.predictions.empty:
        result.notes.append("no fold produced usable predictions")
        logger.warning(
            "%s / %s / h=%d produced no OOS predictions.", model_spec.name, feature_set, horizon
        )
    else:
        logger.info(
            "%s / %s / h=%d: %d OOS prediction(s) across %d fold(s).",
            model_spec.name, feature_set, horizon,
            len(result.predictions), result.predictions["fold"].nunique(),
        )
    return result


def _accepts_sample_weight(pipeline: Any) -> bool:
    try:
        import inspect

        estimator = pipeline.named_steps["model"] if hasattr(pipeline, "named_steps") else pipeline
        return "sample_weight" in inspect.signature(estimator.fit).parameters
    except Exception:
        return False


def fit_final_model(
    features: pd.DataFrame,
    labels: pd.Series,
    model_spec: ModelSpec,
    config: Any,
    train_end: pd.Timestamp,
    validation_days: int = 126,
    params: dict[str, Any] | None = None,
) -> CalibratedModel | None:
    """Refit on all data up to `train_end` for the *latest* live prediction.

    The last `validation_days` before `train_end` are held out for calibration
    so the deployed probabilities remain calibrated rather than over-confident.
    """
    index = features.index
    usable = index[index <= train_end]
    if len(usable) < 200:
        logger.warning("Not enough history to fit the final production model.")
        return None

    split = usable[-validation_days] if len(usable) > validation_days else usable[len(usable) // 2]
    train_index = usable[usable < split]
    validation_index = usable[usable >= split]

    X_train = features.reindex(train_index)
    y_train = labels.reindex(train_index)
    mask = y_train.notna() & X_train.notna().any(axis=1)
    X_train, y_train = X_train[mask], y_train[mask]

    X_validation = features.reindex(validation_index)
    y_validation = labels.reindex(validation_index)
    validation_mask = y_validation.notna() & X_validation.notna().any(axis=1)
    X_validation, y_validation = X_validation[validation_mask], y_validation[validation_mask]

    if len(X_train) < 100 or y_train.sum() < 10:
        logger.warning("Final model not fitted: insufficient training positives.")
        return None

    # Same training-only selection as the walk-forward, so the deployed model
    # sees the same feature-space dimensionality it was evaluated at.
    selected: list[str] = list(features.columns)
    max_features = int(getattr(config.training, "max_features", 0) or 0)
    if max_features and X_train.shape[1] > max_features:
        selector = FeatureSelector(
            max_features=max_features,
            redundancy_threshold=float(config.training.feature_redundancy_threshold),
            seed=int(config.project.seed),
        ).fit(X_train, y_train)
        if selector.selected_:
            selected = list(selector.selected_)
            X_train = selector.transform(X_train)
            X_validation = selector.transform(X_validation)

    estimator = model_spec.build(params, seed=int(config.project.seed))
    weights = sample_weights_from_labels(y_train.to_numpy(), config.models.class_weight)
    if weights is not None and _accepts_sample_weight(estimator):
        estimator.fit(X_train, y_train, model__sample_weight=weights)
    else:
        estimator.fit(X_train, y_train)

    calibrated = calibrate(
        estimator, X_validation, y_validation.to_numpy(),
        method=str(config.models.calibration_method), feature_names=selected,
    )
    if len(X_validation) >= 20:
        probabilities = calibrated.predict_proba(X_validation)
        threshold, _ = optimize_threshold(
            probabilities, y_validation.to_numpy(),
            objective=str(config.evaluation.decision_threshold_objective),
            fixed=float(config.evaluation.fixed_threshold),
        )
        calibrated.decision_threshold = threshold
    calibrated.metadata.update(
        {
            "train_end": str(train_end.date()),
            "n_train": len(X_train),
            "n_validation": len(X_validation),
            "n_features": features.shape[1],
        }
    )
    return calibrated
