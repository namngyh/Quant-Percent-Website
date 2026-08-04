"""GPU-first full-rank ADVI backend implemented in PyTorch.

The generative model matches ``VariationalScenarioModel`` (PyMC): a
fixed-weight regime mixture of Student-t returns where filtered HMM
probabilities and EGARCH conditional volatility are known causal inputs.

    theta = mu + L @ eps,  eps ~ N(0, I)   (reparameterization gradient)

with ``L`` a lower-triangular Cholesky factor (full-rank) or a diagonal
(mean-field fallback). Likelihood, KL accumulation and the Student-t log
density stay in float32/float64 — no float16 anywhere in the ELBO.

Fit protocol per seed: warm-up + cosine learning-rate schedule, gradient
clipping, ELBO moving-average early stopping, NaN retry at lower learning
rates, then mean-field fallback. Every fallback is recorded and surfaced.
Multi-seed posteriors are pooled as an equal-weight mixture of per-seed
variational posteriors; per-seed summaries are kept for stability reports.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from raemf_mc.bayesian.priors import ScenarioPriors


@dataclass
class SeedFitResult:
    seed: int
    method: str
    learning_rate: float
    converged: bool
    final_elbo: float
    n_steps: int
    elbo_history: np.ndarray
    samples: dict[str, np.ndarray]
    fallbacks: list[dict[str, Any]] = field(default_factory=list)


def _torch():
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "The pytorch_cuda Bayesian backend requires PyTorch. Install torch or "
            "set bayesian.backend: pymc."
        ) from exc
    return torch


def _student_t_logpdf(x, nu, loc, scale, torch):
    """Log density of a location-scale Student-t, differentiable in all args."""
    z = (x - loc) / scale
    return (
        torch.lgamma((nu + 1.0) / 2.0)
        - torch.lgamma(nu / 2.0)
        - 0.5 * torch.log(nu * math.pi)
        - torch.log(scale)
        - (nu + 1.0) / 2.0 * torch.log1p(z * z / nu)
    )


class TorchScenarioELBO:
    """Joint log density (likelihood + priors + Jacobians) for the scenario model."""

    def __init__(
        self,
        scaled_returns: np.ndarray,
        probabilities: np.ndarray,
        scaled_sigma: np.ndarray,
        priors: ScenarioPriors,
        device: str,
        dtype: str = "float32",
    ) -> None:
        torch = _torch()
        self.torch = torch
        self.priors = priors
        self.device = device
        self.dtype = getattr(torch, dtype)
        self.n_regimes = int(probabilities.shape[1])
        self.returns = torch.as_tensor(np.array(scaled_returns, dtype=np.float64), dtype=self.dtype, device=device)
        self.log_probabilities = torch.log(
            torch.clamp(
                torch.as_tensor(np.array(probabilities, dtype=np.float64), dtype=self.dtype, device=device),
                min=1e-12,
            )
        )
        self.sigma = torch.as_tensor(np.array(scaled_sigma, dtype=np.float64), dtype=self.dtype, device=device)
        self.dim = priors.n_parameters(self.n_regimes)

    def unpack(self, theta):
        """Split an unconstrained (S, dim) batch into constrained parameters."""
        torch = self.torch
        K = self.n_regimes
        p = self.priors
        idx = 0
        if p.hierarchical:
            mu_global = theta[:, idx]
            idx += 1
            log_tau_mu = theta[:, idx]
            idx += 1
            mu_k = theta[:, idx : idx + K]
            idx += K
            log_c_global = theta[:, idx]
            idx += 1
            log_tau_c = theta[:, idx]
            idx += 1
            log_c_k = theta[:, idx : idx + K]
            idx += K
        else:
            mu_global = log_tau_mu = log_c_global = log_tau_c = None
            mu_k = theta[:, idx : idx + K]
            idx += K
            log_c_k = theta[:, idx : idx + K]
            idx += K
        nu_dim = 1 if p.shared_nu else K
        nu_raw = theta[:, idx : idx + nu_dim]
        idx += nu_dim
        nu_minus_two = torch.exp(torch.clamp(nu_raw, max=12.0))
        nu = 2.0 + nu_minus_two
        if p.shared_nu:
            nu = nu.expand(-1, K) if nu.shape[1] == 1 else nu
        c_k = torch.exp(torch.clamp(log_c_k, min=-8.0, max=8.0))
        return {
            "mu_global": mu_global,
            "log_tau_mu": log_tau_mu,
            "mu_k": mu_k,
            "log_c_global": log_c_global,
            "log_tau_c": log_tau_c,
            "log_c_k": log_c_k,
            "c_k": c_k,
            "nu_raw": nu_raw,
            "nu_minus_two": nu_minus_two,
            "nu": nu,
        }

    @staticmethod
    def _normal_logpdf(x, mean, sd, torch):
        return -0.5 * math.log(2.0 * math.pi) - torch.log(sd) - 0.5 * ((x - mean) / sd) ** 2

    def log_prior(self, parts):
        """Prior log density on constrained values plus transform Jacobians."""
        torch = self.torch
        p = self.priors
        tensor = lambda v: torch.as_tensor(v, dtype=self.dtype, device=self.device)  # noqa: E731
        total = torch.zeros(parts["mu_k"].shape[0], dtype=self.dtype, device=self.device)
        if p.hierarchical:
            total = total + self._normal_logpdf(parts["mu_global"], tensor(0.0), tensor(p.mu_global_sd), torch)
            # HalfNormal(s) on tau = exp(a): log N+(tau; s) + a  (Jacobian)
            for tau_key, sd in (("log_tau_mu", p.mu_tau_sd), ("log_tau_c", p.log_c_tau_sd)):
                a = parts[tau_key]
                tau = torch.exp(torch.clamp(a, min=-10.0, max=6.0))
                total = total + (
                    0.5 * math.log(2.0 / math.pi)
                    - math.log(sd)
                    - 0.5 * (tau / sd) ** 2
                    + a
                )
            tau_mu = torch.exp(torch.clamp(parts["log_tau_mu"], min=-10.0, max=6.0))
            tau_c = torch.exp(torch.clamp(parts["log_tau_c"], min=-10.0, max=6.0))
            total = total + self._normal_logpdf(
                parts["mu_k"], parts["mu_global"][:, None], tau_mu[:, None], torch
            ).sum(dim=1)
            total = total + self._normal_logpdf(parts["log_c_global"], tensor(0.0), tensor(p.log_c_global_sd), torch)
            total = total + self._normal_logpdf(
                parts["log_c_k"], parts["log_c_global"][:, None], tau_c[:, None], torch
            ).sum(dim=1)
        else:
            total = total + self._normal_logpdf(parts["mu_k"], tensor(0.0), tensor(p.mu_scale), torch).sum(dim=1)
            total = total + self._normal_logpdf(parts["log_c_k"], tensor(0.0), tensor(p.log_c_sd), torch).sum(dim=1)
        # nu_minus_two ~ Exponential(rate); raw = log(nu_minus_two) => Jacobian raw
        rate = tensor(p.nu_rate)
        total = total + (torch.log(rate) - rate * parts["nu_minus_two"] + parts["nu_raw"]).sum(dim=1)
        return total

    def log_likelihood(self, parts):
        """Mixture Student-t likelihood, summed over train observations."""
        torch = self.torch
        mu = parts["mu_k"][:, None, :]
        c = parts["c_k"][:, None, :]
        nu = parts["nu"][:, None, :]
        x = self.returns[None, :, None]
        scale = self.sigma[None, :, None] * c
        component = _student_t_logpdf(x, nu, mu, scale, torch)
        mixture = torch.logsumexp(self.log_probabilities[None, :, :] + component, dim=2)
        return mixture.sum(dim=1)

    def log_joint(self, theta):
        parts = self.unpack(theta)
        return self.log_likelihood(parts) + self.log_prior(parts)


class _Approximation:
    """Full-rank or mean-field Gaussian in unconstrained space."""

    def __init__(self, dim: int, method: str, device: str, dtype, torch) -> None:
        self.torch = torch
        self.method = method
        self.dim = dim
        self.loc = torch.zeros(dim, dtype=dtype, device=device, requires_grad=True)
        init_scale = math.log(math.expm1(0.1))
        self.raw_diag = torch.full((dim,), init_scale, dtype=dtype, device=device, requires_grad=True)
        if method == "fullrank_advi":
            self.off_diag = torch.zeros(dim * (dim - 1) // 2, dtype=dtype, device=device, requires_grad=True)
            self.tril_index = torch.tril_indices(dim, dim, offset=-1, device=device)
        else:
            self.off_diag = None
            self.tril_index = None

    def parameters(self):
        params = [self.loc, self.raw_diag]
        if self.off_diag is not None:
            params.append(self.off_diag)
        return params

    def scale_tril(self):
        torch = self.torch
        diag = torch.nn.functional.softplus(self.raw_diag) + 1e-6
        if self.off_diag is None:
            return torch.diag(diag)
        L = torch.diag(diag)
        L[self.tril_index[0], self.tril_index[1]] = self.off_diag
        return L

    def rsample(self, n: int):
        torch = self.torch
        eps = torch.randn(n, self.dim, dtype=self.loc.dtype, device=self.loc.device)
        return self.loc[None, :] + eps @ self.scale_tril().T

    def entropy(self):
        torch = self.torch
        diag = torch.nn.functional.softplus(self.raw_diag) + 1e-6
        return 0.5 * self.dim * (1.0 + math.log(2.0 * math.pi)) + torch.log(diag).sum()


def fit_torch_advi(
    elbo_model: TorchScenarioELBO,
    *,
    method: str = "fullrank_advi",
    seed: int = 42,
    max_steps: int = 15_000,
    min_steps: int = 1_000,
    learning_rate: float = 0.005,
    retry_learning_rates: tuple[float, ...] = (0.001,),
    vi_samples_per_step: int = 8,
    gradient_clip_norm: float = 5.0,
    early_stopping_patience: int = 2_000,
    convergence_window: int = 500,
    convergence_tolerance: float = 1e-3,
    posterior_draws: int = 1_200,
    fallback_to_meanfield: bool = True,
) -> SeedFitResult:
    """Fit one ADVI approximation with retry/fallback; never silently degrades."""
    torch = _torch()
    fallbacks: list[dict[str, Any]] = []
    attempts: list[tuple[str, float]] = [(method, learning_rate)]
    attempts += [(method, lr) for lr in retry_learning_rates]
    if fallback_to_meanfield and method == "fullrank_advi":
        attempts.append(("meanfield_advi", learning_rate))
        attempts += [("meanfield_advi", lr) for lr in retry_learning_rates]
    last_error: str = ""
    for attempt_method, attempt_lr in attempts:
        outcome = _fit_single_attempt(
            elbo_model,
            torch,
            attempt_method,
            seed,
            max_steps,
            min_steps,
            attempt_lr,
            vi_samples_per_step,
            gradient_clip_norm,
            early_stopping_patience,
            convergence_window,
            convergence_tolerance,
            posterior_draws,
        )
        if outcome is not None:
            outcome.fallbacks = fallbacks
            return outcome
        last_error = f"non-finite ELBO with method={attempt_method}, lr={attempt_lr}"
        fallbacks.append({"seed": seed, "failed_method": attempt_method, "failed_learning_rate": attempt_lr, "reason": "non_finite_elbo"})
    raise RuntimeError(f"All ADVI attempts failed for seed {seed}: {last_error}")


def _fit_single_attempt(
    elbo_model: TorchScenarioELBO,
    torch,
    method: str,
    seed: int,
    max_steps: int,
    min_steps: int,
    learning_rate: float,
    vi_samples_per_step: int,
    gradient_clip_norm: float,
    early_stopping_patience: int,
    convergence_window: int,
    convergence_tolerance: float,
    posterior_draws: int,
) -> SeedFitResult | None:
    torch.manual_seed(seed)
    approximation = _Approximation(elbo_model.dim, method, elbo_model.device, elbo_model.dtype, torch)
    optimizer = torch.optim.Adam(approximation.parameters(), lr=learning_rate)
    warmup = max(100, max_steps // 50)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer,
        lambda step: min(1.0, (step + 1) / warmup)
        * (0.5 * (1.0 + math.cos(math.pi * min(step, max_steps) / max_steps))),
    )
    history: list[float] = []
    best_loss = float("inf")
    best_state: list[Any] | None = None
    steps_since_best = 0
    for step in range(max_steps):
        optimizer.zero_grad()
        theta = approximation.rsample(vi_samples_per_step)
        # negative ELBO = -E_q[log p] - H[q]; accumulation stays in float32+
        loss = -(elbo_model.log_joint(theta).mean() + approximation.entropy())
        if not torch.isfinite(loss):
            return None
        loss.backward()
        torch.nn.utils.clip_grad_norm_(approximation.parameters(), gradient_clip_norm)
        optimizer.step()
        scheduler.step()
        loss_value = float(loss.detach())
        history.append(loss_value)
        if loss_value < best_loss - 1e-10:
            best_loss = loss_value
            best_state = [p.detach().clone() for p in approximation.parameters()]
            steps_since_best = 0
        else:
            steps_since_best += 1
        if step >= min_steps and steps_since_best >= early_stopping_patience:
            break
        if step >= min_steps and len(history) >= 2 * convergence_window:
            previous = float(np.mean(history[-2 * convergence_window : -convergence_window]))
            current = float(np.mean(history[-convergence_window:]))
            if abs(current - previous) / max(abs(previous), 1.0) <= convergence_tolerance:
                break
    if best_state is not None:
        with torch.no_grad():
            for parameter, stored in zip(approximation.parameters(), best_state, strict=True):
                parameter.copy_(stored)
    history_array = np.asarray(history, dtype=float)
    if not np.isfinite(history_array).all():
        return None
    with torch.no_grad():
        theta = approximation.rsample(posterior_draws)
        parts = elbo_model.unpack(theta)
        samples = {
            "mu": parts["mu_k"].detach().cpu().numpy().astype(float),
            "c": parts["c_k"].detach().cpu().numpy().astype(float),
            "nu": parts["nu"].detach().cpu().numpy().astype(float),
        }
    if any(not np.isfinite(v).all() for v in samples.values()):
        return None
    converged = False
    if len(history_array) >= 2 * convergence_window:
        previous = float(np.mean(history_array[-2 * convergence_window : -convergence_window]))
        current = float(np.mean(history_array[-convergence_window:]))
        converged = abs(current - previous) / max(abs(previous), 1.0) <= convergence_tolerance
    return SeedFitResult(
        seed=seed,
        method=method,
        learning_rate=learning_rate,
        converged=converged,
        final_elbo=-float(np.mean(history_array[-min(convergence_window, len(history_array)) :])),
        n_steps=len(history_array),
        elbo_history=history_array,
        samples=samples,
    )


def pool_seed_results(
    seed_results: list[SeedFitResult],
    posterior_draws: int,
    pool_seed: int = 0,
) -> tuple[dict[str, np.ndarray], pd.DataFrame]:
    """Equal-weight mixture of per-seed posteriors plus a stability frame.

    Every seed contributes the same number of draws regardless of its final
    ELBO, so a single lucky seed cannot dominate the pooled posterior.
    """
    if not seed_results:
        raise ValueError("No seed results to pool")
    rng = np.random.default_rng(pool_seed)
    per_seed = max(1, posterior_draws // len(seed_results))
    pooled: dict[str, list[np.ndarray]] = {"mu": [], "c": [], "nu": []}
    rows: list[dict[str, Any]] = []
    for result in seed_results:
        available = len(result.samples["mu"])
        take = rng.choice(available, size=per_seed, replace=per_seed > available)
        for name in pooled:
            pooled[name].append(result.samples[name][take])
        n_regimes = result.samples["mu"].shape[1]
        row: dict[str, Any] = {
            "seed": result.seed,
            "method": result.method,
            "learning_rate": result.learning_rate,
            "converged": result.converged,
            "final_elbo": result.final_elbo,
            "n_steps": result.n_steps,
        }
        for name in ("mu", "c", "nu"):
            for regime in range(n_regimes):
                row[f"{name}_{regime}_mean"] = float(result.samples[name][:, regime].mean())
                row[f"{name}_{regime}_sd"] = float(result.samples[name][:, regime].std(ddof=1))
                row[f"{name}_{regime}_q025"] = float(np.quantile(result.samples[name][:, regime], 0.025))
                row[f"{name}_{regime}_q975"] = float(np.quantile(result.samples[name][:, regime], 0.975))
        rows.append(row)
    samples = {name: np.concatenate(chunks, axis=0) for name, chunks in pooled.items()}
    return samples, pd.DataFrame(rows)


def seed_stability_metrics(by_seed: pd.DataFrame) -> dict[str, float]:
    """Max pairwise distance between per-seed posterior means, per parameter."""
    metrics: dict[str, float] = {}
    mean_columns = [c for c in by_seed.columns if c.endswith("_mean")]
    for column in mean_columns:
        values = by_seed[column].to_numpy(dtype=float)
        metrics[f"{column}_max_pairwise_gap"] = float(values.max() - values.min()) if len(values) > 1 else 0.0
    metrics["n_seeds"] = float(len(by_seed))
    metrics["n_converged"] = float(by_seed["converged"].sum())
    return metrics
