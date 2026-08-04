"""End-to-end RAEMF-MC research pipeline."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from raemf_mc import CLASS_ORDER, HORIZONS
from raemf_mc.backtest.exposure import backtest_exposure
from raemf_mc.backtest.metrics import backtest_metrics
from raemf_mc.calibration.temperature_scaling import apply_temperature, fit_temperature
from raemf_mc.config import bayesian_config, write_config_snapshot
from raemf_mc.data.loader import load_price_data, sha256_file
from raemf_mc.evaluation.classification import evaluate_predictions
from raemf_mc.features.selection import select_features
from raemf_mc.features.technical import build_features
from raemf_mc.models.base import fill_features
from raemf_mc.models.ebm_forecaster import EBMForecaster
from raemf_mc.models.macd_baseline import (
    apply_macd_probability_table,
    fit_macd_probability_table,
    macd_deterministic,
)
from raemf_mc.models.random_forest_forecaster import RandomForestForecaster
from raemf_mc.models.xgboost_forecaster import XGBoostForecaster
from raemf_mc.regime.filtered_hmm import FilteredHMMResult, fit_filtered_hmm
from raemf_mc.reporting.plots import generate_all_plots
from raemf_mc.reporting.report_builder import build_docs_and_readme, build_run_report
from raemf_mc.risk.egarch_t import fit_egarch_features
from raemf_mc.simulation.structural_mc import simulate_paths_detailed
from raemf_mc.targets.regime_targets import create_multihorizon_targets
from raemf_mc.tuning.optuna_tuner import TuningResult, tune_ebm_random_search
from raemf_mc.uncertainty.block_bootstrap import bootstrap_prediction_differences
from raemf_mc.uncertainty.confidence import confidence_label, market_filter
from raemf_mc.uncertainty.drift import feature_drift
from raemf_mc.validation.leakage_checks import assert_no_future_feature_columns, assert_target_end_before_boundary
from raemf_mc.validation.purged_split import OuterSplit, make_outer_split


MAIN_MODELS = ["RAEMF-MC", "XGBoost (full features)", "Random Forest (full features)", "MACD probabilistic"]


def _git_metadata() -> dict[str, object]:
    def run(command: list[str]) -> str:
        try:
            return subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return ""

    return {
        "commit": run(["git", "rev-parse", "HEAD"]),
        "short_sha": run(["git", "rev-parse", "--short", "HEAD"]) or "nogit",
        "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "remote": run(["git", "remote", "get-url", "origin"]),
        "dirty": bool(run(["git", "status", "--short"])),
    }


def _run_dir() -> Path:
    metadata = _git_metadata()
    return Path("outputs/runs") / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{metadata['short_sha']}"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")


def _latest_refresh(run_dir: Path) -> None:
    latest = Path("outputs/latest")
    if latest.exists() or latest.is_symlink():
        if latest.is_symlink() or latest.is_file():
            latest.unlink()
        else:
            shutil.rmtree(latest)
    shutil.copytree(run_dir, latest)


def _numeric_hmm(result: FilteredHMMResult) -> pd.DataFrame:
    return result.probabilities.select_dtypes(include=[np.number])


def _prediction_frame(
    dates: pd.Series,
    actual: pd.Series,
    probability: np.ndarray,
    model: str,
    horizon: int,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(dates).to_numpy(),
            "horizon": horizon,
            "model": model,
            "actual": actual.astype(str).to_numpy(),
            "predicted": [CLASS_ORDER[index] for index in probability.argmax(axis=1)],
        }
    )
    for index, target_class in enumerate(CLASS_ORDER):
        frame[f"prob_{target_class}"] = probability[:, index]
    return frame


def _evaluate_and_collect(
    y_test: pd.Series,
    probability: np.ndarray,
    model: str,
    horizon: int,
    metrics_rows: list[dict[str, object]],
    class_rows: list[pd.DataFrame],
    confusion_rows: list[pd.DataFrame],
) -> None:
    metrics, class_metrics, confusion = evaluate_predictions(y_test, probability, model, horizon)
    metrics_rows.append(metrics)
    class_rows.append(class_metrics)
    confusion_rows.append(confusion)


def _fit_variant(
    features: pd.DataFrame,
    split: OuterSplit,
    target: pd.Series,
    seed: int,
    parameters: dict[str, object],
    config: dict[str, Any],
) -> tuple[np.ndarray, list[str]]:
    selected, _ = select_features(
        features,
        split.train,
        float(config["features"]["missing_threshold"]),
        float(config["features"]["correlation_threshold"]),
    )
    x_train, x_test = fill_features(features.loc[split.train, selected], features.loc[split.test, selected])
    model = EBMForecaster(seed, **parameters).fit(x_train, target.iloc[split.train])
    return model.predict_proba(x_test), selected


def _shape_values(model: EBMForecaster, x_train: pd.DataFrame, top_features: list[str]) -> pd.DataFrame:
    baseline = x_train.median(numeric_only=True).to_frame().T
    rows: list[dict[str, object]] = []
    for feature in top_features[:4]:
        if feature not in x_train or not pd.api.types.is_numeric_dtype(x_train[feature]):
            continue
        grid = np.unique(x_train[feature].quantile(np.linspace(0.05, 0.95, 21)).to_numpy(dtype=float))
        probe = pd.concat([baseline] * len(grid), ignore_index=True)
        probe = probe.reindex(columns=x_train.columns, fill_value=0.0)
        probe[feature] = grid
        probability = model.predict_proba(probe)
        for row_index, value in enumerate(grid):
            for class_index, target_class in enumerate(CLASS_ORDER):
                rows.append(
                    {
                        "feature": feature,
                        "value": float(value),
                        "class": target_class,
                        "probability": float(probability[row_index, class_index]),
                    }
                )
    return pd.DataFrame(rows)


def _local_explanation(
    model: EBMForecaster,
    latest: pd.DataFrame,
    training: pd.DataFrame,
    features: list[str],
) -> pd.DataFrame:
    latest_probability = model.predict_proba(latest)[0]
    medians = training.median(numeric_only=True)
    rows: list[dict[str, object]] = []
    for feature in features[:20]:
        counterfactual = latest.copy()
        counterfactual.loc[:, feature] = medians.get(feature, 0.0)
        counterfactual_probability = model.predict_proba(counterfactual)[0]
        for index, target_class in enumerate(CLASS_ORDER):
            rows.append(
                {
                    "feature": feature,
                    "class": target_class,
                    "contribution": float(latest_probability[index] - counterfactual_probability[index]),
                    "latest_value": float(latest.iloc[0][feature]),
                    "train_median": float(medians.get(feature, 0.0)),
                }
            )
    return pd.DataFrame(rows)


def _probability_exposure(probability: np.ndarray) -> np.ndarray:
    class_exposure = np.array([1.0, 0.50, 0.15, 0.0])
    return np.asarray(probability, dtype=float) @ class_exposure


def _build_oos_backtest(
    dates: pd.Series,
    close: pd.Series,
    model_probabilities: dict[str, np.ndarray],
    cost_bps: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    strategies: dict[str, np.ndarray] = {
        model: _probability_exposure(probability) for model, probability in model_probabilities.items()
    }
    strategies["Buy-and-Hold"] = np.ones(len(close), dtype=float)
    strategies["Cash"] = np.zeros(len(close), dtype=float)
    frames: list[pd.DataFrame] = []
    metrics: list[dict[str, object]] = []
    clean_close = pd.Series(close.to_numpy(dtype=float), index=np.arange(len(close)))
    clean_dates = pd.Series(pd.to_datetime(dates).to_numpy(), index=clean_close.index)
    for strategy, signal in strategies.items():
        bt = backtest_exposure(clean_close, pd.Series(signal, index=clean_close.index), cost_bps)
        bt.insert(0, "date", clean_dates)
        bt.insert(1, "strategy", strategy)
        bt["equity"] = np.exp(bt["strategy_return"].cumsum())
        bt["drawdown"] = bt["equity"] / bt["equity"].cummax() - 1.0
        rolling_mean = bt["strategy_return"].rolling(63, min_periods=20).mean()
        rolling_std = bt["strategy_return"].rolling(63, min_periods=20).std()
        bt["rolling_sharpe"] = rolling_mean / rolling_std.replace(0, np.nan) * np.sqrt(252)
        bt["cumulative_turnover"] = bt["turnover"].cumsum()
        frames.append(bt)
        metrics.append(backtest_metrics(bt, strategy))
    return pd.concat(frames, ignore_index=True), pd.DataFrame(metrics)


def _run_tuning(
    features: pd.DataFrame,
    target: pd.Series,
    dates: pd.Series,
    target_end_dates: pd.Series,
    split: OuterSplit,
    horizon: int,
    config: dict[str, Any],
    seed: int,
) -> TuningResult:
    selection_idx = np.sort(np.concatenate([split.train, split.validation]))
    tuning_config = config.get("tuning", {})
    if not bool(tuning_config.get("enabled", True)):
        return TuningResult(dict(config["models"]["ebm"]), float("nan"), pd.DataFrame(), pd.DataFrame(), 0.0)
    return tune_ebm_random_search(
        features.iloc[selection_idx].reset_index(drop=True),
        target.iloc[selection_idx].reset_index(drop=True),
        dates.iloc[selection_idx].reset_index(drop=True),
        target_end_dates.iloc[selection_idx].reset_index(drop=True),
        horizon=horizon,
        base_params=dict(config["models"]["ebm"]),
        n_trials=int(tuning_config.get("trials_per_horizon", 15)),
        n_folds=int(tuning_config.get("folds", 3)),
        seed=seed,
        validation_size=int(tuning_config.get("validation_size", 240)),
    )


def run_pipeline(data_path: str | Path, config: dict[str, Any]) -> Path:
    """Run the complete experiment and persist immutable artifacts."""
    started_at = datetime.now(timezone.utc)
    started = time.time()
    seed = int(config.get("runtime", {}).get("seed", 42))
    np.random.seed(seed)
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib-raemf"))
    run_dir = _run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "figures").mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    bayes_cfg = bayesian_config(config)
    bayesian_model: Any | None = None
    bayesian_fold_rows: list[dict[str, object]] = []

    prices, data_metadata = load_price_data(data_path)
    targeted = create_multihorizon_targets(
        prices,
        bull_threshold=float(config["target"]["bull_threshold"]),
        bear_threshold=float(config["target"]["bear_threshold"]),
        stress_threshold=float(config["target"]["stress_threshold"]),
        volatility_window=int(config["target"]["volatility_window"]),
    )
    technical, registry = build_features(targeted)
    returns = np.log(targeted["close"] / targeted["close"].shift(1))

    valid_60 = targeted["target_60"].notna()
    sixty = targeted.loc[valid_60].reset_index()
    split_60 = make_outer_split(
        sixty["date"],
        sixty["target_end_date_60"],
        float(config["split"]["train_fraction"]),
        float(config["split"]["validation_fraction"]),
    )
    evaluation_train_global = sixty["index"].to_numpy()[split_60.train]
    evaluation_hmm = fit_filtered_hmm(
        technical,
        returns,
        evaluation_train_global,
        int(config["hmm"]["n_states"]),
        list(config["hmm"]["seeds"]),
    )
    evaluation_risk = fit_egarch_features(returns, evaluation_train_global)
    warnings.extend(evaluation_hmm.diagnostics.get("warnings", []))
    warnings.extend(evaluation_risk.diagnostics.get("warnings", []))
    evaluation_features = pd.concat([technical, _numeric_hmm(evaluation_hmm), evaluation_risk.features], axis=1)
    assert_no_future_feature_columns(list(evaluation_features.columns))

    deployment_idx = np.arange(len(targeted), dtype=int)
    deployment_hmm = fit_filtered_hmm(
        technical,
        returns,
        deployment_idx,
        int(config["hmm"]["n_states"]),
        list(config["hmm"]["seeds"]),
    )
    deployment_risk = fit_egarch_features(returns, deployment_idx)
    deployment_features = pd.concat([technical, _numeric_hmm(deployment_hmm), deployment_risk.features], axis=1)

    if bool(bayes_cfg["enabled"]):
        from raemf_mc.bayesian.diagnostics import write_diagnostic_artifacts
        from raemf_mc.bayesian.variational import VariationalScenarioModel

        saved_posterior = bayes_cfg.get("use_saved_posterior")
        bayesian_started = time.perf_counter()
        tracemalloc.start()
        try:
            if saved_posterior:
                bayesian_model = VariationalScenarioModel.load(saved_posterior)
            else:
                bayesian_model = VariationalScenarioModel(bayes_cfg)
                deployment_probability_columns = [
                    column for column in deployment_hmm.probabilities if column.startswith("hmm_prob_state_")
                ]
                deployment_dates = pd.DatetimeIndex(targeted["date"])
                bayesian_model.fit(
                    pd.Series(returns.to_numpy(dtype=float), index=deployment_dates),
                    pd.DataFrame(
                        deployment_hmm.probabilities[deployment_probability_columns].to_numpy(dtype=float),
                        index=deployment_dates,
                        columns=deployment_probability_columns,
                    ),
                    pd.Series(
                        deployment_risk.features["egarch_sigma"].to_numpy(dtype=float),
                        index=deployment_dates,
                    ),
                    deployment_idx,
                    bayes_cfg,
                )
            expected_regimes = len(
                [column for column in deployment_hmm.probabilities if column.startswith("hmm_prob_state_")]
            )
            posterior_regimes = bayesian_model.result.posterior_samples["mu"].shape[1]
            if posterior_regimes != expected_regimes:
                raise ValueError(
                    f"Saved/fitted posterior has {posterior_regimes} regimes; current HMM has {expected_regimes}"
                )
            bayesian_model.save(run_dir / "bayesian")
            if not saved_posterior:
                write_diagnostic_artifacts(bayesian_model, run_dir / "bayesian")
            _, peak_bytes = tracemalloc.get_traced_memory()
            bayesian_fold_rows.append(
                {
                    "scope": "deployment",
                    "train_start": str(bayesian_model.result.train_date_range[0]),
                    "train_end": str(bayesian_model.result.train_date_range[1]),
                    "validation_start": "",
                    "validation_end": "",
                    "test_start": "",
                    "test_end": "",
                    "fit_status": "loaded" if saved_posterior else "fitted",
                    "elbo_final": float(bayesian_model.result.elbo_history[-1]),
                    "posterior_uncertainty_mean": float(
                        np.mean(
                            np.concatenate(
                                [value.ravel() for value in bayesian_model.result.posterior_standard_deviations.values()]
                            )
                        )
                    ),
                    "runtime_seconds": time.perf_counter() - bayesian_started,
                    "peak_memory_bytes": int(peak_bytes),
                    "effective_observations": ";".join(
                        f"{value:.4f}" for value in bayesian_model.result.effective_observations
                    ),
                    "convergence_status": bayesian_model.result.convergence_status,
                    "warning": "; ".join(bayesian_model.result.warnings),
                }
            )
        except Exception as exc:
            if tracemalloc.is_tracing():
                _, peak_bytes = tracemalloc.get_traced_memory()
            else:
                peak_bytes = 0
            message = f"Variational posterior deployment fit failed: {exc}"
            bayesian_fold_rows.append(
                {
                    "scope": "deployment",
                    "fit_status": "fallback_point_estimate",
                    "runtime_seconds": time.perf_counter() - bayesian_started,
                    "peak_memory_bytes": int(peak_bytes),
                    "warning": message,
                }
            )
            if bool(bayes_cfg["fallback_to_point_estimate"]):
                warnings.append(message)
                bayesian_model = None
            else:
                raise
        finally:
            if tracemalloc.is_tracing():
                tracemalloc.stop()

    registry.to_frame().to_csv(run_dir / "feature_registry.csv", index=False)
    evaluation_hmm.state_mapping.to_csv(run_dir / "hmm_state_mapping.csv", index=False)
    deployment_hmm.state_mapping.to_csv(run_dir / "hmm_state_mapping_deployment.csv", index=False)
    hmm_artifact = evaluation_hmm.probabilities.copy()
    hmm_artifact.insert(0, "date", targeted["date"].to_numpy())
    hmm_artifact.to_csv(run_dir / "hmm_filtered_probabilities.csv", index=False)
    risk_artifact = evaluation_risk.features.copy()
    risk_artifact.insert(0, "date", targeted["date"].to_numpy())
    risk_artifact.to_csv(run_dir / "egarch_features.csv", index=False)
    (run_dir / "data_sha256.txt").write_text(sha256_file(data_path) + "\n", encoding="utf-8", newline="\n")
    write_config_snapshot(config, run_dir / "config_snapshot.yaml")
    git_metadata = _git_metadata()
    _write_json(run_dir / "git_metadata.json", git_metadata)
    (run_dir / "environment.txt").write_text(
        f"python={platform.python_version()}\nos={platform.platform()}\nseed={seed}\n",
        encoding="utf-8",
        newline="\n",
    )
    split_boundaries = {
        "horizon_reference": 60,
        "validation_start": split_60.validation_start.strftime("%Y-%m-%d"),
        "test_start": split_60.test_start.strftime("%Y-%m-%d"),
        "test_end": sixty["date"].iloc[split_60.test[-1]].strftime("%Y-%m-%d"),
    }
    _write_json(run_dir / "split_boundaries.json", split_boundaries)

    metric_rows: list[dict[str, object]] = []
    class_rows: list[pd.DataFrame] = []
    confusion_rows: list[pd.DataFrame] = []
    prediction_rows: list[pd.DataFrame] = []
    ablation_rows: list[dict[str, object]] = []
    selected_rows: list[pd.DataFrame] = []
    tuning_trial_rows: list[pd.DataFrame] = []
    walk_forward_rows: list[pd.DataFrame] = []
    calibration_rows: list[dict[str, object]] = []
    macd_table_rows: list[pd.DataFrame] = []
    best_parameters: dict[str, object] = {}
    evaluation_metadata: dict[str, object] = {"scope": "train -> validation calibration -> final test", "horizons": {}}
    deployment_metadata: dict[str, object] = {"scope": "refit on all currently labeled observations after parameter lock", "horizons": {}}
    latest_outlook: dict[str, object] = {
        "as_of_date": targeted["date"].iloc[-1].strftime("%Y-%m-%d"),
        "last_close": float(targeted["close"].iloc[-1]),
        "horizons": {},
        "note": "Không phải lời khuyên đầu tư.",
    }
    backtest_inputs: tuple[pd.Series, pd.Series, dict[str, np.ndarray]] | None = None

    for horizon in HORIZONS:
        valid = targeted[f"target_{horizon}"].notna()
        sub = targeted.loc[valid].reset_index()
        technical_sub = technical.loc[sub["index"]].reset_index(drop=True)
        hmm_sub = _numeric_hmm(evaluation_hmm).loc[sub["index"]].reset_index(drop=True)
        risk_sub = evaluation_risk.features.loc[sub["index"]].reset_index(drop=True)
        full_sub = pd.concat([technical_sub, hmm_sub, risk_sub], axis=1)
        split = make_outer_split(
            sub["date"],
            sub[f"target_end_date_{horizon}"],
            float(config["split"]["train_fraction"]),
            float(config["split"]["validation_fraction"]),
        )
        assert_target_end_before_boundary(sub[f"target_end_date_{horizon}"], split.train, split.validation_start, f"train h={horizon}")
        assert_target_end_before_boundary(sub[f"target_end_date_{horizon}"], split.validation, split.test_start, f"validation h={horizon}")

        if bool(bayes_cfg["enabled"]) and not bayes_cfg.get("use_saved_posterior"):
            from raemf_mc.bayesian.variational import VariationalScenarioModel

            fold_started = time.perf_counter()
            tracemalloc.start()
            fold_status = "fitted"
            fold_warning = ""
            fold_model: Any | None = None
            try:
                probability_columns = [column for column in hmm_sub if column.startswith("hmm_prob_state_")]
                fold_dates = pd.DatetimeIndex(sub["date"])
                fold_model = VariationalScenarioModel(bayes_cfg)
                fold_model.fit(
                    pd.Series(returns.loc[sub["index"]].to_numpy(dtype=float), index=fold_dates),
                    pd.DataFrame(
                        hmm_sub[probability_columns].to_numpy(dtype=float),
                        index=fold_dates,
                        columns=probability_columns,
                    ),
                    pd.Series(risk_sub["egarch_sigma"].to_numpy(dtype=float), index=fold_dates),
                    split.train,
                    bayes_cfg,
                )
                fold_model.save(run_dir / "bayesian" / "folds" / f"horizon_{horizon}")
            except Exception as exc:
                fold_status = "fallback_point_estimate"
                fold_warning = str(exc)
                if not bool(bayes_cfg["fallback_to_point_estimate"]):
                    raise
                warnings.append(f"Variational posterior h={horizon} fit failed: {exc}")
            _, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            bayesian_fold_rows.append(
                {
                    "scope": f"outer_evaluation_h{horizon}",
                    "horizon": horizon,
                    "train_start": sub["date"].iloc[split.train[0]].strftime("%Y-%m-%d"),
                    "train_end": sub["date"].iloc[split.train[-1]].strftime("%Y-%m-%d"),
                    "validation_start": sub["date"].iloc[split.validation[0]].strftime("%Y-%m-%d"),
                    "validation_end": sub["date"].iloc[split.validation[-1]].strftime("%Y-%m-%d"),
                    "test_start": sub["date"].iloc[split.test[0]].strftime("%Y-%m-%d"),
                    "test_end": sub["date"].iloc[split.test[-1]].strftime("%Y-%m-%d"),
                    "fit_status": fold_status,
                    "elbo_final": (
                        float(fold_model.result.elbo_history[-1])
                        if fold_model is not None and fold_model.result is not None
                        else float("nan")
                    ),
                    "posterior_uncertainty_mean": (
                        float(
                            np.mean(
                                np.concatenate(
                                    [value.ravel() for value in fold_model.result.posterior_standard_deviations.values()]
                                )
                            )
                        )
                        if fold_model is not None and fold_model.result is not None
                        else float("nan")
                    ),
                    "runtime_seconds": time.perf_counter() - fold_started,
                    "peak_memory_bytes": int(peak_bytes),
                    "effective_observations": (
                        ";".join(f"{value:.4f}" for value in fold_model.result.effective_observations)
                        if fold_model is not None and fold_model.result is not None
                        else ""
                    ),
                    "convergence_status": (
                        fold_model.result.convergence_status
                        if fold_model is not None and fold_model.result is not None
                        else "failed"
                    ),
                    "warning": fold_warning,
                }
            )
        target = sub[f"target_{horizon}"].astype(str)
        selected, removed = select_features(
            full_sub,
            split.train,
            float(config["features"]["missing_threshold"]),
            float(config["features"]["correlation_threshold"]),
        )
        selected_rows.append(pd.DataFrame({"horizon": horizon, "feature": selected, "status": "selected"}))
        if not removed.empty:
            removed = removed.copy()
            removed.insert(0, "horizon", horizon)
            removed["status"] = "removed"
            selected_rows.append(removed)

        tuning = _run_tuning(
            full_sub[selected],
            target,
            sub["date"],
            sub[f"target_end_date_{horizon}"],
            split,
            horizon,
            config,
            seed,
        )
        best_parameters[str(horizon)] = {
            "parameters": tuning.best_params,
            "objective": tuning.best_objective,
            "runtime_seconds": tuning.runtime_seconds,
            "trials": int(len(tuning.trials)),
            "pruned": int((tuning.trials.get("status", pd.Series(dtype=str)) != "complete").sum()),
        }
        if not tuning.trials.empty:
            tuning_trial_rows.append(tuning.trials)
            best_trial = int(tuning.trials.loc[tuning.trials["objective"].idxmin(), "trial"])
            fold_metrics = tuning.fold_metrics.copy()
            fold_metrics["is_best_trial"] = fold_metrics["trial"] == best_trial
            walk_forward_rows.append(fold_metrics)

        x_train, x_validation, x_test, x_all = fill_features(
            full_sub.loc[split.train, selected],
            full_sub.loc[split.validation, selected],
            full_sub.loc[split.test, selected],
            full_sub[selected],
        )
        y_train = target.iloc[split.train]
        y_validation = target.iloc[split.validation]
        y_test = target.iloc[split.test]
        models = {
            "RAEMF-MC": EBMForecaster(seed, **tuning.best_params).fit(x_train, y_train),
            "XGBoost (full features)": XGBoostForecaster(seed, **config["models"]["xgboost"]).fit(x_train, y_train, x_validation, y_validation),
            "Random Forest (full features)": RandomForestForecaster(seed, **config["models"]["random_forest"]).fit(x_train, y_train),
        }
        probabilities: dict[str, dict[str, np.ndarray]] = {}
        temperatures: dict[str, float] = {}
        for model_name, model in models.items():
            raw_validation = model.predict_proba(x_validation)
            raw_test = model.predict_proba(x_test)
            temperature, validation_loss, use_calibration = fit_temperature(raw_validation, y_validation)
            calibrated_validation = apply_temperature(raw_validation, temperature) if use_calibration else raw_validation
            calibrated_test = apply_temperature(raw_test, temperature) if use_calibration else raw_test
            probabilities[model_name] = {
                "validation": calibrated_validation,
                "test": calibrated_test,
                "raw_test": raw_test,
            }
            temperatures[model_name] = temperature if use_calibration else 1.0
            before, _, _ = evaluate_predictions(y_validation, raw_validation, f"{model_name} raw", horizon)
            after, _, _ = evaluate_predictions(y_validation, calibrated_validation, model_name, horizon)
            calibration_rows.append(
                {
                    "horizon": horizon,
                    "model": model_name,
                    "temperature": temperatures[model_name],
                    "used": use_calibration,
                    "validation_log_loss_optimizer": validation_loss,
                    "brier_before": before["brier"],
                    "brier_after": after["brier"],
                    "log_loss_before": before["log_loss"],
                    "log_loss_after": after["log_loss"],
                    "ece_before": before["ece"],
                    "ece_after": after["ece"],
                }
            )
            if isinstance(model, EBMForecaster) and model.warning:
                warnings.append(model.warning)

        macd_signal = macd_deterministic(sub["close"], sub["target_sigma"])
        macd_table = fit_macd_probability_table(macd_signal.iloc[split.validation], y_validation)
        macd_probability = apply_macd_probability_table(macd_signal, macd_table).to_numpy()
        probabilities["MACD probabilistic"] = {
            "validation": macd_probability[split.validation],
            "test": macd_probability[split.test],
            "raw_test": macd_probability[split.test],
        }
        table_long = macd_table.rename_axis("signal").reset_index().melt(id_vars="signal", var_name="target", value_name="probability")
        table_long.insert(0, "horizon", horizon)
        macd_table_rows.append(table_long)

        for model_name in MAIN_MODELS:
            probability = probabilities[model_name]["test"]
            _evaluate_and_collect(y_test, probability, model_name, horizon, metric_rows, class_rows, confusion_rows)
            prediction_rows.append(_prediction_frame(sub["date"].iloc[split.test], y_test, probability, model_name, horizon))
        raw_raemf = probabilities["RAEMF-MC"]["raw_test"]
        prediction_rows.append(
            _prediction_frame(sub["date"].iloc[split.test], y_test, raw_raemf, "RAEMF-MC uncalibrated", horizon)
        )

        architecture_probabilities: dict[str, np.ndarray] = {}
        architecture_probabilities["technical features only"], _ = _fit_variant(
            technical_sub,
            split,
            target,
            seed,
            tuning.best_params,
            config,
        )
        architecture_probabilities["technical + HMM"], _ = _fit_variant(
            pd.concat([technical_sub, hmm_sub], axis=1), split, target, seed, tuning.best_params, config
        )
        architecture_probabilities["technical + EGARCH"], _ = _fit_variant(
            pd.concat([technical_sub, risk_sub], axis=1), split, target, seed, tuning.best_params, config
        )
        architecture_probabilities["technical + HMM + EGARCH"] = raw_raemf
        architecture_probabilities["technical + HMM + EGARCH + calibration"] = probabilities["RAEMF-MC"]["test"]
        architecture_probabilities["full RAEMF-MC + Monte Carlo"] = probabilities["RAEMF-MC"]["test"]

        technical_selected, _ = select_features(
            technical_sub,
            split.train,
            float(config["features"]["missing_threshold"]),
            float(config["features"]["correlation_threshold"]),
        )
        tech_train, tech_validation, tech_test = fill_features(
            technical_sub.loc[split.train, technical_selected],
            technical_sub.loc[split.validation, technical_selected],
            technical_sub.loc[split.test, technical_selected],
        )
        architecture_probabilities["XGBoost technical only"] = XGBoostForecaster(
            seed, **config["models"]["xgboost"]
        ).fit(tech_train, y_train, tech_validation, y_validation).predict_proba(tech_test)
        architecture_probabilities["Random Forest technical only"] = RandomForestForecaster(
            seed, **config["models"]["random_forest"]
        ).fit(tech_train, y_train).predict_proba(tech_test)
        architecture_probabilities["MACD probabilistic"] = probabilities["MACD probabilistic"]["test"]
        for configuration, probability in architecture_probabilities.items():
            row, _, _ = evaluate_predictions(y_test, probability, configuration, horizon)
            row["configuration"] = row.pop("model")
            ablation_rows.append(row)

        deployment_sub_features = deployment_features.loc[sub["index"]].reset_index(drop=True)
        deployment_selected, _ = select_features(
            deployment_sub_features,
            np.arange(len(deployment_sub_features)),
            float(config["features"]["missing_threshold"]),
            float(config["features"]["correlation_threshold"]),
        )
        deployment_training, deployment_latest = fill_features(
            deployment_sub_features[deployment_selected],
            deployment_features.loc[[targeted.index[-1]], deployment_selected],
        )
        deployment_model = EBMForecaster(seed, **tuning.best_params).fit(deployment_training, target)
        latest_raw = deployment_model.predict_proba(deployment_latest)
        latest_probability = apply_temperature(latest_raw, temperatures["RAEMF-MC"])[0]
        entropy = float(-(latest_probability * np.log(np.clip(latest_probability, 1e-12, 1.0))).sum())
        ordered = np.sort(latest_probability)
        margin = float(ordered[-1] - ordered[-2])
        hmm_entropy = float(deployment_hmm.probabilities["hmm_entropy"].iloc[-1])
        confidence = confidence_label(latest_probability, hmm_entropy)
        latest_outlook["horizons"][str(horizon)] = {
            "probabilities": {target_class: float(latest_probability[index]) for index, target_class in enumerate(CLASS_ORDER)},
            "predicted_class": CLASS_ORDER[int(latest_probability.argmax())],
            "confidence": confidence,
            "entropy": entropy,
            "margin": margin,
            "market_filter": market_filter(latest_probability, confidence, config["market_filter"]),
        }
        importance = deployment_model.importance().head(30)
        importance.to_csv(run_dir / f"feature_importance_RAEMF-MC_{horizon}.csv", index=False)
        top_features = [feature for feature in importance["feature"].astype(str).tolist() if feature in deployment_selected]
        _shape_values(deployment_model, deployment_training, top_features).to_csv(
            run_dir / f"ebm_shape_values_{horizon}.csv", index=False
        )
        _local_explanation(deployment_model, deployment_latest, deployment_training, top_features).to_csv(
            run_dir / f"local_explanation_{horizon}.csv", index=False
        )

        evaluation_metadata["horizons"][str(horizon)] = {
            "train_start": sub["date"].iloc[split.train[0]].strftime("%Y-%m-%d"),
            "train_end": sub["date"].iloc[split.train[-1]].strftime("%Y-%m-%d"),
            "validation_start": sub["date"].iloc[split.validation[0]].strftime("%Y-%m-%d"),
            "validation_end": sub["date"].iloc[split.validation[-1]].strftime("%Y-%m-%d"),
            "test_start": sub["date"].iloc[split.test[0]].strftime("%Y-%m-%d"),
            "test_end": sub["date"].iloc[split.test[-1]].strftime("%Y-%m-%d"),
            "selected_feature_count": len(selected),
            "temperature": temperatures["RAEMF-MC"],
        }
        deployment_metadata["horizons"][str(horizon)] = {
            "fit_start": sub["date"].iloc[0].strftime("%Y-%m-%d"),
            "fit_end": sub["date"].iloc[-1].strftime("%Y-%m-%d"),
            "prediction_date": targeted["date"].iloc[-1].strftime("%Y-%m-%d"),
            "labeled_observations": len(sub),
            "selected_feature_count": len(deployment_selected),
            "calibration_source": "locked temperature learned on evaluation validation",
        }
        if horizon == 20:
            backtest_inputs = (
                sub["date"].iloc[split.test].reset_index(drop=True),
                sub["close"].iloc[split.test].reset_index(drop=True),
                {model: probabilities[model]["test"] for model in MAIN_MODELS},
            )

    metrics = pd.DataFrame(metric_rows)
    predictions = pd.concat(prediction_rows, ignore_index=True)
    metrics.to_csv(run_dir / "metrics_by_model_horizon.csv", index=False)
    pd.concat(class_rows, ignore_index=True).to_csv(run_dir / "class_metrics.csv", index=False)
    pd.concat(confusion_rows, ignore_index=True).to_csv(run_dir / "confusion_matrices.csv", index=False)
    predictions.to_csv(run_dir / "predictions_test.csv", index=False)
    pd.DataFrame(ablation_rows).to_csv(run_dir / "ablation_metrics.csv", index=False)
    pd.concat(selected_rows, ignore_index=True).to_csv(run_dir / "selected_features.csv", index=False)
    pd.concat(tuning_trial_rows, ignore_index=True).to_csv(run_dir / "tuning_trials.csv", index=False)
    pd.concat(walk_forward_rows, ignore_index=True).to_csv(run_dir / "walk_forward_metrics.csv", index=False)
    pd.DataFrame(calibration_rows).to_csv(run_dir / "calibration_comparison.csv", index=False)
    pd.concat(macd_table_rows, ignore_index=True).to_csv(run_dir / "macd_probability_mapping.csv", index=False)
    _write_json(run_dir / "best_parameters.json", best_parameters)
    _write_json(run_dir / "evaluation_model_metadata.json", evaluation_metadata)
    _write_json(run_dir / "deployment_model_metadata.json", deployment_metadata)
    if bayesian_fold_rows:
        pd.DataFrame(bayesian_fold_rows).to_csv(run_dir / "bayesian_fold_metadata.csv", index=False)

    bootstrap = bootstrap_prediction_differences(
        predictions[predictions["model"].isin(MAIN_MODELS)],
        "RAEMF-MC",
        ["XGBoost (full features)", "Random Forest (full features)", "MACD probabilistic"],
        int(config["bootstrap"]["metric_replicates"]),
        int(config["bootstrap"]["block_length"]),
        seed,
    )
    bootstrap.to_csv(run_dir / "bootstrap_differences.csv", index=False)
    bootstrap.rename(columns={"mean_diff": "metric_diff_mean"}).to_csv(run_dir / "metrics_confidence_intervals.csv", index=False)

    transition = np.asarray(deployment_hmm.diagnostics["transition_matrix"], dtype=float)
    probability_columns = [column for column in deployment_hmm.probabilities if column.startswith("hmm_prob_state_")]
    state_probability = deployment_hmm.probabilities[probability_columns].iloc[-1].to_numpy(dtype=float)
    state_mean = np.asarray(deployment_hmm.diagnostics["state_mean"], dtype=float)
    state_volatility = np.asarray(deployment_hmm.diagnostics["state_volatility"], dtype=float)
    monte_carlo_rows: list[pd.DataFrame] = []
    state_distribution_rows: list[pd.DataFrame] = []
    monte_carlo_comparison_rows: list[pd.DataFrame] = []
    for horizon in HORIZONS:
        target_probability = np.array(
            [latest_outlook["horizons"][str(horizon)]["probabilities"][target_class] for target_class in CLASS_ORDER]
        )
        simulation = simulate_paths_detailed(
            float(targeted["close"].iloc[-1]),
            state_probability,
            transition,
            state_mean,
            float(deployment_risk.features["egarch_sigma"].iloc[-1]),
            horizon,
            int(config["monte_carlo"]["paths"]),
            seed,
            state_volatility=state_volatility,
            egarch_params=dict(deployment_risk.diagnostics.get("params", {})),
            nu=float(deployment_risk.diagnostics.get("nu", 8.0)),
            target_class_probabilities=target_probability,
            state_to_class=np.arange(len(state_probability)) % len(CLASS_ORDER),
            scenario_mode="point_estimate",
        )
        simulation.quantiles.to_csv(run_dir / f"monte_carlo_quantiles_{horizon}.csv", index=False)
        monte_carlo_rows.append(simulation.summary)
        monte_carlo_comparison_rows.append(simulation.summary)
        state_distribution_rows.append(simulation.state_distribution)
        if bayesian_model is not None:
            posterior_draws = bayesian_model.sample_parameters(
                int(config["monte_carlo"]["paths"]),
                seed + horizon,
            )
            for scenario_mode in ("posterior_mean_mc", "variational_posterior"):
                scenario_parameters = (
                    bayesian_model.result.posterior_samples
                    if scenario_mode == "posterior_mean_mc"
                    else posterior_draws
                )
                scenario = simulate_paths_detailed(
                    float(targeted["close"].iloc[-1]),
                    state_probability,
                    transition,
                    state_mean,
                    float(deployment_risk.features["egarch_sigma"].iloc[-1]),
                    horizon,
                    int(config["monte_carlo"]["paths"]),
                    seed,
                    state_volatility=state_volatility,
                    egarch_params=dict(deployment_risk.diagnostics.get("params", {})),
                    nu=float(deployment_risk.diagnostics.get("nu", 8.0)),
                    target_class_probabilities=target_probability,
                    state_to_class=np.arange(len(state_probability)) % len(CLASS_ORDER),
                    scenario_mode=scenario_mode,
                    parameter_draws=scenario_parameters,
                )
                scenario.quantiles.to_csv(
                    run_dir / f"monte_carlo_quantiles_{scenario_mode}_{horizon}.csv",
                    index=False,
                )
                monte_carlo_comparison_rows.append(scenario.summary)
    pd.concat(monte_carlo_rows, ignore_index=True).to_csv(run_dir / "monte_carlo_summary.csv", index=False)
    pd.concat(state_distribution_rows, ignore_index=True).to_csv(run_dir / "monte_carlo_state_distribution.csv", index=False)
    monte_carlo_comparison = pd.concat(monte_carlo_comparison_rows, ignore_index=True)
    monte_carlo_comparison.to_csv(
        run_dir / "monte_carlo_comparison_summary.csv",
        index=False,
    )
    requested_scenario = str(config.get("monte_carlo", {}).get("scenario_mode", "point_estimate"))
    selected_scenario = monte_carlo_comparison[
        monte_carlo_comparison["scenario_mode"] == requested_scenario
    ]
    if selected_scenario.empty:
        warnings.append(
            f"Requested Monte Carlo scenario_mode={requested_scenario} unavailable; point_estimate selected"
        )
        selected_scenario = monte_carlo_comparison[
            monte_carlo_comparison["scenario_mode"] == "point_estimate"
        ]
    selected_scenario.to_csv(run_dir / "monte_carlo_selected_summary.csv", index=False)

    if backtest_inputs is None:
        raise RuntimeError("Horizon 20 did not produce OOS backtest inputs")
    backtest, backtest_summary = _build_oos_backtest(
        *backtest_inputs,
        float(config["backtest"]["transaction_cost_bps"]),
    )
    backtest.to_csv(run_dir / "backtest_timeseries.csv", index=False)
    backtest_summary.to_csv(run_dir / "backtest_metrics.csv", index=False)

    drift = feature_drift(
        evaluation_features.iloc[evaluation_train_global].fillna(0),
        evaluation_features.iloc[sixty["index"].to_numpy()[split_60.test]].fillna(0),
    )
    drift.to_csv(run_dir / "feature_drift.csv", index=False)
    _write_json(run_dir / "latest_outlook.json", latest_outlook)
    pd.DataFrame(
        [
            {
                "date": latest_outlook["as_of_date"],
                "horizon": horizon,
                **latest_outlook["horizons"][str(horizon)]["probabilities"],
                "predicted_class": latest_outlook["horizons"][str(horizon)]["predicted_class"],
                "confidence": latest_outlook["horizons"][str(horizon)]["confidence"],
                "entropy": latest_outlook["horizons"][str(horizon)]["entropy"],
                "margin": latest_outlook["horizons"][str(horizon)]["margin"],
                "market_filter": latest_outlook["horizons"][str(horizon)]["market_filter"],
            }
            for horizon in HORIZONS
        ]
    ).to_csv(run_dir / "predictions_latest.csv", index=False)
    _write_json(run_dir / "warnings.json", warnings)

    generate_all_plots(run_dir, data_path)
    build_run_report(run_dir)
    build_docs_and_readme(run_dir)
    finished_at = datetime.now(timezone.utc)
    _write_json(
        run_dir / "runtime.json",
        {
            "started_at_utc": started_at.isoformat(),
            "finished_at_utc": finished_at.isoformat(),
            "seconds": time.time() - started,
            "rows": len(prices),
            "mode": config.get("runtime", {}).get("mode", "unknown"),
            "seed": seed,
            "git_sha": git_metadata["commit"],
            "data_sha256": sha256_file(data_path),
            "data_meta": data_metadata,
        },
    )
    _latest_refresh(run_dir)
    return run_dir


def run_smoke_pipeline(prices: pd.DataFrame, seed: int = 7) -> dict[str, object]:
    """Run a lightweight in-memory integration path for CI fixtures."""
    targeted = create_multihorizon_targets(prices, horizons=[20])
    features, _ = build_features(targeted)
    valid = targeted["target_20"].notna()
    sub = targeted.loc[valid].reset_index(drop=True)
    x = features.loc[valid].reset_index(drop=True)
    split = make_outer_split(sub["date"], sub["target_end_date_20"], 0.60, 0.20)
    selected, _ = select_features(x, split.train, 0.50, 0.99)
    x_train, x_test = fill_features(x.loc[split.train, selected], x.loc[split.test, selected])
    target = sub["target_20"].astype(str)
    model = RandomForestForecaster(seed, n_estimators=20, max_depth=3).fit(x_train, target.iloc[split.train])
    probability = model.predict_proba(x_test)
    metrics, _, _ = evaluate_predictions(target.iloc[split.test], probability, "smoke", 20)
    return {"rows": len(prices), "features": len(selected), "probability_sum": probability.sum(axis=1), "metrics": metrics}
