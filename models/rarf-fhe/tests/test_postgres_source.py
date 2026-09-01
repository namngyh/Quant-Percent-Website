"""Tests for the PostgreSQL/TimescaleDB market data source.

Split in two halves on purpose:

* everything that can be proven without a server (config resolution, `.env`
  parsing, factory dispatch) runs everywhere and always;
* the connector itself needs a real database, so those tests are skipped unless
  ``VNINDEX_MARKET_DSN`` resolves and the server answers. A skipped test proves
  nothing, which is why the read-only guarantee is asserted against the live
  server rather than a mock -- a mock would only prove that the mock says no.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

from vnindex_model.data_source import (
    POSTGRES_BACKENDS,
    ReadOnlyViolation,
    build_market_data_source,
    resolve_dsn,
)
from vnindex_model.dotenv import find_env_file, load_env_file, parse_env_file

DSN_ENV = "VNINDEX_MARKET_DSN"

COLUMN_MAP = {
    "date": "trading_date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}


# ---------------------------------------------------------------------------
# Offline: configuration resolution
# ---------------------------------------------------------------------------
def test_resolve_dsn_prefers_the_environment_variable(monkeypatch):
    monkeypatch.setenv("SOME_DSN", "postgresql://user@host/db")
    assert resolve_dsn({"dsn_env": "SOME_DSN"}) == "postgresql://user@host/db"


def test_resolve_dsn_accepts_a_literal_dsn():
    assert resolve_dsn({"dsn": "postgresql://user@host/db"}) == "postgresql://user@host/db"


def test_resolve_dsn_never_falls_back_to_the_csv_path():
    """`data.source.path` defaults to the batch CSV; using it as a DSN would
    connect to the wrong thing instead of failing."""
    with pytest.raises(ValueError, match="dsn_env"):
        resolve_dsn({"path": "data/raw/VNINDEX_Daily.csv"})


def test_resolve_dsn_reports_the_missing_variable_by_name(monkeypatch, tmp_path):
    monkeypatch.delenv("ABSENT_DSN", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="ABSENT_DSN"):
        resolve_dsn({"dsn_env": "ABSENT_DSN"})


def test_resolve_dsn_falls_back_to_a_dotenv_file(monkeypatch, tmp_path):
    """Task Scheduler starts with a bare environment, so `.env` has to work."""
    monkeypatch.delenv("FILE_DSN", raising=False)
    (tmp_path / ".env").write_text("FILE_DSN=postgresql://user@host/db\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert resolve_dsn({"dsn_env": "FILE_DSN"}) == "postgresql://user@host/db"


def test_factory_requires_a_table_for_postgres(monkeypatch):
    monkeypatch.setenv("SOME_DSN", "postgresql://user@host/db")
    with pytest.raises(ValueError, match="table"):
        build_market_data_source({"backend": "postgres", "dsn_env": "SOME_DSN"})


def test_factory_rejects_postgres_without_credentials(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="dsn_env"):
        build_market_data_source({"backend": "postgres", "table": "bars_1d"})


def test_every_postgres_alias_reaches_the_same_branch(monkeypatch, tmp_path):
    """`postgresql` and `timescaledb` must not fall through to the path check."""
    monkeypatch.chdir(tmp_path)
    for backend in POSTGRES_BACKENDS:
        with pytest.raises(ValueError, match="table"):
            build_market_data_source({"backend": backend, "dsn_env": "SOME_DSN"})


def test_unknown_backend_lists_postgres_as_supported():
    with pytest.raises(ValueError, match="postgres"):
        build_market_data_source({"backend": "mysql", "path": "x", "table": "y"})


# ---------------------------------------------------------------------------
# Offline: .env parsing
# ---------------------------------------------------------------------------
def test_dotenv_keeps_special_characters_in_a_password(tmp_path):
    """Passwords contain `#` and `=`; a naive split would truncate them."""
    (tmp_path / ".env").write_text(
        "# comment line\n"
        "\n"
        "export QUOTED='pa#ss=word'\n"
        "PLAIN=postgresql://u:p@h:5432/db\n"
        "NOT_A_PAIR\n",
        encoding="utf-8",
    )
    values = parse_env_file(tmp_path / ".env")
    assert values == {"QUOTED": "pa#ss=word", "PLAIN": "postgresql://u:p@h:5432/db"}


def test_dotenv_does_not_override_the_real_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SHARED", "from-shell")
    (tmp_path / ".env").write_text("SHARED=from-file\n", encoding="utf-8")
    load_env_file(tmp_path)
    assert os.environ["SHARED"] == "from-shell"


def test_dotenv_override_is_opt_in(monkeypatch, tmp_path):
    monkeypatch.setenv("SHARED", "from-shell")
    (tmp_path / ".env").write_text("SHARED=from-file\n", encoding="utf-8")
    load_env_file(tmp_path, override=True)
    assert os.environ["SHARED"] == "from-file"


def test_dotenv_is_found_from_a_subdirectory(tmp_path):
    (tmp_path / ".env").write_text("K=v\n", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_env_file(nested) == tmp_path / ".env"


def test_missing_dotenv_is_not_an_error(tmp_path):
    assert load_env_file(tmp_path) == {}


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


def test_live_source_reports_the_latest_session(live_source):
    latest = live_source.latest_date()
    assert isinstance(latest, pd.Timestamp)
    assert latest > pd.Timestamp("2020-01-01")


def test_live_source_returns_a_sorted_ohlcv_panel(live_source):
    frame = live_source.fetch_since(None, None)
    assert list(frame.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert frame["date"].is_monotonic_increasing
    assert frame["date"].is_unique
    assert len(frame) > 1000
    for column in ["open", "high", "low", "close"]:
        assert frame[column].dtype.kind == "f"
    assert (frame["close"] > 0).all()


def test_live_source_latest_date_matches_the_panel(live_source):
    assert live_source.latest_date() == pd.Timestamp(live_source.fetch_since(None, None)["date"].max())


def test_live_source_honours_the_lookback_buffer(live_source):
    frame = live_source.fetch_since(None, None)
    since = pd.Timestamp(frame["date"].iloc[-10])
    windowed = live_source.fetch_since(since, 50)
    assert (windowed["date"] <= since).sum() == 50
    assert (windowed["date"] > since).sum() == 9


def test_live_source_full_history_matches_the_windowed_read(live_source):
    """`fetch_since(None, None)` and a wide window must agree on the overlap."""
    full = live_source.fetch_since(None, None)
    since = pd.Timestamp(full["date"].iloc[-5])
    windowed = live_source.fetch_since(since, 100)
    overlap = full.tail(len(windowed)).reset_index(drop=True)
    pd.testing.assert_frame_equal(overlap, windowed.reset_index(drop=True))


def test_live_source_refuses_to_write_to_the_source_database(live_source):
    with pytest.raises(ReadOnlyViolation):
        live_source.execute_for_test("CREATE TABLE vnindex_readonly_probe (x integer)")


def test_live_source_isolates_the_requested_symbol(live_source):
    """A VN30 constituent must not leak into the VN-Index panel."""
    index_rows = len(live_source.fetch_since(None, None))
    other = _live_source(symbol="FPT")
    try:
        assert len(other.fetch_since(None, None)) != index_rows
    finally:
        other.close()


def test_live_source_rejects_an_unknown_symbol():
    source = _live_source(symbol="__NO_SUCH_SYMBOL__")
    try:
        with pytest.raises(ValueError, match="không có phiên nào"):
            source.latest_date()
    finally:
        source.close()
