"""Discovering the `data.source` block instead of being told it.

The VPS schema is not known here, and guessing it would violate the repo's rule
against silent assumptions. These tests pin the behaviour of a probe that reads
a database read-only and reports what a config would have to say.
"""

import sqlite3

import pandas as pd
import pytest

from vnindex_model.source_discovery import (
    describe_source,
    suggest_source_config,
    suggested_yaml,
)

COLUMNS = {
    "TRADINGDATE": "date",
    "OPENPRICE": "open",
    "HIGHPRICE": "high",
    "LOWPRICE": "low",
    "CLOSEPRICE": "close",
    "TOTALMATCHVOL": "volume",
}


@pytest.fixture
def vendor_sqlite(tmp_path):
    dates = pd.bdate_range("2024-01-01", periods=30)
    frame = pd.DataFrame(
        {
            "TRADINGDATE": (dates - pd.Timestamp("1970-01-01")).days,
            "OPENPRICE": range(100, 130),
            "HIGHPRICE": range(101, 131),
            "LOWPRICE": range(99, 129),
            "CLOSEPRICE": range(100, 130),
            "TOTALMATCHVOL": range(1000, 1030),
        }
    )
    path = tmp_path / "vendor.dat"
    connection = sqlite3.connect(path)
    frame.to_sql("HIST", connection, index=False)
    pd.DataFrame({"note": ["unrelated"]}).to_sql("META", connection, index=False)
    connection.close()
    return path


def test_describe_lists_every_table_and_its_columns(vendor_sqlite):
    described = describe_source(vendor_sqlite)
    assert described["backend"] == "sqlite"
    tables = {entry["table"]: entry for entry in described["tables"]}
    assert set(tables) == {"HIST", "META"}
    assert "CLOSEPRICE" in tables["HIST"]["columns"]


def test_suggestion_picks_the_table_that_can_supply_ohlcv(vendor_sqlite):
    suggestion = suggest_source_config(vendor_sqlite)
    assert suggestion["backend"] == "sqlite"
    assert suggestion["table"] == "HIST"
    assert suggestion["column_map"]["close"] == "CLOSEPRICE"
    assert suggestion["column_map"]["date"] == "TRADINGDATE"


def test_suggestion_detects_integer_epoch_day_dates(vendor_sqlite):
    assert suggest_source_config(vendor_sqlite)["date_unit"] == "D"


def test_suggestion_leaves_date_unit_empty_for_text_dates(tmp_path):
    frame = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=12).strftime("%Y-%m-%d"),
            "close": range(12),
        }
    )
    path = tmp_path / "text.sqlite"
    connection = sqlite3.connect(path)
    frame.to_sql("prices", connection, index=False)
    connection.close()
    assert suggest_source_config(path)["date_unit"] is None


def test_a_suggestion_round_trips_through_the_real_connector(vendor_sqlite):
    """The whole point: the suggested block must actually work."""
    from vnindex_model.data_source import build_market_data_source

    source = build_market_data_source(suggest_source_config(vendor_sqlite))
    try:
        assert source.latest_date() == pd.Timestamp("2024-02-09")
        assert len(source.fetch_since(None, None)) == 30
    finally:
        source.close()


def test_suggested_yaml_is_pasteable_into_the_config(vendor_sqlite):
    import yaml

    text = suggested_yaml(vendor_sqlite)
    parsed = yaml.safe_load(text)
    assert set(parsed) == {"data"}
    assert parsed["data"]["source"]["table"] == "HIST"


def test_a_database_without_price_columns_is_reported_not_guessed(tmp_path):
    path = tmp_path / "empty.sqlite"
    connection = sqlite3.connect(path)
    pd.DataFrame({"a": [1], "b": [2]}).to_sql("junk", connection, index=False)
    connection.close()
    with pytest.raises(LookupError, match="không tìm thấy"):
        suggest_source_config(path)


def test_a_csv_source_is_described_without_a_table(tmp_path):
    frame = pd.DataFrame({"Date": ["01/02/2024"], "Close": [100.0]})
    path = tmp_path / "prices.csv"
    frame.to_csv(path, index=False)
    suggestion = suggest_source_config(path)
    assert suggestion["backend"] == "csv"
    assert suggestion["table"] is None
