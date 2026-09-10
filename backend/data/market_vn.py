"""Read-only access to the team's Vietnam market database.

TimescaleDB on the team VPS, reachable only over the Tailscale VPN. The account
can read the ``api`` schema and nothing else, which is deliberate — a
"permission denied" here is a question for the administrator, not something to
work around.

The schema does not carry an exchange column, and the ticker mix in
``api.v_history_1d`` (HBC, BVS, SD9, AAV — HOSE and HNX names side by side)
confirms this is not HOSE-only, whatever it was scoped to originally. Nothing
here claims an exchange for a symbol it cannot actually name.

Four properties of this data shape every query below:

1. **There is no tick data.** One minute is the finest resolution available.
2. **``api.v_history_1m`` has no ``is_final`` column**, so its newest row may be
   a candle still being written. Every query therefore excludes the current
   minute rather than trusting the last row.
3. **``ts`` is UTC.** The Vietnamese session of 09:00–15:00 is 02:00–08:00 UTC.
   Timestamps are converted for display only; everything stored and compared
   here stays UTC, as it does for the Binance data.
4. **``api.v_quote`` is not the whole catalogue.** It is a curated live-price
   feed covering a few hundred names; ``api.v_history_1d`` carries far more
   (2,100 measured, against 389 in the quote feed), most of it still trading.
   ``list_symbols`` folds the gap in rather than only showing what the quote
   feed happens to cover.

The 5m/15m/1h/4h frames are aggregated from 1m in SQL. Only 1m and 1d exist in
the database, and doing the bucketing server-side avoids dragging a hundred
thousand rows across the VPN to resample them locally.
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median, quantiles

import pandas as pd

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Kept below the server's 60-second cap so a slow query fails on our terms.
STATEMENT_TIMEOUT_MS = 30_000
CONNECT_TIMEOUT = 8

# Seconds per bucket for the frames aggregated from 1m data.
BUCKET_SECONDS = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "2h": 7200, "4h": 14400}
SUPPORTED_TIMEFRAMES = ["1m", *BUCKET_SECONDS.keys(), "1d"]

# A plain equity ticker: exactly three letters/digits (VIC, ITA, SD9, S99…).
_EQUITY_TICKER_RE = re.compile(r"^[A-Z0-9]{3}$")

# The `G-` family is this database's international feed: metals, energy, soft
# commodities, FX pairs, crypto and foreign indices, several with history back
# to the 1970s. Which is which cannot be read off the symbol reliably — both
# G-XAUUSD (gold, per ounce) and G-EURUSD (a rate) end in USD, and G-USDTUSD is
# a stablecoin, not a currency pair — so the split is an explicit table rather
# than a regex that would quietly file gold under foreign exchange.
_GLOBAL_CLASSES = {
    "commodity": {
        "G-GOLD", "G-XAUUSD", "G-XAGUSD", "G-PLATINUM", "G-ALUMINUM", "G-COPPER",
        "G-NICKEL", "G-ZINC", "G-LEAD", "G-OIL", "G-BOIL", "G-HOIL", "G-GAS",
        "G-SUGAR", "G-COCOA", "G-COFFEE", "G-COTTON",
    },
    "crypto": {
        "G-BTCUSD", "G-ETHUSD", "G-XRPUSD", "G-BNBUSD", "G-ADAUSD", "G-LTCUSD",
        "G-BCHUSD", "G-EOSUSD", "G-IOTUSD", "G-XEMUSD", "G-XLMUSD", "G-XMRUSD",
        "G-XVGUSD", "G-DASHUSD", "G-USDTUSD", "G-PIUSD",
    },
    "fx": {
        "G-EURUSD", "G-GBPUSD", "G-AUDUSD", "G-NZDUSD", "G-USDJPY", "G-USDCHF",
        "G-USDCAD", "G-USDCNY", "G-USDRUB", "G-USDVND", "G-USDAUD", "G-CHFUSD",
        "G-EURJPY", "G-EURGBP", "G-EURCHF", "G-GBPJPY", "G-AUDJPY", "G-NZDJPY",
        "G-USDX",
    },
    "index_global": {
        "G-SPX", "G-US500", "G-DJI", "G-DJ30F", "G-DJSH", "G-IXIC", "G-N225",
        "G-FTSE", "G-GDAXI", "G-FCHI", "G-HSI", "G-SSEC", "G-KS11", "G-VFS",
    },
}

# Vietnamese index futures. VN30F1M and its siblings are contracts on an index,
# so they trade and are quoted differently from the index itself.
_VN_FUTURES_RE = re.compile(r"^VN(30|100)F[12][MQ]$")

# Exchange-traded funds and fund certificates on the Vietnamese market.
_VN_FUND_RE = re.compile(r"^(FUE|FUC|E1)[A-Z0-9]+$")

# Vietnamese sector indices, published as I1-/I2-/I3- by depth of the ICB tree.
_VN_SECTOR_RE = re.compile(r"^I[123]-")

# Vietnamese headline and basket indices.
_VN_INDEX_NAMES = {
    "VNINDEX", "VN30", "VN100", "VNALL", "VNX50", "VNXALL", "VNMID", "VNSML",
    "VNDIAMOND", "VNFINLEAD", "VNFINSELECT", "VNSI", "VNIT", "VNCOND", "VNCONS",
    "VNENE", "VNFIN", "VNHEAL", "VNIND", "VNMAT", "VNREAL", "VNUTI",
    "HNXINDEX", "HNX30INDEX", "UPCOMINDEX",
}

# Covered warrants (CVNM2609) and bonds (41I1G8000) are deliberately excluded
# everywhere below: a warrant carries time decay against a strike and a bond is
# quoted against face value with accrued interest, and neither survives the
# equity pricing conventions the rest of this platform assumes (§3.1, §3.6).
_WARRANT_RE = re.compile(r"^C[A-Z]{3}\d{4}$")
_BOND_RE = re.compile(r"^\d")

# What each class is quoted in, so the interface never labels an index level as
# money or a gold price as đồng. "point" means the number is an index level.
CLASS_CURRENCY = {
    "equity": "VND",
    "fund": "VND",
    "index_vn": "point",
    "index_sector": "point",
    "index_global": "point",
    "futures_vn": "point",
    "commodity": "USD",
    "crypto": "USD",
    "fx": "rate",
}

# Every class the picker will offer. Anything classified outside this set is
# known about and deliberately not listed.
TRADABLE_CLASSES = tuple(CLASS_CURRENCY)


def classify(symbol: str) -> str | None:
    """Which instrument family a symbol belongs to, or None if unrecognised.

    Returns ``"warrant"`` / ``"bond"`` for the two families that are recognised
    but deliberately kept out of the picker, so the caller can tell "excluded
    on purpose" from "never seen this shape before".
    """
    name = (symbol or "").upper()
    if not name:
        return None

    for asset_class, members in _GLOBAL_CLASSES.items():
        if name in members:
            return asset_class
    if name.startswith("G-"):
        # A new symbol on the international feed. Better to say "unknown" than
        # to guess a class and mislabel its units.
        return None

    if name in _VN_INDEX_NAMES:
        return "index_vn"
    if _VN_SECTOR_RE.match(name):
        return "index_sector"
    if _VN_FUTURES_RE.match(name):
        return "futures_vn"
    if _VN_FUND_RE.match(name):
        return "fund"
    if _WARRANT_RE.match(name):
        return "warrant"
    if _BOND_RE.match(name):
        return "bond"
    if _EQUITY_TICKER_RE.match(name):
        return "equity"
    return None


_pool = None
_pool_lock = threading.Lock()


class MarketUnavailable(RuntimeError):
    """The market database could not be reached or read."""


def dsn() -> str | None:
    """The connection string, or None when it has not been configured."""
    value = os.environ.get("MARKET_DSN")
    if value:
        return value

    # Loaded lazily so importing this module never requires a .env to exist.
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file)
        except ImportError:
            log.warning("python-dotenv is not installed; MARKET_DSN must be in the environment")
    return os.environ.get("MARKET_DSN")


def configured() -> bool:
    return bool(dsn())


def _get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            from psycopg_pool import ConnectionPool

            url = dsn()
            if not url:
                raise MarketUnavailable(
                    "Chưa cấu hình MARKET_DSN. Copy .env.example thành .env và điền mật khẩu."
                )
            # `open=False` then `open()` so a VPN-off start surfaces here rather
            # than at import time.
            _pool = ConnectionPool(
                url,
                min_size=0,
                max_size=4,
                timeout=15,
                kwargs={"connect_timeout": CONNECT_TIMEOUT},
                open=False,
            )
            _pool.open()
        return _pool


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


def _friendly(exc: Exception) -> str:
    text = str(exc).lower()
    if any(
        sign in text
        for sign in (
            "timeout", "timed out", "could not translate host name",
            "no route to host", "network is unreachable", "connection refused",
        )
    ):
        return (
            "Không kết nối được database thị trường VN. "
            "Nhiều khả năng VPN của team (Tailscale) chưa bật."
        )
    if "password authentication failed" in text:
        return "Sai thông tin đăng nhập database thị trường VN (kiểm tra .env)."
    if "permission denied" in text:
        return (
            "Bị từ chối quyền trên database thị trường VN. "
            "Tài khoản chỉ đọc được schema `api`, hãy liên hệ người quản trị."
        )
    return f"Lỗi database thị trường VN: {exc}"


def query(sql: str, params: tuple = ()) -> list[tuple]:
    """Run one read-only statement, with a bounded timeout."""
    try:
        with _get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
                cur.execute(sql, params)
                return cur.fetchall()
    except MarketUnavailable:
        raise
    except Exception as exc:
        log.warning("market query failed: %s", exc)
        raise MarketUnavailable(_friendly(exc)) from exc


# --------------------------------------------------------------------- symbols

def list_symbols() -> list[dict]:
    """Every tradable symbol with its latest quote and instrument class.

    ``api.v_quote`` is a curated live-price feed, not the whole catalogue —
    measured at 389 names while the daily-history table alone carries data for
    2,100. The gap is not stale or delisted stock: roughly 1,150 equity tickers
    were still trading as of the most recent session with real volume, and
    beyond those sits a whole international feed (gold, silver, oil, FX pairs,
    crypto, foreign indices) plus Vietnamese indices, sector indices, index
    futures and fund certificates. Left out, the app was showing a fraction of
    what the database actually has. ``_symbols_without_quote`` fills that gap
    in from the history table itself.
    """
    rows = query(
        """
        SELECT symbol, name, price, change_percent, volume, data_as_of
        FROM api.v_quote
        """
    )
    quotes = [
        {
            "symbol": r[0],
            "name": r[1],
            "price": float(r[2]) if r[2] is not None else None,
            "change_percent": float(r[3]) if r[3] is not None else None,
            "volume": int(r[4]) if r[4] is not None else None,
            "data_as_of": int(r[5].timestamp() * 1000) if r[5] else None,
            # The quote feed carries no class of its own, so it is derived the
            # same way for both sources — one rule, not two that can drift.
            "asset_class": classify(r[0]) or "equity",
        }
        for r in rows
    ]
    for quote in quotes:
        quote["currency"] = CLASS_CURRENCY.get(quote["asset_class"], "")

    known = {q["symbol"] for q in quotes}
    quotes.extend(_symbols_without_quote(known))

    # ``ORDER BY volume DESC NULLS LAST`` was pushed down to SQL before the
    # merge; now that the two sources are combined in Python it is applied
    # here instead, on the same terms for both.
    quotes.sort(key=lambda q: (q["volume"] is None, -(q["volume"] or 0)))
    return quotes


def _symbols_without_quote(known: set[str]) -> list[dict]:
    """Symbols with daily history but no row in ``api.v_quote``.

    Covers every class the picker offers, not just equities: the international
    feed (gold, oil, FX, crypto, foreign indices) and the Vietnamese indices,
    sector indices, index futures and funds all live here rather than in the
    quote feed. Warrants and bonds are recognised and skipped.

    There is no live price feed for these, so each is priced off its own two
    most recent closes instead — a quote that can lag the real feed by up to
    one session, which is the honest cost of listing a symbol the quote feed
    itself does not carry. The window bounds the scan to a recent slice
    rather than ranking the full history of 2,100 symbols just to keep two
    rows of it, and is set to 45 days to match the window ``api.v_quote``'s
    own CTE uses for the same reason (per Nam): a shorter one can lose a
    symbol's previous close across a Tet-length closure, which would either
    drop it from the list for no real reason or silently misprice its change.
    """
    rows = query(
        """
        SELECT symbol, trading_date, close, volume
        FROM (
            SELECT symbol, trading_date, close, volume,
                   row_number() OVER (
                       PARTITION BY symbol ORDER BY trading_date DESC
                   ) AS rn
            FROM api.v_history_1d
            WHERE trading_date >= current_date - interval '45 days'
        ) ranked
        WHERE rn <= 2
        ORDER BY symbol, trading_date DESC
        """
    )

    by_symbol: dict[str, list[tuple]] = {}
    classes: dict[str, str] = {}
    for symbol, trading_date, close, volume in rows:
        if symbol in known:
            continue
        asset_class = classify(symbol)
        if asset_class not in TRADABLE_CLASSES:
            continue  # a warrant, a bond, or a shape nothing here recognises
        classes[symbol] = asset_class
        by_symbol.setdefault(symbol, []).append((trading_date, close, volume))

    out = []
    for symbol, points in by_symbol.items():
        latest_date, latest_close, latest_volume = points[0]
        price = float(latest_close) if latest_close is not None else None
        change_pct = None
        if price is not None and len(points) > 1 and points[1][1]:
            prev_close = float(points[1][1])
            if prev_close > 0:
                change_pct = (price - prev_close) / prev_close * 100
        asset_class = classes[symbol]
        out.append(
            {
                "symbol": symbol,
                "name": None,
                "price": price,
                "change_percent": change_pct,
                "volume": int(latest_volume) if latest_volume is not None else None,
                "data_as_of": _to_ms(latest_date),
                "asset_class": asset_class,
                "currency": CLASS_CURRENCY.get(asset_class, ""),
            }
        )
    return out


def intraday_symbols() -> set[str]:
    """Symbols that actually have minute bars, so the UI can say which do.

    Only 35 of the 389 are covered at minute resolution; offering 1m on the
    rest would produce an empty chart with no explanation.
    """
    rows = query(
        """
        SELECT DISTINCT symbol
        FROM api.v_history_1m
        WHERE ts > now() - interval '30 days'
        """
    )
    return {r[0] for r in rows}


def daily_closes(symbols: list[str], lookback: int) -> dict[str, dict]:
    """Most recent ``lookback`` daily closes for each symbol.

    One query for the whole basket rather than one per symbol: the portfolio
    panel asks for up to fifty names plus the index, and fifty round trips over
    a VPN is the difference between a page that answers and a page that hangs.

    The window is per symbol (``row_number`` partitions by symbol) so a name
    whose feed lags a few sessions still gets its own most recent `lookback`
    rows rather than being truncated by whatever the busiest symbol has.

    Returns ``{symbol: {date: close}}``. Non-positive closes are dropped: they
    are data errors, and a zero close would produce an infinite log return.
    """
    if not symbols:
        return {}

    rows = query(
        """
        SELECT symbol, trading_date, close
        FROM (
            SELECT symbol, trading_date, close,
                   row_number() OVER (
                       PARTITION BY symbol ORDER BY trading_date DESC
                   ) AS rn
            FROM api.v_history_1d
            WHERE symbol = ANY(%s)
        ) ranked
        WHERE rn <= %s
        ORDER BY symbol, trading_date
        """,
        (list(symbols), int(lookback)),
    )

    out: dict[str, dict] = {}
    for symbol, trading_date, close in rows:
        if close is None or float(close) <= 0:
            continue
        out.setdefault(symbol, {})[trading_date] = float(close)
    return out


def freshness() -> list[dict]:
    rows = query("SELECT symbol, data_as_of FROM api.v_data_freshness ORDER BY data_as_of DESC")
    return [
        {"symbol": r[0], "data_as_of": int(r[1].timestamp() * 1000) if r[1] else None}
        for r in rows
    ]


# --------------------------------------------------------------------- candles

def _to_ms(value) -> int:
    if isinstance(value, datetime):
        stamped = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(stamped.timestamp() * 1000)
    if isinstance(value, date):
        # Daily bars are keyed by the trading date at UTC midnight, which is
        # what a charting library expects for a date-indexed series.
        return int(datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp() * 1000)
    raise TypeError(f"unexpected timestamp type: {type(value).__name__}")


def _frame(rows: list[tuple]) -> pd.DataFrame:
    """Shape rows into the same OHLCV frame the DuckDB store returns."""
    if not rows:
        return pd.DataFrame(
            columns=["open_time", "open", "high", "low", "close", "volume"]
        ).astype(
            {
                "open_time": "int64", "open": "float64", "high": "float64",
                "low": "float64", "close": "float64", "volume": "float64",
            }
        )

    return pd.DataFrame(
        {
            "open_time": [_to_ms(r[0]) for r in rows],
            "open": [float(r[1]) for r in rows],
            "high": [float(r[2]) for r in rows],
            "low": [float(r[3]) for r in rows],
            "close": [float(r[4]) for r in rows],
            "volume": [float(r[5]) if r[5] is not None else 0.0 for r in rows],
        }
    )


def get_candles(
    symbol: str,
    timeframe: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """Candles for one symbol, oldest first, excluding any unfinished bar."""
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise MarketUnavailable(
            f"Khung `{timeframe}` không có cho thị trường VN. "
            f"Hỗ trợ: {', '.join(SUPPORTED_TIMEFRAMES)}."
        )

    limit = limit or 2000
    start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc) if start_ms else None
    end = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc) if end_ms else None

    if timeframe == "1d":
        rows = _daily(symbol, start, end, limit)
    elif timeframe == "1m":
        rows = _minute(symbol, start, end, limit)
    else:
        rows = _bucketed(symbol, BUCKET_SECONDS[timeframe], start, end, limit)

    # Queries fetch newest-first so LIMIT keeps the most recent window; the
    # chart wants oldest-first.
    return _frame(list(reversed(rows)))


def _daily(symbol: str, start, end, limit: int) -> list[tuple]:
    clauses = ["symbol = %s"]
    params: list = [symbol]
    if start:
        clauses.append("trading_date >= %s")
        params.append(start.date())
    if end:
        clauses.append("trading_date <= %s")
        params.append(end.date())
    params.append(limit)

    return query(
        f"""
        SELECT trading_date, open, high, low, close, volume
        FROM api.v_history_1d
        WHERE {' AND '.join(clauses)}
        ORDER BY trading_date DESC
        LIMIT %s
        """,
        tuple(params),
    )


def _minute(symbol: str, start, end, limit: int) -> list[tuple]:
    # `ts < date_trunc('minute', now())` drops the candle currently being
    # written. There is no is_final column to ask instead.
    clauses = ["symbol = %s", "ts < date_trunc('minute', now())"]
    params: list = [symbol]
    if start:
        clauses.append("ts >= %s")
        params.append(start)
    if end:
        clauses.append("ts <= %s")
        params.append(end)
    params.append(limit)

    return query(
        f"""
        SELECT ts, open, high, low, close, volume
        FROM api.v_history_1m
        WHERE {' AND '.join(clauses)}
        ORDER BY ts DESC
        LIMIT %s
        """,
        tuple(params),
    )


def _bucketed(symbol: str, seconds: int, start, end, limit: int) -> list[tuple]:
    """Aggregate 1m bars into wider ones, server-side.

    Open is the first minute's open and close is the last minute's close, which
    is why both use array_agg with an explicit order rather than min/max.
    """
    clauses = ["symbol = %s", "ts < date_trunc('minute', now())"]
    params: list = [seconds, symbol]
    if start:
        clauses.append("ts >= %s")
        params.append(start)
    if end:
        clauses.append("ts <= %s")
        params.append(end)
    params.append(limit)

    return query(
        f"""
        SELECT
            to_timestamp(floor(extract(epoch FROM ts) / %s) * %s) AS bucket,
            (array_agg(open  ORDER BY ts ASC))[1]  AS open,
            max(high)                              AS high,
            min(low)                               AS low,
            (array_agg(close ORDER BY ts DESC))[1] AS close,
            sum(volume)                            AS volume
        FROM api.v_history_1m
        WHERE {' AND '.join(clauses)}
        GROUP BY bucket
        ORDER BY bucket DESC
        LIMIT %s
        """,
        (seconds, *params),
    )


def coverage(symbol: str, timeframe: str) -> dict | None:
    """First and last bar plus a count, matching the DuckDB store's shape."""
    if timeframe == "1d":
        rows = query(
            """
            SELECT min(trading_date), max(trading_date), count(*)
            FROM api.v_history_1d WHERE symbol = %s
            """,
            (symbol,),
        )
    else:
        rows = query(
            """
            SELECT min(ts), max(ts), count(*)
            FROM api.v_history_1m WHERE symbol = %s
            """,
            (symbol,),
        )

    if not rows or rows[0][2] == 0:
        return None
    first, last, count = rows[0]
    return {"first": _to_ms(first), "last": _to_ms(last), "count": int(count)}


