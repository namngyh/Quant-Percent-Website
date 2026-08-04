"""Filtered Gaussian HMM regime features."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from scipy.special import logsumexp
from sklearn.preprocessing import StandardScaler

from raemf_mc.regime.state_alignment import align_states, reorder_transition


@dataclass
class FilteredHMMResult:
    probabilities: pd.DataFrame
    diagnostics: dict[str, object]
    state_mapping: pd.DataFrame


def _log_gaussian_diag(x: np.ndarray, means: np.ndarray, covars: np.ndarray) -> np.ndarray:
    if covars.ndim == 3:
        covars = np.stack([np.diag(c) for c in covars], axis=0)
    covars = np.maximum(covars, 1e-8)
    diff = x[:, None, :] - means[None, :, :]
    return -0.5 * (np.sum(np.log(2 * np.pi * covars)[None, :, :], axis=2) + np.sum(diff * diff / covars[None, :, :], axis=2))


def forward_filter(model: GaussianHMM, x_scaled: np.ndarray) -> np.ndarray:
    """Compute P(S_t | F_t) via forward recursion."""
    log_b = _log_gaussian_diag(x_scaled, model.means_, model.covars_)
    log_trans = np.log(np.maximum(model.transmat_, 1e-12))
    log_alpha = np.empty_like(log_b)
    log_alpha[0] = np.log(np.maximum(model.startprob_, 1e-12)) + log_b[0]
    log_alpha[0] -= logsumexp(log_alpha[0])
    for t in range(1, len(x_scaled)):
        pred = logsumexp(log_alpha[t - 1][:, None] + log_trans, axis=0)
        log_alpha[t] = pred + log_b[t]
        log_alpha[t] -= logsumexp(log_alpha[t])
    probs = np.exp(log_alpha)
    return probs / probs.sum(axis=1, keepdims=True)


def fit_filtered_hmm(
    base_features: pd.DataFrame,
    returns: pd.Series,
    train_idx: np.ndarray,
    n_states: int = 4,
    seeds: list[int] | None = None,
) -> FilteredHMMResult:
    """Fit multi-seed Gaussian HMM on train and return filtered probabilities for all rows."""
    seeds = seeds or [42]
    hmm_cols = [c for c in ["ret_1", "ewma_volatility", "log_return_20"] if c in base_features.columns]
    if len(hmm_cols) < 2:
        hmm_cols = list(base_features.columns[: min(4, base_features.shape[1])])
    x = base_features[hmm_cols].replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)
    scaler = StandardScaler().fit(x.iloc[train_idx])
    xs = scaler.transform(x)
    best: GaussianHMM | None = None
    best_score = -np.inf
    warnings: list[str] = []
    for seed in seeds:
        try:
            model = GaussianHMM(
                n_components=n_states,
                covariance_type="diag",
                n_iter=120,
                random_state=seed,
                min_covar=1e-5,
            )
            model.fit(xs[train_idx])
            score = float(model.score(xs[train_idx]))
            occ = np.bincount(model.predict(xs[train_idx]), minlength=n_states) / max(len(train_idx), 1)
            score -= float((occ < 0.03).sum() * 100.0)
            if score > best_score:
                best_score = score
                best = model
        except Exception as exc:  # pragma: no cover - depends on optimizer
            warnings.append(f"HMM seed {seed} failed: {exc}")
    if best is None:
        warnings.append("HMM failed; using uniform state probabilities")
        probs = np.full((len(x), n_states), 1.0 / n_states)
        trans = np.full((n_states, n_states), 1.0 / n_states)
    else:
        probs = forward_filter(best, xs)
        trans = best.transmat_
    alignment = align_states(probs, returns, train_idx)
    probs = probs[:, alignment.raw_order]
    trans = reorder_transition(trans, alignment.raw_order)
    prob_df = pd.DataFrame(probs, index=base_features.index, columns=[f"hmm_prob_state_{i}" for i in range(n_states)])
    entropy = -(prob_df * np.log(prob_df.clip(lower=1e-12))).sum(axis=1)
    prob_df["hmm_entropy"] = entropy
    state_mean = []
    state_vol = []
    for i in range(n_states):
        w = prob_df[f"hmm_prob_state_{i}"]
        denom = max(float(w.iloc[train_idx].sum()), 1e-12)
        state_mean.append(float((returns.iloc[train_idx].fillna(0) * w.iloc[train_idx]).sum() / denom))
        centered = returns.fillna(0) - state_mean[-1]
        state_vol.append(float(np.sqrt(((centered.iloc[train_idx] ** 2) * w.iloc[train_idx]).sum() / denom)))
    prob_only = prob_df[[f"hmm_prob_state_{i}" for i in range(n_states)]]
    prob_df["hmm_expected_return"] = prob_only.to_numpy() @ np.array(state_mean)
    prob_df["hmm_expected_volatility"] = prob_only.to_numpy() @ np.array(state_vol)
    most_likely = prob_only.to_numpy().argmax(axis=1)
    duration = pd.Series(most_likely).groupby((pd.Series(most_likely) != pd.Series(most_likely).shift()).cumsum()).cumcount() + 1
    prob_df["hmm_state_duration"] = duration.to_numpy()
    state_labels = alignment.mapping.sort_values("aligned_state")["economic_label"].tolist()
    prob_df["hmm_state_label"] = [state_labels[i] for i in most_likely]
    diagnostics = {
        "n_states": n_states,
        "score": best_score,
        "transition_matrix": trans.tolist(),
        "state_mean": state_mean,
        "state_volatility": state_vol,
        "state_labels": state_labels,
        "warnings": warnings,
        "feature_columns": hmm_cols,
    }
    return FilteredHMMResult(probabilities=prob_df, diagnostics=diagnostics, state_mapping=alignment.mapping)
