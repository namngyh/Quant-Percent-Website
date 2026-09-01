import sqlite3

import pandas as pd
import pytest

from vnindex_model.data_source import (
    CsvMarketDataSource,
    DuckDBMarketDataSource,
    ReadOnlyViolation,
    SQLiteMarketDataSource,
    build_market_data_source,
)

COLUMN_MAP = {
    "date": "trading_date",
    "open": "open_price",
    "high": "high_price",
    "low": "low_price",
    "close": "close_price",
    "volume": "match_volume",
}


@pytest.fixture
def panel() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=40)
    return pd.DataFrame(
        {
            "trading_date": dates.strftime("%Y-%m-%d"),
            "open_price": range(100, 140),
            "high_price": range(101, 141),
            "low_price": range(99, 139),
            "close_price": range(100, 140),
            "match_volume": range(1000, 1040),
        }
    )


@pytest.fixture
def sqlite_path(tmp_path, panel):
    path = tmp_path / "market.sqlite"
    connection = sqlite3.connect(path)
    panel.to_sql("daily_ohlcv", connection, index=False)
    connection.close()
    return path


@pytest.fixture
def csv_path(tmp_path, panel):
    path = tmp_path / "prices.csv"
    frame = panel.rename(columns={value: key for key, value in COLUMN_MAP.items()})
    # load_price_data parses with dayfirst=True for the local vendor format.
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%d/%m/%Y")
    frame.to_csv(path, index=False)
    return path


def test_sqlite_source_reports_the_latest_session(sqlite_path):
    source = SQLiteMarketDataSource(sqlite_path, "daily_ohlcv", COLUMN_MAP)
    assert source.latest_date() == pd.Timestamp("2024-02-23")
    source.close()


def test_sqlite_source_returns_new_sessions_plus_the_requested_buffer(sqlite_path):
    source = SQLiteMarketDataSource(sqlite_path, "daily_ohlcv", COLUMN_MAP)
    frame = source.fetch_since(pd.Timestamp("2024-02-19"), lookback_buffer_days=3)
    assert list(frame.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert frame["date"].is_monotonic_increasing
    assert (frame["date"] > pd.Timestamp("2024-02-19")).sum() == 4
    assert (frame["date"] <= pd.Timestamp("2024-02-19")).sum() == 3
    source.close()


def test_sqlite_source_returns_everything_when_no_watermark_is_given(sqlite_path):
    source = SQLiteMarketDataSource(sqlite_path, "daily_ohlcv", COLUMN_MAP)
    assert len(source.fetch_since(None, None)) == 40
    source.close()


def test_sqlite_source_refuses_to_write_to_the_source_database(sqlite_path):
    source = SQLiteMarketDataSource(sqlite_path, "daily_ohlcv", COLUMN_MAP)
    with pytest.raises(ReadOnlyViolation):
        source.execute_for_test("DELETE FROM daily_ohlcv")
    source.close()
    # Closed explicitly: a connection left to the garbage collector is finalised
    # after pytest has already removed tmp_path, and the failure then surfaces as
    # an unraisable exception inside whichever unrelated test happens to be
    # running at the time.
    verifier = sqlite3.connect(sqlite_path)
    try:
        assert len(pd.read_sql("SELECT * FROM daily_ohlcv", verifier)) == 40
    finally:
        verifier.close()


def test_sqlite_source_decodes_integer_epoch_day_dates(tmp_path, panel):
    path = tmp_path / "epoch.sqlite"
    encoded = panel.copy()
    encoded["trading_date"] = (pd.to_datetime(encoded["trading_date"]) - pd.Timestamp("1970-01-01")).dt.days
    connection = sqlite3.connect(path)
    encoded.to_sql("daily_ohlcv", connection, index=False)
    connection.close()
    source = SQLiteMarketDataSource(path, "daily_ohlcv", COLUMN_MAP, date_unit="D")
    assert source.latest_date() == pd.Timestamp("2024-02-23")
    source.close()


def test_duckdb_source_reads_the_same_panel_read_only(tmp_path, panel):
    duckdb = pytest.importorskip("duckdb")
    path = tmp_path / "market.duckdb"
    connection = duckdb.connect(str(path))
    connection.register("staging", panel)
    connection.execute("CREATE TABLE daily_ohlcv AS SELECT * FROM staging")
    connection.close()
    source = DuckDBMarketDataSource(path, "daily_ohlcv", COLUMN_MAP)
    assert source.latest_date() == pd.Timestamp("2024-02-23")
    assert len(source.fetch_since(pd.Timestamp("2024-02-19"), 3)) == 7
    with pytest.raises(ReadOnlyViolation):
        source.execute_for_test("DELETE FROM daily_ohlcv")
    source.close()


def test_csv_source_reuses_the_defensive_loader(csv_path):
    source = CsvMarketDataSource(csv_path)
    assert source.latest_date() == pd.Timestamp("2024-02-23")
    frame = source.fetch_since(pd.Timestamp("2024-02-19"), 3)
    assert len(frame) == 7
    assert frame["close"].iloc[-1] == pytest.approx(139.0)


def test_factory_dispatches_on_the_configured_backend(sqlite_path, csv_path):
    sqlite_source = build_market_data_source(
        {"backend": "sqlite", "path": str(sqlite_path), "table": "daily_ohlcv", "column_map": COLUMN_MAP}
    )
    assert isinstance(sqlite_source, SQLiteMarketDataSource)
    sqlite_source.close()
    assert isinstance(build_market_data_source({"backend": "csv", "path": str(csv_path)}), CsvMarketDataSource)


def test_factory_rejects_an_unknown_backend():
    """`postgres` used to be the example here; it is implemented now, so this
    has to name a backend that genuinely does not exist or it would pass for the
    wrong reason."""
    with pytest.raises(ValueError, match="chưa hỗ trợ"):
        build_market_data_source({"backend": "mysql", "path": "x"})
