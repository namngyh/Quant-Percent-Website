import numpy as np
import pandas as pd
import pytest

from raemf_mc.features.downside import build_downside_features
from raemf_mc.targets.downside_targets import create_downside_targets, downside_target_columns
from raemf_mc.targets.regime_targets import create_multihorizon_targets, target_columns
from raemf_mc.validation.leakage_checks import assert_no_future_feature_columns


def _prices(rows: int = 100) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, rows)))
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2020-01-02", periods=rows),
            "open": close * np.exp(rng.normal(0, 0.002, rows)),
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.integers(1_000, 5_000, rows),
        }
    )


def test_downside_targets_are_nonexclusive_and_end_rows_are_missing():
    frame = pd.DataFrame(
        {
            "target_sigma": [0.01, 0.01, 0.01],
            "target_2": ["Bear", "Stress", pd.NA],
            "forward_return_2": [-0.10, -0.02, np.nan],
            "future_mae_2": [-0.20, -0.20, np.nan],
            "target_end_date_2": [pd.Timestamp("2020-01-03"), pd.Timestamp("2020-01-06"), pd.NaT],
        }
    )
    output = create_downside_targets(
        frame,
        horizons=[2],
        bear_threshold=0.5,
        stress_threshold=1.5,
    )
    assert output.loc[0, "risk_off_2"] == 1
    assert output.loc[0, "negative_terminal_2"] == 1
    assert output.loc[0, "stress_path_2"] == 1
    assert output.loc[1, "risk_off_2"] == 1
    assert output.loc[1, "stress_path_2"] == 1
    assert pd.isna(output.loc[2, "risk_off_2"])


def test_target_end_date_and_all_downside_targets_are_forbidden_features():
    prices = _prices(60)
    targeted = create_multihorizon_targets(prices, horizons=[5])
    output = create_downside_targets(targeted, horizons=[5])
    assert output.loc[0, "target_end_date_5"] == prices.loc[5, "date"]
    forbidden = downside_target_columns([5])
    assert set(forbidden).issubset(set(target_columns([5])))
    for column in forbidden:
        with pytest.raises(AssertionError):
            assert_no_future_feature_columns([column])


def test_downside_features_do_not_change_when_only_future_data_changes():
    prices = _prices(120)
    before, _ = build_downside_features(prices)
    changed = prices.copy()
    changed.loc[90:, "close"] *= np.linspace(1.0, 2.0, len(changed) - 90)
    changed.loc[90:, "open"] *= np.linspace(1.0, 1.5, len(changed) - 90)
    after, _ = build_downside_features(changed)
    pd.testing.assert_frame_equal(before.iloc[:90], after.iloc[:90])
    assert not any("target" in column or "future" in column for column in before.columns)
