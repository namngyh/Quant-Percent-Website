"""Tests for the live database source and the volume parsing it exposed.

Comparing the database against the CSV is what found the volume bug: the two
agreed to the last decimal on every price and disagreed on 3879 of 6264 volume
figures, in ratios of exactly 10, 100 and 1000. That is not a data difference,
it is a parser dropping stripped leading zeros.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from raemf_mc.data.ingest import parse_vnindex_csv
from raemf_mc.data.source import (
    clean_ohlcv_frame,
    find_env_file,
    load_env_file,
    parse_env_file,
    resolve_dsn,
)

DSN_ENV = "RAEMF_MARKET_DSN"
REAL_DATA = Path(__file__).resolve().parents[2] / "data" / "raw" / "VNINDEX_Daily.csv"

HEADER = "Date,Open,High,Low,Close,Volume,,,,,,,\n"


# ---------------------------------------------------------------------------
# The volume bug
# ---------------------------------------------------------------------------
def test_volume_restores_leading_zeros_stripped_from_thousands_groups(tmp_path):
    """Real raw line for 3/7/2026: volume 538,080,668 is exported as
    ("538", "80", "640") -- the middle group lost its leading zero. Plain
    concatenation gives 53_880_640, a tenth of the truth and still a perfectly
    plausible VN-Index turnover, so no downstream check would ever flag it."""
    path = tmp_path / "stripped.csv"
    path.write_text(
        HEADER + "3/7/2026 00:00,1,867.17,1,872.98,1,857.28,1,862.08,538,80,640,\n",
        encoding="utf-8",
    )
    assert parse_vnindex_csv(path).iloc[0]["volume"] == 538_080_640


def test_volume_with_intact_groups_is_unchanged(tmp_path):
    """The padding must be a no-op when nothing was stripped."""
    path = tmp_path / "intact.csv"
    path.write_text(
        HEADER + "13/7/2026 00:00,1,829.5,1,829.5,1,781.45,1,800.54,728,451,840,\n",
        encoding="utf-8",
    )
    assert parse_vnindex_csv(path).iloc[0]["volume"] == 728_451_840


def test_a_single_group_volume_is_unchanged(tmp_path):
    path = tmp_path / "single.csv"
    path.write_text(
        HEADER + "28/7/2000 00:00,100,100,100,100,4200,,,,,,,\n", encoding="utf-8"
    )
    assert parse_vnindex_csv(path).iloc[0]["volume"] == 4200


def test_trailing_group_zeros_are_restored(tmp_path):
    """1,024,000 exported as ("1", "24", "0") must not become 1240."""
    path = tmp_path / "trailing.csv"
    path.write_text(
        HEADER + "19/1/2007 00:00,1,24,1,24,1,22.97,1,23.05,1,24,0,\n", encoding="utf-8"
    )
    assert parse_vnindex_csv(path).iloc[0]["volume"] == 1_024_000


# ---------------------------------------------------------------------------
# Validation reuse
# ---------------------------------------------------------------------------
def test_clean_ohlcv_frame_applies_the_same_invariants_as_the_csv_path():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]),
            "open": [100.0, 100.0, 100.0],
            "high": [101.0, 101.0, 101.0],
            # The middle row violates low <= close.
            "low": [99.0, 100.5, 99.0],
            "close": [100.5, 100.0, 100.5],
            "volume": [10, 20, 30],
        }
    )
    # A generous max_drop_fraction: this test is about *which* row is rejected
    # and why, not about the fraction guard, which has its own test below.
    clean, dropped, total = clean_ohlcv_frame(frame, max_drop_fraction=0.9)
    assert total == 3
    assert len(clean) == 2
    assert [row.reason for row in dropped] == ["ohlc_invariant_violation"]


def test_clean_ohlcv_frame_numbers_rows_for_the_dropped_report():
    """`DroppedRow` records where a rejected row came from; a query has no file
    line, so the row's position in the ordered result set stands in."""
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
            "open": [100.0, 100.0],
            "high": [101.0, 101.0],
            "low": [99.0, 100.5],
            "close": [100.5, 100.0],
            "volume": [10, 20],
        }
    )
    _clean, dropped, _total = clean_ohlcv_frame(frame, max_drop_fraction=0.9)
    assert dropped[0].line_number == 2


def test_clean_ohlcv_frame_refuses_to_drop_too_much():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
            "open": [100.0, 100.0],
            "high": [101.0, 101.0],
            "low": [100.5, 100.5],
            "close": [100.0, 100.0],
            "volume": [10, 20],
        }
    )
    with pytest.raises(ValueError, match="dropped fraction"):
        clean_ohlcv_frame(frame)


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
def test_resolve_dsn_prefers_an_explicit_argument():
    assert resolve_dsn("postgresql://u@h/db") == "postgresql://u@h/db"


