"""Tests for the read-only data source and the batch snapshot export.

Split deliberately: configuration resolution, `.env` parsing, date-convention
detection and the export logic all run without a server; the connector itself is
asserted against a real database, because the read-only guarantee is a property
of the connection options and a mock would only prove that the mock says no.
"""
from __future__ import annotations

import os
import sqlite3
import warnings

import pandas as pd
import pytest
import yaml

from msdp.data_io import load_market_data, parse_dates
from msdp.data_source import (
    POSTGRES_BACKENDS,
    ReadOnlyViolation,
    build_market_data_source,
    resolve_dsn,
)
from msdp.data_sync import sync_source
from msdp.dotenv import find_env_file, load_env_file, parse_env_file

DSN_ENV = "MSDP_MARKET_DSN"

COLUMN_MAP = {
    "date": "trading_date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}


# ---------------------------------------------------------------------------
# Configuration resolution
# ---------------------------------------------------------------------------
def test_resolve_dsn_prefers_the_environment_variable(monkeypatch):
    monkeypatch.setenv("SOME_DSN", "postgresql://user@host/db")
    assert resolve_dsn({"dsn_env": "SOME_DSN"}) == "postgresql://user@host/db"


def test_resolve_dsn_never_falls_back_to_the_csv_path():
    """`data.source.path` points at the batch CSV; using it as a DSN would
    connect to the wrong thing instead of failing."""
    with pytest.raises(ValueError, match="dsn_env"):
        resolve_dsn({"path": "data/raw/VNINDEX_Daily.csv"})


def test_resolve_dsn_falls_back_to_a_dotenv_file(monkeypatch, tmp_path):
    monkeypatch.delenv("FILE_DSN", raising=False)
    (tmp_path / ".env").write_text("FILE_DSN=postgresql://user@host/db\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert resolve_dsn({"dsn_env": "FILE_DSN"}) == "postgresql://user@host/db"


def test_every_postgres_alias_reaches_the_same_branch(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for backend in POSTGRES_BACKENDS:
        with pytest.raises(ValueError, match="table"):
            build_market_data_source({"backend": backend, "dsn_env": "SOME_DSN"})


def test_unknown_backend_lists_postgres_as_supported():
    with pytest.raises(ValueError, match="postgres"):
        build_market_data_source({"backend": "mysql", "path": "x", "table": "y"})


def test_dotenv_keeps_special_characters_in_a_password(tmp_path):
    (tmp_path / ".env").write_text(
        "# comment\n\nexport QUOTED='pa#ss=word'\nPLAIN=postgresql://u:p@h/db\nNOPAIR\n",
        encoding="utf-8",
    )
    assert parse_env_file(tmp_path / ".env") == {
        "QUOTED": "pa#ss=word",
        "PLAIN": "postgresql://u:p@h/db",
    }


def test_dotenv_does_not_override_the_real_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SHARED", "from-shell")
    (tmp_path / ".env").write_text("SHARED=from-file\n", encoding="utf-8")
    load_env_file(tmp_path)
    assert os.environ["SHARED"] == "from-shell"


def test_dotenv_is_found_from_a_subdirectory(tmp_path):
    (tmp_path / ".env").write_text("K=v\n", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_env_file(nested) == tmp_path / ".env"


# ---------------------------------------------------------------------------
# Date convention
# ---------------------------------------------------------------------------
def test_iso_dates_parse_without_a_warning():
    """A database export is ISO; `dayfirst=True` on ISO input makes pandas warn."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        parsed = parse_dates(pd.Series(["2026-07-13", "2000-07-28"]))
    assert not caught
    assert parsed.tolist() == [pd.Timestamp("2026-07-13"), pd.Timestamp("2000-07-28")]


def test_vendor_day_first_dates_still_parse():
    """`13/7/2026` is day-first; month-first would be silent corruption."""
    parsed = parse_dates(pd.Series(["13/7/2026", "28/7/2000"]))
    assert parsed.tolist() == [pd.Timestamp("2026-07-13"), pd.Timestamp("2000-07-28")]


def test_empty_dates_do_not_crash_detection():
    assert parse_dates(pd.Series([], dtype=object)).empty


# ---------------------------------------------------------------------------
# Snapshot export
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


def _write_sqlite(path, frame: pd.DataFrame) -> None:
    connection = sqlite3.connect(path)
    try:
        frame.to_sql("daily_ohlcv", connection, index=False, if_exists="replace")
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def workspace(tmp_path):
    database = tmp_path / "market.sqlite"
    _write_sqlite(database, _panel())
    config = {
        "data": {
            "path": "data/raw/snapshot.csv",
            "source": {
                "backend": "sqlite",
                "path": str(database),
                "table": "daily_ohlcv",
                "column_map": {},
            },
        }
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return tmp_path, config_path, database


def test_sync_writes_a_snapshot_the_loader_can_read(workspace):
    root, config_path, _ = workspace
    result = sync_source(config_path, root=root)
    assert result["rows"] == 40
    frame = load_market_data(root / "data/raw/snapshot.csv")
    assert len(frame) == 40
    assert frame["close"].is_monotonic_increasing


def test_sync_is_idempotent(workspace):
    root, config_path, _ = workspace
    sync_source(config_path, root=root)
    second = sync_source(config_path, root=root)
    assert second["rows_added"] == 0
    assert second["history_rewritten"] is False


def test_sync_counts_only_the_genuinely_new_sessions(workspace):
    root, config_path, database = workspace
    sync_source(config_path, root=root)
    _write_sqlite(database, _panel(rows=45))
    assert sync_source(config_path, root=root)["rows_added"] == 5


def test_sync_reports_restated_history(workspace):
    """A changed value on an existing date invalidates the online state, so it
    must surface rather than be absorbed by the overwrite."""
    root, config_path, database = workspace
    sync_source(config_path, root=root)
    _write_sqlite(database, _panel(close_offset=0.25))
    result = sync_source(config_path, root=root)
    assert result["history_rewritten"] is True
    assert result["rewritten_count"] == 40


def test_sync_refuses_to_write_an_empty_file(workspace):
    root, config_path, database = workspace
    _write_sqlite(database, _panel().iloc[0:0])
    with pytest.raises(ValueError, match="không trả về phiên nào"):
        sync_source(config_path, root=root)


def test_sync_refuses_to_overwrite_its_own_source(tmp_path):
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "data" / "raw" / "snapshot.csv").write_text(
        "Date,Close\n2026-01-02,100\n", encoding="utf-8"
    )
    config = {
        "data": {
            "path": "data/raw/snapshot.csv",
            "source": {"backend": "csv", "path": "data/raw/snapshot.csv"},
        }
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="ghi đè chính nó"):
        sync_source(config_path, root=tmp_path)


def test_sync_leaves_no_temporary_file_behind(workspace):
    root, config_path, _ = workspace
    sync_source(config_path, root=root)
    assert not list((root / "data" / "raw").glob("*.tmp"))


# ---------------------------------------------------------------------------
# Live server
# ---------------------------------------------------------------------------
def _live_source(**overrides):
    psycopg = pytest.importorskip("psycopg")
    load_env_file()
    dsn = os.environ.get(DSN_ENV, "").strip()
    if not dsn:
        pytest.skip(f"{DSN_ENV} chưa được đặt — bỏ qua test cần database thật")
    settings = {
        "backend": "postgres",
        "dsn": dsn,
        "table": "bars_1d",
        "symbol": "VNINDEX",
        "column_map": COLUMN_MAP,
        "connect_timeout": 5,
        **overrides,
    }
    try:
        return build_market_data_source(settings)
    except psycopg.OperationalError as error:
        pytest.skip(f"Không kết nối được database: {error}")


@pytest.fixture
def live_source():
    source = _live_source()
    try:
        yield source
    finally:
        source.close()


def test_live_source_returns_a_sorted_unique_panel(live_source):
    frame = live_source.fetch_since(None, None)
    assert list(frame.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert frame["date"].is_monotonic_increasing
    assert frame["date"].is_unique
    assert len(frame) > 1000
    assert (frame["close"] > 0).all()


def test_live_source_latest_date_matches_the_panel(live_source):
    assert live_source.latest_date() == pd.Timestamp(
        live_source.fetch_since(None, None)["date"].max()
    )


def test_live_source_honours_the_lookback_buffer(live_source):
    frame = live_source.fetch_since(None, None)
    since = pd.Timestamp(frame["date"].iloc[-10])
    windowed = live_source.fetch_since(since, 50)
    assert (windowed["date"] <= since).sum() == 50
    assert (windowed["date"] > since).sum() == 9


def test_live_source_refuses_to_write_to_the_source_database(live_source):
    with pytest.raises(ReadOnlyViolation):
        live_source.execute_for_test("CREATE TABLE msdp_readonly_probe (x integer)")


def test_live_source_rejects_an_unknown_symbol():
    source = _live_source(symbol="__NO_SUCH_SYMBOL__")
    try:
        with pytest.raises(ValueError, match="không có phiên nào"):
            source.latest_date()
    finally:
        source.close()
