"""Economic alignment for latent HMM states."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


ECONOMIC_STATE_NAMES = ("Expansion", "Range", "Contraction", "Turbulence")


@dataclass(frozen=True)
class StateAlignment:
    """Mapping from raw optimizer state ids to stable economic state ids."""

    mapping: pd.DataFrame
    raw_order: np.ndarray


def _zscore(values: np.ndarray) -> np.ndarray:
    scale = float(np.nanstd(values))
    if not np.isfinite(scale) or scale < 1e-12:
        return np.zeros_like(values, dtype=float)
    return (values - float(np.nanmean(values))) / scale


def _average_duration(states: np.ndarray, state: int) -> float:
    if len(states) == 0:
        return 0.0
    runs: list[int] = []
    current = 0
    for value in states:
        if int(value) == state:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return float(np.mean(runs)) if runs else 0.0


def align_states(
    probabilities: np.ndarray,
    returns: pd.Series,
    train_idx: np.ndarray,
) -> StateAlignment:
    """Align states using train-only return, risk, and persistence statistics.

    With four states, the labels are assigned by a deterministic economic rule:
    Turbulence has the largest joint volatility/downside score, Expansion has
    the strongest risk-adjusted mean, Contraction has the weakest mean, and the
    remaining state is Range. Other state counts receive neutral ordered names.
    """
    train_idx = np.asarray(train_idx, dtype=int)
    train_prob = probabilities[train_idx]
    train_ret = returns.iloc[train_idx].fillna(0.0).to_numpy(dtype=float)
    hard = train_prob.argmax(axis=1)
    n_states = probabilities.shape[1]
    rows: list[dict[str, float | int | str]] = []
    for raw in range(n_states):
        weights = train_prob[:, raw]
        denom = max(float(weights.sum()), 1e-12)
        mean = float(np.sum(weights * train_ret) / denom)
        variance = float(np.sum(weights * np.square(train_ret - mean)) / denom)
        negative_probability = float(np.sum(weights * (train_ret < 0)) / denom)
        downside = np.minimum(train_ret, 0.0)
        downside_rms = float(np.sqrt(np.sum(weights * downside**2) / denom))
        rows.append(
            {
                "raw_state": raw,
                "mean_return": mean,
                "std_return": float(np.sqrt(max(variance, 0.0))),
                "downside_rms": downside_rms,
                "negative_probability": negative_probability,
                "frequency": float(weights.mean()),
                "average_duration": _average_duration(hard, raw),
            }
        )
    stats = pd.DataFrame(rows)
    if n_states == 4:
        risk = (
            _zscore(stats["std_return"].to_numpy())
            + _zscore(stats["downside_rms"].to_numpy())
            + _zscore(stats["negative_probability"].to_numpy())
            - 0.5 * _zscore(stats["mean_return"].to_numpy())
        )
        turbulent = int(stats.iloc[int(np.argmax(risk))]["raw_state"])
        remaining = [s for s in range(n_states) if s != turbulent]
        expansion_score = stats["mean_return"].to_numpy() - 0.25 * stats["std_return"].to_numpy()
        expansion = max(remaining, key=lambda state: float(expansion_score[state]))
        remaining = [s for s in remaining if s != expansion]
        contraction = min(remaining, key=lambda state: float(stats.loc[state, "mean_return"]))
        range_state = next(s for s in remaining if s != contraction)
        raw_order = np.array([expansion, range_state, contraction, turbulent], dtype=int)
        labels = list(ECONOMIC_STATE_NAMES)
        interpretations = [
            "Lợi suất tương đối mạnh với rủi ro không cực đại",
            "Trạng thái trung gian sau khi loại các cực trị tăng, giảm và biến động",
            "Lợi suất trung bình yếu nhất trong các trạng thái không hỗn loạn",
            "Điểm tổng hợp biến động, downside và xác suất âm cao nhất",
        ]
    else:
        raw_order = np.argsort(stats["mean_return"].to_numpy())[::-1].astype(int)
        labels = [f"Economic state {i}" for i in range(n_states)]
        interpretations = ["Thứ hạng dựa trên lợi suất trung bình train-only" for _ in range(n_states)]

    inverse = {int(raw): aligned for aligned, raw in enumerate(raw_order)}
    stats["aligned_state"] = stats["raw_state"].map(inverse).astype(int)
    stats["economic_label"] = stats["aligned_state"].map(dict(enumerate(labels)))
    stats["economic_interpretation"] = stats["aligned_state"].map(dict(enumerate(interpretations)))
    stats = stats.sort_values("aligned_state").reset_index(drop=True)
    return StateAlignment(mapping=stats, raw_order=raw_order)


def reorder_transition(transition: np.ndarray, raw_order: np.ndarray) -> np.ndarray:
    """Reorder both axes of a transition matrix into aligned-state order."""
    return np.asarray(transition, dtype=float)[np.ix_(raw_order, raw_order)]
