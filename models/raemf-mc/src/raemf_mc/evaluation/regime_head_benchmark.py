"""OOS comparison of the Bayesian regime head against the production EBM.

Uses the same purged expanding-window folds as the distribution benchmark so
classification and distribution results are directly comparable. The EBM
stays the production classifier unless the Bayesian head beats it OOS in a
stable way — this module only produces the evidence, it never switches the
production model.

Ablation A (feature families) is run on the configured ablation horizons with
the EBM to answer: does HMM / EGARCH information improve regime forecasts?
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from raemf_mc import CLASS_ORDER, HORIZONS
from raemf_mc.calibration.temperature_scaling import apply_temperature, fit_temperature
from raemf_mc.config import write_config_snapshot
from raemf_mc.data.loader import load_price_data, sha256_file
from raemf_mc.evaluation.classification import evaluate_predictions
from raemf_mc.evaluation.oos_distribution_benchmark import make_distribution_folds
from raemf_mc.features.selection import select_features
from raemf_mc.features.technical import build_features
from raemf_mc.models.base import fill_features
from raemf_mc.models.bayesian_regime_head import BayesianRegimeHead
from raemf_mc.models.ebm_forecaster import EBMForecaster
from raemf_mc.models.macd_baseline import apply_macd_probability_table, fit_macd_probability_table, macd_deterministic
from raemf_mc.models.random_forest_forecaster import RandomForestForecaster
from raemf_mc.models.xgboost_forecaster import XGBoostForecaster
from raemf_mc.regime.filtered_hmm import fit_filtered_hmm
from raemf_mc.risk.egarch_t import fit_egarch_features
from raemf_mc.targets.regime_targets import create_multihorizon_targets
from raemf_mc.validation.leakage_checks import assert_target_end_before_boundary

OBJECTIVE_WEIGHTS = {
    "macro_f1": 0.30,
    "balanced_accuracy": 0.20,
    "recall_bear": 0.15,
    "recall_stress": 0.15,
    "one_minus_normalized_brier": 0.20,
}


def composite_objective(metrics: dict[str, object]) -> float:
    """J = 0.30 MacroF1 + 0.20 BalAcc + 0.15 RecBear + 0.15 RecStress + 0.20 (1 - Brier/2)."""
    return float(
        OBJECTIVE_WEIGHTS["macro_f1"] * float(metrics["macro_f1"])
        + OBJECTIVE_WEIGHTS["balanced_accuracy"] * float(metrics["balanced_accuracy"])
        + OBJECTIVE_WEIGHTS["recall_bear"] * float(metrics["recall_bear"])
        + OBJECTIVE_WEIGHTS["recall_stress"] * float(metrics["recall_stress"])
        + OBJECTIVE_WEIGHTS["one_minus_normalized_brier"] * (1.0 - float(metrics["brier"]) / 2.0)
    )


def _feature_families(columns: list[str]) -> dict[str, list[str]]:
    hmm = [c for c in columns if c.startswith("hmm_")]
    egarch = [c for c in columns if c.startswith("egarch_")]
    technical = [c for c in columns if c not in hmm and c not in egarch]
    return {
        "technical_only": technical,
        "technical_plus_hmm": technical + hmm,
        "technical_plus_egarch": technical + egarch,
        "full": columns,
    }


def run_regime_head_benchmark(
    data_path: str | Path,
    config: dict[str, Any],
    output_dir: str | Path,
) -> Path:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    write_config_snapshot(config, destination / "config_snapshot.yaml")
    head_cfg = dict(config.get("bayesian_regime_head", {}))
    benchmark = dict(config.get("distribution_benchmark", {}))
    n_folds = int(benchmark.get("n_folds", 3))
    test_fraction = float(benchmark.get("test_fraction", 0.30))
    validation_fraction = float(benchmark.get("validation_fraction", 0.10))
    horizons = [int(v) for v in benchmark.get("horizons", HORIZONS)]
    ablation_horizons = [int(v) for v in head_cfg.get("ablation_horizons", [20])]
    started = time.perf_counter()

    prices, data_metadata = load_price_data(data_path)
    targeted = create_multihorizon_targets(
        prices,
        horizons=horizons,
        bull_threshold=float(config["target"]["bull_threshold"]),
        bear_threshold=float(config["target"]["bear_threshold"]),
        stress_threshold=float(config["target"]["stress_threshold"]),
        volatility_window=int(config["target"]["volatility_window"]),
    )
    technical, _ = build_features(targeted)
    returns = np.log(targeted["close"] / targeted["close"].shift(1))

    metrics_rows: list[dict[str, object]] = []
    class_rows: list[pd.DataFrame] = []
    confusion_rows: list[pd.DataFrame] = []
    interval_rows: list[pd.DataFrame] = []
    seed_rows: list[pd.DataFrame] = []
    ablation_rows: list[dict[str, object]] = []

    for horizon in horizons:
        sub = targeted.loc[targeted[f"target_{horizon}"].notna()].reset_index()
        folds = make_distribution_folds(
            sub["date"],
            sub[f"target_end_date_{horizon}"],
            n_folds,
            test_fraction,
            validation_fraction,
        )
        for fold in folds:
            assert_target_end_before_boundary(
                sub[f"target_end_date_{horizon}"],
                fold.train,
                fold.validation_start,
                f"regime-head train h={horizon} fold={fold.fold}",
            )
            train_global = sub["index"].to_numpy()[fold.train]
            hmm = fit_filtered_hmm(
                technical,
                returns,
                train_global,
                int(config["hmm"]["n_states"]),
                list(config["hmm"]["seeds"]),
            )
            risk = fit_egarch_features(returns, train_global)
            probability_columns = [c for c in hmm.probabilities if c.startswith("hmm_prob_state_")]
            hmm_sub = hmm.probabilities[probability_columns].loc[sub["index"]].reset_index(drop=True)
            risk_sub = risk.features.loc[sub["index"]].reset_index(drop=True)
            technical_sub = technical.loc[sub["index"]].reset_index(drop=True)
            full_features = pd.concat([technical_sub, hmm_sub, risk_sub], axis=1)
            selected, _ = select_features(
                full_features,
                fold.train,
                float(config["features"]["missing_threshold"]),
                float(config["features"]["correlation_threshold"]),
            )
            x_train, x_validation, x_test = fill_features(
                full_features.loc[fold.train, selected],
                full_features.loc[fold.validation, selected],
                full_features.loc[fold.test, selected],
            )
            target = sub[f"target_{horizon}"].astype(str)
            y_train = target.iloc[fold.train]
            y_validation = target.iloc[fold.validation]
            y_test = target.iloc[fold.test]
            seed = int(config["runtime"]["seed"])

            model_probabilities: dict[str, np.ndarray] = {}
            ebm = EBMForecaster(seed, **config["models"]["ebm"]).fit(x_train, y_train)
            ebm_validation = ebm.predict_proba(x_validation)
            ebm_test = ebm.predict_proba(x_test)
            model_probabilities["EBM"] = ebm_test
            temperature, _, use_calibration = fit_temperature(ebm_validation, y_validation)
            model_probabilities["EBM calibrated"] = (
                apply_temperature(ebm_test, temperature) if use_calibration else ebm_test
            )
            xgb = XGBoostForecaster(seed, **config["models"]["xgboost"]).fit(x_train, y_train, x_validation, y_validation)
            model_probabilities["XGBoost"] = xgb.predict_proba(x_test)
            forest = RandomForestForecaster(seed, **config["models"]["random_forest"]).fit(x_train, y_train)
            model_probabilities["Random Forest"] = forest.predict_proba(x_test)
            volatility_proxy = returns.rolling(int(config["target"]["volatility_window"])).std()
            signals = macd_deterministic(targeted["close"], volatility_proxy)
            signals_sub = signals.loc[sub["index"]].reset_index(drop=True)
            table = fit_macd_probability_table(signals_sub.iloc[fold.validation], y_validation)
            macd_test = apply_macd_probability_table(signals_sub.iloc[fold.test], table).to_numpy(dtype=float)
            model_probabilities["MACD probabilistic"] = macd_test

            head = BayesianRegimeHead(
                max_features=int(head_cfg.get("max_features", 20)),
                seeds=tuple(int(s) for s in head_cfg.get("seeds", [11, 42, 73])),
                advi_steps=int(head_cfg.get("advi_steps", 6000)),
                posterior_draws=int(head_cfg.get("posterior_draws", 800)),
                learning_rate=float(head_cfg.get("learning_rate", 0.01)),
                device=str(head_cfg.get("device", config.get("bayesian", {}).get("device", "auto"))),
            ).fit(x_train, y_train)
            head_uncertainty = head.predict_with_uncertainty(x_test)
            head_test = head_uncertainty["mean"]
            model_probabilities["Bayesian regime head"] = head_test
            head_validation = head.predict_proba(x_validation)
            head_temperature, _, head_use_calibration = fit_temperature(head_validation, y_validation)
            if head_use_calibration:
                model_probabilities["Bayesian regime head calibrated"] = apply_temperature(
                    head_test, head_temperature
                )

            for model_name, probability in model_probabilities.items():
                metrics, class_metrics, confusion = evaluate_predictions(y_test, probability, model_name, horizon)
                metrics["fold"] = fold.fold
                metrics["objective_j"] = composite_objective(metrics)
                metrics_rows.append(metrics)
                class_metrics["fold"] = fold.fold
                class_rows.append(class_metrics)
                confusion["fold"] = fold.fold
                confusion_rows.append(confusion)

            interval = pd.DataFrame(
                {
                    "date": sub["date"].iloc[fold.test].to_numpy(),
                    "horizon": horizon,
                    "fold": fold.fold,
                    "actual": y_test.to_numpy(),
                    "epistemic_sd": head_uncertainty["epistemic_sd"],
                    "predictive_entropy": head_uncertainty["predictive_entropy"],
                }
            )
            for index, class_name in enumerate(CLASS_ORDER):
                interval[f"prob_{class_name}"] = head_uncertainty["mean"][:, index]
                interval[f"prob_{class_name}_q05"] = head_uncertainty["q05"][:, index]
                interval[f"prob_{class_name}_q95"] = head_uncertainty["q95"][:, index]
            interval_rows.append(interval)
            seeds = head.seed_summary()
            seeds.insert(0, "fold", fold.fold)
            seeds.insert(0, "horizon", horizon)
            seed_rows.append(seeds)

            if horizon in ablation_horizons:
                families = _feature_families(selected)
                for family, columns in families.items():
                    columns = [c for c in columns if c in x_train.columns]
                    if not columns:
                        continue
                    ablation_model = EBMForecaster(seed, **config["models"]["ebm"]).fit(
                        x_train[columns], y_train
                    )
                    ablation_probability = ablation_model.predict_proba(x_test[columns])
                    ablation_metrics, _, _ = evaluate_predictions(
                        y_test, ablation_probability, f"EBM [{family}]", horizon
                    )
                    ablation_metrics["fold"] = fold.fold
                    ablation_metrics["feature_family"] = family
                    ablation_metrics["n_features"] = len(columns)
                    ablation_metrics["objective_j"] = composite_objective(ablation_metrics)
                    ablation_rows.append(ablation_metrics)

    metrics = pd.DataFrame(metrics_rows)
    metrics.to_csv(destination / "classification_metrics.csv", index=False)
    aggregated = (
        metrics.groupby(["model", "horizon"], as_index=False)
        .agg({c: "mean" for c in metrics.select_dtypes(include=[np.number]).columns if c != "fold"})
    )
    aggregated.to_csv(destination / "classification_metrics_aggregated.csv", index=False)
    pd.concat(class_rows, ignore_index=True).to_csv(destination / "class_metrics.csv", index=False)
    pd.concat(confusion_rows, ignore_index=True).to_csv(destination / "confusion_matrices.csv", index=False)
    pd.concat(interval_rows, ignore_index=True).to_csv(destination / "probability_intervals.csv", index=False)
    pd.concat(seed_rows, ignore_index=True).to_csv(destination / "bayesian_head_seed_summary.csv", index=False)
    if ablation_rows:
        pd.DataFrame(ablation_rows).to_csv(destination / "feature_family_ablation.csv", index=False)
    runtime = {
        "seconds": time.perf_counter() - started,
        "horizons": horizons,
        "folds": n_folds,
        "data_sha256": sha256_file(data_path),
        "data_metadata": data_metadata,
        "objective_weights": OBJECTIVE_WEIGHTS,
    }
    (destination / "runtime.json").write_text(json.dumps(runtime, indent=2, default=str), encoding="utf-8")
    return destination
