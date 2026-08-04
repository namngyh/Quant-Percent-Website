"""Hyperparameter tuning (nested: outer = walk-forward OOS, inner = validation).

Optuna is used when installed; otherwise a small deterministic random search
runs instead so tuning never becomes a hard dependency.

The objective never optimises accuracy on an imbalanced target. Defaults are
Brier score (proper scoring rule) with AUPRC / composite alternatives.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger
from dynamicgraph.models.baselines import ModelSpec, sample_weights_from_labels

logger = get_logger(__name__)


def _has_optuna() -> bool:
    try:
        import optuna  # noqa: F401

        return True
    except Exception:
        return False


def objective_value(
    y_true: np.ndarray, probabilities: np.ndarray, objective: str = "brier"
) -> float:
    """Return a value to MINIMISE."""
    from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, matthews_corrcoef

    y = np.asarray(y_true, dtype=float)
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-7, 1 - 1e-7)
    mask = ~np.isnan(y) & ~np.isnan(p)
    y, p = y[mask], p[mask]
    if y.size < 20 or y.sum() == 0 or y.sum() == y.size:
        return float("inf")

    if objective == "brier":
        return float(brier_score_loss(y, p))
    if objective == "logloss":
        return float(log_loss(y, p, labels=[0, 1]))
    if objective == "auprc":
        return float(-average_precision_score(y, p))
    if objective == "mcc":
        return float(-matthews_corrcoef(y, (p >= 0.5).astype(int)))
    if objective == "composite":
        # Balance a proper scoring rule against ranking quality; both matter for
        # a dashboard that shows a probability AND an alert.
        brier = brier_score_loss(y, p)
        auprc = average_precision_score(y, p)
        base = y.mean()
        lift = auprc / base if base > 0 else 0.0
        return float(brier - 0.02 * lift)
    raise ValueError(f"Unknown tuning objective `{objective}`.")


def _sample(space: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for name, spec in space.items():
        kind = spec[0]
        if kind == "loguniform":
            low, high = float(spec[1]), float(spec[2])
            params[name] = float(np.exp(rng.uniform(np.log(low), np.log(high))))
        elif kind == "uniform":
            params[name] = float(rng.uniform(float(spec[1]), float(spec[2])))
        elif kind == "int":
            params[name] = int(rng.integers(int(spec[1]), int(spec[2]) + 1))
        elif kind == "categorical":
            params[name] = spec[1][int(rng.integers(0, len(spec[1])))]
    return params


def make_tuner(config: Any) -> Callable[..., dict[str, Any]] | None:
    """Return a tuner callable for `walk_forward.run_walk_forward`, or None."""
    if not bool(config.training.enable_tuning):
        return None

    mode = str(config.project.mode)
    n_trials = int(
        config.training.optuna_trials_fast if mode == "fast" else config.training.optuna_trials_full
    )
    objective = str(config.training.tuning_objective)
    use_optuna = _has_optuna()
    if not use_optuna:
        logger.info("Optuna not installed; using a deterministic random search instead.")

    def tuner(
        model_spec: ModelSpec,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_validation: pd.DataFrame,
        y_validation: pd.Series,
        seed: int = 42,
    ) -> dict[str, Any]:
        if not model_spec.search_space or len(X_validation) < 40 or y_validation.sum() < 5:
            return {}

        def evaluate(params: dict[str, Any]) -> float:
            estimator = model_spec.build(params, seed=seed)
            weights = sample_weights_from_labels(y_train.to_numpy(), config.models.class_weight)
            try:
                from dynamicgraph.training.walk_forward import _accepts_sample_weight

                if weights is not None and _accepts_sample_weight(estimator):
                    estimator.fit(X_train, y_train, model__sample_weight=weights)
                else:
                    estimator.fit(X_train, y_train)
                proba = estimator.predict_proba(X_validation)[:, 1]
            except Exception:
                return float("inf")
            return objective_value(y_validation.to_numpy(), proba, objective)

        if use_optuna:
            import optuna

            optuna.logging.set_verbosity(optuna.logging.WARNING)

            def optuna_objective(trial: Any) -> float:
                params: dict[str, Any] = {}
                for name, spec in model_spec.search_space.items():
                    kind = spec[0]
                    if kind == "loguniform":
                        params[name] = trial.suggest_float(name, spec[1], spec[2], log=True)
                    elif kind == "uniform":
                        params[name] = trial.suggest_float(name, spec[1], spec[2])
                    elif kind == "int":
                        params[name] = trial.suggest_int(name, spec[1], spec[2])
                    elif kind == "categorical":
                        params[name] = trial.suggest_categorical(name, spec[1])
                return evaluate(params)

            study = optuna.create_study(
                direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed)
            )
            study.optimize(optuna_objective, n_trials=n_trials, show_progress_bar=False)
            return dict(study.best_params)

        rng = np.random.default_rng(seed)
        best_params: dict[str, Any] = {}
        best_score = float("inf")
        for _ in range(n_trials):
            params = _sample(model_spec.search_space, rng)
            score = evaluate(params)
            if score < best_score:
                best_score, best_params = score, params
        return best_params

    return tuner
