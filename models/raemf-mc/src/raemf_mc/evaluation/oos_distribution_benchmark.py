"""Leakage-safe expanding-window OOS distribution benchmark."""

from __future__ import annotations

import json
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from raemf_mc import CLASS_ORDER, HORIZONS
from raemf_mc.bayesian.model import create_scenario_model
from raemf_mc.bayesian.variational import VariationalScenarioModel
from raemf_mc.calibration.temperature_scaling import apply_temperature, fit_temperature
from raemf_mc.config import bayesian_config, write_config_snapshot
from raemf_mc.data.loader import load_price_data, sha256_file
from raemf_mc.evaluation.classification import evaluate_predictions
from raemf_mc.evaluation.distribution import evaluate_point_forecast
from raemf_mc.evaluation.risk_backtests import christoffersen_conditional_coverage_test, kupiec_test
from raemf_mc.features.selection import select_features
from raemf_mc.features.technical import build_features
from raemf_mc.models.base import fill_features
from raemf_mc.models.ebm_forecaster import EBMForecaster
from raemf_mc.regime.filtered_hmm import fit_filtered_hmm
from raemf_mc.risk.egarch_t import fit_egarch_features
from raemf_mc.simulation.reweighting import weighted_quantile
from raemf_mc.simulation.structural_mc import simulate_paths_detailed
from raemf_mc.targets.regime_targets import create_multihorizon_targets
from raemf_mc.uncertainty.block_bootstrap import moving_block_indices
from raemf_mc.validation.leakage_checks import assert_target_end_before_boundary


@dataclass(frozen=True)
class DistributionFold:
    fold: int
    train: np.ndarray
    validation: np.ndarray
    test: np.ndarray
    validation_start: pd.Timestamp
    test_start: pd.Timestamp


def make_distribution_folds(
    dates: pd.Series,
    target_end_dates: pd.Series,
    n_folds: int = 3,
    test_fraction: float = 0.30,
    validation_fraction: float = 0.10,
) -> list[DistributionFold]:
    """Create non-overlapping OOS test blocks with expanding purged train sets."""
    n = len(dates)
    if n_folds < 1 or not 0 < test_fraction < 0.8 or not 0 < validation_fraction < 0.5:
        raise ValueError("Invalid fold count or benchmark fractions")
    first_test = int(n * (1.0 - test_fraction))
    validation_size = max(20, int(n * validation_fraction))
    boundaries = np.linspace(first_test, n, n_folds + 1, dtype=int)
    folds: list[DistributionFold] = []
    for fold in range(n_folds):
        test_start_pos = int(boundaries[fold])
        test_end_pos = int(boundaries[fold + 1])
        validation_start_pos = test_start_pos - validation_size
        if validation_start_pos <= 0 or test_end_pos <= test_start_pos:
            raise ValueError("Not enough observations for requested OOS folds")
        validation_start = pd.Timestamp(dates.iloc[validation_start_pos])
        test_start = pd.Timestamp(dates.iloc[test_start_pos])
        positions = np.arange(n)
        train = positions[
            (positions < validation_start_pos)
            & (target_end_dates < validation_start).to_numpy()
        ]
        validation = positions[
            (positions >= validation_start_pos)
            & (positions < test_start_pos)
            & (target_end_dates < test_start).to_numpy()
        ]
        test = positions[(positions >= test_start_pos) & (positions < test_end_pos)]
        if not len(train) or not len(validation) or not len(test):
            raise ValueError(f"Fold {fold} is empty after purging")
        folds.append(DistributionFold(fold, train, validation, test, validation_start, test_start))
    return folds


