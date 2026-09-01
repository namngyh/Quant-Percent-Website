"""Tests for the PostgreSQL/TimescaleDB connector.

The corporate-action tests are the important ones. `bars_1d.adj_rate` is a
cumulative *divisor* whose latest value is 1, the opposite convention to the
DataPro SQLite `ADJUST_RATE`, and inverting it is silent: prices stay plausible
and only the returns across corporate actions are wrong. So the direction is
asserted against the vendor's own reference price rather than against a fixture
that would simply encode whichever convention the connector happens to use.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.config import load_config
from dynamicgraph.constants import DATA_CONTRACT_COLUMNS
from dynamicgraph.data.connectors import (
    PostgresConnector,
    ReadOnlyViolation,
    build_connector,
    is_postgres_url,
    normalise_postgres_dsn,
)
from dynamicgraph.dotenv import find_env_file, load_env_file, parse_env_file

DSN_ENV = "DYNAMICGRAPH_DATABASE_URL"


# ---------------------------------------------------------------------------
# URL handling
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@h:5432/db",
        "postgres://u:p@h/db",
        "postgresql+psycopg://u:p@h/db",
        "timescaledb://u:p@h/db",
    ],
)
def test_postgres_urls_are_recognised(url):
    assert is_postgres_url(url)


@pytest.mark.parametrize(
    "value",
    ["C:/DataPro/D.dat", "sqlite:////tmp/x.db", "duckdb:///x.duckdb", "", None],
)
def test_non_postgres_values_are_not_recognised(value):
    assert not is_postgres_url(value)


def test_sqlalchemy_driver_suffix_is_stripped():
    """`.env.example` documents `postgresql+psycopg://`, which psycopg rejects."""
    assert normalise_postgres_dsn("postgresql+psycopg://u:p@h/db") == "postgresql://u:p@h/db"


def test_timescaledb_scheme_is_aliased_to_postgresql():
    assert normalise_postgres_dsn("timescaledb://u:p@h/db") == "postgresql://u:p@h/db"


def test_a_plain_path_is_left_alone():
    assert normalise_postgres_dsn("C:/DataPro/D.dat") == "C:/DataPro/D.dat"


def test_backend_postgres_without_a_url_is_an_error():
    """Falling through to the file branch would report `file not found`, which
    sends the reader looking for a missing file instead of a missing DSN."""
    config = load_config("config/default.yaml")
    config.data.backend = "postgres"
    config.data.database_path = "C:/DataPro/D.dat"
    with pytest.raises(ValueError, match="not a Postgres URL"):
        build_connector(config)


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------
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


def test_missing_dotenv_is_not_an_error(tmp_path):
    assert load_env_file(tmp_path) == {}


# ---------------------------------------------------------------------------
# Live server
# ---------------------------------------------------------------------------
def _connect(**kwargs) -> PostgresConnector:
    psycopg = pytest.importorskip("psycopg")
    load_env_file()
    dsn = os.environ.get(DSN_ENV, "").strip()
    if not dsn or not is_postgres_url(dsn):
        pytest.skip(f"{DSN_ENV} is not a Postgres URL - skipping live database tests")
    try:
        return PostgresConnector(dsn, connect_timeout=5, **kwargs)
    except psycopg.OperationalError as error:
        pytest.skip(f"Database unreachable: {error}")


@pytest.fixture
def live():
    connector = _connect()
    try:
        yield connector
    finally:
        connector.close()


def test_live_connector_returns_the_data_contract(live):
    frame = live.load(tickers=["FPT", "VCB"], start="2024-01-01")
    for column in DATA_CONTRACT_COLUMNS:
        assert column in frame.columns
    assert set(frame["ticker"]) == {"FPT", "VCB"}
    assert frame["date"].min() >= pd.Timestamp("2024-01-01")
    assert frame.groupby("ticker")["date"].is_monotonic_increasing.all()


def test_live_connector_filters_by_ticker_and_date(live):
    frame = live.load(tickers=["FPT"], start="2025-01-01", end="2025-06-30")
    assert set(frame["ticker"]) == {"FPT"}
    assert frame["date"].min() >= pd.Timestamp("2025-01-01")
    assert frame["date"].max() <= pd.Timestamp("2025-06-30")


def test_live_connector_detects_the_vn30_index(live):
    assert live.detect_index_symbol("VN30INDEX") == "VN30INDEX"


def test_live_connector_lists_symbols_with_the_index_flagged(live):
    symbols = live.list_symbols()
    assert len(symbols) > 30
    assert symbols.loc[symbols["ticker"] == "VN30INDEX", "is_index"].all()
    assert not symbols.loc[symbols["ticker"] == "FPT", "is_index"].any()


def test_live_connector_redacts_the_password_from_metadata(live):
    """`metadata.path` reaches the data-audit report and the reproducibility
    record, so it must never carry the credential."""
    assert "***" in live.metadata.path
    assert "@" in live.metadata.path
    dsn = os.environ[DSN_ENV]
    password = dsn.partition("://")[2].partition(":")[2].partition("@")[0]
    assert password
    assert password not in live.metadata.path


def test_live_connector_refuses_to_write(live):
    with pytest.raises(ReadOnlyViolation):
        live.execute_for_test("CREATE TABLE dynamicgraph_readonly_probe (x integer)")


def test_live_connector_reports_an_unknown_table(live):
    """Fail at construction, not at the first query: the table name is a config
    mistake and should be reported before any pipeline stage has run."""
    with pytest.raises(ValueError, match="does not exist"):
        _connect(table="no_such_table_here")


def test_adjustment_divides_rather_than_multiplies(live):
    """The identity that fixes the direction.

    `adj_rate` changes exactly at corporate actions. Across such a boundary the
    vendor's reference price already carries the adjustment, so

        (ref_px(t) / close(t-1)) * (adj_rate(t-1) / adj_rate(t)) == 1

    holds only for the divisor convention. Under the multiplicative convention
    the same expression is off by roughly 9%.
    """
    frame = live.load(tickers=["ACB"], start="2015-01-01").sort_values("date")
    rate = 1.0 / frame["adjustment_factor"].to_numpy(dtype=float)
    reference = frame["reference_price"].to_numpy(dtype=float)
    close = frame["close"].to_numpy(dtype=float)

    changed = np.flatnonzero(np.abs(rate[:-1] / rate[1:] - 1.0) > 1e-4) + 1
    assert len(changed) >= 8, "expected several corporate actions for ACB since 2015"

    identity = (reference[changed] / close[changed - 1]) * (rate[changed - 1] / rate[changed])
    assert np.abs(identity - 1.0).max() < 1e-3

    inverted = (reference[changed] / close[changed - 1]) * (rate[changed] / rate[changed - 1])
    assert np.abs(inverted - 1.0).max() > 0.05, "the wrong convention must not also pass"


def test_adjusted_close_removes_the_corporate_action_jump(live):
    """The point of adjusting: no |daily log return| above HOSE's 7% band plus a
    margin, once the split-adjusted series is used."""
    frame = live.load(tickers=["ACB"], start="2015-01-01").sort_values("date")
    raw = np.diff(np.log(frame["close"].to_numpy(dtype=float)))
    adjusted = np.diff(np.log(frame["adjusted_close"].to_numpy(dtype=float)))
    assert np.abs(raw).max() > 0.15, "ACB should show unadjusted corporate-action jumps"
    assert np.abs(adjusted).max() < 0.15


def test_index_series_has_a_flat_adjustment(live):
    """An index has no corporate actions; a factor other than 1 would mean the
    connector is applying a stock adjustment to it."""
    frame = live.load(tickers=["VN30INDEX"], start="2024-01-01")
    assert np.allclose(frame["adjustment_factor"].to_numpy(dtype=float), 1.0)
    assert np.allclose(
        frame["adjusted_close"].to_numpy(dtype=float),
        frame["close"].to_numpy(dtype=float),
    )


def test_empty_selection_is_an_error_not_an_empty_frame(live):
    with pytest.raises(ValueError, match="no rows"):
        live.load(tickers=["__NO_SUCH_TICKER__"])
