"""Persistent state for the online (per-session) Bayesian update layer.

The batch pipeline refits everything from scratch. The online layer instead
carries the handful of quantities that are genuinely *recursive* - the HMM
forward variable, the EGARCH conditional log-variance, the conformal score
pool - from one trading session to the next, and reuses every fitted model
unchanged. This module owns that state and its on-disk representation; the
state machine that advances it lives in :mod:`vnindex_model.online`.

Every stored state is pinned to the batch run that produced it
(``source_run_metadata``) and to the exact price buffer it was computed from
(``buffer_checksum``), so a mismatched or hand-edited artifact is refused
rather than silently overwritten.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler

from .calibration import ProbabilityCalibrator
from .conformal import AdaptiveConformalState, ConformalPool, PendingScore
from .persistence import save_model, write_json

SCHEMA_VERSION = 1
STATE_DIRECTORY = "artifacts/online_state"


class OnlineStateSchemaError(RuntimeError):
    """Raised when a stored online state cannot be trusted as-is."""


@dataclass
class HMMOnlineState:
    """Everything needed to advance the filtered regime posterior by one step.

    ``log_alpha`` is the only field that changes between sessions; it is held in
    the model's *raw* state order, with ``economic_order`` mapping it onto the
    economically sorted columns the rest of the pipeline publishes.
    """

    model: GaussianHMM
    scaler: StandardScaler
    feature_names: list[str]
    economic_order: np.ndarray
    economic_labels: list[str]
    transition_matrix: np.ndarray
    log_alpha: np.ndarray
    state_duration: int = 1
    last_state: int = 0

    def ordered_probabilities(self) -> np.ndarray:
        return np.exp(self.log_alpha)[self.economic_order]


@dataclass
class EGARCHOnlineState:
    """Conditional volatility state; parameters stay frozen between refits."""

    model_name: str
    parameters: dict[str, float]
    log_variance: float
    forecast_volatility: float
    nu: float
    standardized_residuals: np.ndarray

    @property
    def uses_ewma_fallback(self) -> bool:
        return str(self.model_name).startswith("EWMA")


@dataclass
class ConformalOnlineState:
    """Score pools, unmatured forecasts, and the locked batch selection."""

    pools: dict[int, ConformalPool]
    pending: list[PendingScore]
    selected_method: dict[int, str]
    selected_window: dict[int, int | None]
    alpha_levels: list[float]
    minimum_stratum_size: int
    volatility_edges: np.ndarray
    adaptive: AdaptiveConformalState | None = None


@dataclass
class OnlineState:
    """The complete per-session state handed from one update to the next."""

    schema_version: int
    as_of_date: str
    last_close: float
    horizon: int
    raw_ohlcv_buffer: pd.DataFrame
    hmm: HMMOnlineState
    egarch: EGARCHOnlineState
    conformal: ConformalOnlineState
    forest: Any
    selected_model: str
    forest_feature_names: list[str]
    selected_technical: list[str]
    calibrator: ProbabilityCalibrator
    center_alpha: float
    regime_probability_history: np.ndarray
    block_length: int
    seed: int
    simulation: dict[str, Any]
    source_run_metadata: dict[str, Any]
    session_log: list[dict[str, Any]] = field(default_factory=list)

    def buffer_checksum(self) -> str:
        """SHA-256 of the price buffer, so a tampered state cannot load."""
        digest = hashlib.sha256()
        frame = self.raw_ohlcv_buffer
        digest.update(",".join(map(str, frame.columns)).encode("utf-8"))
        digest.update(pd.to_datetime(frame["date"]).astype("int64").to_numpy().tobytes())
        for column in [name for name in frame.columns if name != "date"]:
            digest.update(np.ascontiguousarray(frame[column].to_numpy(dtype=float)).tobytes())
        return digest.hexdigest()

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "as_of_date": self.as_of_date,
            "last_close": self.last_close,
            "horizon": self.horizon,
            "buffer_rows": int(len(self.raw_ohlcv_buffer)),
            "buffer_start_date": str(pd.Timestamp(self.raw_ohlcv_buffer["date"].iloc[0]).date()),
            "buffer_sha256": self.buffer_checksum(),
            "hmm_states": int(self.hmm.model.n_components),
            "egarch_model": self.egarch.model_name,
            "conformal_method": {str(key): value for key, value in self.conformal.selected_method.items()},
            "conformal_window": {str(key): value for key, value in self.conformal.selected_window.items()},
            "conformal_pool_sizes": {str(key): len(pool) for key, pool in self.conformal.pools.items()},
            "conformal_pending": len(self.conformal.pending),
            "adaptive_conformal": None
            if self.conformal.adaptive is None
            else {
                "gamma": self.conformal.adaptive.gamma,
                "alpha_current": {str(key): value for key, value in self.conformal.adaptive.alpha_current.items()},
            },
            "sessions_applied": len(self.session_log),
            "source_run_metadata": self.source_run_metadata,
        }


def online_state_paths(root: str | Path) -> dict[str, Path]:
    directory = Path(root) / STATE_DIRECTORY
    return {
        "directory": directory,
        "state": directory / "online_state.joblib",
        "manifest": directory / "online_state_manifest.json",
        "handoff": directory / "batch_handoff.joblib",
        "sessions": directory / "online_sessions.csv",
    }


def save_online_state(root: str | Path, state: OnlineState) -> dict[str, Path]:
    paths = online_state_paths(root)
    save_model(paths["state"], state)
    write_json(paths["manifest"], state.manifest())
    return paths


def load_online_state(root: str | Path) -> OnlineState:
    """Load the stored state, refusing anything that no longer matches its manifest."""
    paths = online_state_paths(root)
    if not paths["state"].exists():
        raise OnlineStateSchemaError(
            f"Chưa có online state tại {paths['state']}; chạy `init-online-state` sau `run-all` trước."
        )
    state: OnlineState = joblib.load(paths["state"])
    if state.schema_version != SCHEMA_VERSION:
        raise OnlineStateSchemaError(
            f"Online state dùng schema {state.schema_version}, code hiện tại là {SCHEMA_VERSION}; "
            "chạy lại `run-all` + `init-online-state`."
        )
    if paths["manifest"].exists():
        import json

        manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
        if manifest.get("buffer_sha256") != state.buffer_checksum():
            raise OnlineStateSchemaError(
                "Buffer checksum của online state không khớp manifest; state có thể đã bị sửa tay. "
                "Không tự động ghi đè — hãy kiểm tra thủ công hoặc chạy lại `init-online-state`."
            )
    return state
