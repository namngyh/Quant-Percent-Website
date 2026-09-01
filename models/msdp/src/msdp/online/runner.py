"""CLI entry points for the MSDP online tier.

`init_online_state` seeds the state from the production bundle; `update_latest`
applies every session that has become observable since the last run. Neither
trains the network: the only things that move are the Hedge gate posterior and
the adaptive conformal width, both of which are convex combinations of things
the batch tier froze.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..data_io import load_market_data
from ..inference import load_production_bundle, predict_latest_ensemble
from ..training.ensemble import average_predictions
from .persistence import assert_state_matches_run, load_online_state, save_online_state
from .session import empirical_coverage, mature_pending, record_forecast
from .state import OnlineState


def _bundle_shape(model_or_manifest: str | Path) -> tuple[dict[str, Any], list[int], int]:
    """Horizons and expert count, read from the artefact rather than the config.

    The config can drift from what was actually trained; the bundle cannot. A
    Hedge state with the wrong number of experts would silently misalign every
    loss it ever records.
    """
    manifest, states, _ = load_production_bundle(model_or_manifest)
    horizons = [int(h) for h in manifest["model_args"]["horizons"]]
    n_experts = int(manifest["model_args"].get("n_experts") or 0)
    if not n_experts:
        # `n_experts` is not always spelled out in `model_args`, but the expert
        # submodules are always numbered in the state dict.
        n_experts = _infer_expert_count(states[0])
    return manifest, horizons, n_experts


def _infer_expert_count(state_dict: dict[str, Any]) -> int:
    """Count experts from the parameter names of one seed's state dict."""
    indices = set()
    for key in state_dict:
        parts = key.split(".")
        for position, part in enumerate(parts[:-1]):
            if part == "experts" and parts[position + 1].isdigit():
                indices.add(int(parts[position + 1]))
    if not indices:
        raise ValueError("Không suy ra được số expert từ state dict của model")
    return max(indices) + 1


def initialize_online_state(
    data_path: str | Path,
    model_or_manifest: str | Path,
    *,
    root: str | Path = ".",
    eta: float = 0.5,
) -> dict[str, Any]:
    """Seed the online state from the production bundle and the current panel."""
    started = time.perf_counter()
    root = Path(root).resolve()
    manifest, horizons, n_experts = _bundle_shape(model_or_manifest)
    frame = load_market_data(data_path)
    if frame.empty:
        raise ValueError("Nguồn dữ liệu không có phiên nào")

    state = OnlineState.initial(
        horizons=horizons,
        n_experts=n_experts,
        eta=float(eta),
        source_run_metadata={
            "run_id": manifest.get("run_id"),
            "artifact_role": manifest.get("artifact_role"),
            "seeds": list(manifest.get("seeds", [])),
            "data_path": str(data_path),
            "last_data_date": str(pd.Timestamp(frame["date"].iloc[-1]).date()),
        },
        as_of_date=str(pd.Timestamp(frame["date"].iloc[-1]).date()),
    )
    paths = save_online_state(root, state)
    return {
        "status": "initialized",
        "as_of_date": state.as_of_date,
        "horizons": horizons,
        "n_experts": n_experts,
        "eta": float(eta),
        "run_id": manifest.get("run_id"),
        "state_path": str(paths["state"]),
        "manifest_path": str(paths["manifest"]),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def update_latest(
    data_path: str | Path,
    model_or_manifest: str | Path,
    *,
    root: str | Path = ".",
) -> dict[str, Any]:
    """Score what has matured, refresh the gate posterior, republish the forecast."""
    started = time.perf_counter()
    root = Path(root).resolve()
    state = load_online_state(root)
    manifest, _horizons, _experts = _bundle_shape(model_or_manifest)
    assert_state_matches_run(state, str(manifest.get("run_id", "")))

    frame = load_market_data(data_path)
    closes = pd.Series(frame["close"].to_numpy(dtype=float), index=pd.DatetimeIndex(frame["date"]))
    latest_date = str(pd.Timestamp(frame["date"].iloc[-1]).date())

    if state.as_of_date and latest_date <= state.as_of_date:
        return {
            "status": "no_new_sessions",
            "as_of_date": state.as_of_date,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }

    # 1. Learn from every forecast whose horizon has actually elapsed.
    matured = mature_pending(state, closes)

    # 2. Re-forecast with the updated posterior. The network is untouched.
    payload, seed_predictions = predict_latest_ensemble(data_path, model_or_manifest, hedge=state.hedge)
    ensemble = average_predictions(seed_predictions)

    # 3. Queue the new forecast so a later session can score it.
    experts = np.asarray(ensemble["aux_return_median"])[0]
    for index, entry in enumerate(payload["horizons"]):
        lower, upper = entry["calibrated_interval"]
        record_forecast(
            state,
            origin_date=payload["data_date"][:10],
            horizon=int(entry["horizon"]),
            horizon_index=index,
            expert_predictions=experts[index],
            lower=float(lower),
            upper=float(upper),
        )
        entry["gate_weights_source"] = "online_posterior"
        entry["empirical_coverage"] = empirical_coverage(state, int(entry["horizon"]))

    state.as_of_date = latest_date
    state.session_log.append(
        {
            "as_of_date": latest_date,
            "matured": len(matured),
            "pending": len(state.pending),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    )
    paths = save_online_state(root, state)
    if state.session_log:
        pd.DataFrame(state.session_log).to_csv(paths["sessions"], index=False)

    written = _publish(root, payload)
    return {
        "status": "updated",
        "as_of_date": latest_date,
        "matured_forecasts": len(matured),
        "pending_forecasts": len(state.pending),
        "hedge_rounds": list(state.hedge.rounds or []),
        "artifacts": [str(path) for path in written],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def _publish(root: Path, payload: dict[str, Any]) -> list[Path]:
    """Write the same `artifacts/predictions/` files `predict_latest.py` writes.

    Same filenames and same schema on purpose: whatever reads them downstream
    must not have to know whether the batch tier or the online tier produced
    them.
    """
    import json

    target = root / "artifacts" / "predictions"
    target.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    written = []
    for name in ("latest_forecast.json",):
        path = target / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    frame_path = target / "latest_forecast.csv"
    pd.json_normalize(payload["horizons"]).to_csv(frame_path, index=False)
    written.append(frame_path)
    markdown = "# Hồ sơ dự báo mới nhất theo kỳ hạn\n\n```json\n" + text + "\n```\n"
    for name in ("latest_forecast.md", "latest_forecast_VI.md"):
        path = target / name
        path.write_text(markdown, encoding="utf-8")
        written.append(path)
    return written
