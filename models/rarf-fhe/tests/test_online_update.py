import numpy as np
import pandas as pd
import pytest

from vnindex_model.features import build_features
from vnindex_model.hmm import forward_filter
from vnindex_model.online import (
    AbnormalSessionError,
    advance_one_session,
    advance_to,
    build_online_state,
    validate_new_session,
)


@pytest.fixture
def seeded_state(synthetic_handoff, batch_frame):
    return build_online_state(synthetic_handoff, batch_frame)


def test_online_hmm_posterior_matches_a_batch_filter_over_the_extended_series(
    seeded_state, synthetic_handoff, synthetic_ohlcv
):
    """The acceptance gate: stepping forward must reproduce refiltering history."""
    extended = synthetic_ohlcv.iloc[:650].reset_index(drop=True)
    hmm = synthetic_handoff.hmm
    observations = build_features(extended)[hmm.feature_names].ffill().fillna(0)
    batch = forward_filter(hmm.model, hmm.scaler.transform(observations))
    order = np.asarray(hmm.diagnostics["economic_order"], dtype=int)
    for position in range(600, 650):
        record = advance_one_session(seeded_state, extended.iloc[position], simulate=False)
        assert np.allclose(record["regime_probabilities"], batch[position][order], atol=1e-10)


def test_online_egarch_log_variance_matches_the_batch_recursion(seeded_state, synthetic_ohlcv):
    from vnindex_model.volatility import egarch_step

    extended = synthetic_ohlcv.iloc[:640].reset_index(drop=True)
    returns = build_features(extended)["log_return"].fillna(0.0).astype(float)
    parameters = seeded_state.egarch.parameters
    model_name = seeded_state.egarch.model_name
    expected = seeded_state.egarch.log_variance
    for position in range(600, 640):
        expected = egarch_step(parameters, expected, float(returns.iloc[position - 1] * 100), model_name)[0]
        record = advance_one_session(seeded_state, extended.iloc[position], simulate=False)
        assert record["log_variance"] == pytest.approx(expected, abs=1e-10)


def test_twenty_sessions_keep_every_published_quantity_well_formed(seeded_state, synthetic_ohlcv):
    extended = synthetic_ohlcv.iloc[:620].reset_index(drop=True)
    for position in range(600, 620):
        record = advance_one_session(seeded_state, extended.iloc[position], simulate=False)
        probabilities = np.asarray(record["regime_probabilities"])
        assert probabilities.min() >= 0 and probabilities.sum() == pytest.approx(1.0)
        assert 0 < record["sigma_horizon"] < 1 and np.isfinite(record["sigma_horizon"])
        interval = record["interval"]
        assert interval["upper_95"] - interval["lower_95"] > interval["upper_50"] - interval["lower_50"] > 0
        assert interval["lower_95"] <= record["center"] <= interval["upper_95"]
    assert seeded_state.as_of_date == str(extended["date"].iloc[-1].date())


def test_pending_forecasts_mature_into_the_pool_after_the_horizon(seeded_state, synthetic_ohlcv):
    horizon = seeded_state.horizon
    pool = seeded_state.conformal.pools[horizon]
    seeded = len(pool)
    extended = synthetic_ohlcv.iloc[: 600 + horizon + 5].reset_index(drop=True)
    for position in range(600, len(extended)):
        advance_one_session(seeded_state, extended.iloc[position], simulate=False)
    assert len(pool) == seeded + 5
    assert len(seeded_state.conformal.pending) == horizon


def test_adaptive_conformal_moves_alpha_only_when_enabled(synthetic_handoff, batch_frame, synthetic_ohlcv):
    horizon = synthetic_handoff.horizon
    synthetic_handoff.adaptive_conformal = {"enabled": True, "gamma": 0.05}
    state = build_online_state(synthetic_handoff, batch_frame)
    extended = synthetic_ohlcv.iloc[: 600 + horizon + 3].reset_index(drop=True)
    for position in range(600, len(extended)):
        advance_one_session(state, extended.iloc[position], simulate=False)
    assert state.conformal.adaptive is not None
    assert state.conformal.adaptive.alpha_current[0.05] != pytest.approx(0.05)


def test_advance_to_replays_a_multi_session_gap_one_session_at_a_time(
    synthetic_handoff, batch_frame, synthetic_ohlcv
):
    one = build_online_state(synthetic_handoff, batch_frame)
    many = build_online_state(synthetic_handoff, batch_frame)
    extended = synthetic_ohlcv.iloc[:610].reset_index(drop=True)
    for position in range(600, 610):
        advance_one_session(one, extended.iloc[position], simulate=False)
    advance_to(many, extended, simulate=False)
    assert many.as_of_date == one.as_of_date
    assert np.allclose(many.hmm.log_alpha, one.hmm.log_alpha)
    assert many.egarch.log_variance == pytest.approx(one.egarch.log_variance)


def test_advance_to_is_idempotent_when_no_session_is_new(seeded_state, batch_frame):
    records = advance_to(seeded_state, batch_frame, simulate=False)
    assert records == []
    assert seeded_state.as_of_date == str(batch_frame["date"].iloc[-1].date())


def test_a_session_with_a_missing_close_is_rejected(seeded_state, synthetic_ohlcv):
    row = synthetic_ohlcv.iloc[600].copy()
    row["close"] = np.nan
    with pytest.raises(AbnormalSessionError, match="thiếu giá trị"):
        validate_new_session(seeded_state, row)


