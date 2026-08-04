"""Live RAEMF-VB-MC forecast from the newest session, with maturity labels.

Fits HMM, EGARCH and the variational posterior on ALL available history (a
deployment fit — never used to score the past), then simulates the three
scenario modes from the last close. Each horizon is labelled with the date on
which it becomes verifiable; nothing produced here is an evaluated result.

Also writes a simple variance decomposition:
  parameter uncertainty ~ Var[M2] - Var[M1] (posterior draws vs posterior mean)
  regime uncertainty    ~ Var[M2] - Var[M2 | modal initial state]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from raemf_mc.bayesian.model import create_scenario_model
from raemf_mc.config import bayesian_config, load_config
from raemf_mc.data.loader import load_price_data
from raemf_mc.features.technical import build_features
from raemf_mc.regime.filtered_hmm import fit_filtered_hmm
from raemf_mc.risk.egarch_t import fit_egarch_features
from raemf_mc.simulation.structural_mc import simulate_paths_detailed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="outputs/latest/canonical_vnindex.csv")
    parser.add_argument("--config", default="configs/laptop_vb.yaml")
    parser.add_argument("--output-dir", default="outputs/latest")
    args = parser.parse_args()
    destination = Path(args.output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    config = load_config(args.config)
    bayes_cfg = bayesian_config(config)
    bayes_cfg["enabled"] = True

    prices, _ = load_price_data(args.data)
    features, _ = build_features(prices)
    returns = np.log(prices["close"] / prices["close"].shift(1))
    train_index = np.arange(len(prices), dtype=int)
    hmm = fit_filtered_hmm(
        features, returns, train_index, int(config["hmm"]["n_states"]), list(config["hmm"]["seeds"])
    )
    risk = fit_egarch_features(returns, train_index)
    probability_columns = [c for c in hmm.probabilities if c.startswith("hmm_prob_state_")]
    dates = pd.DatetimeIndex(prices["date"])
    model = create_scenario_model(bayes_cfg)
    model.fit(
        pd.Series(returns.to_numpy(dtype=float), index=dates),
        pd.DataFrame(
            hmm.probabilities[probability_columns].to_numpy(dtype=float),
            index=dates,
            columns=probability_columns,
        ),
        pd.Series(risk.features["egarch_sigma"].to_numpy(dtype=float), index=dates),
        train_index,
        bayes_cfg,
    )
    model.save(destination / "deployment_posterior")
    try:
        from raemf_mc.bayesian.diagnostics import write_diagnostic_artifacts

        write_diagnostic_artifacts(model, destination / "deployment_posterior")
    except Exception as exc:  # noqa: BLE001 - diagnostics must not block the forecast
        print(f"[WARN] Không vẽ được diagnostics posterior: {exc}")

    last_date = pd.Timestamp(prices["date"].iloc[-1])
    last_close = float(prices["close"].iloc[-1])
    current_probability = hmm.probabilities[probability_columns].iloc[-1].to_numpy(dtype=float)
    transition = np.asarray(hmm.diagnostics["transition_matrix"], dtype=float)
    state_mean = np.asarray(hmm.diagnostics["state_mean"], dtype=float)
    state_volatility = np.asarray(hmm.diagnostics["state_volatility"], dtype=float)
    sigma = float(risk.features["egarch_sigma"].iloc[-1])
    egarch_params = dict(risk.diagnostics.get("params", {}))
    nu_point = float(risk.diagnostics.get("nu", 8.0))
    paths = int(config["monte_carlo"]["paths"])
    seed = int(config["runtime"]["seed"])
    horizons = [20, 40, 60]

    quantile_rows: list[dict[str, object]] = []
    drawdown_rows: list[dict[str, object]] = []
    decomposition: dict[str, dict[str, float]] = {}
    forecast: dict[str, object] = {
        "generated_from": str(args.data),
        "forecast_origin": str(last_date.date()),
        "last_close": last_close,
        "scenario_mode": "variational_posterior",
        "paths": paths,
        "posterior_convergence": model.result.convergence_status,
        "posterior_warnings": model.result.warnings,
        "verifiable_note": (
            "Dự báo live: chưa thể kiểm chứng cho tới khi đủ số phiên tương lai của từng horizon."
        ),
        "horizons": {},
    }
    for horizon in horizons:
        draws = model.sample_parameters(paths, seed + horizon)
        posterior_mean = {k: v.mean(axis=0, keepdims=True).repeat(2, axis=0) for k, v in draws.items()}
        outputs = {}
        for mode, parameters in (
            ("point_estimate", None),
            ("posterior_mean_mc", posterior_mean),
            ("variational_posterior", draws),
        ):
            outputs[mode] = simulate_paths_detailed(
                last_close,
                current_probability,
                transition,
                state_mean,
                sigma,
                horizon,
                paths,
                seed,
                state_volatility=state_volatility,
                egarch_params=egarch_params,
                nu=nu_point,
                scenario_mode=mode,
                parameter_draws=parameters,
                lightweight=True,
            )
        # modal-initial-state variant for regime-uncertainty share
        modal = np.zeros_like(current_probability)
        modal[int(np.argmax(current_probability))] = 1.0
        modal_output = simulate_paths_detailed(
            last_close,
            modal,
            transition,
            state_mean,
            sigma,
            horizon,
            paths,
            seed,
            state_volatility=state_volatility,
            egarch_params=egarch_params,
            nu=nu_point,
            scenario_mode="variational_posterior",
            parameter_draws=draws,
            lightweight=True,
        )
        m2 = outputs["variational_posterior"].terminal_returns
        m1 = outputs["posterior_mean_mc"].terminal_returns
        var_m2 = float(np.var(m2))
        var_m1 = float(np.var(m1))
        var_modal = float(np.var(modal_output.terminal_returns))
        decomposition[str(horizon)] = {
            "variance_m2_total": var_m2,
            "variance_m1_no_parameter_uncertainty": var_m1,
            "parameter_uncertainty_share": max(0.0, 1.0 - var_m1 / max(var_m2, 1e-18)),
            "variance_m2_modal_initial_state": var_modal,
            "initial_regime_uncertainty_share": max(0.0, 1.0 - var_modal / max(var_m2, 1e-18)),
        }
        horizon_summary: dict[str, object] = {
            "verifiable_after_sessions": horizon,
            "matured": False,
        }
        for mode, output in outputs.items():
            terminal = output.terminal_returns
            drawdowns = output.drawdown_paths.min(axis=1)
            quantiles = {
                f"q{int(q * 100):02d}": float(np.quantile(terminal, q))
                for q in (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)
            }
            quantile_rows.append({"horizon": horizon, "scenario_mode": mode, **quantiles})
            drawdown_rows.append(
                {
                    "horizon": horizon,
                    "scenario_mode": mode,
                    "prob_negative_return": float(np.mean(terminal < 0)),
                    "prob_drawdown_gt_5pct": float(np.mean(drawdowns < -0.05)),
                    "prob_drawdown_gt_10pct": float(np.mean(drawdowns < -0.10)),
                    "prob_drawdown_gt_15pct": float(np.mean(drawdowns < -0.15)),
                    "var_95": -float(np.quantile(terminal, 0.05)),
                    "cvar_95": -float(terminal[terminal <= np.quantile(terminal, 0.05)].mean()),
                }
            )
            if mode == "variational_posterior":
                horizon_summary.update(
                    {
                        "median_return": float(np.quantile(terminal, 0.50)),
                        "interval_80": [float(np.quantile(terminal, 0.10)), float(np.quantile(terminal, 0.90))],
                        "interval_95": [float(np.quantile(terminal, 0.025)), float(np.quantile(terminal, 0.975))],
                        "prob_negative_return": float(np.mean(terminal < 0)),
                        "prob_drawdown_gt_10pct": float(np.mean(drawdowns < -0.10)),
                    }
                )
        forecast["horizons"][str(horizon)] = horizon_summary

    hmm_state_map_rows = pd.DataFrame(
        {
            "state": np.arange(len(current_probability)),
            "probability": current_probability,
            "state_mean": state_mean,
            "state_volatility": state_volatility,
        }
    )
    hmm_state_map_rows.to_csv(destination / "latest_regime_probabilities_vb.csv", index=False)
    pd.DataFrame(quantile_rows).to_csv(destination / "latest_return_quantiles_vb.csv", index=False)
    pd.DataFrame(drawdown_rows).to_csv(destination / "latest_drawdown_risk_vb.csv", index=False)
    (destination / "latest_uncertainty_decomposition.json").write_text(
        json.dumps(decomposition, indent=2), encoding="utf-8"
    )
    (destination / "latest_forecast_vb.json").write_text(
        json.dumps(forecast, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(forecast["horizons"], indent=2, ensure_ascii=False))
    print(destination / "latest_forecast_vb.json")


if __name__ == "__main__":
    main()
