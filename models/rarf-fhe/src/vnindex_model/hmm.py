"""Train-only Gaussian HMM with forward-filtered regime probabilities."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from scipy.special import logsumexp
from sklearn.preprocessing import StandardScaler

from .validation import assert_probabilities


@dataclass
class FilteredHMM:
    model: GaussianHMM
    scaler: StandardScaler
    feature_names: list[str]
    probabilities: pd.DataFrame
    transition_matrix: np.ndarray
    economic_labels: list[str]
    diagnostics: dict[str, object]


def _log_emissions(model: GaussianHMM, observations: np.ndarray) -> np.ndarray:
    covariances = model.covars_
    if covariances.ndim == 3:
        covariances = np.stack([np.diag(item) for item in covariances])
    covariances = np.maximum(covariances, 1e-8)
    difference = observations[:, None, :] - model.means_[None, :, :]
    return -0.5 * (
        np.sum(np.log(2 * np.pi * covariances)[None, :, :], axis=2)
        + np.sum(difference**2 / covariances[None, :, :], axis=2)
    )


def forward_filter_with_state(model: GaussianHMM, observations: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Forward-filter a batch and also return the final normalized log-alpha.

    The trailing log-alpha is the sufficient statistic the online layer needs to
    continue the recursion one session at a time without refiltering history.
    Probabilities stay in the model's raw state order, exactly like
    :func:`forward_filter`; the economic permutation is applied by callers.
    """
    emissions = _log_emissions(model, observations)
    transition = np.log(np.maximum(model.transmat_, 1e-12))
    alpha = np.empty_like(emissions)
    alpha[0] = np.log(np.maximum(model.startprob_, 1e-12)) + emissions[0]
    alpha[0] -= logsumexp(alpha[0])
    for row in range(1, len(observations)):
        alpha[row] = emissions[row] + logsumexp(alpha[row - 1][:, None] + transition, axis=0)
        alpha[row] -= logsumexp(alpha[row])
    probabilities = np.exp(alpha)
    assert_probabilities(probabilities)
    return probabilities, alpha[-1]


def forward_filter(model: GaussianHMM, observations: np.ndarray) -> np.ndarray:
    """Compute P(S_t | F_t) only; hmmlearn smoothed posteriors are not used."""
    return forward_filter_with_state(model, observations)[0]


