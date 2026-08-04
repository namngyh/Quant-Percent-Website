"""Bayesian hierarchical multinomial regime head (ablation model).

A small class-weighted multinomial logistic regression with hierarchical
shrinkage priors, fitted with reparameterized ADVI on PyTorch (CUDA when
available). It is an *ablation* benchmark against the production EBM — it
never replaces the EBM automatically.

Priors (per class c, feature j, on standardized features):

    tau_c ~ HalfNormal(tau_scale)          # per-class coefficient scale
    beta_{j,c} ~ Normal(0, tau_c)          # partial pooling within a class
    intercept_c ~ Normal(0, intercept_sd)

Feature selection (top-k mutual information) and standardization are fitted
strictly on the training rows supplied to :meth:`fit`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_classif

from raemf_mc import CLASS_ORDER
from raemf_mc.models.base import class_weights as balanced_class_weights
from raemf_mc.runtime.hardware import select_device


@dataclass
class RegimeHeadFit:
    seed: int
    method: str
    converged: bool
    final_elbo: float
    n_steps: int
    elbo_history: np.ndarray
    beta: np.ndarray  # (draws, p, C)
    intercept: np.ndarray  # (draws, C)
    fallbacks: list[dict[str, Any]] = field(default_factory=list)


class BayesianRegimeHead:
    def __init__(
        self,
        max_features: int = 20,
        seeds: tuple[int, ...] = (11, 42, 73),
        advi_steps: int = 6_000,
        min_steps: int = 1_000,
        posterior_draws: int = 800,
        learning_rate: float = 0.01,
        vi_samples_per_step: int = 8,
        gradient_clip_norm: float = 5.0,
        early_stopping_patience: int = 1_500,
        convergence_window: int = 300,
        convergence_tolerance: float = 1e-3,
        tau_scale: float = 1.0,
        intercept_sd: float = 2.0,
        device: str = "auto",
        use_class_weights: bool = True,
    ) -> None:
        self.max_features = int(max_features)
        self.seeds = tuple(int(s) for s in seeds)
        self.advi_steps = int(advi_steps)
        self.min_steps = int(min_steps)
        self.posterior_draws = int(posterior_draws)
        self.learning_rate = float(learning_rate)
        self.vi_samples_per_step = int(vi_samples_per_step)
        self.gradient_clip_norm = float(gradient_clip_norm)
        self.early_stopping_patience = int(early_stopping_patience)
        self.convergence_window = int(convergence_window)
        self.convergence_tolerance = float(convergence_tolerance)
        self.tau_scale = float(tau_scale)
        self.intercept_sd = float(intercept_sd)
        self.device_request = device
        self.use_class_weights = bool(use_class_weights)
        self.selected_features: list[str] = []
        self.feature_mean: np.ndarray | None = None
        self.feature_std: np.ndarray | None = None
        self.fits: list[RegimeHeadFit] = []
        self.classes_: list[str] = list(CLASS_ORDER)

    # ---------------------------------------------------------------- fitting
    def _select_features(self, x: pd.DataFrame, y: pd.Series, seed: int) -> list[str]:
        numeric = x.select_dtypes(include=[np.number])
        filled = numeric.fillna(numeric.median(numeric_only=True)).fillna(0.0)
        constant = filled.std(ddof=0) <= 1e-12
        filled = filled.loc[:, ~constant]
        if filled.shape[1] <= self.max_features:
            return list(filled.columns)
        scores = mutual_info_classif(
            filled.to_numpy(dtype=float), y.astype(str).to_numpy(), random_state=seed
        )
        order = np.argsort(scores)[::-1][: self.max_features]
        return [filled.columns[i] for i in sorted(order)]

    def fit(self, x_train: pd.DataFrame, y_train: pd.Series) -> "BayesianRegimeHead":
        import torch

        device = select_device(self.device_request)
        y = y_train.astype(str).reset_index(drop=True)
        self.selected_features = self._select_features(x_train, y, self.seeds[0])
        raw = x_train[self.selected_features].to_numpy(dtype=float)
        raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
        self.feature_mean = raw.mean(axis=0)
        self.feature_std = np.maximum(raw.std(axis=0, ddof=0), 1e-8)
        features = (raw - self.feature_mean) / self.feature_std
        labels = np.array([self.classes_.index(v) for v in y], dtype=np.int64)
        if self.use_class_weights:
            weights = balanced_class_weights(y)[labels]
            weights = weights / weights.mean()
        else:
            weights = np.ones(len(labels))

        n, p = features.shape
        n_classes = len(self.classes_)
        dim = n_classes + p * n_classes + n_classes  # log_tau, beta, intercept
        x_tensor = torch.as_tensor(features, dtype=torch.float32, device=device)
        y_tensor = torch.as_tensor(labels, device=device)
        w_tensor = torch.as_tensor(weights, dtype=torch.float32, device=device)

        def unpack(theta):
            idx = 0
            log_tau = theta[:, idx : idx + n_classes]
            idx += n_classes
            beta = theta[:, idx : idx + p * n_classes].reshape(-1, p, n_classes)
            idx += p * n_classes
            intercept = theta[:, idx : idx + n_classes]
            return log_tau, beta, intercept

        def log_joint(theta):
            log_tau, beta, intercept = unpack(theta)
            tau = torch.exp(torch.clamp(log_tau, min=-8.0, max=4.0))
            # HalfNormal(tau_scale) prior on tau + log|d tau/d log_tau| Jacobian
            prior = (
                0.5 * math.log(2.0 / math.pi)
                - math.log(self.tau_scale)
                - 0.5 * (tau / self.tau_scale) ** 2
                + log_tau
            ).sum(dim=1)
            prior = prior + (
                -0.5 * math.log(2.0 * math.pi)
                - torch.log(tau[:, None, :])
                - 0.5 * (beta / tau[:, None, :]) ** 2
            ).sum(dim=(1, 2))
            prior = prior + (
                -0.5 * math.log(2.0 * math.pi)
                - math.log(self.intercept_sd)
                - 0.5 * (intercept / self.intercept_sd) ** 2
            ).sum(dim=1)
            logits = torch.einsum("np,spc->snc", x_tensor, beta) + intercept[:, None, :]
            log_probability = torch.log_softmax(logits, dim=2)
            picked = log_probability.gather(2, y_tensor[None, :, None].expand(theta.shape[0], -1, -1)).squeeze(2)
            return (picked * w_tensor[None, :]).sum(dim=1) + prior

        method = "fullrank_advi" if dim <= 150 else "meanfield_advi"
        self.fits = []
        for seed in self.seeds:
            fit = self._fit_seed(torch, device, dim, method, seed, log_joint, unpack)
            self.fits.append(fit)
        if not self.fits:
            raise RuntimeError("Bayesian regime head failed to fit any seed")
        return self

    def _fit_seed(self, torch, device, dim, method, seed, log_joint, unpack) -> RegimeHeadFit:
        from raemf_mc.bayesian.torch_backend import _Approximation

        fallbacks: list[dict[str, Any]] = []
        for attempt_method, lr in ((method, self.learning_rate), (method, self.learning_rate / 5), ("meanfield_advi", self.learning_rate / 5)):
            torch.manual_seed(seed)
            approximation = _Approximation(dim, attempt_method, device, torch.float32, torch)
            optimizer = torch.optim.Adam(approximation.parameters(), lr=lr)
            warmup = max(50, self.advi_steps // 50)
            scheduler = torch.optim.lr_scheduler.LambdaLR(
                optimizer,
                lambda step: min(1.0, (step + 1) / warmup)
                * (0.5 * (1.0 + math.cos(math.pi * min(step, self.advi_steps) / self.advi_steps))),
            )
            history: list[float] = []
            failed = False
            best_loss = float("inf")
            steps_since_best = 0
            for step in range(self.advi_steps):
                optimizer.zero_grad()
                theta = approximation.rsample(self.vi_samples_per_step)
                loss = -(log_joint(theta).mean() + approximation.entropy())
                if not torch.isfinite(loss):
                    failed = True
                    break
                loss.backward()
                torch.nn.utils.clip_grad_norm_(approximation.parameters(), self.gradient_clip_norm)
                optimizer.step()
                scheduler.step()
                value = float(loss.detach())
                history.append(value)
                if value < best_loss - 1e-10:
                    best_loss = value
                    steps_since_best = 0
                else:
                    steps_since_best += 1
                if step >= self.min_steps and steps_since_best >= self.early_stopping_patience:
                    break
                window = self.convergence_window
                if step >= self.min_steps and len(history) >= 2 * window:
                    previous = float(np.mean(history[-2 * window : -window]))
                    current = float(np.mean(history[-window:]))
                    if abs(current - previous) / max(abs(previous), 1.0) <= self.convergence_tolerance:
                        break
            if failed or not history:
                fallbacks.append({"seed": seed, "failed_method": attempt_method, "failed_learning_rate": lr, "reason": "non_finite_elbo"})
                continue
            with torch.no_grad():
                theta = approximation.rsample(self.posterior_draws)
                _, beta, intercept = unpack(theta)
                beta_np = beta.detach().cpu().numpy().astype(float)
                intercept_np = intercept.detach().cpu().numpy().astype(float)
            if not (np.isfinite(beta_np).all() and np.isfinite(intercept_np).all()):
                fallbacks.append({"seed": seed, "failed_method": attempt_method, "failed_learning_rate": lr, "reason": "non_finite_posterior"})
                continue
            history_array = np.asarray(history, dtype=float)
            window = self.convergence_window
            converged = False
            if len(history_array) >= 2 * window:
                previous = float(np.mean(history_array[-2 * window : -window]))
                current = float(np.mean(history_array[-window:]))
                converged = abs(current - previous) / max(abs(previous), 1.0) <= self.convergence_tolerance
            return RegimeHeadFit(
                seed=seed,
                method=attempt_method,
                converged=converged,
                final_elbo=-float(np.mean(history_array[-min(window, len(history_array)) :])),
                n_steps=len(history_array),
                elbo_history=history_array,
                beta=beta_np,
                intercept=intercept_np,
                fallbacks=fallbacks,
            )
        raise RuntimeError(f"Bayesian regime head: all ADVI attempts failed for seed {seed}")

    # ------------------------------------------------------------- prediction
    def _standardize(self, x: pd.DataFrame) -> np.ndarray:
        raw = x[self.selected_features].to_numpy(dtype=float)
        raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
        return (raw - self.feature_mean) / self.feature_std

    def _draw_probabilities(self, x: pd.DataFrame, per_seed_draws: int | None = None) -> np.ndarray:
        """Posterior predictive class probabilities, shape (draws, n, C)."""
        features = self._standardize(x)
        chunks: list[np.ndarray] = []
        for fit in self.fits:
            beta = fit.beta
            intercept = fit.intercept
            if per_seed_draws is not None and per_seed_draws < len(beta):
                beta = beta[:per_seed_draws]
                intercept = intercept[:per_seed_draws]
            logits = np.einsum("np,spc->snc", features, beta) + intercept[:, None, :]
            logits -= logits.max(axis=2, keepdims=True)
            probability = np.exp(logits)
            probability /= probability.sum(axis=2, keepdims=True)
            chunks.append(probability)
        return np.concatenate(chunks, axis=0)

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        """Posterior-mean class probabilities."""
        return self._draw_probabilities(x, per_seed_draws=max(1, self.posterior_draws // max(len(self.fits), 1))).mean(axis=0)

    def predict_with_uncertainty(self, x: pd.DataFrame) -> dict[str, np.ndarray]:
        draws = self._draw_probabilities(x, per_seed_draws=max(1, self.posterior_draws // max(len(self.fits), 1)))
        mean = draws.mean(axis=0)
        lower = np.quantile(draws, 0.05, axis=0)
        upper = np.quantile(draws, 0.95, axis=0)
        epistemic = draws.std(axis=0, ddof=1).mean(axis=1)
        entropy = -np.sum(mean * np.log(np.clip(mean, 1e-12, None)), axis=1)
        return {
            "mean": mean,
            "q05": lower,
            "q95": upper,
            "epistemic_sd": epistemic,
            "predictive_entropy": entropy,
        }

    def seed_summary(self) -> pd.DataFrame:
        rows = []
        for fit in self.fits:
            rows.append(
                {
                    "seed": fit.seed,
                    "method": fit.method,
                    "converged": fit.converged,
                    "final_elbo": fit.final_elbo,
                    "n_steps": fit.n_steps,
                    "n_fallbacks": len(fit.fallbacks),
                    "beta_mean_norm": float(np.linalg.norm(fit.beta.mean(axis=0))),
                }
            )
        return pd.DataFrame(rows)
