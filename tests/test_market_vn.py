"""Checks for the Vietnam market source.

Run directly:  .venv\\Scripts\\python.exe tests/test_market_vn.py

Routing and frame shaping are tested without a network, so these run whether or
not the VPN is up. The live checks at the end are skipped — reported, not
failed — when the database is unreachable, since being off the VPN is a normal
state for this machine and not a broken build.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from backend.data import market_vn, sources  # noqa: E402

CHECKS = []
LIVE_CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def live(name):
    def wrap(fn):
        LIVE_CHECKS.append((name, fn))
        return fn
    return wrap


# ------------------------------------------------------------ routing (offline)

@check("a VN: prefix routes to the Vietnam market, anything else to crypto")
def _():
    assert sources.parse("VN:VN30F1M") == ("vn", "VN30F1M")
    assert sources.parse("vn:vnindex") == ("vn", "VNINDEX")
    assert sources.parse("BTCUSDT") == ("crypto", "BTCUSDT")
    assert sources.is_vietnam("VN:VIC") and not sources.is_vietnam("BTCUSDT")


@check("qualify and parse round-trip")
def _():
    assert sources.qualify("vn", "VIC") == "VN:VIC"
    assert sources.qualify("crypto", "BTCUSDT") == "BTCUSDT"
    assert sources.parse(sources.qualify("vn", "VIC")) == ("vn", "VIC")


@check("backfill is refused for Vietnam symbols, but live data is not")
def _():
    # The team database is read-only, so there is nothing for us to backfill.
    assert sources.supports_backfill("BTCUSDT")
    assert not sources.supports_backfill("VN:VNINDEX")

    # Both markets do go live, by different means: Binance pushes over a
    # socket, the HOSE database is polled.
    assert sources.supports_live_stream("BTCUSDT")
    assert sources.supports_live_stream("VN:VNINDEX")
    assert sources.live_mode("BTCUSDT") == "push"
    assert sources.live_mode("VN:VNINDEX") == "poll"


@check("each market advertises its own timeframes")
def _():
    vn = sources.timeframes_for("VN:VN30F1M")
    assert "1d" in vn and "1m" in vn and "30m" in vn, vn
    crypto = sources.timeframes_for("BTCUSDT")
    assert "1h" in crypto, crypto


@check("an unsupported timeframe is refused before any query runs")
def _():
    try:
        market_vn.get_candles("VNINDEX", "3d")
    except market_vn.MarketUnavailable as exc:
        assert "không có cho thị trường VN" in str(exc), exc
    else:
        raise AssertionError("expected a timeframe check")


@check("daily bars are keyed at UTC midnight of the trading date")
def _():
    ms = market_vn._to_ms(date(2026, 9, 4))
    when = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    assert (when.year, when.month, when.day) == (2026, 9, 4), when
    assert (when.hour, when.minute) == (0, 0), when


@check("a naive timestamp is read as UTC, not as local time")
def _():
    # ts is documented as UTC; treating a naive value as local would shift the
    # whole session by seven hours and quietly corrupt every intraday chart.
    naive = market_vn._to_ms(datetime(2026, 9, 4, 7, 11))
    aware = market_vn._to_ms(datetime(2026, 9, 4, 7, 11, tzinfo=timezone.utc))
    assert naive == aware, (naive, aware)


@check("an empty result still has the right columns and dtypes")
def _():
    frame = market_vn._frame([])
    assert list(frame.columns) == ["open_time", "open", "high", "low", "close", "volume"]
    assert frame.empty
    assert frame["open_time"].dtype == "int64", frame.dtypes


@check("rows become the same OHLCV frame the DuckDB store returns")
def _():
    rows = [
        (datetime(2026, 9, 4, 7, 11, tzinfo=timezone.utc), 1979.9, 1980.5, 1978.8, 1980.4, 933),
        (datetime(2026, 9, 4, 7, 12, tzinfo=timezone.utc), 1980.3, 1982.7, 1979.4, 1982.0, 2119),
    ]
    frame = market_vn._frame(rows)
    assert len(frame) == 2
    assert frame["open_time"].iloc[0] == 1788505860000, frame["open_time"].iloc[0]
    assert frame["close"].iloc[1] == 1982.0
    assert frame["volume"].dtype == "float64"
    # Same shape as the crypto store, so nothing downstream can tell them apart.
    assert list(frame.columns) == ["open_time", "open", "high", "low", "close", "volume"]


@check("a null volume becomes zero rather than NaN")
def _():
    rows = [(datetime(2026, 9, 4, tzinfo=timezone.utc), 1.0, 2.0, 0.5, 1.5, None)]
    assert market_vn._frame(rows)["volume"].iloc[0] == 0.0


@check("every instrument family is classified, and gold is not filed as FX")
def _():
    cases = {
        # Equities: exactly three letters/digits.
        "VIC": "equity", "ITA": "equity", "SD9": "equity", "S99": "equity",
        # The international feed. G-XAUUSD and G-EURUSD both end in USD, which
        # is exactly why the split is a table and not a regex.
        "G-GOLD": "commodity", "G-XAUUSD": "commodity", "G-XAGUSD": "commodity",
        "G-OIL": "commodity", "G-COFFEE": "commodity",
        "G-BTCUSD": "crypto", "G-ETHUSD": "crypto",
        # A stablecoin pair, which reads like FX and is not.
        "G-USDTUSD": "crypto",
        "G-EURUSD": "fx", "G-USDVND": "fx", "G-USDX": "fx",
        "G-SPX": "index_global", "G-N225": "index_global",
        # Vietnamese families.
        "VNINDEX": "index_vn", "HNXINDEX": "index_vn", "UPCOMINDEX": "index_vn",
        "I1-FIN": "index_sector", "I3-BANK": "index_sector",
        "VN30F1M": "futures_vn", "VN100F2Q": "futures_vn",
        "FUESSV50": "fund", "E1VFVN30": "fund",
        # Recognised, and deliberately not offered.
        "CVNM2609": "warrant", "41I1G8000": "bond",
    }
    for symbol, expected in cases.items():
        assert market_vn.classify(symbol) == expected, (
            symbol, market_vn.classify(symbol), expected)


@check("an unrecognised symbol is refused rather than guessed at")
def _():
    # A new name on the international feed has unknown units; filing it under
    # a class would put a wrong currency next to a real price.
    assert market_vn.classify("G-NEWTHING") is None
    assert market_vn.classify("") is None
    assert market_vn.classify(None) is None


@check("each class states what it is quoted in")
def _():
    # An index level is not money, and gold is not đồng. Anything the picker
    # offers must say which of the three it is.
    for asset_class in market_vn.TRADABLE_CLASSES:
        assert market_vn.CLASS_CURRENCY[asset_class] in ("VND", "USD", "point", "rate")
    assert market_vn.CLASS_CURRENCY["equity"] == "VND"
    assert market_vn.CLASS_CURRENCY["commodity"] == "USD"
    assert market_vn.CLASS_CURRENCY["index_vn"] == "point"
    # Warrants and bonds are not offered, so they carry no unit at all.
    assert "warrant" not in market_vn.TRADABLE_CLASSES
    assert "bond" not in market_vn.TRADABLE_CLASSES


@contextmanager
def _fake_query(rows):
    """Swap ``market_vn.query`` for the duration of one test, then restore it."""
    original = market_vn.query
    market_vn.query = lambda sql, params=(): rows
    try:
        yield
    finally:
        market_vn.query = original


@check("a symbol with daily history but no live quote is priced off its own closes")
def _():
    rows = [
        # Newest first, as the SQL orders it; two rows is what the query keeps.
        ("ABC", date(2026, 9, 9), 15.0, 1000),
        ("ABC", date(2026, 9, 8), 10.0, 2000),
    ]
    with _fake_query(rows):
        out = market_vn._symbols_without_quote(known=set())
    assert len(out) == 1, out
    row = out[0]
    assert row["symbol"] == "ABC"
    assert row["name"] is None, row  # no name source for these — honestly absent
    assert row["price"] == 15.0
    assert abs(row["change_percent"] - 50.0) < 1e-9, row["change_percent"]
    assert row["volume"] == 1000


@check("a symbol already covered by the live quote is not duplicated")
def _():
    rows = [("ABC", date(2026, 9, 9), 15.0, 1000)]
    with _fake_query(rows):
        out = market_vn._symbols_without_quote(known={"ABC"})
    assert out == [], out


@check("a warrant or bond never reaches the picker, but an index does")
def _():
    rows = [
        ("CVNM2609", date(2026, 9, 9), 15.0, 1000),    # time decay against a strike
        ("41I1G8000", date(2026, 9, 9), 100.0, 5),     # quoted against face value
        ("VNINDEX", date(2026, 9, 9), 1900.0, 0),      # a legitimate index level
        ("G-XAUUSD", date(2026, 9, 9), 4418.11, 0),    # gold, priced in USD
    ]
    with _fake_query(rows):
        out = market_vn._symbols_without_quote(known=set())

    got = {row["symbol"]: row for row in out}
    assert "CVNM2609" not in got, got
    assert "41I1G8000" not in got, got
    # And the two that belong come through carrying the right units, so the
    # interface never prints an index level or an ounce of gold as đồng.
    assert got["VNINDEX"]["asset_class"] == "index_vn"
    assert got["VNINDEX"]["currency"] == "point"
    assert got["G-XAUUSD"]["asset_class"] == "commodity"
    assert got["G-XAUUSD"]["currency"] == "USD"


@check("only one close means no percentage claim, not a fabricated one")
def _():
    rows = [("XYZ", date(2026, 9, 9), 15.0, 1000)]
    with _fake_query(rows):
        out = market_vn._symbols_without_quote(known=set())
    assert out[0]["change_percent"] is None, out[0]


@check("the merged list has no duplicates and stays sorted by volume, None last")
def _():
    quote_rows = [
        ("VIC", "Vingroup", 45.0, 1.2, 900, None),
        ("VNM", "Vinamilk", 60.0, -0.5, 300, None),
    ]
    daily_rows = [
        ("ABC", date(2026, 9, 9), 10.0, 5000),  # louder than both quoted names
        ("ABC", date(2026, 9, 8), 9.0, 4000),
        ("XYZ", date(2026, 9, 9), 3.0, None),   # no volume at all
    ]
    calls = iter([quote_rows, daily_rows])
    original = market_vn.query
    market_vn.query = lambda sql, params=(): next(calls)  # v_quote, then history
    try:
        out = market_vn.list_symbols()
    finally:
        market_vn.query = original

    symbols = [q["symbol"] for q in out]
    assert len(symbols) == len(set(symbols)), symbols
    assert symbols[0] == "ABC", symbols  # 5000 beats 900 and 300
    assert symbols[-1] == "XYZ", symbols  # None volume sorts last


@check("connection errors are translated into something actionable")
def _():
    cases = {
        "connection timed out": "VPN",
        "could not translate host name": "VPN",
        "password authentication failed for user": "đăng nhập",
        "permission denied for view bars_1d": "quản trị",
    }
    for raw, expected in cases.items():
        message = market_vn._friendly(RuntimeError(raw))
        assert expected.lower() in message.lower(), (raw, message)


# ---------------------------------------------------------------- live (VPN)

@live("the database answers and reports our read-only user")
def _():
    rows = market_vn.query("SELECT current_user")
    assert rows[0][0] == "qp_remote", rows


@live("minute bars exclude the candle currently being written")
def _():
    frame = market_vn.get_candles("VN30F1M", "1m", limit=20)
    assert not frame.empty, "no minute bars returned"
    newest = pd.to_datetime(frame["open_time"].iloc[-1], unit="ms", utc=True)
    now = pd.Timestamp.now(tz="UTC").floor("min")
    assert newest < now, f"newest bar {newest} is in the current minute {now}"


@live("candles come back oldest first")
def _():
    frame = market_vn.get_candles("VN30F1M", "1m", limit=30)
    assert frame["open_time"].is_monotonic_increasing, "not sorted ascending"


@live("intraday timestamps land inside the Vietnamese session")
def _():
    # 09:00-15:00 in Ho Chi Minh City is 02:00-08:00 UTC. Bars outside that
    # would mean the timezone handling is wrong somewhere.
    frame = market_vn.get_candles("VN30F1M", "1m", limit=200)
    hours = pd.to_datetime(frame["open_time"], unit="ms", utc=True).dt.tz_convert(
        "Asia/Ho_Chi_Minh"
    ).dt.hour
    assert hours.between(9, 15).all(), sorted(hours.unique())


@live("wider frames are aggregated from the minute bars, not invented")
def _():
    minutes = market_vn.get_candles("VN30F1M", "1m", limit=600)
    quarters = market_vn.get_candles("VN30F1M", "15m", limit=20)
    assert not quarters.empty

    # Every 15m bar must sit on a 15-minute boundary and stay within the day's
    # high/low from the minute data covering it.
    starts = pd.to_datetime(quarters["open_time"], unit="ms", utc=True)
    assert (starts.dt.minute % 15 == 0).all(), starts.dt.minute.unique()
    assert quarters["high"].max() <= minutes["high"].max() * 1.001
    assert quarters["low"].min() >= minutes["low"].min() * 0.999


@live("daily history reaches back further than the minute history")
def _():
    daily = market_vn.coverage("VNINDEX", "1d")
    assert daily and daily["count"] > 4000, daily
    first = pd.to_datetime(daily["first"], unit="ms", utc=True)
    assert first.year <= 2010, first


@live("the symbol list covers the whole exchange and flags intraday coverage")
def _():
    symbols = market_vn.list_symbols()
    intraday = market_vn.intraday_symbols()
    # Bounded well below the live-measured 1,529 (389 quoted + ~1,140 folded
    # in from daily history) so ordinary listings/delistings don't flake this.
    assert len(symbols) > 1000, len(symbols)

    # `intraday` also covers warrants and bonds this picker deliberately
    # excludes (§_EQUITY_TICKER_RE), so it is not a subset of `symbols` any
    # more — comparing sizes directly would compare two different universes.
    # What must hold is the overlap: some but not all of our equities carry
    # minute bars.
    overlap = intraday & {s["symbol"] for s in symbols}
    assert 0 < len(overlap) < len(symbols), (len(overlap), len(symbols))
    assert "VN30F1M" in intraday

    # No symbol appears twice: a name in both v_quote and the folded-in daily
    # history must have been deduplicated, not double-listed.
    names = [s["symbol"] for s in symbols]
    assert len(names) == len(set(names)), "duplicate symbol in the merged list"


@live("gold, crypto, FX and the index families all reach the list")
def _():
    symbols = {s["symbol"]: s for s in market_vn.list_symbols()}

    # These were in the database all along and never reachable from the app.
    expected = {
        "G-GOLD": "commodity", "G-XAUUSD": "commodity", "G-BTCUSD": "crypto",
        "G-USDVND": "fx", "G-SPX": "index_global", "HNXINDEX": "index_vn",
        "I1-FIN": "index_sector", "E1VFVN30": "fund", "VN30F1M": "futures_vn",
    }
    for symbol, asset_class in expected.items():
        assert symbol in symbols, f"{symbol} missing from the symbol list"
        assert symbols[symbol]["asset_class"] == asset_class, symbols[symbol]

    # Every listed symbol carries a class and a unit; a price with no stated
    # unit is the §2.7 failure this whole split exists to avoid.
    for symbol, row in symbols.items():
        assert row["asset_class"] in market_vn.TRADABLE_CLASSES, row
        assert row["currency"], row

    # And the two excluded families really are absent.
    assert not [s for s in symbols if market_vn.classify(s) in ("warrant", "bond")]


@live("the account holds no write privileges")
def _():
    # Asked of the catalogue rather than attempted. Trying an INSERT to see
    # whether it fails is both a worse test — a temp-table probe "passes" on a
    # fetch error, not a refusal — and the wrong thing to do to somebody
    # else's production database.
    rows = market_vn.query(
        """
        SELECT
            has_table_privilege(current_user, 'api.v_quote', 'INSERT'),
            has_table_privilege(current_user, 'api.v_quote', 'UPDATE'),
            has_table_privilege(current_user, 'api.v_quote', 'DELETE'),
            has_table_privilege(current_user, 'api.v_quote', 'SELECT'),
            has_schema_privilege(current_user, 'public', 'CREATE'),
            (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)
        """
    )
    insert, update, delete, select, create_public, superuser = rows[0]
    assert select, "should be able to read api.v_quote"
    assert not insert and not update and not delete, (insert, update, delete)
    assert not create_public, "read-only account can create objects in public"
    assert not superuser, "read-only account is a superuser"


@live("only the api schema is reachable")
def _():
    # Asked of the catalogue, so this never becomes an attempt to reach what is
    # documented as off limits. `has_schema_privilege` raises on a schema that
    # does not exist, so existence is checked first.
    rows = market_vn.query(
        """
        SELECT nspname,
               has_schema_privilege(current_user, nspname, 'USAGE') AS usable
        FROM pg_namespace
        WHERE nspname IN ('api', 'quant', 'web', 'public')
        ORDER BY nspname
        """
    )
    privileges = {name: usable for name, usable in rows}
    assert privileges.get("api"), f"the api schema should be readable: {privileges}"

    for restricted in ("quant", "web"):
        if restricted in privileges:
            assert not privileges[restricted], (
                f"schema `{restricted}` is readable but was documented as denied"
            )


# --------------------------------------------------------------------------

def run(items) -> tuple[int, int]:
    passed = failed = 0
    for name, fn in items:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL  {name}")
            print(f"          {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERROR {name}")
            print(f"          {type(exc).__name__}: {exc}")
            failed += 1
    return passed, failed


def main() -> int:
    print("Offline checks (routing and shaping):")
    passed, failed = run(CHECKS)

    print("\nLive checks (need the team VPN):")
    if not market_vn.configured():
        print("  SKIP  MARKET_DSN chưa cấu hình")
        return 1 if failed else 0

    try:
        market_vn.query("SELECT 1")
    except market_vn.MarketUnavailable as exc:
        print(f"  SKIP  không kết nối được: {exc}")
        print(f"\n{passed} passed, {failed} failed, live checks skipped")
        return 1 if failed else 0

    live_passed, live_failed = run(LIVE_CHECKS)
    passed += live_passed
    failed += live_failed

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