# ------------------------------------------------------------- data coverage

# Below this many bars in a typical session, a symbol is too thinly traded for
# a missing-bar count to mean anything: AAH prints six minutes of bars in a
# whole session, so "three bars today" is its normal, not an outage.
_THIN_SESSION_BARS = 30

# A session must be at least this far below its weekday's median before it is
# ever reported, however steady the symbol is. Without it, a symbol that
# prints exactly the same count every session has zero spread, and every
# session one bar short would qualify as an outage.
_COVERAGE_MIN_DROP = 0.20

# Below that floor, the threshold is Tukey's lower fence on the symbol's own
# session-to-session spread. A fixed percentage measures the wrong thing:
# VN30F1M prints 241 bars every session and a 30% drop is an outage, while AAH
# swings between 29 and 62 bars normally, and one rule at "20% down" flags
# seven ordinary AAH sessions to catch the one real fault on VN30F1M. Same
# class of error as the K-ratio in §2.6 — the threshold has to scale with the
# data's own spread. The fence is used rather than a multiple of the median
# absolute deviation because the counts are not remotely normal (they pile up
# at a full session and trail off to the left), and a quartile range measures
# that shape without assuming one.
_COVERAGE_FENCE = 1.5

# Sessions needed on a given weekday before its median means anything.
_MIN_SESSIONS_PER_WEEKDAY = 4


