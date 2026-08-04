"""Backend-agnostic scenario-model factory and the PyTorch implementation.

``create_scenario_model(config)`` returns either the PyMC reference
implementation (:class:`VariationalScenarioModel`) or the GPU-first PyTorch
implementation below. Both expose the same public surface used by the OOS
benchmark and the deployment workflow: ``fit``, ``sample_parameters``,
``posterior_summary``, ``save``/``load`` and ``result``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from raemf_mc.bayesian.priors import ScenarioPriors
from raemf_mc.bayesian.torch_backend import (
    SeedFitResult,
    TorchScenarioELBO,
    fit_torch_advi,
    pool_seed_results,
    seed_stability_metrics,
)
from raemf_mc.bayesian.variational import (
    VariationalPosteriorResult,
    VariationalScenarioModel,
    _parameter_frame,
)
from raemf_mc.config import bayesian_config
from raemf_mc.runtime.hardware import select_device


class TorchVariationalScenarioModel(VariationalScenarioModel):
    """Full-rank ADVI on PyTorch (CUDA when available), multi-seed, hierarchical.

    Inherits the input alignment, fingerprinting, predictive-check and
    ``sample_parameters`` machinery from the PyMC implementation; only the
    inference engine is replaced. HMM probabilities and EGARCH sigma remain
    fixed causal inputs — this is not a full Bayesian HMM–EGARCH–EBM.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.seed_results: list[SeedFitResult] = []
        self.posterior_by_seed: pd.DataFrame | None = None
        self.fallback_records: list[dict[str, Any]] = []

    def fit(
        self,
        returns: pd.Series | np.ndarray,
        regime_probabilities: pd.DataFrame | np.ndarray,
        conditional_volatility: pd.Series | np.ndarray,
        train_index: Any,
        config: dict[str, Any] | None = None,
    ) -> VariationalPosteriorResult:
        if config is not None:
            self.config = bayesian_config(config)
        cfg = self.config
        ret, probabilities, volatility = self._aligned_inputs(returns, regime_probabilities, conditional_volatility)
        positions = self._train_positions(train_index, len(ret))
        train_ret = ret.iloc[positions].to_numpy(dtype=float)
        train_prob = probabilities.iloc[positions].to_numpy(dtype=float)
        train_sigma = volatility.iloc[positions].to_numpy(dtype=float)
        finite = np.isfinite(train_ret) & np.isfinite(train_sigma) & np.isfinite(train_prob).all(axis=1)
        warnings: list[str] = []
        if not finite.all():
            warnings.append(f"Dropped {int((~finite).sum())} non-finite training observations")
            positions = positions[finite]
            train_ret = train_ret[finite]
            train_prob = train_prob[finite]
            train_sigma = train_sigma[finite]
        if len(train_ret) < 250:
            raise ValueError(f"Need at least 250 finite train observations, got {len(train_ret)}")
        if np.any(train_sigma <= 0):
            raise ValueError("conditional_volatility must be strictly positive on train")
        row_sums = train_prob.sum(axis=1)
        if np.any(train_prob < -1e-12) or not np.allclose(row_sums, 1.0, atol=1e-6, rtol=1e-6):
            raise ValueError("filtered regime probabilities must be a valid simplex")
        effective = train_prob.sum(axis=0)
        priors = ScenarioPriors.from_config(cfg)
        priors.validate()
        minimum = float(cfg["min_effective_observations"])
        small = np.flatnonzero(effective < minimum)
        if len(small) and not priors.shared_nu:
            detail = ", ".join(f"regime {i}={effective[i]:.1f}" for i in small)
            warnings.append(
                f"Effective observations below {minimum:g} ({detail}); "
                "falling back to a shared Student-t nu instead of regime-specific nu"
            )
            priors = ScenarioPriors(**{**priors.__dict__, "shared_nu": True})

        return_scale = float(np.std(train_ret, ddof=1))
        if not np.isfinite(return_scale) or return_scale <= 1e-12:
            raise ValueError("Training return scale is zero or non-finite")
        scaled_return = train_ret / return_scale
        scaled_sigma = train_sigma / return_scale

        device = select_device(str(cfg.get("device", "auto")), require=bool(cfg.get("require_gpu", False)))
        elbo_model = TorchScenarioELBO(
            scaled_return,
            train_prob,
            scaled_sigma,
            priors,
            device=device,
            dtype=str(cfg.get("dtype", "float32")),
        )
        seeds = [int(s) for s in cfg.get("seeds") or [int(cfg["random_seed"])]]
        seed_results: list[SeedFitResult] = []
        fallback_records: list[dict[str, Any]] = []
        for seed in seeds:
            outcome = fit_torch_advi(
                elbo_model,
                method=str(cfg["method"]),
                seed=seed,
                max_steps=int(cfg["advi_steps"]),
                min_steps=int(cfg.get("min_steps", min(1000, int(cfg["advi_steps"])))),
                learning_rate=float(cfg["learning_rate"]),
                retry_learning_rates=tuple(float(v) for v in cfg.get("retry_learning_rates", [0.001])),
                vi_samples_per_step=int(cfg.get("vi_samples_per_step", 8)),
                gradient_clip_norm=float(cfg.get("gradient_clip_norm", 5.0)),
                early_stopping_patience=int(cfg.get("early_stopping_patience", 2000)),
                convergence_window=int(cfg["convergence_window"]),
                convergence_tolerance=float(cfg["convergence_tolerance"]),
                posterior_draws=int(cfg["posterior_draws"]),
                fallback_to_meanfield=bool(cfg.get("fallback_to_meanfield", True)),
            )
            seed_results.append(outcome)
            fallback_records.extend(outcome.fallbacks)
            if outcome.method != cfg["method"]:
                warnings.append(f"Seed {seed} fell back to {outcome.method}")
            if not outcome.converged:
                warnings.append(f"Seed {seed} did not meet the ELBO moving-average criterion")
        samples, by_seed = pool_seed_results(seed_results, int(cfg["posterior_draws"]), pool_seed=seeds[0])
        samples = {"mu": samples["mu"] * return_scale, "c": samples["c"], "nu": samples["nu"]}
        for result in seed_results:
            result.samples = {**result.samples, "mu": result.samples["mu"] * return_scale}
        mu_columns = [c for c in by_seed.columns if c.startswith("mu_") and not c.startswith("mu_raw")]
        by_seed[mu_columns] = by_seed[mu_columns] * return_scale
        if any(not np.isfinite(v).all() for v in samples.values()):
            raise RuntimeError("Pooled posterior contains NaN or infinite values")
        if np.any(samples["c"] <= 0) or np.any(samples["nu"] <= 2):
            raise RuntimeError("Pooled posterior violates c > 0 or nu > 2")

        labels = [str(column) for column in probabilities.columns]
        n_converged = int(by_seed["converged"].sum())
        status = "converged" if n_converged == len(seeds) else (
            "partially_converged" if n_converged else "not_converged"
        )
        credible_rows: list[dict[str, object]] = []
        for name, value in samples.items():
            for regime, label in enumerate(labels):
                credible_rows.append(
                    {
                        "parameter": name,
                        "regime": regime,
                        "regime_label": label,
                        "q025": float(np.quantile(value[:, regime], 0.025)),
                        "q50": float(np.quantile(value[:, regime], 0.50)),
                        "q975": float(np.quantile(value[:, regime], 0.975)),
                    }
                )
        date_values = ret.index[positions]
        result = VariationalPosteriorResult(
            fitted=True,
            inference_method=f"torch_{cfg['method']}_x{len(seeds)}seeds",
            elbo_history=seed_results[0].elbo_history,
            posterior_samples=samples,
            posterior_means={name: value.mean(axis=0) for name, value in samples.items()},
            posterior_standard_deviations={name: value.std(axis=0, ddof=1) for name, value in samples.items()},
            credible_intervals=pd.DataFrame(credible_rows),
            regime_labels=labels,
            scaling_metadata={"return_scale": return_scale},
            train_date_range=(str(date_values[0]), str(date_values[-1])),
            data_fingerprint=self._fingerprint(date_values, train_ret, train_prob, train_sigma),
            random_seed=int(seeds[0]),
            convergence_status=status,
            warnings=warnings,
            effective_observations=effective,
        )
        self.result = result
        self.seed_results = seed_results
        self.posterior_by_seed = by_seed
        self.fallback_records = fallback_records
        self._training_data = {
            "returns": train_ret,
            "probabilities": train_prob,
            "volatility": train_sigma,
        }
        self._device = device
        return result

    def prior_predictive_check(self, n_draws: int | None = None) -> dict[str, Any]:
        """Hierarchical-aware prior predictive draws on the return scale."""
        priors = ScenarioPriors.from_config(self.config)
        if not priors.hierarchical:
            return super().prior_predictive_check(n_draws)
        result = self._require_result()
        requested = int(n_draws or self.config["posterior_predictive_draws"])
        rng = np.random.default_rng(result.random_seed)
        n_regimes = len(result.regime_labels)
        return_scale = float(result.scaling_metadata["return_scale"])
        mu_global = rng.normal(0.0, priors.mu_global_sd, size=requested)
        tau_mu = np.abs(rng.normal(0.0, priors.mu_tau_sd, size=requested))
        mu = rng.normal(mu_global[:, None], np.maximum(tau_mu, 1e-6)[:, None], size=(requested, n_regimes)) * return_scale
        log_c_global = rng.normal(0.0, priors.log_c_global_sd, size=requested)
        tau_c = np.abs(rng.normal(0.0, priors.log_c_tau_sd, size=requested))
        c = np.exp(rng.normal(log_c_global[:, None], np.maximum(tau_c, 1e-6)[:, None], size=(requested, n_regimes)))
        if priors.shared_nu:
            shared = 2.0 + rng.exponential(1.0 / priors.nu_rate, size=requested)
            nu = np.repeat(shared[:, None], n_regimes, axis=1)
        else:
            nu = 2.0 + rng.exponential(1.0 / priors.nu_rate, size=(requested, n_regimes))
        parameters = {"mu": mu, "c": c, "nu": nu}
        draws = self._predictive_draws(parameters, result.random_seed + 1)
        return {
            "draws": draws,
            "metrics": pd.DataFrame([{"source": "prior_predictive", **self._distribution_metrics(draws)}]),
            "parameter_samples": parameters,
        }

    def save(self, path: str | Path) -> Path:
        result = self._require_result()
        destination = Path(path)
        destination.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            destination / "posterior_samples.npz",
            mu=result.posterior_samples["mu"],
            c=result.posterior_samples["c"],
            nu=result.posterior_samples["nu"],
        )
        pd.DataFrame({"iteration": np.arange(len(result.elbo_history)), "loss": result.elbo_history}).to_csv(
            destination / "elbo_history.csv", index=False
        )
        if self.seed_results:
            frames = []
            for seed_result in self.seed_results:
                frames.append(
                    pd.DataFrame(
                        {
                            "seed": seed_result.seed,
                            "iteration": np.arange(len(seed_result.elbo_history)),
                            "loss": seed_result.elbo_history,
                        }
                    )
                )
            pd.concat(frames, ignore_index=True).to_csv(destination / "elbo_history_by_seed.csv", index=False)
        result.summary_frame().to_csv(destination / "posterior_summary.csv", index=False)
        result.credible_intervals.to_csv(destination / "credible_intervals.csv", index=False)
        _parameter_frame(result.posterior_samples).corr().to_csv(destination / "posterior_correlations.csv")
        if self.posterior_by_seed is not None:
            self.posterior_by_seed.to_csv(destination / "posterior_by_seed.csv", index=False)
            stability = seed_stability_metrics(self.posterior_by_seed)
            (destination / "seed_stability.json").write_text(
                json.dumps(stability, indent=2), encoding="utf-8"
            )
        (destination / "fallbacks.json").write_text(
            json.dumps(self.fallback_records, indent=2), encoding="utf-8"
        )
        with (destination / "config_snapshot.yaml").open("w", encoding="utf-8") as handle:
            yaml.safe_dump({"bayesian": self.config}, handle, sort_keys=False, allow_unicode=True)
        metadata = {
            "fitted": result.fitted,
            "backend": "pytorch",
            "device": getattr(self, "_device", "cpu"),
            "inference_method": result.inference_method,
            "regime_labels": result.regime_labels,
            "scaling_metadata": result.scaling_metadata,
            "train_date_range": list(result.train_date_range),
            "data_fingerprint": result.data_fingerprint,
            "random_seed": result.random_seed,
            "convergence_status": result.convergence_status,
            "warnings": result.warnings,
            "effective_observations": [float(v) for v in np.asarray(result.effective_observations, dtype=float)],
            "config": self.config,
        }
        (destination / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return destination


def create_scenario_model(config: dict[str, Any] | None = None):
    """Return the configured Bayesian scenario backend.

    ``bayesian.backend: pytorch_cuda`` (default in the VB configs) uses the
    GPU-first PyTorch implementation. ``pytorch_cpu`` uses the same
    implementation without touching CUDA; ``pymc`` keeps the reference backend.
    """
    cfg = bayesian_config(config)
    backend = str(cfg.get("backend", "pymc"))
    if backend in ("pytorch_cuda", "pytorch_cpu", "pytorch", "torch"):
        if backend == "pytorch_cpu":
            cfg = {**cfg, "device": "cpu", "require_gpu": False}
        return TorchVariationalScenarioModel(cfg)
    return VariationalScenarioModel(cfg)
