"""Online (per-session) Bayesian update layer.

Two tiers cooperate:

* the **batch** tier is `run_pipeline()` - Baum-Welch, EGARCH MLE, forest
  training, conformal method selection - run on a slow cadence. It ends by
  writing a :class:`BatchHandoff`;
* the **online** tier, here, advances the recursive quantities one trading
  session at a time in seconds: one HMM forward-filter step, one EGARCH
  log-variance step, forest *inference* under the new regime posterior, one
  conformal pool update, and a fresh Monte Carlo resample.

Nothing in this module refits anything. Every fitted object is reused exactly
as the batch tier left it, and each `run-all` resets the online state.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

from .calibration import ProbabilityCalibrator
from .config import load_config
from .conformal import (
    AdaptiveConformalState,
    ConformalPool,
    PendingScore,
    assign_volatility_bins,
    interval_from_scores,
    mature_pending_scores,
)
from .data_source import build_market_data_source
from .features import build_features
from .hmm import FilteredHMM, forward_filter_step, forward_filter_with_state, regime_feature_frame
from .online_state import (
    SCHEMA_VERSION,
    ConformalOnlineState,
    EGARCHOnlineState,
    HMMOnlineState,
    OnlineState,
    OnlineStateSchemaError,
    load_online_state,
    online_state_paths,
    save_online_state,
)
from .persistence import save_model, write_json
from .point_forecast import apply_center_blend
from .random_forest import predict_bundle, predict_soft_gated
from .simulation import maximum_drawdown, simulate_paths
from .volatility import VolatilityResult, egarch_step, ewma_volatility_fallback

logger = logging.getLogger("vnindex_model.online")

FORECAST_VOLATILITY_SPAN = 5
MAXIMUM_CALENDAR_GAP_DAYS = 10
SCORE_EPSILON = 1e-8


class AbnormalSessionError(RuntimeError):
    """Raised when a new session cannot be trusted; the repo never silently patches data."""


# ---------------------------------------------------------------------------
# Batch -> online handoff
# ---------------------------------------------------------------------------


@dataclass
class BatchHandoff:
    """Everything `run_pipeline` fitted that the online tier needs to reuse."""

    horizon: int
    selected_technical: list[str]
    hmm: FilteredHMM
    volatility: VolatilityResult
    forest: Any
    selected_model: str
    forest_feature_names: list[str]
    calibrator: ProbabilityCalibrator
    center_alpha: float
    conformal_method: str
    conformal_window: int | None
    volatility_edges: np.ndarray
    calibration_actual: np.ndarray
    calibration_center: np.ndarray
    calibration_sigma: np.ndarray
    calibration_regime: np.ndarray
    calibration_volatility_bin: np.ndarray
    alpha_levels: list[float]
    minimum_stratum_size: int
    block_length: int
    seed: int
    simulation: dict[str, Any]
    adaptive_conformal: dict[str, Any]
    run_metadata: dict[str, Any]
    advanced_enabled: bool = True
    schema_version: int = SCHEMA_VERSION


def save_batch_handoff(root: str | Path, handoff: BatchHandoff) -> Path:
    path = online_state_paths(root)["handoff"]
    save_model(path, handoff)
    return path


def load_batch_handoff(root: str | Path) -> BatchHandoff:
    path = online_state_paths(root)["handoff"]
    if not path.exists():
        raise OnlineStateSchemaError(
            f"Chưa có batch handoff tại {path}; chạy `run-all` trước rồi mới `init-online-state`."
        )
    import joblib

    handoff: BatchHandoff = joblib.load(path)
    if handoff.schema_version != SCHEMA_VERSION:
        raise OnlineStateSchemaError(
            f"Batch handoff dùng schema {handoff.schema_version}, code hiện tại là {SCHEMA_VERSION}; chạy lại `run-all`."
        )
    return handoff


# ---------------------------------------------------------------------------
# Seeding the online state from a finished batch run
# ---------------------------------------------------------------------------


def _state_duration_from(states: np.ndarray) -> int:
    duration = 1
    for position in range(len(states) - 1, 0, -1):
        if states[position] != states[position - 1]:
            break
        duration += 1
    return duration


def _forest_bundles(forest: Any) -> list[Any]:
    experts = getattr(forest, "experts", None)
    if experts is None:
        return [forest]
    return [forest.global_bundle, *[expert for expert in experts if expert is not None]]


def _single_threaded(forest: Any) -> Any:
    """Predict a single feature row on one thread.

    The batch tier trains with ``n_jobs=-1``, which is right for fitting but is
    pure dispatch overhead when scoring one row per session (measured ~28%
    slower end-to-end). ``n_jobs`` is a runtime hint, not a fitted parameter,
    so overriding it changes nothing about the predictions.
    """
    for bundle in _forest_bundles(forest):
        for estimator in [
            bundle.classifier,
            bundle.return_regressor,
            bundle.normalized_regressor,
            bundle.drawdown_regressor,
        ]:
            estimator.n_jobs = 1
    return forest


def build_online_state(handoff: BatchHandoff, data: pd.DataFrame) -> OnlineState:
    """Turn a finished batch run into the state the online tier continues from."""
    data = data.reset_index(drop=True)
    # The standardized residuals and the regime posteriors are indexed by
    # session, and the Monte Carlo resample weights one by the other. A buffer
    # that is not exactly the series the batch tier fitted would desynchronise
    # them, so refuse rather than seed a state that breaks several steps later.
    fitted_rows = {
        "egarch": len(handoff.volatility.features),
        "hmm": len(handoff.hmm.probabilities),
    }
    mismatched = {name: rows for name, rows in fitted_rows.items() if rows != len(data)}
    if mismatched:
        raise OnlineStateSchemaError(
            f"Buffer có {len(data)} phiên nhưng batch run đã fit trên số phiên khác ({mismatched}); "
            "nguồn dữ liệu phải chứa đúng chuỗi mà `run-all` đã dùng. Chạy lại `run-all` trên nguồn "
            "hiện tại rồi `init-online-state`."
        )
    features = build_features(data)
    hmm = handoff.hmm
    observations = features[hmm.feature_names].ffill().fillna(0.0)
    scaled = hmm.scaler.transform(observations)
    raw_probabilities, log_alpha = forward_filter_with_state(hmm.model, scaled)
    order = np.asarray(hmm.diagnostics["economic_order"], dtype=int)
    ordered = raw_probabilities[:, order]
    states = ordered.argmax(axis=1)

    sigma = handoff.volatility.features["egarch_conditional_volatility"].to_numpy(dtype=float)
    hmm_state = HMMOnlineState(
        model=hmm.model,
        scaler=hmm.scaler,
        feature_names=list(hmm.feature_names),
        economic_order=order,
        economic_labels=list(hmm.economic_labels),
        transition_matrix=np.asarray(hmm.transition_matrix, dtype=float),
        log_alpha=np.asarray(log_alpha, dtype=float),
        state_duration=_state_duration_from(states),
        last_state=int(states[-1]),
    )
    egarch_state = EGARCHOnlineState(
        model_name=str(handoff.volatility.diagnostics["model"]),
        parameters={str(key): float(value) for key, value in handoff.volatility.diagnostics["parameters"].items()},
        log_variance=float(np.log(np.square(sigma[-1] * 100))),
        forecast_volatility=float(handoff.volatility.features["egarch_forecast_volatility"].iloc[-1]),
        nu=float(handoff.volatility.diagnostics.get("nu", 8.0)),
        standardized_residuals=np.asarray(handoff.volatility.standardized_residuals, dtype=float),
    )

    scores = (handoff.calibration_actual - handoff.calibration_center) / np.maximum(
        handoff.calibration_sigma, SCORE_EPSILON
    )
    finite = np.isfinite(scores)
    pool = ConformalPool(
        scores=scores[finite].tolist(),
        regimes=np.asarray(handoff.calibration_regime, dtype=int)[finite].tolist(),
        volatility_bins=np.asarray(handoff.calibration_volatility_bin, dtype=int)[finite].tolist(),
    )
    pool.truncate(handoff.conformal_window)
    adaptive = None
    if handoff.adaptive_conformal.get("enabled", False):
        targets = {float(level): float(level) for level in handoff.alpha_levels}
        adaptive = AdaptiveConformalState(
            gamma=float(handoff.adaptive_conformal.get("gamma", 0.02)),
            alpha_target=targets,
            alpha_current=dict(targets),
        )
    conformal_state = ConformalOnlineState(
        pools={handoff.horizon: pool},
        pending=[],
        selected_method={handoff.horizon: handoff.conformal_method},
        selected_window={handoff.horizon: handoff.conformal_window},
        alpha_levels=[float(level) for level in handoff.alpha_levels],
        minimum_stratum_size=int(handoff.minimum_stratum_size),
        volatility_edges=np.asarray(handoff.volatility_edges, dtype=float),
        adaptive=adaptive,
    )
    return OnlineState(
        schema_version=SCHEMA_VERSION,
        as_of_date=str(pd.Timestamp(data["date"].iloc[-1]).date()),
        last_close=float(data["close"].iloc[-1]),
        horizon=int(handoff.horizon),
        raw_ohlcv_buffer=data.copy(),
        hmm=hmm_state,
        egarch=egarch_state,
        conformal=conformal_state,
        forest=_single_threaded(handoff.forest),
        selected_model=str(handoff.selected_model),
        forest_feature_names=list(handoff.forest_feature_names),
        selected_technical=list(handoff.selected_technical),
        calibrator=handoff.calibrator,
        center_alpha=float(handoff.center_alpha),
        regime_probability_history=ordered,
        block_length=int(handoff.block_length),
        seed=int(handoff.seed),
        simulation={**handoff.simulation, "advanced_enabled": bool(handoff.advanced_enabled)},
        source_run_metadata=dict(handoff.run_metadata),
    )


# ---------------------------------------------------------------------------
# Session validation
# ---------------------------------------------------------------------------


def validate_new_session(state: OnlineState, row: pd.Series) -> pd.Timestamp:
    """Reject anything anomalous instead of interpolating or repairing it."""
    date = pd.Timestamp(row["date"])
    as_of = pd.Timestamp(state.as_of_date)
    if pd.isna(date):
        raise AbnormalSessionError("Phiên mới thiếu giá trị ngày giao dịch")
    if date <= as_of:
        raise AbnormalSessionError(
            f"Phiên {date.date()} không mới hơn as_of_date {as_of.date()} của online state"
        )
    present = [name for name in ["open", "high", "low", "close", "volume"] if name in row.index]
    missing = [name for name in present if pd.isna(row[name])]
    if missing:
        raise AbnormalSessionError(f"Phiên {date.date()} thiếu giá trị: {missing}")
    prices = [name for name in ["open", "high", "low", "close"] if name in row.index]
    nonpositive = [name for name in prices if float(row[name]) <= 0]
    if nonpositive:
        raise AbnormalSessionError(f"Phiên {date.date()} có giá <= 0: {nonpositive}")
    if {"open", "high", "low", "close"}.issubset(row.index):
        high, low = float(row["high"]), float(row["low"])
        top, bottom = max(float(row["open"]), float(row["close"])), min(float(row["open"]), float(row["close"]))
        if high < top - 1e-8 or low > bottom + 1e-8 or high < low:
            raise AbnormalSessionError(
                f"Phiên {date.date()} vi phạm ràng buộc OHLC (high={high}, low={low}, open/close={top}/{bottom})"
            )
    gap = int((date - as_of).days)
    if gap > MAXIMUM_CALENDAR_GAP_DAYS:
        raise AbnormalSessionError(
            f"Calendar gap {gap} ngày giữa {as_of.date()} và {date.date()} vượt ngưỡng "
            f"{MAXIMUM_CALENDAR_GAP_DAYS}; dừng để rà soát thủ công thay vì tự nội suy"
        )
    return date


# ---------------------------------------------------------------------------
# One session
# ---------------------------------------------------------------------------


def _hmm_feature_row(state: OnlineState, probabilities: np.ndarray, state_duration: int) -> dict[str, float]:
    """The row `fit_filtered_hmm` would publish for this session.

    ``state_duration`` is the run length *including* the current session, which
    is what `regime_feature_frame` produces in batch.
    """
    frame = regime_feature_frame(probabilities[None, :], state.hmm.transition_matrix)
    values = {name: float(frame[name].iloc[0]) for name in frame.columns if name != "hmm_state"}
    values["hmm_state_duration"] = float(state_duration)
    return values


def _forest_input(state: OnlineState, values: dict[str, float]) -> pd.DataFrame:
    missing = [name for name in state.forest_feature_names if name not in values]
    if missing:
        raise OnlineStateSchemaError(
            f"Không dựng được feature row cho forest, thiếu cột: {missing[:10]}"
            f"{' ...' if len(missing) > 10 else ''}"
        )
    return pd.DataFrame([[values[name] for name in state.forest_feature_names]], columns=state.forest_feature_names)


def _resolve_pending_targets(state: OnlineState) -> dict[str, int]:
    """Fill in the true target date of every pending forecast the buffer can now name."""
    dates = pd.to_datetime(state.raw_ohlcv_buffer["date"])
    positions = {str(value.date()): index for index, value in enumerate(dates)}
    last = len(dates) - 1
    for item in state.conformal.pending:
        origin = positions.get(item.origin_date)
        if origin is None:
            continue
        target = origin + item.horizon
        if target <= last:
            item.target_end_date = str(dates.iloc[target].date())
    return positions


def _realized_return(state: OnlineState, positions: dict[str, int]):
    close = state.raw_ohlcv_buffer["close"].to_numpy(dtype=float)

    def lookup(item: PendingScore) -> float | None:
        origin = positions.get(item.origin_date)
        if origin is None:
            return None
        target = origin + int(item.horizon)
        if target >= len(close):
            return None
        return float(np.log(close[target] / close[origin]))

    return lookup


def advance_one_session(state: OnlineState, row: pd.Series, simulate: bool = True) -> dict[str, Any]:
    """Advance every recursive quantity by exactly one trading session."""
    started = time.perf_counter()
    date = validate_new_session(state, row)

    columns = list(state.raw_ohlcv_buffer.columns)
    appended = pd.DataFrame([{name: row[name] for name in columns}], columns=columns)
    appended["date"] = pd.to_datetime(appended["date"])
    buffer = pd.concat([state.raw_ohlcv_buffer, appended], ignore_index=True)
    features = build_features(buffer)
    latest = features.iloc[-1]

    # --- HMM: one forward-filter step -------------------------------------
    # Keep the column names so the fitted StandardScaler validates them.
    observation = features[state.hmm.feature_names].ffill().fillna(0.0).iloc[[-1]]
    log_alpha, raw_probabilities = forward_filter_step(
        state.hmm.model, state.hmm.log_alpha, state.hmm.scaler.transform(observation)[0]
    )
    probabilities = raw_probabilities[state.hmm.economic_order]
    current_state = int(probabilities.argmax())
    state_duration = state.hmm.state_duration + 1 if current_state == state.hmm.last_state else 1

    # --- EGARCH: one recursive variance step ------------------------------
    returns = features["log_return"].fillna(0.0).astype(float).to_numpy()
    if state.egarch.uses_ewma_fallback:
        # The EWMA branch has no closed one-step form matching pandas' bias
        # correction; recomputing the exact expression on the buffer is O(n)
        # and refits nothing, so it stays exactly equal to the batch tier.
        sigma_series = ewma_volatility_fallback(pd.Series(returns))
        sigma_daily = float(sigma_series[-1])
        log_variance = float(np.log(np.square(sigma_daily * 100)))
        standardized = float(np.clip(returns[-1] / max(sigma_daily, 1e-12), -20, 20))
    else:
        log_variance, _ = egarch_step(
            state.egarch.parameters, state.egarch.log_variance, float(returns[-2] * 100), state.egarch.model_name
        )
        sigma_daily = float(np.sqrt(np.exp(log_variance)) / 100)
        mean = float(state.egarch.parameters.get("mu", 0.0))
        standardized = float((returns[-1] * 100 - mean) / np.sqrt(np.exp(log_variance)))
    smoothing = 2.0 / (FORECAST_VOLATILITY_SPAN + 1.0)
    forecast_volatility = float(
        state.egarch.forecast_volatility + smoothing * (sigma_daily - state.egarch.forecast_volatility)
    )

    # --- Forest inference under the new regime posterior ------------------
    values: dict[str, float] = {name: float(latest.get(name, np.nan)) for name in state.selected_technical}
    values.update(_hmm_feature_row(state, probabilities, state_duration))
    values.update(
        {
            "egarch_conditional_volatility": sigma_daily,
            "egarch_forecast_volatility": forecast_volatility,
            "egarch_standardized_residual": standardized,
            "student_t_degrees_freedom": state.egarch.nu,
        }
    )
    x_row = _forest_input(state, values)
    if state.selected_model == "soft_gated_rf":
        prediction = predict_soft_gated(state.forest, x_row, probabilities[None, :])
    else:
        prediction = predict_bundle(state.forest, x_row)
    class_probability = state.calibrator.transform(prediction["probabilities"])[0]

    # --- Locked point-forecast blend --------------------------------------
    close = buffer["close"].to_numpy(dtype=float)
    drift = float(np.log(close[-1] / close[0]) / max(len(close) - 1, 1) * state.horizon)
    center = float(
        apply_center_blend(np.asarray(prediction["return"], dtype=float), np.array([drift]), state.center_alpha)[0]
    )
    sigma_horizon = float(forecast_volatility * np.sqrt(state.horizon))
    volatility_bin = int(assign_volatility_bins(np.array([sigma_horizon]), state.conformal.volatility_edges)[0])

    # --- Conformal: mature what is now observable, then issue the interval -
    state.raw_ohlcv_buffer = buffer
    positions = _resolve_pending_targets(state)
    windows = {state.horizon: state.conformal.selected_window.get(state.horizon)}
    state.conformal.pending, matured = mature_pending_scores(
        state.conformal.pending,
        state.conformal.pools,
        date,
        _realized_return(state, positions),
        windows,
        state.conformal.adaptive,
    )
    pool = state.conformal.pools.setdefault(state.horizon, ConformalPool())
    scores, regimes, bins = pool.arrays()
    interval = interval_from_scores(
        scores,
        regimes,
        bins,
        state.conformal.selected_method.get(state.horizon, "global"),
        current_state,
        volatility_bin,
        center,
        sigma_horizon,
        state.conformal.alpha_levels,
        state.conformal.minimum_stratum_size,
        None if state.conformal.adaptive is None else state.conformal.adaptive.effective_alpha(),
    )
    estimated_target = pd.Timestamp(date) + pd.offsets.BDay(state.horizon)
    state.conformal.pending.append(
        PendingScore(
            origin_date=str(date.date()),
            horizon=state.horizon,
            target_end_date=str(estimated_target.date()),
            center=center,
            sigma=sigma_horizon,
            regime=current_state,
            volatility_bin=volatility_bin,
            interval_bounds={
                float(level): (
                    float(interval[f"lower_{int(round((1 - float(level)) * 100))}"]),
                    float(interval[f"upper_{int(round((1 - float(level)) * 100))}"]),
                )
                for level in state.conformal.alpha_levels
            },
        )
    )

    # --- Commit the new state --------------------------------------------
    state.hmm.log_alpha = log_alpha
    state.hmm.last_state = current_state
    state.hmm.state_duration = state_duration
    state.egarch.log_variance = log_variance
    state.egarch.forecast_volatility = forecast_volatility
    state.egarch.standardized_residuals = np.append(state.egarch.standardized_residuals, standardized)
    state.regime_probability_history = np.vstack([state.regime_probability_history, probabilities])
    state.as_of_date = str(date.date())
    state.last_close = float(close[-1])

    simulation = _simulate(state, interval, class_probability, center) if simulate else None
    record: dict[str, Any] = {
        "as_of_date": state.as_of_date,
        "close": state.last_close,
        "regime_probabilities": probabilities,
        "regime": current_state,
        "regime_label": state.hmm.economic_labels[current_state],
        "state_duration": state_duration,
        "log_variance": log_variance,
        "sigma_daily": sigma_daily,
        "forecast_volatility": forecast_volatility,
        "sigma_horizon": sigma_horizon,
        "center": center,
        "volatility_bin": volatility_bin,
        "class_probability": class_probability,
        "forest_input": x_row,
        "interval": interval,
        "matured_scores": matured,
        "pool_size": len(pool),
        "pending": len(state.conformal.pending),
        "simulation": simulation,
        "elapsed_seconds": max(time.perf_counter() - started, 1e-9),
    }
    state.session_log.append({key: record[key] for key in ["as_of_date", "close", "regime", "center", "sigma_horizon"]})
    return record


def _simulate(state: OnlineState, interval: dict[str, Any], class_probability: np.ndarray, center: float):
    """Resample the hybrid Monte Carlo paths from the freshly updated state."""
    nu = float(state.egarch.nu)
    nominal = abs(float(student_t.ppf(0.975, nu) * np.sqrt((nu - 2) / nu)))
    scale = (
        float(interval["multiplier_95"] / max(nominal, 1e-8)) if state.simulation.get("advanced_enabled", True) else 1.0
    )
    return simulate_paths(
        last_close=state.last_close,
        horizon=int(state.simulation["horizon"]),
        paths=int(state.simulation["paths"]),
        daily_drift=center / state.horizon,
        daily_volatility=float(state.egarch.forecast_volatility * scale),
        degrees_of_freedom=nu,
        residuals=state.egarch.standardized_residuals,
        historical_regime_probabilities=state.regime_probability_history,
        transition_matrix=state.hmm.transition_matrix,
        current_regime_probability=state.hmm.ordered_probabilities(),
        rf_class_probability=class_probability,
        economic_labels=state.hmm.economic_labels,
        method="hybrid",
        student_weight=float(state.simulation.get("student_weight", 0.35)),
        block_length=int(state.block_length),
        seed=int(state.seed),
    )


def advance_to(state: OnlineState, frame: pd.DataFrame, simulate: bool = True) -> list[dict[str, Any]]:
    """Replay every session newer than the watermark, one at a time.

    Sessions are never skipped ahead: the forward-filter and EGARCH recursions
    are only correct when each observation is applied in order.
    """
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    fresh = frame[frame["date"] > pd.Timestamp(state.as_of_date)].sort_values("date")
    records: list[dict[str, Any]] = []
    for position in range(len(fresh)):
        last = position == len(fresh) - 1
        records.append(advance_one_session(state, fresh.iloc[position], simulate=simulate and last))
    return records


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------


def _source_config(config: dict[str, Any]) -> dict[str, Any]:
    source = dict(config.get("data", {}).get("source") or {})
    source.setdefault("backend", "csv")
    source.setdefault("path", config["project"].get("data_path", "data/raw/VNINDEX_Daily.csv"))
    return source


def _lookback(config: dict[str, Any]) -> int | None:
    value = config.get("online", {}).get("lookback_buffer_days")
    return None if value in (None, "", "null") else int(value)


def initialize_online_state(config_path: str | Path = "configs/default.yaml") -> dict[str, Any]:
    """Seed the online state from the most recent batch run (`run-all`)."""
    started = time.perf_counter()
    root = Path(".").resolve()
    config = load_config(config_path)
    handoff = load_batch_handoff(root)
    source = build_market_data_source(_source_config(config))
    try:
        data = source.fetch_since(None, _lookback(config))
    finally:
        source.close()
    batch_end = pd.Timestamp(handoff.run_metadata.get("last_data_date", data["date"].iloc[-1]))
    data = data[pd.to_datetime(data["date"]) <= batch_end].reset_index(drop=True)
    if data.empty:
        raise OnlineStateSchemaError("Nguồn dữ liệu không có phiên nào <= ngày cuối của batch run")
    state = build_online_state(handoff, data)
    paths = save_online_state(root, state)
    logger.info("online_state_initialized as_of=%s rows=%d", state.as_of_date, len(data))
    return {
        "status": "initialized",
        "as_of_date": state.as_of_date,
        "buffer_rows": int(len(data)),
        "conformal_pool_size": len(state.conformal.pools[state.horizon]),
        "state_path": str(paths["state"]),
        "manifest_path": str(paths["manifest"]),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def _assert_history_unchanged(state: OnlineState, frame: pd.DataFrame) -> None:
    buffer = state.raw_ohlcv_buffer
    overlap = frame[pd.to_datetime(frame["date"]) <= pd.Timestamp(state.as_of_date)]
    rows = min(len(overlap), len(buffer))
    if rows == 0:
        raise AbnormalSessionError("Nguồn dữ liệu không chứa phiên nào trùng với buffer của online state")
    left = overlap.tail(rows).reset_index(drop=True)
    right = buffer.tail(rows).reset_index(drop=True)
    if not pd.to_datetime(left["date"]).equals(pd.to_datetime(right["date"])):
        raise AbnormalSessionError(
            "Lịch giao dịch trong nguồn đã khác với buffer của online state; dừng để rà soát thay vì ghi đè"
        )
    if not np.allclose(left["close"].to_numpy(dtype=float), right["close"].to_numpy(dtype=float), atol=1e-8):
        raise AbnormalSessionError(
            "Giá đóng cửa lịch sử trong nguồn đã bị sửa so với buffer của online state; "
            "cần chạy lại `run-all` + `init-online-state` thay vì cập nhật tiếp"
        )


def update_latest(config_path: str | Path = "configs/default.yaml") -> dict[str, Any]:
    """Apply every unseen trading session and republish the `latest_*` artifacts."""
    started = time.perf_counter()
    root = Path(".").resolve()
    config = load_config(config_path)
    state = load_online_state(root)
    paths = online_state_paths(root)
    source = build_market_data_source(_source_config(config))
    try:
        frame = source.fetch_since(pd.Timestamp(state.as_of_date), _lookback(config))
    finally:
        source.close()
    fresh = frame[pd.to_datetime(frame["date"]) > pd.Timestamp(state.as_of_date)]
    if fresh.empty:
        logger.info("update_latest_no_new_session as_of=%s", state.as_of_date)
        return {
            "status": "no_new_sessions",
            "as_of_date": state.as_of_date,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    _assert_history_unchanged(state, frame)
    records = advance_to(state, frame, simulate=True)
    artifacts = _publish(root, state, records[-1], config)
    save_online_state(root, state)
    if state.session_log:
        pd.DataFrame(state.session_log).to_csv(paths["sessions"], index=False)
    elapsed = time.perf_counter() - started
    logger.info(
        "update_latest_applied sessions=%d as_of=%s elapsed=%.2fs", len(records), state.as_of_date, elapsed
    )
    return {
        "status": "updated",
        "sessions_applied": len(records),
        "as_of_date": state.as_of_date,
        "center": records[-1]["center"],
        "sigma_horizon": records[-1]["sigma_horizon"],
        "regime_label": records[-1]["regime_label"],
        "conformal_pool_size": records[-1]["pool_size"],
        "artifacts": artifacts,
        "elapsed_seconds": round(elapsed, 3),
    }


def _publish(root: Path, state: OnlineState, record: dict[str, Any], config: dict[str, Any]) -> list[str]:
    """Rewrite the `latest_*` artifacts, keeping the schema downstream expects."""
    simulation = record["simulation"]
    directory = root / "artifacts/forecasts"
    directory.mkdir(parents=True, exist_ok=True)
    forecast = simulation.forecast.copy()
    future = pd.bdate_range(pd.Timestamp(state.as_of_date) + pd.offsets.BDay(1), periods=len(forecast))
    forecast.insert(1, "estimated_trading_date", future.strftime("%Y-%m-%d"))
    forecast.to_csv(directory / "latest_forecast.csv", index=False)
    sample_count = min(int(state.simulation.get("sample_paths", 150)), len(simulation.price_paths))
    np.savez_compressed(
        directory / "latest_monte_carlo_samples.npz",
        price_paths=simulation.price_paths[:sample_count],
        return_paths=simulation.return_paths[:sample_count],
        terminal_prices=simulation.price_paths[:, -1],
        maximum_drawdowns=maximum_drawdown(
            np.column_stack([np.full(len(simulation.price_paths), state.last_close), simulation.price_paths])
        ),
    )
    interval = record["interval"]
    summary = {
        "forecast_origin": state.as_of_date,
        "last_observed_close": state.last_close,
        **simulation.summary,
        "point_center": {
            "mode": "online_locked_blend",
            "alpha": state.center_alpha,
            "horizon_return": record["center"],
        },
        "conformal": {
            "method": state.conformal.selected_method.get(state.horizon),
            "window": state.conformal.selected_window.get(state.horizon),
            "latest_multiplier_95": float(interval["multiplier_95"]),
            "stratum_used": interval["stratum_used"],
            "score_count": int(interval["score_count"]),
            "adaptive": None
            if state.conformal.adaptive is None
            else {str(key): value for key, value in state.conformal.adaptive.alpha_current.items()},
        },
        "conformal_interval": {
            key: value for key, value in interval.items() if key.startswith(("lower_", "upper_", "multiplier_"))
        },
        "regime": {
            "label": record["regime_label"],
            "probabilities": {
                label: float(value) for label, value in zip(state.hmm.economic_labels, record["regime_probabilities"], strict=True)
            },
            "state_duration": record["state_duration"],
        },
        "update_mode": "online",
        "update_note": (
            "Sinh bởi tầng online (`update-latest`): không refit HMM/EGARCH/RF. "
            "Các khối chỉ có ở batch (importance sampling, seed stability, drawdown layer) không được ghi lại ở đây."
        ),
        "source_run_metadata": state.source_run_metadata,
        "config_path": config.get("_config_path"),
        "model_version": "1.1.0-online",
        "trading_date_note": "Ngày làm việc gần đúng; chưa loại ngày nghỉ chính thức HOSE.",
    }
    write_json(directory / "latest_forecast_summary.json", summary)
    return [
        "artifacts/forecasts/latest_forecast.csv",
        "artifacts/forecasts/latest_forecast_summary.json",
        "artifacts/forecasts/latest_monte_carlo_samples.npz",
    ]