def data_coverage(symbol: str, lookback_days: int = 45) -> dict:
    """How complete this symbol's minute data is, judged against its own habit.

    The obvious source for this looks like ``api.v_ingestion_gaps``, and it is
    the wrong one. Measured over its 210 rows: 156 fall outside trading hours
    and cost nothing, ``reconnect_ts IS NULL`` means "the reconnect was not
    recorded" rather than "still down" (bars keep arriving afterwards), and
    several long disconnects sit entirely inside the 11:30-13:00 lunch break
    when no bars exist to lose. Counting those would raise 210 alarms for
    three genuinely missing bars.

    So this counts bars instead, and compares each session against the median
    for that same weekday. Judging a symbol against itself is what separates
    the three things a naive "missing %" conflates:

    * an outage — the session holds far fewer bars than that weekday usually
      brings, and typically every other symbol dips at the same moment;
    * a thin symbol — the median is tiny to begin with, which is not a data
      fault but does make intraday backtests on it meaningless;
    * a closed market — gold prints nothing on Sundays, and Sundays are
      compared with other Sundays, so the day never registers as missing.
    """
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    # One row per session: small enough to cross the VPN cheaply even for a
    # symbol that trades around the clock.
    rows = query(
        """
        SELECT ts::date AS d,
               extract(isodow FROM ts)::int AS dow,
               count(*) AS bars
        FROM api.v_history_1m
        WHERE symbol = %s AND ts >= %s AND ts < date_trunc('day', now())
        GROUP BY d, dow
        ORDER BY d
        """,
        (symbol, since),
    )
    if not rows:
        return {
            "symbol": symbol, "sessions": 0, "gaps": [], "thin": False,
            "median_bars": None, "checked_from": int(since.timestamp() * 1000),
        }

    by_weekday: dict[int, list[int]] = {}
    for _, dow, bars in rows:
        by_weekday.setdefault(dow, []).append(int(bars))
    medians = {dow: median(counts) for dow, counts in by_weekday.items()}

    overall = median([int(r[2]) for r in rows])
    thin = overall < _THIN_SESSION_BARS

    # Each session as a share of what that weekday usually brings, so the
    # spread below is measured on one scale across every symbol.
    scored = [
        (day, int(bars), medians[dow], int(bars) / medians[dow])
        for day, dow, bars in rows
        # A weekday whose own median is tiny (a half-session holiday, or a
        # market that barely trades that day) carries no signal either.
        if medians[dow] >= _THIN_SESSION_BARS
        # And a weekday seen only a handful of times has a median made of
        # noise. Splitting by weekday is what keeps a closed Sunday from
        # reading as an outage, but it also divides the sample five to seven
        # ways, so a newly listed symbol would otherwise be judged against
        # two or three of its own sessions.
        and len(by_weekday[dow]) >= _MIN_SESSIONS_PER_WEEKDAY
    ]

    gaps = []
    spread = None
    if not thin and len(scored) >= 4:
        ratios = sorted(r for *_, r in scored)
        q1, _q2, q3 = quantiles(ratios, n=4)
        spread = q3 - q1
        # Never stricter than the fixed floor, so a perfectly steady symbol
        # (spread 0, fence sitting at its own median) does not report every
        # session that came up one bar short.
        floor = min(1.0 - _COVERAGE_MIN_DROP, q1 - _COVERAGE_FENCE * spread)
        for day, bars, expected, ratio in scored:
            if ratio < floor:
                gaps.append(
                    {
                        "date": _to_ms(day),
                        "bars": bars,
                        "expected": int(expected),
                        "missing_pct": (1 - ratio) * 100,
                    }
                )

    return {
        "symbol": symbol,
        "sessions": len(rows),
        "median_bars": int(overall),
        # True when the symbol prints so few bars per session that intraday
        # work on it is not meaningful, whatever the data pipeline did.
        "thin": thin,
        # The interquartile range of this symbol's session counts, as a share
        # of its own weekday median. Reported because it is what makes the gap
        # list readable: 0.02 means the count barely moves and a dip is real,
        # 0.40 means the symbol is erratic by nature and only a collapse shows.
        "session_spread": round(spread, 4) if spread is not None else None,
        "gaps": sorted(gaps, key=lambda g: -g["missing_pct"]),
        "checked_from": int(since.timestamp() * 1000),
    }


