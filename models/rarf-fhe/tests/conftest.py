from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_ohlcv() -> pd.DataFrame:
    rng = np.random.default_rng(55)
    n = 650
    returns = rng.normal(0.0003, 0.012, n)
    close = 1000 * np.exp(np.cumsum(returns))
    open_ = close * np.exp(rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.01, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.01, n))
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2020-01-01", periods=n),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.integers(1_000_000, 20_000_000, n),
        }
    )


BATCH_ROWS = 600
BATCH_HORIZON = 20


def _build_synthetic_handoff(frame: pd.DataFrame):
    """A miniature of `run_pipeline`'s final refit, small enough for tests.

    It fits exactly the objects the online layer consumes - filtered HMM,
    EGARCH, a soft-gated forest, a calibrator and a conformal calibration
    stream - so the handoff under test has the same shape the real pipeline
    produces without paying for the full research run.
    """
    from vnindex_model.calibration import fit_calibrator
    from vnindex_model.conformal import assign_volatility_bins, volatility_bin_edges
    from vnindex_model.features import build_features, select_train_features
    from vnindex_model.hmm import fit_filtered_hmm
    from vnindex_model.online import BatchHandoff
    from vnindex_model.random_forest import fit_soft_gated_forest
    from vnindex_model.targets import build_targets
    from vnindex_model.volatility import fit_egarch_student_t

    features = build_features(frame)
    targets = build_targets(frame, [BATCH_HORIZON])
    train = np.arange(int(len(frame) * 0.6))
    calibration = np.arange(len(train), len(frame) - BATCH_HORIZON)
    selected_technical = select_train_features(features, train)[:25]
    hmm = fit_filtered_hmm(
        features, features["log_return"], features["current_drawdown"], train, [2], [55], 50
    )
    volatility = fit_egarch_student_t(features["log_return"], train)
    hmm_columns = [column for column in hmm.probabilities if column.startswith("hmm_probability_")]
    augmented = pd.concat(
        [features[selected_technical], hmm.probabilities.drop(columns=["hmm_state"]), volatility.features], axis=1
    )
    regime_probabilities = hmm.probabilities[hmm_columns].to_numpy()
    usable = (
        targets[
            [
                f"forward_return_{BATCH_HORIZON}",
                f"normalized_return_{BATCH_HORIZON}",
                f"forward_max_drawdown_{BATCH_HORIZON}",
            ]
        ]
        .notna()
        .all(axis=1)
        .to_numpy()
        & targets[f"regime_{BATCH_HORIZON}"].notna().to_numpy()
    )
    labelled = train[usable[train]]
    calibration = calibration[usable[calibration]]
    forest_config = {"n_estimators": 40, "max_depth": 5, "min_samples_leaf": 20, "max_features": "sqrt", "max_samples": 0.8}
    forest = fit_soft_gated_forest(
        augmented.iloc[labelled],
        regime_probabilities[labelled],
        targets[f"regime_{BATCH_HORIZON}"].astype(object).to_numpy()[labelled],
        targets[f"forward_return_{BATCH_HORIZON}"].to_numpy()[labelled],
        targets[f"normalized_return_{BATCH_HORIZON}"].to_numpy()[labelled],
        targets[f"forward_max_drawdown_{BATCH_HORIZON}"].to_numpy()[labelled],
        augmented.columns.tolist(),
        forest_config,
        55,
    )
    calibrator = fit_calibrator(
        np.full((len(labelled), 4), 0.25), targets[f"regime_{BATCH_HORIZON}"].astype(object).to_numpy()[labelled], "none"
    )
    sigma = volatility.features["egarch_forecast_volatility"].to_numpy()[calibration] * np.sqrt(BATCH_HORIZON)
    edges = volatility_bin_edges(sigma, 3)
    return BatchHandoff(
        horizon=BATCH_HORIZON,
        selected_technical=selected_technical,
        hmm=hmm,
        volatility=volatility,
        forest=forest,
        selected_model="soft_gated_rf",
        forest_feature_names=augmented.columns.tolist(),
        calibrator=calibrator,
        center_alpha=1.0,
        conformal_method="global",
        conformal_window=None,
        volatility_edges=edges,
        calibration_actual=targets[f"forward_return_{BATCH_HORIZON}"].to_numpy()[calibration],
        calibration_center=np.zeros(len(calibration)),
        calibration_sigma=sigma,
        calibration_regime=regime_probabilities[calibration].argmax(axis=1),
        calibration_volatility_bin=assign_volatility_bins(sigma, edges),
        alpha_levels=[0.50, 0.20, 0.10, 0.05],
        minimum_stratum_size=80,
        block_length=10,
        seed=55,
        simulation={"paths": 400, "horizon": 20, "student_weight": 0.35, "sample_paths": 50},
        adaptive_conformal={"enabled": False, "gamma": 0.02},
        run_metadata={"run_timestamp_utc": "2024-01-01T00:00:00+00:00", "data_hash": "test", "model_version": "1.0.0"},
    )


@pytest.fixture
def batch_frame(synthetic_ohlcv) -> pd.DataFrame:
    return synthetic_ohlcv.iloc[:BATCH_ROWS].reset_index(drop=True)


_HANDOFF_CACHE: dict[int, object] = {}


@pytest.fixture
def synthetic_handoff(batch_frame):
    # Fitting the miniature pipeline takes seconds; the frame is deterministic,
    # so build it once and hand each test its own dataclass copy to mutate.
    from dataclasses import replace

    key = len(batch_frame)
    if key not in _HANDOFF_CACHE:
        _HANDOFF_CACHE[key] = _build_synthetic_handoff(batch_frame)
    return replace(_HANDOFF_CACHE[key])
