"""Create immutable CPU Risk-off forecasts and mature only eligible history."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from raemf_mc import CLASS_ORDER
from raemf_mc.calibration.temperature_scaling import apply_temperature
from raemf_mc.data.loader import load_price_data, sha256_file
from raemf_mc.features.downside import build_downside_features
from raemf_mc.features.selection import select_features
from raemf_mc.features.technical import build_features
from raemf_mc.models.base import fill_features
from raemf_mc.models.ebm_forecaster import EBMForecaster
from raemf_mc.models.risk_off import BinaryTemperatureCalibrator, RiskOffHead, downside_sample_weights
from raemf_mc.regime.filtered_hmm import fit_filtered_hmm
from raemf_mc.risk.egarch_t import fit_egarch_features
from raemf_mc.runtime.cpu import configure_cpu_runtime
from raemf_mc.shadow.registry import append_forecasts, mature_forecasts
from raemf_mc.simulation.structural_mc import simulate_paths_detailed
from raemf_mc.targets.downside_targets import create_downside_targets
from raemf_mc.targets.regime_targets import create_multihorizon_targets


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "nogit"


def _checksum(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def update_shadow_registry(
    data_path: str | Path,
    config: dict[str, Any],
    *,
    registry_path: str | Path = "outputs/shadow_registry/forecast_registry.csv",
) -> Path:
    """Score matured records, then append one new immutable origin per horizon."""
    configure_cpu_runtime(config)
    experiment = dict(config["downside_experiment"])
    frozen_path = Path(str(experiment.get("frozen_artifact", "")))
    if not frozen_path.exists():
        raise FileNotFoundError(f"shadow-update requires a frozen downside artifact: {frozen_path}")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if frozen.get("acceptance_status") != "accepted_for_shadow_test":
        raise ValueError("Frozen candidate did not pass acceptance criteria; shadow forecast is not authorized")

    prices, _ = load_price_data(data_path)
    horizons = [int(value) for value in experiment["horizons"]]
    targeted = create_downside_targets(
        create_multihorizon_targets(
            prices,
            horizons=horizons,
            bull_threshold=float(config["target"]["bull_threshold"]),
            bear_threshold=float(config["target"]["bear_threshold"]),
            stress_threshold=float(config["target"]["stress_threshold"]),
            volatility_window=int(config["target"]["volatility_window"]),
        ),
        horizons=horizons,
        bear_threshold=float(config["target"]["bear_threshold"]),
        stress_threshold=float(config["target"]["stress_threshold"]),
    )
    technical, _ = build_features(targeted)
    returns = np.log(targeted["close"] / targeted["close"].shift(1))
    deployment_index = np.arange(len(targeted))
    hmm = fit_filtered_hmm(
        technical,
        returns,
        deployment_index,
        int(config["hmm"]["n_states"]),
        list(config["hmm"]["seeds"]),
    )
    risk = fit_egarch_features(returns, deployment_index)
    hmm_numeric = hmm.probabilities.select_dtypes(include=[np.number])
    downside = build_downside_features(
        targeted,
        hmm_probabilities=hmm_numeric,
        egarch_features=risk.features,
    )[0]
    base = pd.concat([technical, hmm_numeric, risk.features], axis=1)
    groups = {
        "base": base,
        "base_plus_downside_price": pd.concat(
            [
                base,
                downside[
                    [
                        column
                        for column in downside
                        if "hmm_" not in column and "sigma_" not in column
                    ]
                ],
            ],
            axis=1,
        ),
        "base_plus_downside_all": pd.concat([base, downside], axis=1),
    }
    feature_group = str(frozen["feature_group"])
    features = groups[feature_group]
    kind = str(frozen["model_kind"])
    transition = np.asarray(hmm.diagnostics["transition_matrix"], dtype=float)
    probability_columns = [column for column in hmm.probabilities if column.startswith("hmm_prob_state_")]
    state_probability = hmm.probabilities[probability_columns].iloc[-1].to_numpy(dtype=float)
    state_mean = np.asarray(hmm.diagnostics["state_mean"], dtype=float)
    state_volatility = np.asarray(hmm.diagnostics["state_volatility"], dtype=float)
    seed = int(config["runtime"].get("seed", 42))
    rows: list[dict[str, Any]] = []

    for horizon in horizons:
        labeled = targeted[f"risk_off_{horizon}"].notna()
        train = np.flatnonzero(labeled.to_numpy())
        selected, _ = select_features(
            features,
            train,
            float(config["features"]["missing_threshold"]),
            float(config["features"]["correlation_threshold"]),
        )
        x_train, x_latest = fill_features(
            features.loc[train, selected],
            features.loc[[features.index[-1]], selected],
        )
        binary_target = targeted[f"risk_off_{horizon}"].iloc[train].astype(int)
        weights = downside_sample_weights(
            binary_target,
            targeted[f"future_mae_{horizon}"].iloc[train],
            targeted["target_sigma"].iloc[train],
            horizon,
            frozen.get("sample_weight_config", config["risk_off"]["sample_weight"]),
        )
        head = RiskOffHead(
            kind,
            random_state=seed,
            params=dict(
                frozen.get(
                    "model_params",
                    config["risk_off"]["models"].get(kind, {}),
                )
            ),
        ).fit(
            x_train,
            binary_target,
            sample_weight=weights,
            compute_importance=False,
        )
        raw_risk_probability = head.predict_proba(x_latest)
        temperature = float(frozen.get("calibration_temperature_by_horizon", {}).get(str(horizon), 1.0))
        risk_probability = float(BinaryTemperatureCalibrator.apply(raw_risk_probability, temperature)[0])
        threshold = float(frozen["threshold_by_horizon"][str(horizon)])

        baseline_selected, _ = select_features(
            base,
            train,
            float(config["features"]["missing_threshold"]),
            float(config["features"]["correlation_threshold"]),
        )
        baseline_train, baseline_latest = fill_features(
            base.loc[train, baseline_selected],
            base.loc[[base.index[-1]], baseline_selected],
        )
        multiclass_model = EBMForecaster(
            seed,
            **dict(frozen.get("baseline_ebm_params", config["models"]["ebm"])),
        ).fit(
            baseline_train,
            targeted[f"target_{horizon}"].iloc[train].astype(str),
        )
        class_probability_matrix = multiclass_model.predict_proba(baseline_latest)
        baseline_temperature = float(
            frozen.get("baseline_calibration_temperature_by_horizon", {}).get(
                str(horizon),
                1.0,
            )
        )
        if not np.isclose(baseline_temperature, 1.0):
            class_probability_matrix = apply_temperature(
                class_probability_matrix,
                baseline_temperature,
            )
        class_probability = class_probability_matrix[0]
        scenario = simulate_paths_detailed(
            float(targeted["close"].iloc[-1]),
            state_probability,
            transition,
            state_mean,
            float(risk.features["egarch_sigma"].iloc[-1]),
            horizon,
            paths=int(config["monte_carlo"]["paths"]),
            seed=seed,
            state_volatility=state_volatility,
            egarch_params=dict(risk.diagnostics.get("params", {})),
            nu=float(risk.diagnostics.get("nu", 8.0)),
            target_class_probabilities=class_probability,
            state_to_class=np.arange(len(state_probability)) % len(CLASS_ORDER),
            scenario_mode="point_estimate",
        ).summary.iloc[0]
        origin = pd.Timestamp(targeted["date"].iloc[-1])
        maturity = pd.bdate_range(origin, periods=horizon + 1)[-1]
        rows.append(
            {
                "forecast_origin": origin,
                "origin_close": float(targeted["close"].iloc[-1]),
                "horizon": horizon,
                "model_version": f"downside-{Path(frozen_path).parent.name}",
                "git_sha": _git_sha(),
                "data_checksum": sha256_file(data_path),
                "config_checksum": _checksum(config),
                "prob_bull": float(class_probability[0]),
                "prob_sideway": float(class_probability[1]),
                "prob_bear": float(class_probability[2]),
                "prob_stress": float(class_probability[3]),
                "risk_off_probability": risk_probability,
                "threshold": threshold,
                "alert_state": int(risk_probability >= threshold),
                "prob_drawdown_5": float(scenario["prob_drawdown_gt_5pct"]),
                "prob_drawdown_10": float(scenario["prob_drawdown_gt_10pct"]),
                "prob_drawdown_15": float(scenario["prob_drawdown_gt_15pct"]),
                "prob_drawdown_20": float(scenario["prob_drawdown_gt_20pct"]),
                "var_95": float(scenario["var_95"]),
                "cvar_95": float(scenario["cvar_95"]),
                "maturity_date": maturity,
            }
        )
    registry = Path(registry_path)
    if registry.exists():
        mature_forecasts(registry, prices)
    append_forecasts(registry, pd.DataFrame(rows))
    return registry