def test_a_session_violating_the_ohlc_constraint_is_rejected(seeded_state, synthetic_ohlcv):
    row = synthetic_ohlcv.iloc[600].copy()
    row["high"] = float(row["low"]) - 1.0
    with pytest.raises(AbnormalSessionError, match="OHLC"):
        validate_new_session(seeded_state, row)


def test_a_long_calendar_gap_is_reported_instead_of_being_bridged(seeded_state, synthetic_ohlcv):
    row = synthetic_ohlcv.iloc[600].copy()
    row["date"] = pd.Timestamp(row["date"]) + pd.Timedelta(days=40)
    with pytest.raises(AbnormalSessionError, match="gap"):
        validate_new_session(seeded_state, row)


def test_a_session_that_is_not_after_the_current_watermark_is_rejected(seeded_state, batch_frame):
    with pytest.raises(AbnormalSessionError, match="as_of_date"):
        validate_new_session(seeded_state, batch_frame.iloc[-1])


def test_advance_one_session_refuses_an_abnormal_row_without_mutating_state(seeded_state, synthetic_ohlcv):
    before = seeded_state.as_of_date
    buffer_rows = len(seeded_state.raw_ohlcv_buffer)
    row = synthetic_ohlcv.iloc[600].copy()
    row["close"] = np.nan
    with pytest.raises(AbnormalSessionError):
        advance_one_session(seeded_state, row, simulate=False)
    assert seeded_state.as_of_date == before
    assert len(seeded_state.raw_ohlcv_buffer) == buffer_rows


def test_a_simulated_session_publishes_a_monte_carlo_forecast(seeded_state, synthetic_ohlcv):
    record = advance_one_session(seeded_state, synthetic_ohlcv.iloc[600], simulate=True)
    forecast = record["simulation"].forecast
    assert len(forecast) == seeded_state.simulation["horizon"]
    assert (forecast["upper_95"] >= forecast["lower_95"]).all()
    assert record["elapsed_seconds"] > 0


def test_a_non_gated_selection_predicts_through_the_global_bundle(
    synthetic_handoff, batch_frame, synthetic_ohlcv
):
    """`run_pipeline` may pick `rf_hmm_egarch`, whose handoff carries a plain bundle."""
    synthetic_handoff.selected_model = "rf_hmm_egarch"
    synthetic_handoff.forest = synthetic_handoff.forest.global_bundle
    state = build_online_state(synthetic_handoff, batch_frame)
    record = advance_one_session(state, synthetic_ohlcv.iloc[600], simulate=False)
    assert np.isfinite(record["center"])
    assert record["class_probability"].shape == (4,)
    assert record["class_probability"].sum() == pytest.approx(1.0)


def test_online_forest_input_row_matches_the_batch_regime_features(
    seeded_state, synthetic_handoff, synthetic_ohlcv
):
    """The forest sees the same regime columns online as `fit_filtered_hmm` builds in batch."""
    from vnindex_model.hmm import regime_feature_frame

    extended = synthetic_ohlcv.iloc[:615].reset_index(drop=True)
    hmm = synthetic_handoff.hmm
    observations = build_features(extended)[hmm.feature_names].ffill().fillna(0)
    order = np.asarray(hmm.diagnostics["economic_order"], dtype=int)
    batch = regime_feature_frame(
        forward_filter(hmm.model, hmm.scaler.transform(observations))[:, order], hmm.transition_matrix
    )
    columns = [
        "hmm_entropy",
        "hmm_state_duration",
        "hmm_expected_duration",
        "hmm_transition_probability",
        *[f"hmm_probability_{index}" for index in range(hmm.model.n_components)],
    ]
    for position in range(600, 615):
        record = advance_one_session(seeded_state, extended.iloc[position], simulate=False)
        row = record["forest_input"]
        for column in columns:
            assert float(row[column].iloc[0]) == pytest.approx(
                float(batch[column].iloc[position]), abs=1e-9
            ), f"{column} @ {position}"


def test_online_forest_input_row_matches_the_batch_technical_features(
    seeded_state, synthetic_handoff, synthetic_ohlcv
):
    """Feature columns are recomputed from the buffer, so they must equal the batch frame."""
    extended = synthetic_ohlcv.iloc[:610].reset_index(drop=True)
    batch = build_features(extended)
    for position in range(600, 610):
        record = advance_one_session(seeded_state, extended.iloc[position], simulate=False)
        row = record["forest_input"]
        for column in seeded_state.selected_technical:
            expected = float(batch[column].iloc[position])
            actual = float(row[column].iloc[0])
            if np.isnan(expected):
                assert np.isnan(actual), column
            else:
                assert actual == pytest.approx(expected, rel=1e-12, abs=1e-12), f"{column} @ {position}"


def test_session_histories_stay_aligned_with_the_buffer_as_sessions_are_applied(
    seeded_state, synthetic_ohlcv
):
    """The Monte Carlo resample weights residuals by regime posteriors; both are per-session."""
    extended = synthetic_ohlcv.iloc[:608].reset_index(drop=True)
    for position in range(600, 608):
        advance_one_session(seeded_state, extended.iloc[position], simulate=False)
        rows = len(seeded_state.raw_ohlcv_buffer)
        assert len(seeded_state.egarch.standardized_residuals) == rows
        assert len(seeded_state.regime_probability_history) == rows
