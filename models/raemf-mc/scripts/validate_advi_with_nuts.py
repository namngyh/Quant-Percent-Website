"""Small synthetic validation: torch ADVI vs PyMC ADVI vs NUTS.

Never imported by production code. Fits the same 2-regime mixture model with
three inference engines on identical synthetic data and reports posterior
means, standard deviations and credible intervals side by side, so we can see
whether ADVI (torch or PyMC) understates posterior uncertainty relative to
the NUTS reference.

Usage:
    python scripts/validate_advi_with_nuts.py --observations 1500 \
        --output-dir outputs/latest/advi_nuts_validation
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _data(seed: int, observations: int):
    rng = np.random.default_rng(seed)
    states = rng.choice(2, size=observations, p=[0.65, 0.35])
    probabilities = np.full((observations, 2), 0.05)
    probabilities[np.arange(observations), states] = 0.95
    sigma = 0.01 * np.exp(rng.normal(0, 0.08, observations))
    mu = np.array([0.0015, -0.0025])
    c = np.array([0.8, 1.5])
    nu = 6.0
    z = rng.standard_t(nu, size=observations) * np.sqrt((nu - 2) / nu)
    returns = mu[states] + c[states] * sigma * z
    return returns, probabilities, sigma, {"mu": mu.tolist(), "c": c.tolist(), "nu": nu}


def _summaries(samples: dict[str, np.ndarray], engine: str) -> pd.DataFrame:
    rows = []
    for name, values in samples.items():
        for regime in range(values.shape[1]):
            column = values[:, regime]
            rows.append(
                {
                    "engine": engine,
                    "parameter": name,
                    "regime": regime,
                    "mean": float(column.mean()),
                    "sd": float(column.std(ddof=1)),
                    "q025": float(np.quantile(column, 0.025)),
                    "q975": float(np.quantile(column, 0.975)),
                }
            )
    return pd.DataFrame(rows)


def fit_torch(returns, probabilities, sigma, seed: int, steps: int) -> pd.DataFrame:
    from raemf_mc.bayesian.model import TorchVariationalScenarioModel

    model = TorchVariationalScenarioModel(
        {
            "enabled": True,
            "backend": "pytorch_cuda",
            "method": "fullrank_advi",
            "hierarchical": False,
            "shared_nu": True,
            "seeds": [seed],
            "advi_steps": steps,
            "min_steps": min(1000, steps),
            "posterior_draws": 2000,
            "learning_rate": 0.01,
            "vi_samples_per_step": 8,
            "min_effective_observations": 20,
            "device": "auto",
        }
    )
    result = model.fit(
        pd.Series(returns),
        pd.DataFrame(probabilities, columns=["calm", "stress"]),
        pd.Series(sigma),
        np.arange(len(returns)),
    )
    return _summaries(result.posterior_samples, "torch_fullrank_advi")


def _pymc_model(returns, probabilities, sigma):
    import pymc as pm

    scale = returns.std(ddof=1)
    with pm.Model(coords={"regime": ["calm", "stress"]}) as model:
        mu_std = pm.Normal("mu_std", 0, 0.5, dims="regime")
        log_c = pm.Normal("log_c", 0, 0.3, dims="regime")
        c = pm.Deterministic("c", pm.math.exp(log_c), dims="regime")
        nu_minus_two = pm.Exponential("nu_minus_two_shared", 0.1)
        nu = pm.Deterministic("nu", mu_std * 0.0 + (2.0 + nu_minus_two), dims="regime")
        components = pm.StudentT.dist(
            nu=nu[None, :],
            mu=mu_std[None, :],
            sigma=(sigma / scale)[:, None] * c[None, :],
            shape=(len(returns), 2),
        )
        component_log_probability = pm.logp(components, (returns / scale)[:, None])
        pm.Potential(
            "returns_likelihood",
            pm.math.logsumexp(np.log(probabilities) + component_log_probability, axis=1).sum(),
        )
    return model, scale


def _extract(inference_data, scale) -> dict[str, np.ndarray]:
    def stacked(name):
        return (
            inference_data.posterior[name]
            .stack(sample=("chain", "draw"))
            .transpose("sample", "regime")
            .to_numpy()
            .astype(float)
        )

    return {"mu": stacked("mu_std") * scale, "c": stacked("c"), "nu": stacked("nu")}


def fit_pymc_advi(returns, probabilities, sigma, seed: int, steps: int) -> pd.DataFrame:
    import pymc as pm

    model, scale = _pymc_model(returns, probabilities, sigma)
    with model:
        approximation = pm.fit(
            steps,
            method="fullrank_advi",
            obj_optimizer=pm.adam(learning_rate=0.01),
            random_seed=seed,
            progressbar=False,
        )
        inference_data = approximation.sample(2000, random_seed=seed, return_inferencedata=True)
    return _summaries(_extract(inference_data, scale), "pymc_fullrank_advi")


def fit_pymc_nuts(returns, probabilities, sigma, seed: int, draws: int, tune: int) -> pd.DataFrame:
    import pymc as pm

    model, scale = _pymc_model(returns, probabilities, sigma)
    with model:
        inference_data = pm.sample(
            draws=draws,
            tune=tune,
            chains=2,
            cores=1,
            random_seed=seed,
            progressbar=False,
            compute_convergence_checks=True,
        )
    return _summaries(_extract(inference_data, scale), "pymc_nuts")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--observations", type=int, default=1500)
    parser.add_argument("--advi-steps", type=int, default=8000)
    parser.add_argument("--nuts-draws", type=int, default=800)
    parser.add_argument("--nuts-tune", type=int, default=800)
    parser.add_argument("--skip-nuts", action="store_true")
    parser.add_argument("--skip-pymc-advi", action="store_true")
    parser.add_argument("--output-dir", default="outputs/latest/advi_nuts_validation")
    args = parser.parse_args()

    destination = Path(args.output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    returns, probabilities, sigma, truth = _data(args.seed, args.observations)
    frames = [fit_torch(returns, probabilities, sigma, args.seed, args.advi_steps)]
    if not args.skip_pymc_advi:
        frames.append(fit_pymc_advi(returns, probabilities, sigma, args.seed, args.advi_steps))
    if not args.skip_nuts:
        frames.append(fit_pymc_nuts(returns, probabilities, sigma, args.seed, args.nuts_draws, args.nuts_tune))
    comparison = pd.concat(frames, ignore_index=True)
    comparison.to_csv(destination / "engine_comparison.csv", index=False)
    (destination / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")

    # SD ratio vs NUTS: values well below 1 flag ADVI underdispersion.
    if not args.skip_nuts:
        nuts = comparison[comparison["engine"] == "pymc_nuts"].set_index(["parameter", "regime"])
        rows = []
        for engine in comparison["engine"].unique():
            if engine == "pymc_nuts":
                continue
            other = comparison[comparison["engine"] == engine].set_index(["parameter", "regime"])
            for key in nuts.index:
                rows.append(
                    {
                        "engine": engine,
                        "parameter": key[0],
                        "regime": key[1],
                        "mean_gap_vs_nuts": float(other.loc[key, "mean"] - nuts.loc[key, "mean"]),
                        "sd_ratio_vs_nuts": float(other.loc[key, "sd"] / max(nuts.loc[key, "sd"], 1e-12)),
                    }
                )
        pd.DataFrame(rows).to_csv(destination / "advi_vs_nuts_ratios.csv", index=False)
    print(comparison.to_string(index=False))
    print(f"\nArtifacts in {destination}")


if __name__ == "__main__":
    main()