def forward_filter_step(
    model: GaussianHMM,
    previous_log_alpha: np.ndarray,
    new_observation_scaled: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Advance the forward recursion by exactly one observation.

    ``previous_log_alpha`` is the normalized log-alpha at t-1 (raw state order),
    ``new_observation_scaled`` a single row already transformed by the fitted
    scaler. Returns the new normalized log-alpha and P(S_t | F_t).
    """
    observation = np.asarray(new_observation_scaled, dtype=float).reshape(1, -1)
    emission = _log_emissions(model, observation)[0]
    transition = np.log(np.maximum(model.transmat_, 1e-12))
    log_alpha = emission + logsumexp(np.asarray(previous_log_alpha, dtype=float)[:, None] + transition, axis=0)
    log_alpha -= logsumexp(log_alpha)
    probabilities = np.exp(log_alpha)
    assert_probabilities(probabilities[None, :])
    return log_alpha, probabilities


def regime_feature_frame(
    probabilities: np.ndarray, transition_matrix: np.ndarray, index=None
) -> pd.DataFrame:
    """Posterior columns plus the regime features the forests consume.

    Shared by the batch fit and the online session update so the two tiers
    cannot drift apart on how entropy, run length, expected duration and switch
    probability are defined. ``probabilities`` must already be in economic
    order, matching ``transition_matrix``.
    """
    probabilities = np.asarray(probabilities, dtype=float)
    states = probabilities.shape[1]
    columns = [f"hmm_probability_{position}" for position in range(states)]
    frame = pd.DataFrame(probabilities, index=index, columns=columns)
    frame["hmm_entropy"] = -(frame * np.log(frame.clip(lower=1e-12))).sum(axis=1)
    most_likely = probabilities.argmax(axis=1)
    runs = pd.Series(most_likely).ne(pd.Series(most_likely).shift()).cumsum()
    frame["hmm_state_duration"] = pd.Series(most_likely).groupby(runs).cumcount().add(1).to_numpy()
    diagonal = np.diag(np.asarray(transition_matrix, dtype=float))
    frame["hmm_expected_duration"] = probabilities @ (1 / np.maximum(1 - diagonal, 1e-6))
    frame["hmm_transition_probability"] = 1 - probabilities @ diagonal
    frame["hmm_state"] = most_likely
    return frame


def _economic_order(
    probabilities: np.ndarray, returns: pd.Series, drawdown: pd.Series, train_index: np.ndarray
) -> tuple[np.ndarray, list[str], list[dict[str, float]]]:
    statistics: list[dict[str, float]] = []
    train_returns = returns.iloc[train_index].fillna(0).to_numpy()
    train_drawdown = drawdown.iloc[train_index].fillna(0).to_numpy()
    for state in range(probabilities.shape[1]):
        weights = probabilities[train_index, state]
        denominator = max(weights.sum(), 1e-12)
        mean = float(np.sum(weights * train_returns) / denominator)
        volatility = float(np.sqrt(np.sum(weights * (train_returns - mean) ** 2) / denominator))
        mean_drawdown = float(np.sum(weights * train_drawdown) / denominator)
        statistics.append(
            {"raw_state": state, "mean_return": mean, "volatility": volatility, "mean_drawdown": mean_drawdown}
        )
    stress = max(
        range(len(statistics)),
        key=lambda idx: statistics[idx]["volatility"]
        - 2 * statistics[idx]["mean_return"]
        - statistics[idx]["mean_drawdown"],
    )
    remaining = [idx for idx in range(len(statistics)) if idx != stress]
    ordered_remaining = sorted(remaining, key=lambda idx: statistics[idx]["mean_return"])
    order = np.array(ordered_remaining + [stress], dtype=int)
    if len(order) == 2:
        labels = ["Bull" if statistics[order[0]]["mean_return"] > 0 else "Bear", "Stress"]
    else:
        labels = []
        for position, _state in enumerate(order):
            if position == len(order) - 1:
                labels.append("Stress")
            elif position == 0:
                labels.append("Bear")
            elif position == len(order) - 2:
                labels.append("Bull")
            else:
                labels.append("Sideway")
    return order, labels, statistics


def fit_filtered_hmm(
    features: pd.DataFrame,
    returns: pd.Series,
    drawdown: pd.Series,
    train_index: np.ndarray,
    candidate_states: list[int],
    seeds: list[int],
    n_iter: int = 150,
) -> FilteredHMM:
    names = [
        name
        for name in [
            "log_return",
            "rolling_volatility_20",
            "downside_volatility",
            "cumulative_return_20",
            "current_drawdown",
            "volume_zscore",
        ]
        if name in features
    ]
    observations = features[names].ffill().fillna(0.0)
    scaler = StandardScaler().fit(observations.iloc[train_index])
    scaled = scaler.transform(observations)
    candidates: list[dict[str, object]] = []
    best: tuple[float, GaussianHMM] | None = None
    warnings: list[str] = []
    for states in candidate_states:
        for seed in seeds:
            try:
                model = GaussianHMM(
                    n_components=states,
                    covariance_type="diag",
                    n_iter=n_iter,
                    min_covar=1e-5,
                    random_state=seed,
                    tol=1e-3,
                ).fit(scaled[train_index])
                log_likelihood = float(model.score(scaled[train_index]))
                parameters = states * states + 2 * states * len(names) + states - 1
                aic = 2 * parameters - 2 * log_likelihood
                bic = np.log(len(train_index)) * parameters - 2 * log_likelihood
                filtered = forward_filter(model, scaled[train_index])
                occupancy = filtered.mean(axis=0)
                penalty = 1e4 * float(np.maximum(0.02 - occupancy, 0).sum())
                score = bic + penalty + (0 if model.monitor_.converged else 1e5)
                candidates.append(
                    {
                        "states": states,
                        "seed": seed,
                        "aic": aic,
                        "bic": bic,
                        "min_occupancy": occupancy.min(),
                        "converged": bool(model.monitor_.converged),
                        "selection_score": score,
                    }
                )
                if best is None or score < best[0]:
                    best = (score, model)
            except (ValueError, FloatingPointError) as error:
                warnings.append(f"HMM K={states}, seed={seed} thất bại: {error}")
    if best is None:
        raise RuntimeError("Không có cấu hình HMM hội tụ")
    model = best[1]
    probabilities = forward_filter(model, scaled)
    order, labels, statistics = _economic_order(probabilities, returns, drawdown, train_index)
    probabilities = probabilities[:, order]
    transition = model.transmat_[np.ix_(order, order)]
    probability_frame = regime_feature_frame(probabilities, transition, features.index)
    diagnostics = {
        "selected_states": model.n_components,
        "selected_seed": model.random_state,
        "converged": bool(model.monitor_.converged),
        "feature_names": names,
        "transition_matrix": transition.tolist(),
        "expected_duration": (1 / np.maximum(1 - np.diag(transition), 1e-6)).tolist(),
        "economic_labels": labels,
        "economic_order": order.tolist(),
        "state_statistics_raw": statistics,
        "candidate_models": candidates,
        "warnings": warnings,
        "probability_type": "forward-filtered P(S_t | F_t); not smoothed",
    }
    return FilteredHMM(model, scaler, names, probability_frame, transition, labels, diagnostics)
