"""Small synthetic ADVI-vs-NUTS validation; never imported by production code."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import arviz as az
import numpy as np
import pandas as pd
import pymc as pm


def _data(seed: int, observations: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    states = rng.choice(2, size=observations, p=[0.65, 0.35])
    probabilities = np.full((observations, 2), 0.05)
    probabilities[np.arange(observations), states] = 0.95
    sigma = 0.01 * np.exp(rng.normal(0, 0.08, observations))
    mu = np.array([0.0015, -0.0025])
    c = np.array([0.8, 1.5])
    nu = np.array([12.0, 5.0])
    z = rng.standard_t(nu[states]) * np.sqrt((nu[states] - 2) / nu[states])
    returns = mu[states] + c[states] * sigma * z
    return returns, probabilities, sigma


def _model(returns: np.ndarray, probabilities: np.ndarray, sigma: np.ndarray) -> pm.Model:
    scale = returns.std(ddof=1)
    with pm.Model(coords={"regime": ["calm", "stress"], "observation": np.arange(len(returns))}) as model:
        mu_std = pm.Normal("mu_std", 0, 0.5, dims="regime")
        log_c = pm.Normal("log_c", 0, 0.3, dims="regime")
        c = pm.Deterministic("c", pm.math.exp(log_c), dims="regime")
        nu_minus_two = pm.Exponential("nu_minus_two", 0.1, dims="regime")
        nu = pm.Deterministic("nu", 2 + nu_minus_two, dims="regime")
        components = pm.StudentT.dist(
            nu=nu[None, :],
            mu=mu_std[None, :],
            sigma=(sigma / scale)[:, None] * c[None, :],
            shape=(len(returns), 2),
        )
        component_log_probability = pm.logp(components, (returns / scale)[:, None])
        pm.Potential(
            "returns_likelihood",
            pm.math.logsumexp(pm.math.log(probabilities) + component_log_probability, axis=1).sum(),
        )
    return model


def _fit_advi(model: pm.Model, method: str, steps: int, draws: int, seed: int) -> az.InferenceData:
    pymc_method = "advi" if method == "meanfield_advi" else "fullrank_advi"
    with model:
        approximation = pm.fit(
            steps,
            method=pymc_method,
            obj_optimizer=pm.adam(learning_rate=0.01),
            random_seed=seed,
            progressbar=False,
        )
        return approximation.sample(draws, random_seed=seed, return_inferencedata=True)


def _summary(idata: az.InferenceData, method: str) -> pd.DataFrame:
    summary = az.summary(idata, var_names=["mu_std", "c", "nu"], hdi_prob=0.95).reset_index()
    summary.insert(0, "method", method)
    summary["interval_width"] = summary["hdi_97.5%"] - summary["hdi_2.5%"]
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Small ADVI-vs-NUTS posterior benchmark")
    parser.add_argument("--output-dir", default="outputs/bayesian/mcmc_benchmark")
    parser.add_argument("--observations", type=int, default=240)
    parser.add_argument("--advi-steps", type=int, default=5000)
    parser.add_argument("--draws", type=int, default=1000)
    parser.add_argument("--nuts-tune", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    returns, probabilities, sigma = _data(args.seed, args.observations)
    meanfield = _fit_advi(_model(returns, probabilities, sigma), "meanfield_advi", args.advi_steps, args.draws, args.seed)
    fullrank = _fit_advi(_model(returns, probabilities, sigma), "fullrank_advi", args.advi_steps, args.draws, args.seed)
    nuts_model = _model(returns, probabilities, sigma)
    with nuts_model:
        nuts = pm.sample(
            draws=args.draws,
            tune=args.nuts_tune,
            chains=2,
            cores=1,
            random_seed=args.seed,
            progressbar=False,
            target_accept=0.9,
            return_inferencedata=True,
        )
    summary = pd.concat(
        [_summary(meanfield, "meanfield_advi"), _summary(fullrank, "fullrank_advi"), _summary(nuts, "nuts")],
        ignore_index=True,
    )
    summary.to_csv(output / "posterior_method_comparison.csv", index=False)
    nuts_sd = summary[summary["method"] == "nuts"].set_index("index")["sd"]
    warnings = []
    for method in ("meanfield_advi", "fullrank_advi"):
        current = summary[summary["method"] == method].set_index("index")["sd"]
        ratios = current / nuts_sd
        for parameter, ratio in ratios.items():
            if ratio < 0.70:
                warnings.append(f"{method} posterior sd for {parameter} is {ratio:.3f} of NUTS")
    (output / "warnings.json").write_text(json.dumps(warnings, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
