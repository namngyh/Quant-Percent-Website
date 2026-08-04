"""Standalone causal fit workflow for the optional scenario posterior."""

from __future__ import annotations

import json
import subprocess
import time
import tracemalloc
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from raemf_mc.bayesian.diagnostics import write_diagnostic_artifacts
from raemf_mc.bayesian.model import create_scenario_model
from raemf_mc.config import bayesian_config
from raemf_mc.data.loader import load_price_data, sha256_file
from raemf_mc.features.technical import build_features
from raemf_mc.regime.filtered_hmm import fit_filtered_hmm
from raemf_mc.risk.egarch_t import fit_egarch_features


def _commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def fit_variational_from_data(
    data_path: str | Path,
    config: dict[str, Any],
    output_dir: str | Path,
) -> Path:
    """Fit a deployment posterior using observations available at the last date."""
    cfg = bayesian_config(config)
    cfg["enabled"] = True
    prices, _ = load_price_data(data_path)
    features, _ = build_features(prices)
    returns = np.log(prices["close"] / prices["close"].shift(1))
    train_index = np.arange(len(prices), dtype=int)
    hmm = fit_filtered_hmm(
        features,
        returns,
        train_index,
        int(config["hmm"]["n_states"]),
        list(config["hmm"]["seeds"]),
    )
    risk = fit_egarch_features(returns, train_index)
    probability_columns = [column for column in hmm.probabilities if column.startswith("hmm_prob_state_")]
    dates = pd.DatetimeIndex(prices["date"])
    model = create_scenario_model(cfg)
    tracemalloc.start()
    started = time.perf_counter()
    model.fit(
        pd.Series(returns.to_numpy(dtype=float), index=dates),
        pd.DataFrame(
            hmm.probabilities[probability_columns].to_numpy(dtype=float),
            index=dates,
            columns=probability_columns,
        ),
        pd.Series(risk.features["egarch_sigma"].to_numpy(dtype=float), index=dates),
        train_index,
        cfg,
    )
    runtime = time.perf_counter() - started
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    destination = model.save(output_dir)
    write_diagnostic_artifacts(model, destination)
    metadata = {
        "runtime_seconds": runtime,
        "peak_memory_bytes": int(peak_memory),
        "artifact_size_bytes": int(sum(path.stat().st_size for path in destination.rglob("*") if path.is_file())),
        "data_sha256": sha256_file(data_path),
        "commit": _commit_hash(),
        "inference_family": cfg["method"],
        "iterations": int(cfg["advi_steps"]),
        "seed": int(cfg["random_seed"]),
        "convergence_status": model.result.convergence_status,
    }
    (destination / "fit_runtime.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return destination
