"""Configuration loading utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_BAYESIAN_CONFIG: dict[str, Any] = {
    "enabled": False,
    "backend": "pymc",
    "method": "fullrank_advi",
    "advi_steps": 30_000,
    "posterior_draws": 2_000,
    "posterior_predictive_draws": 1_000,
    "learning_rate": 0.01,
    "convergence_window": 500,
    "convergence_tolerance": 0.001,
    "shared_nu": False,
    "prior_mu_scale": 0.5,
    "prior_log_scale_sd": 0.3,
    "prior_nu_rate": 0.1,
    "random_seed": 42,
    "fallback_to_point_estimate": True,
    "min_effective_observations": 20.0,
    # GPU-first / multi-seed extensions (pytorch_cuda backend)
    "seeds": None,  # list of ADVI seeds; None -> [random_seed]
    "hierarchical": False,
    "priors": {},
    "device": "auto",  # auto | cuda | cpu
    "require_gpu": False,
    "dtype": "float32",
    "min_steps": 1_000,
    "vi_samples_per_step": 8,
    "retry_learning_rates": [0.001],
    "gradient_clip_norm": 5.0,
    "early_stopping_patience": 2_000,
    "fallback_to_meanfield": True,
}

VALID_BAYESIAN_BACKENDS = {"pymc", "pytorch_cpu", "pytorch_cuda"}


def bayesian_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return one validated Bayesian configuration with repository defaults."""
    source = config or {}
    overrides = source.get("bayesian", source)
    merged = {**DEFAULT_BAYESIAN_CONFIG, **dict(overrides)}
    if merged["backend"] not in VALID_BAYESIAN_BACKENDS:
        raise ValueError(f"bayesian.backend must be one of {sorted(VALID_BAYESIAN_BACKENDS)}")
    if merged["seeds"] is not None:
        seeds = [int(value) for value in merged["seeds"]]
        if not seeds:
            raise ValueError("bayesian.seeds must be a non-empty list when provided")
        merged["seeds"] = seeds
    if merged["method"] not in {"fullrank_advi", "meanfield_advi"}:
        raise ValueError("bayesian.method must be 'fullrank_advi' or 'meanfield_advi'")
    positive = [
        "advi_steps",
        "posterior_draws",
        "posterior_predictive_draws",
        "learning_rate",
        "convergence_window",
        "convergence_tolerance",
        "prior_mu_scale",
        "prior_log_scale_sd",
        "prior_nu_rate",
        "min_effective_observations",
    ]
    for key in positive:
        if float(merged[key]) <= 0:
            raise ValueError(f"bayesian.{key} must be positive")
    return merged


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML configuration file."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}
    parent = loaded.pop("extends", None)
    if parent is None:
        return loaded
    base = load_config((config_path.parent / str(parent)).resolve())

    def merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        output = dict(left)
        for key, value in right.items():
            if isinstance(value, dict) and isinstance(output.get(key), dict):
                output[key] = merge(output[key], value)
            else:
                output[key] = value
        return output

    return merge(base, loaded)


def write_config_snapshot(config: dict[str, Any], path: str | Path) -> None:
    """Persist a configuration snapshot."""
    with Path(path).open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh, sort_keys=False, allow_unicode=True)