def test_resolve_dsn_reads_the_environment(monkeypatch):
    monkeypatch.setenv("SOME_DSN", "postgresql://u@h/db")
    assert resolve_dsn(None, "SOME_DSN") == "postgresql://u@h/db"


def test_resolve_dsn_reports_the_missing_variable(monkeypatch, tmp_path):
    monkeypatch.delenv("ABSENT_DSN", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="ABSENT_DSN"):
        resolve_dsn(None, "ABSENT_DSN")


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
# Live server
# ---------------------------------------------------------------------------
def _live_frame():
    pytest.importorskip("psycopg")
    import psycopg

    from raemf_mc.data.source import load_vnindex_from_database

    load_env_file()
    if not os.environ.get(DSN_ENV, "").strip():
        pytest.skip(f"{DSN_ENV} chua duoc dat - bo qua test can database that")
    try:
        return load_vnindex_from_database()
    except psycopg.OperationalError as error:
        pytest.skip(f"Khong ket noi duoc database: {error}")


def test_live_source_returns_the_same_shape_as_the_csv_loader():
    frame, _dropped, _total = _live_frame()
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.index.name == "date"
    assert frame.index.is_monotonic_increasing
    assert frame.index.is_unique
    assert len(frame) > 6000


def test_live_source_agrees_with_the_csv_on_every_overlapping_price():
    """The CSV is the series the published fits were estimated on. If the
    database disagreed on prices, swapping the source would silently change the
    model rather than merely extend it."""
    from raemf_mc.data.loader import load_vnindex_ohlcv

    database, _dropped, _total = _live_frame()
    csv = load_vnindex_ohlcv(REAL_DATA)
    joined = csv.join(database, how="inner", lsuffix="_csv", rsuffix="_db")
    assert len(joined) > 6000
    for column in ("open", "high", "low", "close"):
        difference = (joined[f"{column}_csv"] - joined[f"{column}_db"]).abs()
        assert difference.max() == 0.0, column


def test_live_source_volume_matches_the_repaired_parser_to_float32():
    """The CSV stores volume as float32 somewhere upstream, so exact equality is
    unreachable; anything beyond float32 epsilon would be a parsing difference
    rather than a rounding one."""
    from raemf_mc.data.loader import load_vnindex_ohlcv

    database, _dropped, _total = _live_frame()
    csv = load_vnindex_ohlcv(REAL_DATA)
    joined = csv.join(database, how="inner", lsuffix="_csv", rsuffix="_db")
    relative = (joined["volume_csv"] - joined["volume_db"]).abs() / joined["volume_db"].abs()
    assert relative.max() < 1e-5


def test_live_source_extends_beyond_the_csv():
    from raemf_mc.data.loader import load_vnindex_ohlcv

    database, _dropped, _total = _live_frame()
    csv = load_vnindex_ohlcv(REAL_DATA)
    assert database.index.max() > csv.index.max()


def test_live_source_refuses_to_write():
    pytest.importorskip("psycopg")
    import psycopg

    from raemf_mc.data.source import PostgresOHLCVSource

    load_env_file()
    dsn = os.environ.get(DSN_ENV, "").strip()
    if not dsn:
        pytest.skip(f"{DSN_ENV} chua duoc dat")
    try:
        source = PostgresOHLCVSource(dsn, connect_timeout=5)
    except psycopg.OperationalError as error:
        pytest.skip(f"Khong ket noi duoc database: {error}")
    try:
        with pytest.raises(PermissionError):
            source.execute_for_test("CREATE TABLE raemf_readonly_probe (x integer)")
    finally:
        source.close()


def test_live_source_rejects_an_unknown_symbol():
    pytest.importorskip("psycopg")
    import psycopg

    from raemf_mc.data.source import PostgresOHLCVSource

    load_env_file()
    dsn = os.environ.get(DSN_ENV, "").strip()
    if not dsn:
        pytest.skip(f"{DSN_ENV} chua duoc dat")
    try:
        source = PostgresOHLCVSource(dsn, symbol="__NO_SUCH_SYMBOL__", connect_timeout=5)
    except psycopg.OperationalError as error:
        pytest.skip(f"Khong ket noi duoc database: {error}")
    try:
        with pytest.raises(ValueError, match="khong co phien nao"):
            source.read_raw()
    finally:
        source.close()
