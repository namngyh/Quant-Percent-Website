"""Tests for `sync-source`, the batch tier's snapshot of the live source.

The snapshot exists so `run_metadata` can keep hashing a file while the numbers
come from the database. Two properties matter most and are asserted directly:
re-running the export must be a no-op, and a restated historical value must be
reported rather than absorbed silently -- that is the signal that the online
state has to be rebuilt instead of advanced.
"""

from __future__ import annotations

import sqlite3
import warnings

import pandas as pd
import pytest
import yaml

from vnindex_model.data import load_price_data, parse_dates
from vnindex_model.data_sync import sync_source


# ---------------------------------------------------------------------------
# Date convention detection
# ---------------------------------------------------------------------------
def test_iso_dates_parse_without_a_warning():
    """A database export is ISO; `dayfirst=True` on ISO input makes pandas warn,
    and this repository treats warnings as failures."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        parsed = parse_dates(pd.Series(["2026-07-13", "2000-07-28"]))
    assert not caught
    assert parsed.tolist() == [pd.Timestamp("2026-07-13"), pd.Timestamp("2000-07-28")]


def test_vendor_day_first_dates_still_parse():
    """`13/7/2026` is day-first; reading it as month-first would be a silent
    corruption, not an error."""
    parsed = parse_dates(pd.Series(["13/7/2026", "28/7/2000"]))
    assert parsed.tolist() == [pd.Timestamp("2026-07-13"), pd.Timestamp("2000-07-28")]


def test_already_parsed_dates_pass_through():
    values = pd.Series(pd.to_datetime(["2026-07-13", "2026-07-14"]))
    assert parse_dates(values).tolist() == values.tolist()


def test_empty_dates_do_not_crash_detection():
    assert parse_dates(pd.Series([], dtype=object)).empty


def test_both_repository_fixtures_load_without_warnings(tmp_path):
    iso = tmp_path / "iso.csv"
    iso.write_text("Date,Open,High,Low,Close,Volume\n2026-08-25,1,2,0.5,1.5,10\n", encoding="utf-8")
    vendor = tmp_path / "vendor.csv"
    vendor.write_text("Date,Open,High,Low,Close,Volume\n25/8/2026,1,2,0.5,1.5,10\n", encoding="utf-8")
    for path in (iso, vendor):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            frame = load_price_data(path)[0]
        assert not caught, f"{path.name}: {[str(w.message) for w in caught]}"
        assert frame["date"].iloc[0] == pd.Timestamp("2026-08-25")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def _panel(rows: int = 40, close_offset: float = 0.0) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=rows)
    return pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "open": [100.0 + i for i in range(rows)],
            "high": [101.0 + i for i in range(rows)],
            "low": [99.0 + i for i in range(rows)],
            "close": [100.5 + i + close_offset for i in range(rows)],
            "volume": [1000 + i for i in range(rows)],
        }
    )


def _sqlite_source(path, frame: pd.DataFrame) -> None:
    connection = sqlite3.connect(path)
    frame.to_sql("daily_ohlcv", connection, index=False, if_exists="replace")
    connection.commit()
    connection.close()


@pytest.fixture
def workspace(tmp_path):
    """A minimal repo layout: a SQLite source plus a config pointing at it."""
    database = tmp_path / "market.sqlite"
    _sqlite_source(database, _panel())
    config = {
        "project": {"data_path": "data/raw/snapshot.csv"},
        "data": {
            "source": {
                "backend": "sqlite",
                "path": str(database),
                "table": "daily_ohlcv",
                "column_map": {},
            }
        },
        "hmm": {},
        "random_forest": {},
        "simulation": {},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return tmp_path, config_path, database


def test_sync_writes_a_snapshot_the_batch_loader_can_read(workspace):
    root, config_path, _ = workspace
    result = sync_source(config_path, root=root)
    assert result["status"] == "synced"
    assert result["rows"] == 40
    frame = load_price_data(root / "data/raw/snapshot.csv")[0]
    assert len(frame) == 40
    assert list(frame.columns[:6]) == ["date", "open", "high", "low", "close", "volume"]


def test_sync_is_idempotent(workspace):
    root, config_path, _ = workspace
    sync_source(config_path, root=root)
    second = sync_source(config_path, root=root)
    assert second["rows_added"] == 0
    assert second["history_rewritten"] is False


def test_sync_counts_only_the_genuinely_new_sessions(workspace):
    root, config_path, database = workspace
    sync_source(config_path, root=root)
    _sqlite_source(database, _panel(rows=45))
    result = sync_source(config_path, root=root)
    assert result["rows_added"] == 5
    assert result["history_rewritten"] is False


def test_sync_reports_restated_history(workspace):
    """A changed value on an existing date invalidates the online state, so it
    must surface in the result rather than being absorbed by the overwrite."""
    root, config_path, database = workspace
    sync_source(config_path, root=root)
    _sqlite_source(database, _panel(close_offset=0.25))
    result = sync_source(config_path, root=root)
    assert result["history_rewritten"] is True
    assert result["rewritten_count"] == 40
    assert result["rows_added"] == 0


def test_sync_refuses_to_write_an_empty_file(workspace):
    root, config_path, database = workspace
    _sqlite_source(database, _panel().iloc[0:0])
    with pytest.raises(ValueError, match="không trả về phiên nào"):
        sync_source(config_path, root=root)


def test_sync_refuses_to_overwrite_its_own_source(tmp_path):
    """With a CSV backend pointed at the destination, the export would consume
    the file it is writing."""
    (tmp_path / "data" / "raw").mkdir(parents=True)
    origin = tmp_path / "data" / "raw" / "snapshot.csv"
    origin.write_text("Date,Close\n2026-01-02,100\n", encoding="utf-8")
    config = {
        "project": {"data_path": "data/raw/snapshot.csv"},
        "data": {"source": {"backend": "csv", "path": "data/raw/snapshot.csv"}},
        "hmm": {},
        "random_forest": {},
        "simulation": {},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="ghi đè chính nó"):
        sync_source(config_path, root=tmp_path)


def test_sync_rejects_an_unsupported_destination_format(workspace):
    root, config_path, _ = workspace
    with pytest.raises(ValueError, match="chưa hỗ trợ"):
        sync_source(config_path, root=root, destination=root / "snapshot.xlsx")


def test_sync_leaves_no_temporary_file_behind(workspace):
    root, config_path, _ = workspace
    sync_source(config_path, root=root)
    assert not list((root / "data" / "raw").glob("*.tmp"))


def test_sync_supports_a_parquet_destination(workspace):
    pytest.importorskip("pyarrow")
    root, config_path, _ = workspace
    target = root / "data" / "raw" / "snapshot.parquet"
    result = sync_source(config_path, root=root, destination=target)
    assert result["rows"] == 40
    assert len(load_price_data(target)[0]) == 40
