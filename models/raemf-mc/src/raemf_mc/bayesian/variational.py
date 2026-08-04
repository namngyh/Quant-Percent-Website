"""Variational posterior for regime-conditional return scenario parameters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy.stats import kurtosis, skew

from raemf_mc.config import bayesian_config


def _json_default(value: object) -> object:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _parameter_frame(samples: dict[str, np.ndarray]) -> pd.DataFrame:
    columns: dict[str, np.ndarray] = {}
    for parameter in ("mu", "c", "nu"):
        values = np.asarray(samples[parameter], dtype=float)
        for regime in range(values.shape[1]):
            columns[f"{parameter}_{regime}"] = values[:, regime]
    return pd.DataFrame(columns)


@dataclass
class VariationalPosteriorResult:
    """Serializable fit result, independent of PyMC global state."""

    fitted: bool
    inference_method: str
    elbo_history: np.ndarray
    posterior_samples: dict[str, np.ndarray]
    posterior_means: dict[str, np.ndarray]
    posterior_standard_deviations: dict[str, np.ndarray]
    credible_intervals: pd.DataFrame
    regime_labels: list[str]
    scaling_metadata: dict[str, float]
    train_date_range: tuple[str, str]
    data_fingerprint: str
    random_seed: int
    convergence_status: str
    warnings: list[str] = field(default_factory=list)
    inference_data: Any | None = field(default=None, repr=False)
    inference_data_path: str | None = None
    effective_observations: np.ndarray = field(default_factory=lambda: np.empty(0))

    def summary_frame(self) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for parameter in ("mu", "c", "nu"):
            values = np.asarray(self.posterior_samples[parameter], dtype=float)
            for regime, label in enumerate(self.regime_labels):
                rows.append(
                    {
                        "parameter": parameter,
                        "regime": regime,
                        "regime_label": label,
                        "mean": float(values[:, regime].mean()),
                        "sd": float(values[:, regime].std(ddof=1)),
                        "q025": float(np.quantile(values[:, regime], 0.025)),
                        "q50": float(np.quantile(values[:, regime], 0.50)),
                        "q975": float(np.quantile(values[:, regime], 0.975)),
                    }
                )
        return pd.DataFrame(rows)


class VariationalScenarioModel:
    """PyMC ADVI model for a fixed-weight regime mixture of Student-t returns.

    HMM probabilities and EGARCH conditional volatility are treated as known
    causal inputs. Only regime drift ``mu``, volatility multiplier ``c`` and
    Student-t degrees of freedom ``nu`` receive a variational posterior.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = bayesian_config(config)
        self.result: VariationalPosteriorResult | None = None
        self._training_data: dict[str, np.ndarray] | None = None

    @staticmethod
    def _backend() -> tuple[Any, Any]:
        try:
            import arviz as az
            import pymc as pm
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Bayesian mode requires PyMC and ArviZ. Install with "
                "`python -m pip install -e .[bayesian]`."
            ) from exc
        return pm, az

    @staticmethod
    def _train_positions(train_index: Any, length: int) -> np.ndarray:
        values = np.asarray(train_index)
        if values.dtype == bool:
            if values.ndim != 1 or len(values) != length:
                raise ValueError("Boolean train_index must have the same length as returns")
            positions = np.flatnonzero(values)
        else:
            if values.ndim != 1:
                raise ValueError("train_index must be a one-dimensional positional index or mask")
            positions = values.astype(int)
        positions = np.unique(positions)
        if not len(positions):
            raise ValueError("train_index is empty")
        if positions[0] < 0 or positions[-1] >= length:
            raise ValueError("train_index contains positions outside the aligned input")
        return positions

    @staticmethod
    def _aligned_inputs(
        returns: pd.Series | np.ndarray,
        regime_probabilities: pd.DataFrame | np.ndarray,
        conditional_volatility: pd.Series | np.ndarray,
    ) -> tuple[pd.Series, pd.DataFrame, pd.Series]:
        ret = returns.astype(float).copy() if isinstance(returns, pd.Series) else pd.Series(np.asarray(returns, dtype=float))
        if isinstance(regime_probabilities, pd.DataFrame):
            probabilities = regime_probabilities.astype(float).copy()
        else:
            values = np.asarray(regime_probabilities, dtype=float)
            probabilities = pd.DataFrame(values, index=ret.index)
        volatility = (
            conditional_volatility.astype(float).copy()
            if isinstance(conditional_volatility, pd.Series)
            else pd.Series(np.asarray(conditional_volatility, dtype=float), index=ret.index)
        )
        if len(ret) != len(probabilities) or len(ret) != len(volatility):
            raise ValueError("returns, conditional_volatility and regime_probabilities must have equal length")
        if isinstance(returns, pd.Series) and isinstance(regime_probabilities, pd.DataFrame) and not ret.index.equals(probabilities.index):
            raise ValueError("Index mismatch between returns and regime_probabilities")
        if isinstance(returns, pd.Series) and isinstance(conditional_volatility, pd.Series) and not ret.index.equals(volatility.index):
            raise ValueError("Index mismatch between returns and conditional_volatility")
        if probabilities.ndim != 2 or probabilities.shape[1] < 2:
            raise ValueError("regime_probabilities must be an n_observation x K matrix with K >= 2")
        return ret, probabilities, volatility

    @staticmethod
    def _fingerprint(
        dates: pd.Index,
        returns: np.ndarray,
        probabilities: np.ndarray,
        volatility: np.ndarray,
    ) -> str:
        digest = hashlib.sha256()
        digest.update("|".join(map(str, dates)).encode("utf-8"))
        for values in (returns, probabilities, volatility):
            digest.update(np.ascontiguousarray(values, dtype=np.float64).tobytes())
        return digest.hexdigest()

    @staticmethod
    def _convergence(history: np.ndarray, window: int, tolerance: float) -> tuple[str, float]:
        if len(history) < 2 * window:
            return "insufficient_history", float("nan")
        previous = float(np.mean(history[-2 * window : -window]))
        current = float(np.mean(history[-window:]))
        relative_change = abs(current - previous) / max(abs(previous), 1.0)
        return ("converged" if relative_change <= tolerance else "not_converged"), relative_change

    def fit(
        self,
        returns: pd.Series | np.ndarray,
        regime_probabilities: pd.DataFrame | np.ndarray,
        conditional_volatility: pd.Series | np.ndarray,
        train_index: Any,
        config: dict[str, Any] | None = None,
    ) -> VariationalPosteriorResult:
        """Fit the posterior strictly on the supplied positional train index."""
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
        if not len(train_ret):
            raise ValueError("No finite training observations remain")
        if np.any(train_sigma <= 0):
            raise ValueError("conditional_volatility must be strictly positive on train")
        if np.any(train_prob < -1e-12):
            raise ValueError("filtered regime probabilities cannot be negative")
        row_sums = train_prob.sum(axis=1)
        if not np.allclose(row_sums, 1.0, atol=1e-6, rtol=1e-6):
            maximum_error = float(np.max(np.abs(row_sums - 1.0)))
            raise ValueError(f"filtered regime probabilities must sum to 1; max error={maximum_error:.3g}")
        effective = train_prob.sum(axis=0)
        minimum = float(cfg["min_effective_observations"])
        small = np.flatnonzero(effective < minimum)
        use_shared_nu = bool(cfg["shared_nu"])
        if len(small):
            detail = ", ".join(f"regime {i}={effective[i]:.2f}" for i in small)
            if use_shared_nu:
                warnings.append(f"Low effective observations under shared nu: {detail}")
            else:
                warnings.append(
                    f"Too few effective observations for regime-specific nu (minimum {minimum:g}): "
                    f"{detail}; falling back to shared nu"
                )
                use_shared_nu = True
        return_scale = float(np.std(train_ret, ddof=1))
        if not np.isfinite(return_scale) or return_scale <= 1e-12:
            raise ValueError("Training return scale is zero or non-finite")
        scaled_return = train_ret / return_scale
        scaled_sigma = train_sigma / return_scale
        if np.any(scaled_sigma <= 0) or not np.isfinite(scaled_sigma).all():
            raise ValueError("Scaled conditional volatility must be finite and positive")

        pm, _ = self._backend()
        n_regimes = train_prob.shape[1]
        labels = [str(column) for column in probabilities.columns]
        seed = int(cfg["random_seed"])
        prior_details = dict(cfg.get("priors") or {})
        hierarchical = bool(cfg.get("hierarchical", False))
        with pm.Model(coords={"regime": labels, "observation": np.arange(len(train_ret))}):
            if hierarchical:
                mu_global = pm.Normal("mu_global", mu=0.0, sigma=float(prior_details.get("mu_global_sd", 0.25)))
                tau_mu = pm.HalfNormal("tau_mu", sigma=float(prior_details.get("mu_tau_sd", 0.25)))
                mu_std = pm.Normal("mu_std", mu=mu_global, sigma=tau_mu, dims="regime")
                log_c_global = pm.Normal(
                    "log_c_global", mu=0.0, sigma=float(prior_details.get("log_c_global_sd", 0.25))
                )
                tau_c = pm.HalfNormal("tau_c", sigma=float(prior_details.get("log_c_tau_sd", 0.20)))
                log_c = pm.Normal("log_c", mu=log_c_global, sigma=tau_c, dims="regime")
            else:
                mu_std = pm.Normal("mu_std", mu=0.0, sigma=float(cfg["prior_mu_scale"]), dims="regime")
                log_c = pm.Normal("log_c", mu=0.0, sigma=float(cfg["prior_log_scale_sd"]), dims="regime")
            c = pm.Deterministic("c", pm.math.exp(log_c), dims="regime")
            if use_shared_nu:
                nu_minus_two_shared = pm.Exponential("nu_minus_two_shared", lam=float(cfg["prior_nu_rate"]))
                nu = pm.Deterministic(
                    "nu",
                    mu_std * 0.0 + (2.0 + nu_minus_two_shared),
                    dims="regime",
                )
            else:
                nu_minus_two = pm.Exponential(
                    "nu_minus_two",
                    lam=float(cfg["prior_nu_rate"]),
                    dims="regime",
                )
                nu = pm.Deterministic("nu", 2.0 + nu_minus_two, dims="regime")
            components = pm.StudentT.dist(
                nu=nu[None, :],
                mu=mu_std[None, :],
                sigma=scaled_sigma[:, None] * c[None, :],
                shape=(len(train_ret), n_regimes),
            )
            component_log_probability = pm.logp(components, scaled_return[:, None])
            pm.Potential(
                "returns_likelihood",
                pm.math.logsumexp(pm.math.log(train_prob) + component_log_probability, axis=1).sum(),
            )
            pymc_method = "fullrank_advi" if cfg["method"] == "fullrank_advi" else "advi"
            approximation = pm.fit(
                n=int(cfg["advi_steps"]),
                method=pymc_method,
                obj_optimizer=pm.adam(learning_rate=float(cfg["learning_rate"])),
                random_seed=seed,
                progressbar=False,
            )
            history = np.asarray(approximation.hist, dtype=float)
            if not np.isfinite(history).all():
                bad = int((~np.isfinite(history)).sum())
                raise RuntimeError(f"ADVI ELBO/loss history contains {bad} NaN or infinite values")
            inference_data = approximation.sample(
                draws=int(cfg["posterior_draws"]),
                random_seed=seed,
                return_inferencedata=True,
            )

        def values(name: str) -> np.ndarray:
            array = (
                inference_data.posterior[name]
                .stack(sample=("chain", "draw"))
                .transpose("sample", "regime")
                .to_numpy()
            )
            return np.asarray(array, dtype=float)

        samples = {
            "mu": values("mu_std") * return_scale,
            "c": values("c"),
            "nu": values("nu"),
        }
        if any(not np.isfinite(value).all() for value in samples.values()):
            raise RuntimeError("Posterior draw contains NaN or infinite values")
        if np.any(samples["c"] <= 0):
            raise RuntimeError("Posterior volatility multiplier c is not strictly positive")
        if np.any(samples["nu"] <= 2):
            raise RuntimeError("Posterior Student-t nu must be greater than 2")
        status, relative_change = self._convergence(
            history,
            int(cfg["convergence_window"]),
            float(cfg["convergence_tolerance"]),
        )
        if status != "converged":
            warnings.append(
                "ELBO moving-average convergence criterion was not met"
                if np.isfinite(relative_change)
                else "Not enough ELBO history for two convergence windows"
            )
        means = {name: value.mean(axis=0) for name, value in samples.items()}
        standard_deviations = {name: value.std(axis=0, ddof=1) for name, value in samples.items()}
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
        fingerprint = self._fingerprint(date_values, train_ret, train_prob, train_sigma)
        result = VariationalPosteriorResult(
            fitted=True,
            inference_method=str(cfg["method"]),
            elbo_history=history,
            posterior_samples=samples,
            posterior_means=means,
            posterior_standard_deviations=standard_deviations,
            credible_intervals=pd.DataFrame(credible_rows),
            regime_labels=labels,
            scaling_metadata={"return_scale": return_scale},
            train_date_range=(str(date_values[0]), str(date_values[-1])),
            data_fingerprint=fingerprint,
            random_seed=seed,
            convergence_status=status,
            warnings=warnings,
            inference_data=inference_data,
            effective_observations=effective,
        )
        self.result = result
        self._training_data = {
            "returns": train_ret,
            "probabilities": train_prob,
            "volatility": train_sigma,
        }
        return result

    def _require_result(self) -> VariationalPosteriorResult:
        if self.result is None or not self.result.fitted:
            raise RuntimeError("VariationalScenarioModel has not been fitted or loaded")
        return self.result

    def sample_parameters(self, n_draws: int, random_seed: int | None = None) -> dict[str, np.ndarray]:
        """Sample joint parameter vectors; row i is one coherent path draw."""
        result = self._require_result()
        if n_draws <= 0:
            raise ValueError("n_draws must be positive")
        available = len(result.posterior_samples["mu"])
        rng = np.random.default_rng(result.random_seed if random_seed is None else random_seed)
        indices = rng.choice(available, size=int(n_draws), replace=n_draws > available)
        return {name: np.asarray(values[indices], dtype=float).copy() for name, values in result.posterior_samples.items()}

    def posterior_summary(self) -> pd.DataFrame:
        return self._require_result().summary_frame()

    @staticmethod
    def _distribution_metrics(values: np.ndarray) -> dict[str, float]:
        data = np.asarray(values, dtype=float).ravel()
        data = data[np.isfinite(data)]
        if not len(data):
            raise ValueError("Cannot summarize an empty predictive distribution")
        absolute = np.abs(data)
        clustering = float(np.corrcoef(absolute[:-1], absolute[1:])[0, 1]) if len(data) > 2 else float("nan")
        return {
            "mean_return": float(np.mean(data)),
            "standard_deviation": float(np.std(data, ddof=1)),
            "skewness": float(skew(data, bias=False)),
            "kurtosis": float(kurtosis(data, fisher=False, bias=False)),
            "q01": float(np.quantile(data, 0.01)),
            "q05": float(np.quantile(data, 0.05)),
            "q95": float(np.quantile(data, 0.95)),
            "q99": float(np.quantile(data, 0.99)),
            "proportion_below_minus_2pct": float(np.mean(data < -0.02)),
            "volatility_clustering_proxy": clustering,
        }

    def _predictive_draws(self, parameter_samples: dict[str, np.ndarray], seed: int) -> np.ndarray:
        if self._training_data is None:
            raise RuntimeError("Predictive checks require training data from the current fit")
        probabilities = self._training_data["probabilities"]
        sigma = self._training_data["volatility"]
        n_draws = len(parameter_samples["mu"])
        n_observations, n_regimes = probabilities.shape
        rng = np.random.default_rng(seed)
        output = np.empty((n_draws, n_observations), dtype=float)
        cumulative = np.cumsum(probabilities, axis=1)
        for draw in range(n_draws):
            states = (rng.random(n_observations)[:, None] > cumulative).sum(axis=1).clip(max=n_regimes - 1)
            nu = parameter_samples["nu"][draw, states]
            standardized = rng.standard_t(nu) * np.sqrt((nu - 2.0) / nu)
            output[draw] = (
                parameter_samples["mu"][draw, states]
                + parameter_samples["c"][draw, states] * sigma * standardized
            )
        return output

    def posterior_predictive_check(self, n_draws: int | None = None) -> dict[str, Any]:
        """Return finite posterior-predictive draws and required diagnostics."""
        result = self._require_result()
        requested = int(n_draws or self.config["posterior_predictive_draws"])
        parameters = self.sample_parameters(requested, result.random_seed + 1)
        draws = self._predictive_draws(parameters, result.random_seed + 2)
        observed = self._training_data["returns"] if self._training_data is not None else np.empty(0)
        metrics = pd.DataFrame(
            [
                {"source": "observed", **self._distribution_metrics(observed)},
                {"source": "posterior_predictive", **self._distribution_metrics(draws)},
            ]
        )
        regime_rows: list[dict[str, object]] = []
        if self._training_data is not None:
            probabilities = self._training_data["probabilities"]
            for regime, label in enumerate(result.regime_labels):
                weights = probabilities[:, regime]
                observed_mean = float(np.sum(observed * weights) / max(weights.sum(), 1e-12))
                observed_volatility = float(
                    np.sqrt(
                        np.sum(((observed - observed_mean) ** 2) * weights)
                        / max(weights.sum(), 1e-12)
                    )
                )
                predictive_mean = float(np.mean(parameters["mu"][:, regime]))
                predictive_scale = float(
                    np.mean(parameters["c"][:, regime]) * np.sum(self._training_data["volatility"] * weights) / max(weights.sum(), 1e-12)
                )
                regime_rows.append(
                    {
                        "regime": regime,
                        "regime_label": label,
                        "effective_observations": float(weights.sum()),
                        "observed_weighted_mean": observed_mean,
                        "observed_weighted_volatility": observed_volatility,
                        "posterior_predictive_mean": predictive_mean,
                        "posterior_predictive_scale": predictive_scale,
                    }
                )
        return {"draws": draws, "metrics": metrics, "regime_metrics": pd.DataFrame(regime_rows)}

    def prior_predictive_check(self, n_draws: int | None = None) -> dict[str, Any]:
        """Draw the configured priors on the standardized-return scale."""
        result = self._require_result()
        requested = int(n_draws or self.config["posterior_predictive_draws"])
        rng = np.random.default_rng(result.random_seed)
        n_regimes = len(result.regime_labels)
        return_scale = float(result.scaling_metadata["return_scale"])
        mu = rng.normal(0.0, float(self.config["prior_mu_scale"]), size=(requested, n_regimes)) * return_scale
        c = np.exp(rng.normal(0.0, float(self.config["prior_log_scale_sd"]), size=(requested, n_regimes)))
        if bool(self.config["shared_nu"]):
            shared = 2.0 + rng.exponential(1.0 / float(self.config["prior_nu_rate"]), size=requested)
            nu = np.repeat(shared[:, None], n_regimes, axis=1)
        else:
            nu = 2.0 + rng.exponential(
                1.0 / float(self.config["prior_nu_rate"]),
                size=(requested, n_regimes),
            )
        parameters = {"mu": mu, "c": c, "nu": nu}
        draws = self._predictive_draws(parameters, result.random_seed + 1)
        return {
            "draws": draws,
            "metrics": pd.DataFrame([{"source": "prior_predictive", **self._distribution_metrics(draws)}]),
            "parameter_samples": parameters,
        }

    def save(self, path: str | Path) -> Path:
        """Save reusable posterior arrays, metadata, summaries and InferenceData."""
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
        result.summary_frame().to_csv(destination / "posterior_summary.csv", index=False)
        result.credible_intervals.to_csv(destination / "credible_intervals.csv", index=False)
        _parameter_frame(result.posterior_samples).corr().to_csv(destination / "posterior_correlations.csv")
        with (destination / "config_snapshot.yaml").open("w", encoding="utf-8") as handle:
            yaml.safe_dump({"bayesian": self.config}, handle, sort_keys=False, allow_unicode=True)
        data_metadata = {
            "data_fingerprint": result.data_fingerprint,
            "train_start": result.train_date_range[0],
            "train_end": result.train_date_range[1],
            "effective_observations": result.effective_observations.tolist(),
        }
        (destination / "data_fingerprint.json").write_text(
            json.dumps(data_metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        metadata = {
            "fitted": result.fitted,
            "inference_method": result.inference_method,
            "regime_labels": result.regime_labels,
            "scaling_metadata": result.scaling_metadata,
            "train_date_range": result.train_date_range,
            "data_fingerprint": result.data_fingerprint,
            "random_seed": result.random_seed,
            "convergence_status": result.convergence_status,
            "warnings": result.warnings,
            "effective_observations": result.effective_observations,
            "config": self.config,
        }
        (destination / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )
        if result.inference_data is not None:
            _, az = self._backend()
            posterior_path = destination / "posterior.nc"
            az.to_netcdf(result.inference_data, posterior_path)
            result.inference_data_path = str(posterior_path)
        return destination

    @classmethod
    def load(cls, path: str | Path) -> "VariationalScenarioModel":
        """Load posterior parameters without refitting or requiring PyMC."""
        source = Path(path)
        metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
        stored = np.load(source / "posterior_samples.npz")
        samples = {name: np.asarray(stored[name], dtype=float) for name in ("mu", "c", "nu")}
        if any(value.ndim != 2 or not np.isfinite(value).all() for value in samples.values()):
            raise ValueError("Saved posterior arrays must be finite two-dimensional matrices")
        if len({value.shape for value in samples.values()}) != 1:
            raise ValueError("Saved mu, c and nu posterior arrays must have identical shapes")
        if np.any(samples["c"] <= 0) or np.any(samples["nu"] <= 2):
            raise ValueError("Saved posterior violates c > 0 or nu > 2 constraints")
        elbo = pd.read_csv(source / "elbo_history.csv")["loss"].to_numpy(dtype=float)
        credible = pd.read_csv(source / "credible_intervals.csv")
        means = {name: value.mean(axis=0) for name, value in samples.items()}
        standard_deviations = {name: value.std(axis=0, ddof=1) for name, value in samples.items()}
        model = cls(metadata["config"])
        model.result = VariationalPosteriorResult(
            fitted=bool(metadata["fitted"]),
            inference_method=str(metadata["inference_method"]),
            elbo_history=elbo,
            posterior_samples=samples,
            posterior_means=means,
            posterior_standard_deviations=standard_deviations,
            credible_intervals=credible,
            regime_labels=list(metadata["regime_labels"]),
            scaling_metadata={key: float(value) for key, value in metadata["scaling_metadata"].items()},
            train_date_range=tuple(metadata["train_date_range"]),
            data_fingerprint=str(metadata["data_fingerprint"]),
            random_seed=int(metadata["random_seed"]),
            convergence_status=str(metadata["convergence_status"]),
            warnings=list(metadata["warnings"]),
            inference_data_path=str(source / "posterior.nc") if (source / "posterior.nc").exists() else None,
            effective_observations=np.asarray(metadata["effective_observations"], dtype=float),
        )
        return model
