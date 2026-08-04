"""Persist prior/posterior predictive diagnostics for the scenario layer."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from raemf_mc.bayesian.variational import VariationalScenarioModel, _parameter_frame


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def write_diagnostic_artifacts(model: VariationalScenarioModel, path: str | Path) -> list[Path]:
    """Write required predictive metrics, compressed draws and diagnostic plots."""
    result = model._require_result()
    destination = Path(path)
    destination.mkdir(parents=True, exist_ok=True)
    posterior = model.posterior_predictive_check()
    prior = model.prior_predictive_check()
    posterior["metrics"].to_csv(destination / "posterior_predictive_metrics.csv", index=False)
    prior["metrics"].to_csv(destination / "prior_predictive_metrics.csv", index=False)
    posterior["regime_metrics"].to_csv(destination / "posterior_regime_metrics.csv", index=False)
    np.savez_compressed(destination / "posterior_predictive_draws.npz", draws=posterior["draws"])

    paths: list[Path] = []
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(result.elbo_history, linewidth=0.8)
    ax.set(title="ADVI loss / negative ELBO", xlabel="Iteration", ylabel="Loss")
    paths.append(destination / "elbo_convergence.png")
    _save(fig, paths[-1])

    for parameter in ("mu", "c", "nu"):
        fig, ax = plt.subplots(figsize=(7, 4))
        for regime, label in enumerate(result.regime_labels):
            ax.hist(result.posterior_samples[parameter][:, regime], bins=35, density=True, alpha=0.35, label=label)
        ax.set(title=f"Posterior {parameter}", xlabel=parameter, ylabel="Density")
        ax.legend(fontsize=7)
        paths.append(destination / f"posterior_{parameter}.png")
        _save(fig, paths[-1])

    correlation = _parameter_frame(result.posterior_samples).corr()
    fig, ax = plt.subplots(figsize=(8, 7))
    image = ax.imshow(correlation, vmin=-1, vmax=1, cmap="coolwarm")
    ax.set_xticks(range(len(correlation)), correlation.columns, rotation=90, fontsize=6)
    ax.set_yticks(range(len(correlation)), correlation.index, fontsize=6)
    fig.colorbar(image, ax=ax, fraction=0.04)
    ax.set_title("Posterior correlation matrix")
    paths.append(destination / "posterior_correlation_matrix.png")
    _save(fig, paths[-1])

    observed = model._training_data["returns"]
    simulated = posterior["draws"].ravel()
    fig, ax = plt.subplots(figsize=(7, 4))
    limits = np.quantile(np.concatenate([observed, simulated]), [0.005, 0.995])
    ax.hist(observed, bins=45, range=tuple(limits), density=True, alpha=0.5, label="Observed")
    ax.hist(simulated, bins=45, range=tuple(limits), density=True, alpha=0.4, label="Posterior predictive")
    ax.set(title="Observed vs posterior-predictive returns", xlabel="Log-return", ylabel="Density")
    ax.legend()
    paths.append(destination / "observed_vs_posterior_predictive_histogram.png")
    _save(fig, paths[-1])

    probabilities = np.linspace(0.005, 0.25, 60)
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(np.quantile(observed, probabilities), np.quantile(simulated, probabilities), s=12)
    lower = min(ax.get_xlim()[0], ax.get_ylim()[0])
    upper = max(ax.get_xlim()[1], ax.get_ylim()[1])
    ax.plot([lower, upper], [lower, upper], linestyle="--", color="black", linewidth=0.8)
    ax.set(title="Lower-tail QQ plot", xlabel="Observed quantiles", ylabel="Predictive quantiles")
    paths.append(destination / "lower_tail_qq.png")
    _save(fig, paths[-1])

    regime_metrics = posterior["regime_metrics"]
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(regime_metrics))
    ax.bar(
        x - 0.18,
        regime_metrics["observed_weighted_volatility"],
        width=0.36,
        label="Observed weighted volatility",
    )
    ax.bar(x + 0.18, regime_metrics["posterior_predictive_scale"], width=0.36, label="Predictive scale")
    ax.set_xticks(x, regime_metrics["regime_label"], rotation=20)
    ax.set(title="Observed mean vs simulated regime-conditional volatility", ylabel="Return scale")
    ax.legend()
    paths.append(destination / "regime_conditional_volatility.png")
    _save(fig, paths[-1])

    fig, axes = plt.subplots(1, 3, figsize=(11, 3.5))
    for ax, parameter in zip(axes, ("mu", "c", "nu"), strict=True):
        prior_values = prior["parameter_samples"][parameter].ravel()
        posterior_values = result.posterior_samples[parameter].ravel()
        combined = np.concatenate([prior_values, posterior_values])
        limits = np.quantile(combined, [0.005, 0.995])
        ax.hist(prior_values, bins=35, range=tuple(limits), density=True, alpha=0.4, label="Prior")
        ax.hist(posterior_values, bins=35, range=tuple(limits), density=True, alpha=0.5, label="Posterior")
        ax.set_title(parameter)
    axes[0].legend()
    paths.append(destination / "prior_vs_posterior.png")
    _save(fig, paths[-1])

    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8))
    for ax, parameter in zip(axes, ("mu", "c", "nu"), strict=True):
        values = result.posterior_samples[parameter]
        means = values.mean(axis=0)
        low, high = np.quantile(values, [0.025, 0.975], axis=0)
        x = np.arange(values.shape[1])
        ax.errorbar(means, x, xerr=[means - low, high - means], fmt="o", capsize=3)
        ax.set_yticks(x, result.regime_labels)
        ax.set_title(parameter)
    fig.suptitle("Posterior 95% intervals by regime")
    paths.append(destination / "posterior_intervals_by_regime.png")
    _save(fig, paths[-1])
    return paths
