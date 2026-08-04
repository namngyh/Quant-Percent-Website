"""State-conditioned Monte Carlo with recursive EGARCH Student-t risk."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd

from raemf_mc.simulation.reweighting import tempered_class_weights, weighted_quantile
from raemf_mc.simulation.risk_metrics import max_drawdown


@dataclass
class SimulationOutput:
    paths: np.ndarray
    weights: np.ndarray
    terminal_states: np.ndarray
    quantiles: pd.DataFrame
    summary: pd.DataFrame
    state_distribution: pd.DataFrame
    terminal_returns: np.ndarray | None = None
    drawdown_paths: np.ndarray | None = None
    parameter_draw_indices: np.ndarray | None = None


def _draw_next_states(rng: np.random.Generator, states: np.ndarray, transition: np.ndarray) -> np.ndarray:
    uniforms = rng.random(len(states))
    cumulative = np.cumsum(transition[states], axis=1)
    return (uniforms[:, None] > cumulative).sum(axis=1).clip(max=transition.shape[0] - 1)


def simulate_paths_detailed(
    last_price: float,
    current_state_prob: np.ndarray,
    transition: np.ndarray,
    state_mean: np.ndarray,
    sigma: float,
    horizon: int,
    paths: int = 1000,
    seed: int = 42,
    *,
    state_volatility: np.ndarray | None = None,
    egarch_params: dict[str, float] | None = None,
    nu: float | None = None,
    target_class_probabilities: np.ndarray | None = None,
    state_to_class: np.ndarray | None = None,
    scenario_mode: str = "point_estimate",
    parameter_draws: dict[str, np.ndarray] | None = None,
    lightweight: bool = False,
) -> SimulationOutput:
    """Simulate paths and return weighted risk diagnostics.

    HMM state affects both drift and volatility. EGARCH parameters and Student-t
    degrees of freedom come from the fitted risk model when supplied. EBM
    horizon probabilities reweight terminal-state paths with an ESS safeguard.
    In ``variational_posterior`` mode, row m of ``parameter_draws`` is fixed
    for every time step of path m.
    """
    rng = np.random.default_rng(seed + horizon)
    state_prob = np.asarray(current_state_prob, dtype=float)
    state_prob = np.clip(state_prob, 1e-12, None)
    state_prob /= state_prob.sum()
    transition = np.asarray(transition, dtype=float)
    transition = np.clip(transition, 1e-12, None)
    transition /= transition.sum(axis=1, keepdims=True)
    state_mean = np.asarray(state_mean, dtype=float)
    n_states = len(state_prob)
    sim = np.empty((paths, horizon + 1), dtype=float)
    sim[:, 0] = last_price
    states = rng.choice(n_states, size=paths, p=state_prob)

    params = egarch_params or {}
    omega = float(params.get("omega", -0.08))
    alpha = float(params.get("alpha[1]", 0.10))
    gamma_leverage = float(params.get("gamma[1]", -0.05))
    beta = float(np.clip(params.get("beta[1]", 0.94), 0.0, 0.995))
    fitted_nu = max(float(nu if nu is not None else params.get("nu", 8.0)), 2.05)
    log_variance = np.full(paths, np.log(max((sigma * 100.0) ** 2, 1e-10)))
    previous_z = np.zeros(paths, dtype=float)
    # arch centers |z| by sqrt(2/pi) in the EGARCH recursion regardless of the
    # innovation distribution; the fitted omega absorbs the Student-t offset,
    # so the simulation must use the same constant to stay consistent.
    expected_abs_z = sqrt(2.0 / np.pi)
    if state_volatility is None:
        state_scale = np.ones(n_states, dtype=float)
    else:
        state_volatility = np.maximum(np.asarray(state_volatility, dtype=float), 1e-8)
        reference = float(np.sum(state_prob * state_volatility))
        state_scale = np.clip(state_volatility / max(reference, 1e-8), 0.50, 2.50)

    valid_modes = {"point_estimate", "posterior_mean_mc", "variational_posterior"}
    if scenario_mode not in valid_modes:
        raise ValueError(f"scenario_mode must be one of {sorted(valid_modes)}")
    parameter_indices: np.ndarray | None = None
    path_mu: np.ndarray | None = None
    path_c: np.ndarray | None = None
    path_nu: np.ndarray | None = None
    if scenario_mode != "point_estimate":
        if parameter_draws is None or any(name not in parameter_draws for name in ("mu", "c", "nu")):
            raise ValueError(f"{scenario_mode} requires parameter_draws with mu, c and nu")
        arrays = {name: np.asarray(parameter_draws[name], dtype=float) for name in ("mu", "c", "nu")}
        if any(value.ndim != 2 or value.shape[1] != n_states for value in arrays.values()):
            raise ValueError("Each posterior parameter array must have shape (draws, n_states)")
        if any(not np.isfinite(value).all() for value in arrays.values()):
            raise ValueError("Posterior parameter draws must be finite")
        if np.any(arrays["c"] <= 0):
            raise ValueError("Every posterior c draw must be strictly positive")
        if np.any(arrays["nu"] <= 2):
            raise ValueError("Every posterior nu draw must be greater than 2")
        if scenario_mode == "posterior_mean_mc":
            path_mu = np.broadcast_to(arrays["mu"].mean(axis=0), (paths, n_states))
            path_c = np.broadcast_to(arrays["c"].mean(axis=0), (paths, n_states))
            path_nu = np.broadcast_to(arrays["nu"].mean(axis=0), (paths, n_states))
            parameter_indices = np.zeros(paths, dtype=int)
        else:
            draw_count = arrays["mu"].shape[0]
            if any(value.shape[0] != draw_count for value in arrays.values()):
                raise ValueError("mu, c and nu posterior arrays must contain the same number of draws")
            if draw_count < paths:
                raise ValueError("variational_posterior requires at least one joint parameter draw per path")
            path_mu = arrays["mu"][:paths]
            path_c = arrays["c"][:paths]
            path_nu = arrays["nu"][:paths]
            parameter_indices = np.arange(paths, dtype=int)

    path_index = np.arange(paths)
    for step in range(1, horizon + 1):
        states = _draw_next_states(rng, states, transition)
        log_variance = (
            omega
            + beta * log_variance
            + alpha * (np.abs(previous_z) - expected_abs_z)
            + gamma_leverage * previous_z
        )
        log_variance = np.clip(log_variance, -20.0, 20.0)
        conditional_sigma = np.sqrt(np.exp(log_variance)) / 100.0
        if scenario_mode == "point_estimate":
            standardized_t = rng.standard_t(df=fitted_nu, size=paths) * sqrt((fitted_nu - 2.0) / fitted_nu)
            shocks = standardized_t * conditional_sigma * state_scale[states]
            simulated_return = np.clip(state_mean[states] + shocks, -0.25, 0.25)
            previous_z = standardized_t * state_scale[states]
        else:
            active_nu = path_nu[path_index, states]
            standardized_t = rng.standard_t(df=active_nu, size=paths) * np.sqrt((active_nu - 2.0) / active_nu)
            active_c = path_c[path_index, states]
            shocks = standardized_t * conditional_sigma * active_c
            simulated_return = np.clip(path_mu[path_index, states] + shocks, -0.25, 0.25)
            previous_z = standardized_t * active_c
        sim[:, step] = np.maximum(sim[:, step - 1] * np.exp(simulated_return), 1e-6)

    if state_to_class is None:
        state_to_class = np.arange(n_states, dtype=int) % 4
    state_to_class = np.asarray(state_to_class, dtype=int)
    terminal_classes = state_to_class[states]
    if target_class_probabilities is None:
        weights = np.full(paths, 1.0 / paths)
        ess = float(paths)
        tempering_power = 1.0
        proposal = np.bincount(terminal_classes, minlength=4) / paths
    else:
        weights, ess, tempering_power, proposal = tempered_class_weights(
            terminal_classes,
            np.asarray(target_class_probabilities, dtype=float),
            n_classes=4,
        )

    terminal_return = np.log(sim[:, -1] / last_price)
    drawdowns = max_drawdown(sim)
    running_peak = np.maximum.accumulate(sim, axis=1)
    drawdown_paths = sim / np.maximum(running_peak, 1e-12) - 1.0
    time_under_water = (drawdown_paths[:, 1:] < 0).sum(axis=1)
    if lightweight:
        return SimulationOutput(
            sim,
            weights,
            states,
            pd.DataFrame(),
            pd.DataFrame({"horizon": [horizon], "scenario_mode": [scenario_mode]}),
            pd.DataFrame(),
            terminal_return,
            drawdown_paths,
            parameter_indices,
        )
    q_levels = np.array([0.025, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.975])
    path_quantiles = np.column_stack(
        [weighted_quantile(sim[:, step], q_levels, weights) for step in range(horizon + 1)]
    )
    quantiles = pd.DataFrame(path_quantiles.T, columns=[f"q{int(q * 1000):03d}" for q in q_levels])
    quantiles.insert(0, "step", np.arange(horizon + 1))
    return_quantiles = weighted_quantile(terminal_return, q_levels, weights)
    var_cut = float(weighted_quantile(terminal_return, np.array([0.05]), weights)[0])
    tail_mask = terminal_return <= var_cut
    tail_weights = weights[tail_mask]
    cvar = -float(np.sum(terminal_return[tail_mask] * tail_weights) / max(tail_weights.sum(), 1e-12))
    var_99_cut = float(weighted_quantile(terminal_return, np.array([0.01]), weights)[0])
    tail_99 = terminal_return <= var_99_cut
    cvar_99 = -float(np.sum(terminal_return[tail_99] * weights[tail_99]) / max(weights[tail_99].sum(), 1e-12))
    weighted_state = np.bincount(states, weights=weights, minlength=n_states)
    raw_state = np.bincount(states, minlength=n_states) / paths
    state_distribution = pd.DataFrame(
        {
            "horizon": horizon,
            "state": np.arange(n_states),
            "raw_probability": raw_state,
            "weighted_probability": weighted_state,
        }
    )
    dominant_state = int(np.argmax(weighted_state))
    summary = pd.DataFrame(
        {
            "horizon": [horizon],
            "expected_return": [float(np.sum(terminal_return * weights))],
            "median_return": [float(return_quantiles[4])],
            "q01": [float(weighted_quantile(terminal_return, np.array([0.01]), weights)[0])],
            "q05": [float(return_quantiles[1])],
            "q25": [float(return_quantiles[3])],
            "q50": [float(return_quantiles[4])],
            "q75": [float(return_quantiles[5])],
            "q95": [float(return_quantiles[7])],
            "q99": [float(weighted_quantile(terminal_return, np.array([0.99]), weights)[0])],
            "prob_positive": [float(weights[terminal_return > 0].sum())],
            "prob_negative": [float(weights[terminal_return < 0].sum())],
            "prob_drawdown_gt_5pct": [float(weights[drawdowns < -0.05].sum())],
            "prob_drawdown_gt_10pct": [float(weights[drawdowns < -0.10].sum())],
            "prob_drawdown_gt_15pct": [float(weights[drawdowns < -0.15].sum())],
            "prob_drawdown_gt_20pct": [float(weights[drawdowns < -0.20].sum())],
            "var_95": [-var_cut],
            "cvar_95": [cvar],
            "var_99": [-var_99_cut],
            "cvar_99": [cvar_99],
            "max_drawdown_mean": [float(np.sum(drawdowns * weights))],
            "max_drawdown_q05": [float(weighted_quantile(drawdowns, np.array([0.05]), weights)[0])],
            "max_drawdown_q50": [float(weighted_quantile(drawdowns, np.array([0.50]), weights)[0])],
            "time_under_water_mean": [float(np.sum(time_under_water * weights))],
            "first_passage_below_10pct": [float(weights[(drawdown_paths <= -0.10).any(axis=1)].sum())],
            "ess": [ess],
            "ess_fraction": [ess / paths],
            "tempering_power": [tempering_power],
            "student_t_nu": [fitted_nu if scenario_mode == "point_estimate" else float(path_nu.mean())],
            "scenario_mode": [scenario_mode],
            "dominant_terminal_state": [dominant_state],
            "proposal_class_probabilities": [";".join(f"{x:.8f}" for x in proposal)],
        }
    )
    return SimulationOutput(
        sim,
        weights,
        states,
        quantiles,
        summary,
        state_distribution,
        terminal_return,
        drawdown_paths,
        parameter_indices,
    )


def simulate_paths(
    last_price: float,
    current_state_prob: np.ndarray,
    transition: np.ndarray,
    state_mean: np.ndarray,
    sigma: float,
    horizon: int,
    paths: int = 1000,
    seed: int = 42,
    **kwargs: object,
) -> tuple[np.ndarray, pd.DataFrame]:
    """Backward-compatible wrapper returning paths and summary."""
    result = simulate_paths_detailed(
        last_price,
        current_state_prob,
        transition,
        state_mean,
        sigma,
        horizon,
        paths,
        seed,
        **kwargs,
    )
    return result.paths, result.summary
