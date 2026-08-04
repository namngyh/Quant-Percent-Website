"""Data contract, normalisation and validation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.constants import DATA_CONTRACT_COLUMNS, UNKNOWN_SECTOR
from dynamicgraph.data.calendar import align_to_calendar, infer_trading_calendar, missing_trading_dates
from dynamicgraph.data.connectors import DataProSQLiteConnector, _finalize_contract
from dynamicgraph.data.constituent_manager import resolve_liquidity_universe
from dynamicgraph.data.normalizer import normalize_panel
from dynamicgraph.data.schema_inference import infer_columns_from_names
from dynamicgraph.data.validator import rolling_window_validity, validate_panel


def test_contract_columns_are_enforced():
    frame = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-01"]), "ticker": ["abc"], "close": [10.0]}
    )
    frame["sector"] = np.nan
    frame["is_index"] = np.nan
    out = _finalize_contract(frame)
    assert list(out.columns)[: len(DATA_CONTRACT_COLUMNS)] == DATA_CONTRACT_COLUMNS
    assert out["ticker"].iloc[0] == "ABC"
    assert out["sector"].iloc[0] == UNKNOWN_SECTOR
    assert out["is_index"].iloc[0] is np.False_ or out["is_index"].iloc[0] == False  # noqa: E712


def test_column_inference_prefers_adjusted_over_close():
    mapping = infer_columns_from_names(["Date", "Symbol", "Close", "Adj Close", "Volume"])
    assert mapping["date"] == "Date"
    assert mapping["ticker"] == "Symbol"
    assert mapping["adjusted_close"] == "Adj Close"
    assert mapping["close"] == "Close"


def test_column_inference_handles_vendor_names():
    mapping = infer_columns_from_names(
        ["TRADING_KEY", "SYMBOL", "OPEN_PX", "HIGH_PX", "LOW_PX", "CLOSE_PX", "VOL", "VAL"]
    )
    assert mapping["open"] == "OPEN_PX"
    assert mapping["close"] == "CLOSE_PX"
    assert mapping["volume"] == "VOL"
    assert mapping["turnover"] == "VAL"


def test_datapro_icb_mapping():
    assert DataProSQLiteConnector.icb_to_sector(803050) == "Banks"
    assert DataProSQLiteConnector.icb_to_sector(806030) == "Real Estate"
    assert DataProSQLiteConnector.icb_to_sector(905030) == "Technology"
    assert DataProSQLiteConnector.icb_to_sector(0) == UNKNOWN_SECTOR
    assert DataProSQLiteConnector.icb_to_sector(None) == UNKNOWN_SECTOR


def test_normalizer_renames_the_index_symbol(synthetic_panel, base_config):
    panel = synthetic_panel.copy()
    panel.loc[panel["ticker"] == "VN30", "ticker"] = "VN30INDEX"
    out, report = normalize_panel(panel, base_config, index_source_symbol="VN30INDEX")
    assert "VN30" in set(out["ticker"])
    assert out.loc[out["ticker"] == "VN30", "is_index"].all()
    assert report.index_ticker == "VN30"


def test_normalizer_drops_duplicates(synthetic_panel, base_config):
    duplicated = pd.concat([synthetic_panel, synthetic_panel.head(20)], ignore_index=True)
    out, report = normalize_panel(duplicated, base_config, index_source_symbol="VN30")
    assert report.n_duplicates_dropped == 20
    assert not out.duplicated(subset=["ticker", "date"]).any()


def test_normalizer_refuses_unadjusted_when_not_allowed(synthetic_panel, base_config):
    panel = synthetic_panel.drop(columns=["adjusted_close"])
    panel["adjusted_close"] = np.nan
    base_config.data.allow_unadjusted_price = False
    with pytest.raises(ValueError, match="allow_unadjusted_price"):
        normalize_panel(panel, base_config, index_source_symbol="VN30")


def test_normalizer_warns_when_using_unadjusted(synthetic_panel, base_config):
    panel = synthetic_panel.copy()
    panel["adjusted_close"] = np.nan
    base_config.data.allow_unadjusted_price = True
    try:
        out, report = normalize_panel(panel, base_config, index_source_symbol="VN30")
        assert report.used_unadjusted_price
        assert any("UNADJUSTED" in w.upper() for w in report.warnings)
        assert out["adjusted_close"].notna().any()
    finally:
        base_config.data.allow_unadjusted_price = False


def test_normalizer_nulls_non_positive_prices(synthetic_panel, base_config):
    panel = synthetic_panel.copy()
    panel.loc[panel.index[:5], "close"] = -1.0
    out, report = normalize_panel(panel, base_config, index_source_symbol="VN30")
    assert (out["close"].dropna() > 0).all()
    assert any("non-positive" in w for w in report.warnings)


def test_calendar_inference_uses_the_index(synthetic_panel):
    calendar = infer_trading_calendar(synthetic_panel, "VN30")
    index_dates = synthetic_panel.loc[synthetic_panel["ticker"] == "VN30", "date"]
    assert len(calendar) == index_dates.nunique()


def test_align_to_calendar_never_forward_fills_volume(synthetic_panel):
    panel = synthetic_panel.copy()
    calendar = infer_trading_calendar(panel, "VN30")
    # Remove one ticker's observations on a few days.
    victim = "BNK1"
    gap_dates = calendar[100:103]
    panel = panel[~((panel["ticker"] == victim) & (panel["date"].isin(gap_dates)))]

    aligned = align_to_calendar(panel, calendar, max_forward_fill_days=1)
    rows = aligned[(aligned["ticker"] == victim) & (aligned["date"].isin(gap_dates))]
    assert len(rows) == 3
    assert rows["is_filled"].all()
    assert (rows["volume"] == 0).all(), "volume must be zeroed, never carried forward"
    assert rows["close"].notna().iloc[0], "one day of price forward-fill is allowed"
    assert rows["close"].isna().iloc[2], "forward fill must stop at the configured limit"


def test_missing_trading_dates_ignores_pre_listing_gaps(synthetic_panel):
    panel = synthetic_panel.copy()
    calendar = infer_trading_calendar(panel, "VN30")
    late = panel[panel["ticker"] == "TEC1"].iloc[400:]
    panel = pd.concat([panel[panel["ticker"] != "TEC1"], late], ignore_index=True)
    report = missing_trading_dates(panel, calendar).set_index("ticker")
    assert report.loc["TEC1", "missing_ratio"] == pytest.approx(0.0, abs=1e-9)


def test_validator_flags_duplicates(synthetic_panel, base_config):
    panel = pd.concat([synthetic_panel, synthetic_panel.head(5)], ignore_index=True)
    report = validate_panel(panel, base_config, "VN30")
    check = next(c for c in report.checks if c.name == "duplicate_ticker_date")
    assert not check.passed
    assert check.severity == "error"


def test_validator_flags_corporate_action_like_jumps(synthetic_panel, base_config):
    panel = synthetic_panel.copy()
    mask = (panel["ticker"] == "BNK1") & (panel["date"] == panel["date"].iloc[500])
    halved = panel.loc[mask, "close"] * 0.5
    panel.loc[mask, "close"] = halved
    panel.loc[mask, "adjusted_close"] = halved
    report = validate_panel(panel, base_config, "VN30")
    check = next(c for c in report.checks if c.name == "corporate_action_like_jumps")
    assert not check.passed


def test_validator_flags_short_history(synthetic_panel, base_config):
    panel = synthetic_panel.copy()
    short = panel[panel["ticker"] == "TEC3"].tail(30)
    panel = pd.concat([panel[panel["ticker"] != "TEC3"], short], ignore_index=True)
    report = validate_panel(panel, base_config, "VN30")
    assert "TEC3" in report.excluded_tickers


def test_validator_passes_a_clean_panel(synthetic_panel, base_config):
    report = validate_panel(synthetic_panel, base_config, "VN30")
    assert not report.errors, [c.message for c in report.errors]


def test_rolling_window_validity_masks_sparse_tickers(synthetic_returns):
    returns = synthetic_returns.copy()
    returns.iloc[100:160, 0] = np.nan          # 60 of 60 missing at t=159
    mask = rolling_window_validity(returns, 60, max_missing_ratio=0.10)
    assert not mask.iloc[159, 0]
    assert mask.iloc[400, 0]


def test_liquidity_universe_is_point_in_time(synthetic_panel):
    calendar = infer_trading_calendar(synthetic_panel, "VN30")
    resolution = resolve_liquidity_universe(
        synthetic_panel, calendar, size=6, lookback=120, rebalance_days=126, exclude={"VN30"}
    )
    assert not resolution.survivorship_bias
    assert not resolution.membership.empty
    counts = resolution.membership.groupby("date")["ticker"].nunique()
    assert counts.max() <= 6
    assert "VN30" not in set(resolution.membership["ticker"])