def _weighted_crps(observation: float, samples: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(samples)
    values = np.asarray(samples, dtype=float)[order]
    probability = np.asarray(weights, dtype=float)[order]
    probability = probability / probability.sum()
    first = float(np.sum(probability * np.abs(values - observation)))
    cumulative_weight = np.cumsum(probability) - probability
    cumulative_value = np.cumsum(probability * values) - probability * values
    half_pairwise = float(np.sum(probability * (values * cumulative_weight - cumulative_value)))
    return first - half_pairwise


def _weighted_distribution_row(
    observation: float,
    samples: np.ndarray,
    weights: np.ndarray,
) -> dict[str, float]:
    values = np.asarray(samples, dtype=float)
    probability = np.asarray(weights, dtype=float)
    probability = probability / probability.sum()
    mean = float(np.sum(values * probability))
    variance = float(np.sum(probability * (values - mean) ** 2))
    bandwidth = max(1.06 * np.sqrt(variance) * len(values) ** (-0.2), 1e-8)
    density = float(
        np.sum(
            probability
            * np.exp(-0.5 * ((observation - values) / bandwidth) ** 2)
            / (bandwidth * np.sqrt(2 * np.pi))
        )
    )
    result = {
        "actual_return": float(observation),
        "predicted_mean": mean,
        "nlpd": -float(np.log(max(density, 1e-300))),
        "crps": _weighted_crps(observation, values, probability),
        "pit": float(probability[values <= observation].sum()),
        "prob_negative_return": float(probability[values < 0].sum()),
    }
    quantiles = weighted_quantile(
        values,
        np.array([0.01, 0.025, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.975, 0.99]),
        probability,
    )
    for key, value in zip(
        ("q01", "q025", "q05", "q10", "q25", "q50", "q75", "q90", "q95", "q975", "q99"),
        quantiles,
        strict=True,
    ):
        result[key] = float(value)
    interval_levels = (0.50, 0.80, 0.90, 0.95)
    wis_terms = 0.5 * abs(observation - result["q50"])
    wis_weight_sum = 0.5
    for level in interval_levels:
        alpha = 1.0 - level
        lower, upper = weighted_quantile(values, np.array([alpha / 2, 1 - alpha / 2]), probability)
        key = int(level * 100)
        result[f"coverage_{key}"] = float(lower <= observation <= upper)
        result[f"width_{key}"] = float(upper - lower)
        interval_score = float(
            (upper - lower)
            + (2 / alpha) * (lower - observation) * (observation < lower)
            + (2 / alpha) * (observation - upper) * (observation > upper)
        )
        result[f"interval_score_{key}"] = interval_score
        wis_terms += (alpha / 2.0) * interval_score
        wis_weight_sum += 1.0
    # Weighted interval score (Bracher et al. 2021) over the configured levels.
    result["wis"] = float(wis_terms / wis_weight_sum)
    for alpha, name in ((0.05, "95"), (0.01, "99")):
        cut = float(weighted_quantile(values, np.array([alpha]), probability)[0])
        mask = values <= cut
        result[f"var_{name}"] = -cut
        result[f"expected_shortfall_{name}"] = -float(
            np.sum(values[mask] * probability[mask]) / max(probability[mask].sum(), 1e-12)
        )
    return result


def _realized_path_metrics(close: np.ndarray, origin: int, horizon: int) -> tuple[float, float]:
    path = np.asarray(close[origin : origin + horizon + 1], dtype=float)
    peak = np.maximum.accumulate(path)
    drawdown = path / peak - 1.0
    return float(drawdown.min()), float((drawdown[1:] < 0).sum())


def _summarize_seed(group: pd.DataFrame) -> dict[str, float]:
    point = evaluate_point_forecast(
        group["actual_return"].to_numpy(dtype=float),
        group["predicted_mean"].to_numpy(dtype=float),
    )
    summary: dict[str, float] = {
        "n_origins": float(len(group)),
        **point,
        "nlpd": float(group["nlpd"].mean()),
        "crps": float(group["crps"].mean()),
        "pit_mean": float(group["pit"].mean()),
        "pit_variance": float(group["pit"].var(ddof=1)),
        "realized_es95": -float(group.loc[group["actual_return"] <= group["q05"], "actual_return"].mean()),
        "forecast_es95": float(group["expected_shortfall_95"].mean()),
        "realized_es99": -float(group.loc[group["actual_return"] <= group["q01"], "actual_return"].mean()),
        "forecast_es99": float(group["expected_shortfall_99"].mean()),
        "drawdown_90_coverage": float(
            ((group["actual_max_drawdown"] >= group["mdd_q05"]) & (group["actual_max_drawdown"] <= group["mdd_q95"])).mean()
        ),
        "drawdown_95_coverage": float(
            ((group["actual_max_drawdown"] >= group["mdd_q025"]) & (group["actual_max_drawdown"] <= group["mdd_q975"])).mean()
        ),
        "time_under_water_mae": float(
            np.mean(np.abs(group["predicted_time_under_water"] - group["actual_time_under_water"]))
        ),
    }
    summary["wis"] = float(group["wis"].mean())
    negative = (group["actual_return"] < 0).to_numpy(dtype=float)
    summary["brier_negative_return"] = float(
        np.mean((group["prob_negative_return"].to_numpy(dtype=float) - negative) ** 2)
    )
    summary["realized_negative_rate"] = float(negative.mean())
    for threshold in (5, 10, 15):
        column = f"prob_drawdown_below_{threshold}pct"
        if column in group:
            event = (group["actual_max_drawdown"] <= -threshold / 100.0).to_numpy(dtype=float)
            summary[f"brier_drawdown_{threshold}pct"] = float(
                np.mean((group[column].to_numpy(dtype=float) - event) ** 2)
            )
            summary[f"realized_drawdown_{threshold}pct_rate"] = float(event.mean())
            summary[f"forecast_drawdown_{threshold}pct_rate"] = float(group[column].mean())
    for level in (50, 80, 90, 95):
        for metric in ("coverage", "width", "interval_score"):
            summary[f"{metric}_{level}"] = float(group[f"{metric}_{level}"].mean())
    for rate, quantile in ((0.05, "q05"), (0.01, "q01")):
        hits = (group["actual_return"] < group[quantile]).to_numpy()
        suffix = "95" if rate == 0.05 else "99"
        summary.update({f"kupiec_{suffix}_{key}": value for key, value in kupiec_test(hits, rate).items()})
        summary.update(
            {
                f"christoffersen_{suffix}_{key}": value
                for key, value in christoffersen_conditional_coverage_test(hits, rate).items()
            }
        )
    return summary


def bootstrap_distribution_differences(
    origins: pd.DataFrame,
    replicates: int = 500,
    block_length: int = 20,
    seed: int = 42,
) -> pd.DataFrame:
    """Paired moving-block CIs for VB minus each baseline on lower-is-better metrics."""
    data = origins.copy()
    data["var95_hit"] = (data["actual_return"] < data["q05"]).astype(float)
    data["var99_hit"] = (data["actual_return"] < data["q01"]).astype(float)
    data["drawdown90_hit"] = (
        (data["actual_max_drawdown"] >= data["mdd_q05"])
        & (data["actual_max_drawdown"] <= data["mdd_q95"])
    ).astype(float)
    data["drawdown95_hit"] = (
        (data["actual_max_drawdown"] >= data["mdd_q025"])
        & (data["actual_max_drawdown"] <= data["mdd_q975"])
    ).astype(float)
    if "prob_negative_return" in data:
        data["brier_negative"] = (
            data["prob_negative_return"] - (data["actual_return"] < 0).astype(float)
        ) ** 2
    for threshold in (5, 10, 15):
        if f"prob_drawdown_below_{threshold}pct" in data:
            data[f"brier_drawdown_{threshold}"] = (
                data[f"prob_drawdown_below_{threshold}pct"]
                - (data["actual_max_drawdown"] <= -threshold / 100.0).astype(float)
            ) ** 2
    averaged = (
        data.groupby(["horizon", "date", "fold", "scenario_mode"], as_index=False)
        .mean(numeric_only=True)
    )
    additive = [
        column
        for column in (
            "crps",
            "wis",
            "nlpd",
            "brier_negative",
            "brier_drawdown_5",
            "brier_drawdown_10",
            "brier_drawdown_15",
            "interval_score_50",
            "interval_score_80",
            "interval_score_90",
            "interval_score_95",
        )
        if column in data
    ]
    calibration = {
        "coverage_50_error": ("coverage_50", 0.50),
        "coverage_80_error": ("coverage_80", 0.80),
        "coverage_90_error": ("coverage_90", 0.90),
        "coverage_95_error": ("coverage_95", 0.95),
        "var95_rate_error": ("var95_hit", 0.05),
        "var99_rate_error": ("var99_hit", 0.01),
        "drawdown90_coverage_error": ("drawdown90_hit", 0.90),
        "drawdown95_coverage_error": ("drawdown95_hit", 0.95),
    }
    rows: list[dict[str, object]] = []
    rng = np.random.default_rng(seed)
    for horizon, horizon_frame in averaged.groupby("horizon"):
        for benchmark in ("point_estimate", "posterior_mean_mc"):
            vb = horizon_frame[horizon_frame["scenario_mode"] == "variational_posterior"].sort_values("date")
            base = horizon_frame[horizon_frame["scenario_mode"] == benchmark].sort_values("date")
            if not np.array_equal(vb["date"].to_numpy(), base["date"].to_numpy()):
                raise ValueError(f"Unaligned origin calendar for h={horizon}, benchmark={benchmark}")
            n = len(vb)
            indices = np.vstack(
                [moving_block_indices(n, block_length, rng) for _ in range(replicates)]
            )
            for metric in additive:
                differences = vb[metric].to_numpy(dtype=float) - base[metric].to_numpy(dtype=float)
                boot = differences[indices].mean(axis=1)
                low, high = np.quantile(boot, [0.025, 0.975])
                rows.append(
                    {
                        "horizon": int(horizon),
                        "benchmark": benchmark,
                        "metric": metric,
                        "mean_diff_vb_minus_benchmark": float(differences.mean()),
                        "ci_low": float(low),
                        "ci_high": float(high),
                        "ci_excludes_zero": bool(low > 0 or high < 0),
                        "lower_is_better": True,
                    }
                )
            for metric, (column, nominal) in calibration.items():
                vb_values = vb[column].to_numpy(dtype=float)
                base_values = base[column].to_numpy(dtype=float)
                observed = abs(vb_values.mean() - nominal) - abs(base_values.mean() - nominal)
                boot = (
                    np.abs(vb_values[indices].mean(axis=1) - nominal)
                    - np.abs(base_values[indices].mean(axis=1) - nominal)
                )
                low, high = np.quantile(boot, [0.025, 0.975])
                rows.append(
                    {
                        "horizon": int(horizon),
                        "benchmark": benchmark,
                        "metric": metric,
                        "mean_diff_vb_minus_benchmark": float(observed),
                        "ci_low": float(low),
                        "ci_high": float(high),
                        "ci_excludes_zero": bool(low > 0 or high < 0),
                        "lower_is_better": True,
                    }
                )
    return pd.DataFrame(rows)


def _fit_fold_components(
    targeted: pd.DataFrame,
    technical: pd.DataFrame,
    returns: pd.Series,
    sub: pd.DataFrame,
    fold: DistributionFold,
    horizon: int,
    config: dict[str, Any],
    destination: Path,
) -> tuple[Any, Any, VariationalScenarioModel, np.ndarray, dict[str, object]]:
    train_global = sub["index"].to_numpy()[fold.train]
    hmm = fit_filtered_hmm(
        technical,
        returns,
        train_global,
        int(config["hmm"]["n_states"]),
        list(config["hmm"]["seeds"]),
    )
    risk = fit_egarch_features(returns, train_global)
    probability_columns = [column for column in hmm.probabilities if column.startswith("hmm_prob_state_")]
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
    ebm = EBMForecaster(int(config["runtime"]["seed"]), **config["models"]["ebm"]).fit(
        x_train,
        target.iloc[fold.train],
    )
    validation_probability = ebm.predict_proba(x_validation)
    temperature, validation_loss, use_calibration = fit_temperature(
        validation_probability,
        target.iloc[fold.validation],
    )
    test_probability = ebm.predict_proba(x_test)
    if use_calibration:
        test_probability = apply_temperature(test_probability, temperature)
    bayes_cfg = bayesian_config(config)
    posterior = create_scenario_model(bayes_cfg)
    dates = pd.DatetimeIndex(sub["date"])
    posterior.fit(
        pd.Series(returns.loc[sub["index"]].to_numpy(dtype=float), index=dates),
        pd.DataFrame(hmm_sub.to_numpy(dtype=float), index=dates, columns=probability_columns),
        pd.Series(risk_sub["egarch_sigma"].to_numpy(dtype=float), index=dates),
        fold.train,
        bayes_cfg,
    )
    posterior.save(destination / "posterior")
    classification, _, _ = evaluate_predictions(
        target.iloc[fold.test],
        test_probability,
        "RAEMF-MC",
        horizon,
    )
    metadata: dict[str, object] = {
        "selected_features": len(selected),
        "temperature": temperature if use_calibration else 1.0,
        "calibration_used": use_calibration,
        "validation_log_loss": validation_loss,
        "classification": classification,
    }
    return hmm, risk, posterior, test_probability, metadata


def run_oos_distribution_benchmark(
    data_path: str | Path,
    config: dict[str, Any],
    output_dir: str | Path,
    *,
    resume: bool = True,
) -> Path:
    """Run every configured OOS origin and persist checkpointed metrics."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    previous_runtime: dict[str, Any] = {}
    runtime_path = destination / "runtime.json"
    if resume and runtime_path.exists():
        previous_runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    write_config_snapshot(config, destination / "config_snapshot.yaml")
    benchmark = dict(config.get("distribution_benchmark", {}))
    n_folds = int(benchmark.get("n_folds", 3))
    test_fraction = float(benchmark.get("test_fraction", 0.30))
    validation_fraction = float(benchmark.get("validation_fraction", 0.10))
    paths = int(benchmark.get("paths", config["monte_carlo"]["paths"]))
    seeds = [int(value) for value in benchmark.get("mc_seeds", [int(config["runtime"]["seed"])])]
    horizons = [int(value) for value in benchmark.get("horizons", HORIZONS)]
    modes = ["point_estimate", "posterior_mean_mc", "variational_posterior"]
    started = time.perf_counter()
    tracemalloc.start()
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
    close = targeted["close"].to_numpy(dtype=float)
    fold_metadata_rows: list[dict[str, object]] = []
    classification_rows: list[dict[str, object]] = []

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
                f"distribution train h={horizon} fold={fold.fold}",
            )
            assert_target_end_before_boundary(
                sub[f"target_end_date_{horizon}"],
                fold.validation,
                fold.test_start,
                f"distribution validation h={horizon} fold={fold.fold}",
            )
            fold_dir = destination / f"horizon_{horizon}" / f"fold_{fold.fold}"
            fold_dir.mkdir(parents=True, exist_ok=True)
            expected = [fold_dir / f"origin_metrics_seed_{seed}.csv" for seed in seeds]
            metadata_path = fold_dir / "fold_metadata.json"
            if resume and metadata_path.exists() and all(path.exists() for path in expected):
                stored_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                fold_metadata_rows.append(stored_metadata["fold"])
                classification_rows.append(stored_metadata["classification"])
                continue
            fold_started = time.perf_counter()
            hmm, risk, posterior, test_probability, fitted_metadata = _fit_fold_components(
                targeted,
                technical,
                returns,
                sub,
                fold,
                horizon,
                config,
                fold_dir,
            )
            transition = np.asarray(hmm.diagnostics["transition_matrix"], dtype=float)
            state_mean = np.asarray(hmm.diagnostics["state_mean"], dtype=float)
            state_volatility = np.asarray(hmm.diagnostics["state_volatility"], dtype=float)
            probability_columns = [column for column in hmm.probabilities if column.startswith("hmm_prob_state_")]
            posterior_mean = posterior.result.posterior_samples
            for seed in seeds:
                metric_rows: list[dict[str, object]] = []
                for test_offset, sub_position in enumerate(fold.test):
                    global_position = int(sub["index"].iloc[sub_position])
                    actual_return = float(sub[f"forward_return_{horizon}"].iloc[sub_position])
                    actual_mdd, actual_tuw = _realized_path_metrics(close, global_position, horizon)
                    current_state_probability = hmm.probabilities[probability_columns].iloc[
                        global_position
                    ].to_numpy(dtype=float)
                    target_probability = test_probability[test_offset]
                    joint_draws = posterior.sample_parameters(
                        paths,
                        seed + horizon * 100_000 + fold.fold * 10_000 + test_offset,
                    )
                    for mode in modes:
                        parameters = None
                        if mode == "posterior_mean_mc":
                            parameters = posterior_mean
                        elif mode == "variational_posterior":
                            parameters = joint_draws
                        simulation = simulate_paths_detailed(
                            float(close[global_position]),
                            current_state_probability,
                            transition,
                            state_mean,
                            float(risk.features["egarch_sigma"].iloc[global_position]),
                            horizon,
                            paths,
                            seed + test_offset,
                            state_volatility=state_volatility,
                            egarch_params=dict(risk.diagnostics.get("params", {})),
                            nu=float(risk.diagnostics.get("nu", 8.0)),
                            target_class_probabilities=target_probability,
                            state_to_class=np.arange(len(current_state_probability)) % len(CLASS_ORDER),
                            scenario_mode=mode,
                            parameter_draws=parameters,
                            lightweight=True,
                        )
                        row: dict[str, object] = {
                            "date": sub["date"].iloc[sub_position],
                            "horizon": horizon,
                            "fold": fold.fold,
                            "seed": seed,
                            "scenario_mode": mode,
                            **_weighted_distribution_row(
                                actual_return,
                                simulation.terminal_returns,
                                simulation.weights,
                            ),
                            "actual_max_drawdown": actual_mdd,
                            "actual_time_under_water": actual_tuw,
                        }
                        mdd = simulation.drawdown_paths.min(axis=1)
                        mdd_quantiles = weighted_quantile(
                            mdd,
                            np.array([0.025, 0.05, 0.50, 0.95, 0.975]),
                            simulation.weights,
                        )
                        for key, value in zip(
                            ("mdd_q025", "mdd_q05", "mdd_q50", "mdd_q95", "mdd_q975"),
                            mdd_quantiles,
                            strict=True,
                        ):
                            row[key] = float(value)
                        time_under_water = (simulation.drawdown_paths[:, 1:] < 0).sum(axis=1)
                        row["predicted_time_under_water"] = float(
                            np.sum(time_under_water * simulation.weights)
                        )
                        for threshold in (0.05, 0.10, 0.15, 0.20):
                            row[f"prob_drawdown_below_{int(threshold * 100)}pct"] = float(
                                simulation.weights[mdd <= -threshold].sum()
                            )
                        metric_rows.append(row)
                pd.DataFrame(metric_rows).to_csv(
                    fold_dir / f"origin_metrics_seed_{seed}.csv",
                    index=False,
                )
            fold_row = {
                "horizon": horizon,
                "fold": fold.fold,
                "train_start": str(sub["date"].iloc[fold.train[0]].date()),
                "train_end": str(sub["date"].iloc[fold.train[-1]].date()),
                "validation_start": str(sub["date"].iloc[fold.validation[0]].date()),
                "validation_end": str(sub["date"].iloc[fold.validation[-1]].date()),
                "test_start": str(sub["date"].iloc[fold.test[0]].date()),
                "test_end": str(sub["date"].iloc[fold.test[-1]].date()),
                "train_observations": len(fold.train),
                "validation_observations": len(fold.validation),
                "test_observations": len(fold.test),
                "posterior_status": posterior.result.convergence_status,
                "elbo_final": float(posterior.result.elbo_history[-1]),
                "effective_observations": ";".join(
                    f"{value:.4f}" for value in posterior.result.effective_observations
                ),
                "runtime_seconds": time.perf_counter() - fold_started,
            }
            classification = dict(fitted_metadata["classification"])
            classification["fold"] = fold.fold
            payload = {"fold": fold_row, "classification": classification}
            metadata_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            fold_metadata_rows.append(fold_row)
            classification_rows.append(classification)

    metric_files = sorted(destination.glob("horizon_*/fold_*/origin_metrics_seed_*.csv"))
    origins = pd.concat([pd.read_csv(path) for path in metric_files], ignore_index=True)
    origins.to_csv(destination / "origin_metrics.csv", index=False)
    by_seed_rows: list[dict[str, object]] = []
    for (horizon, mode, seed), group in origins.groupby(["horizon", "scenario_mode", "seed"]):
        by_seed_rows.append(
            {
                "horizon": int(horizon),
                "scenario_mode": str(mode),
                "seed": int(seed),
                **_summarize_seed(group.sort_values("date")),
            }
        )
    by_seed = pd.DataFrame(by_seed_rows)
    by_seed.to_csv(destination / "distribution_metrics_by_seed.csv", index=False)
    by_fold_rows: list[dict[str, object]] = []
    for (horizon, mode, fold, seed), group in origins.groupby(
        ["horizon", "scenario_mode", "fold", "seed"]
    ):
        by_fold_rows.append(
            {
                "horizon": int(horizon),
                "scenario_mode": str(mode),
                "fold": int(fold),
                "seed": int(seed),
                **_summarize_seed(group.sort_values("date")),
            }
        )
    pd.DataFrame(by_fold_rows).to_csv(destination / "distribution_metrics_by_fold_seed.csv", index=False)
    numeric = [
        column
        for column in by_seed.select_dtypes(include=[np.number]).columns
        if column not in {"horizon", "seed"}
    ]
    summary_rows: list[dict[str, object]] = []
    for (horizon, mode), group in by_seed.groupby(["horizon", "scenario_mode"]):
        row: dict[str, object] = {
            "horizon": int(horizon),
            "scenario_mode": str(mode),
            "seeds": len(group),
        }
        for column in numeric:
            row[column] = float(group[column].mean())
            row[f"{column}_seed_sd"] = float(group[column].std(ddof=1)) if len(group) > 1 else 0.0
        summary_rows.append(row)
    pd.DataFrame(summary_rows).to_csv(destination / "distribution_metrics_summary.csv", index=False)
    bootstrap_distribution_differences(
        origins,
        replicates=int(benchmark.get("bootstrap_replicates", 500)),
        block_length=int(benchmark.get("bootstrap_block_length", 20)),
        seed=int(config["runtime"]["seed"]),
    ).to_csv(destination / "bootstrap_distribution_differences.csv", index=False)
    pit = origins.copy()
    pit["pit_bin"] = pd.cut(pit["pit"], bins=np.linspace(0, 1, 11), include_lowest=True).astype(str)
    pit.groupby(["horizon", "scenario_mode", "seed", "pit_bin"], observed=False).size().rename("count").reset_index().to_csv(
        destination / "pit_histogram.csv",
        index=False,
    )
    pd.DataFrame(fold_metadata_rows).to_csv(destination / "fold_metadata.csv", index=False)
    pd.DataFrame(classification_rows).to_csv(destination / "classification_metrics.csv", index=False)
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    runtime = {
        "seconds": float(previous_runtime.get("seconds", 0.0)) + time.perf_counter() - started,
        "peak_python_traced_memory_bytes": max(
            int(previous_runtime.get("peak_python_traced_memory_bytes", 0)),
            int(peak_memory),
        ),
        "paths_per_origin": paths,
        "mc_seeds": seeds,
        "horizons": horizons,
        "folds": n_folds,
        "origin_rows": int(len(origins)),
        "unique_forecast_origins": int(origins[["date", "horizon", "fold"]].drop_duplicates().shape[0]),
        "data_sha256": sha256_file(data_path),
        "data_metadata": data_metadata,
    }
    runtime_path.write_text(
        json.dumps(runtime, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return destination
