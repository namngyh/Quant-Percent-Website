import json

import numpy as np
import pandas as pd
import pytest

from vnindex_model.online import build_online_state
from vnindex_model.online_state import (
    SCHEMA_VERSION,
    OnlineStateSchemaError,
    load_online_state,
    online_state_paths,
    save_online_state,
)


@pytest.fixture
def seeded_state(synthetic_handoff, batch_frame):
    return build_online_state(synthetic_handoff, batch_frame)


def test_seeded_state_records_the_last_batch_session(seeded_state, batch_frame):
    assert seeded_state.as_of_date == str(batch_frame["date"].iloc[-1].date())
    assert seeded_state.last_close == pytest.approx(float(batch_frame["close"].iloc[-1]))
    assert len(seeded_state.raw_ohlcv_buffer) == len(batch_frame)
    assert seeded_state.schema_version == SCHEMA_VERSION


def test_seeded_log_alpha_reproduces_the_batch_forward_filter(seeded_state, synthetic_handoff, batch_frame):
    from vnindex_model.features import build_features

    hmm = synthetic_handoff.hmm
    observations = build_features(batch_frame)[hmm.feature_names].ffill().fillna(0)
    scaled = hmm.scaler.transform(observations)
    from vnindex_model.hmm import forward_filter

    expected = forward_filter(hmm.model, scaled)[-1]
    assert np.allclose(np.exp(seeded_state.hmm.log_alpha), expected, atol=1e-12)


def test_seeded_conformal_pool_carries_the_batch_calibration_scores(seeded_state, synthetic_handoff):
    pool = seeded_state.conformal.pools[synthetic_handoff.horizon]
    assert len(pool) == len(synthetic_handoff.calibration_actual)
    expected = (synthetic_handoff.calibration_actual - synthetic_handoff.calibration_center) / np.maximum(
        synthetic_handoff.calibration_sigma, 1e-8
    )
    assert np.allclose(pool.arrays()[0], expected)


def test_save_and_load_round_trips_the_state(tmp_path, seeded_state):
    save_online_state(tmp_path, seeded_state)
    restored = load_online_state(tmp_path)
    assert restored.as_of_date == seeded_state.as_of_date
    assert np.allclose(restored.hmm.log_alpha, seeded_state.hmm.log_alpha)
    assert restored.egarch.log_variance == pytest.approx(seeded_state.egarch.log_variance)
    assert len(restored.raw_ohlcv_buffer) == len(seeded_state.raw_ohlcv_buffer)


def test_manifest_pins_the_state_to_its_data_and_batch_run(tmp_path, seeded_state):
    save_online_state(tmp_path, seeded_state)
    manifest = json.loads(online_state_paths(tmp_path)["manifest"].read_text(encoding="utf-8"))
    assert manifest["as_of_date"] == seeded_state.as_of_date
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["buffer_sha256"] == seeded_state.buffer_checksum()
    assert manifest["source_run_metadata"]["data_hash"] == "test"
    assert manifest["buffer_rows"] == len(seeded_state.raw_ohlcv_buffer)


def test_loading_a_state_from_another_schema_version_is_refused(tmp_path, seeded_state):
    save_online_state(tmp_path, seeded_state)
    seeded_state.schema_version = SCHEMA_VERSION + 1
    save_online_state(tmp_path, seeded_state)
    with pytest.raises(OnlineStateSchemaError, match="schema"):
        load_online_state(tmp_path)


def test_loading_a_state_whose_buffer_was_tampered_with_is_refused(tmp_path, seeded_state):
    save_online_state(tmp_path, seeded_state)
    seeded_state.raw_ohlcv_buffer.loc[0, "close"] = 1.0
    from vnindex_model.persistence import save_model

    save_model(online_state_paths(tmp_path)["state"], seeded_state)
    with pytest.raises(OnlineStateSchemaError, match="checksum"):
        load_online_state(tmp_path)


def test_buffer_checksum_changes_with_the_buffer(seeded_state):
    before = seeded_state.buffer_checksum()
    seeded_state.raw_ohlcv_buffer = pd.concat(
        [seeded_state.raw_ohlcv_buffer, seeded_state.raw_ohlcv_buffer.tail(1)], ignore_index=True
    )
    assert seeded_state.buffer_checksum() != before


def test_seeding_on_a_shorter_history_than_the_batch_fit_is_refused(synthetic_handoff, batch_frame):
    """The residual and regime histories are indexed by session; a short buffer desynchronises them."""
    with pytest.raises(OnlineStateSchemaError, match="số phiên"):
        build_online_state(synthetic_handoff, batch_frame.iloc[:-5].reset_index(drop=True))


def test_seeding_on_a_longer_history_than_the_batch_fit_is_refused(synthetic_handoff, batch_frame):
    longer = pd.concat([batch_frame, batch_frame.tail(1)], ignore_index=True)
    longer.loc[longer.index[-1], "date"] = pd.Timestamp(longer["date"].iloc[-2]) + pd.Timedelta(days=1)
    with pytest.raises(OnlineStateSchemaError, match="số phiên"):
        build_online_state(synthetic_handoff, longer)


def test_seeded_histories_stay_aligned_with_the_buffer(seeded_state):
    rows = len(seeded_state.raw_ohlcv_buffer)
    assert len(seeded_state.egarch.standardized_residuals) == rows
    assert len(seeded_state.regime_probability_history) == rows