# --------------------------------------------------------- team risk model

def market_risk() -> dict:
    """The team's own Monte Carlo risk read on VNINDEX.

    A second opinion, not a replacement: the Risk tools tab measures the
    user's own backtested strategy, while this measures the index itself from
    the pipeline's simulation. They answer different questions and are worth
    seeing side by side, which only works if the differences are stated rather
    than smoothed over.

    Three limits travel with the numbers because none of them is visible in
    the figures themselves:

    * ``mc_paths`` is not constant across rows (10,000 and 40,000 both
      appear), so two rows printed to the same decimals do not carry the same
      simulation error. It is returned per row, with that error worked out.
    * the series is sparse and irregular — six timestamps with a month-long
      hole in the middle — so it is a set of snapshots, not a curve.
    * it covers VNINDEX only, whatever symbol the user happens to be looking
      at.
    """
    rows = query(
        """
        SELECT ts, current_drawdown, rolling_drawdown_60d, volatility,
               var_95, es_95, downside_probability, risk_state, mc_paths,
               generated_at
        FROM api.v_risk_metrics
        ORDER BY ts
        """
    )
    if not rows:
        return {"available": False, "snapshots": [], "distribution": []}

    snapshots = []
    for (ts, dd, dd60, vol, var95, es95, down_p, state, paths, made) in rows:
        paths = int(paths) if paths else None
        p = float(down_p) if down_p is not None else None
        # Standard error of a simulated probability: sqrt(p(1-p)/N). Without
        # it, 0.4699 from 10,000 paths and 0.4676 from 40,000 read as if the
        # difference between them meant something.
        sim_error = (
            math.sqrt(p * (1 - p) / paths) if p is not None and paths else None
        )
        snapshots.append(
            {
                "time": _to_ms(ts),
                "current_drawdown_pct": float(dd) * 100 if dd is not None else None,
                "rolling_drawdown_60d_pct": float(dd60) * 100 if dd60 is not None else None,
                "volatility_pct": float(vol) * 100 if vol is not None else None,
                "var_95_pct": float(var95) * 100 if var95 is not None else None,
                "es_95_pct": float(es95) * 100 if es95 is not None else None,
                "downside_probability_pct": p * 100 if p is not None else None,
                "downside_sim_error_pct": sim_error * 100 if sim_error else None,
                "risk_state": state,
                "mc_paths": paths,
                "generated_at": _to_ms(made) if made else None,
            }
        )

    latest_ts = rows[-1][0]
    dist_rows = query(
        """
        SELECT bucket, probability FROM api.v_risk_distribution
        WHERE ts = %s ORDER BY bucket DESC
        """,
        (latest_ts,),
    )
    latest_paths = snapshots[-1]["mc_paths"]
    distribution = []
    for bucket, probability in dist_rows:
        p = float(probability)
        distribution.append(
            {
                "loss_pct": float(bucket) * 100,
                "probability_pct": p * 100,
                "sim_error_pct": (
                    math.sqrt(p * (1 - p) / latest_paths) * 100 if latest_paths else None
                ),
            }
        )

    # Whether the snapshots are close enough together to read as a series.
    spacing_days = None
    if len(rows) > 1:
        spans = [
            (rows[i][0] - rows[i - 1][0]).total_seconds() / 86400
            for i in range(1, len(rows))
        ]
        spacing_days = {"median": median(spans), "max": max(spans)}

    return {
        "available": True,
        "symbol": "VNINDEX",
        "snapshots": snapshots,
        "latest": snapshots[-1],
        "distribution": distribution,
        "spacing_days": spacing_days,
    }
