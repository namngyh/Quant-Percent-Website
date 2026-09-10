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
import os
import re
import threading
from datetime import date, datetime, timezone
from pathlib import Path

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
# Everything longer belongs to a different instrument class this platform does
# not model separately — covered warrants (7-8 chars, e.g. CVNM2609), bonds
# (9 chars, numeric-led, e.g. 41I1G8000), indices and fund certificates
# (VNINDEX, VN30, FUESSV50). Mixing those into the equity picker would carry
# them into backtests built on equity pricing conventions (§3.6) that do not
# apply to a bond's accrued-interest quoting or a warrant's time decay.
_EQUITY_TICKER_RE = re.compile(r"^[A-Z0-9]{3}$")

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
    """Every tradable symbol with its latest quote.

    ``api.v_quote`` is a curated live-price feed, not the whole catalogue —
    measured at 389 names while the daily-history table alone carries data for
    2,100. The gap is not stale or delisted stock: roughly 1,150 of those
    extra tickers were still trading as of the most recent session, with real
    volume, just never added to the quote feed. Left out, the app was showing
    a fraction of what the database actually has. ``_equities_without_quote``
    fills that gap in from the history table itself.
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
        }
        for r in rows
    ]
    known = {q["symbol"] for q in quotes}
    quotes.extend(_equities_without_quote(known))

    # ``ORDER BY volume DESC NULLS LAST`` was pushed down to SQL before the
    # merge; now that the two sources are combined in Python it is applied
    # here instead, on the same terms for both.
    quotes.sort(key=lambda q: (q["volume"] is None, -(q["volume"] or 0)))
    return quotes


def _equities_without_quote(known: set[str]) -> list[dict]:
    """Plain equity tickers with daily history but no row in ``api.v_quote``.

    There is no live price feed for these, so each is priced off its own two
    most recent closes instead — a quote that can lag the real feed by up to
    one session, which is the honest cost of listing a symbol the quote feed
    itself does not carry. The 15-day window bounds the scan to roughly the
    last two trading weeks rather than ranking the full history of 2,100
    symbols just to keep two rows of it.
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
            WHERE trading_date >= current_date - interval '15 days'
        ) ranked
        WHERE rn <= 2
        ORDER BY symbol, trading_date DESC
        """
    )

    by_symbol: dict[str, list[tuple]] = {}
    for symbol, trading_date, close, volume in rows:
        if symbol in known or not _EQUITY_TICKER_RE.match(symbol):
            continue
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
        out.append(
            {
                "symbol": symbol,
                "name": None,
                "price": price,
                "change_percent": change_pct,
                "volume": int(latest_volume) if latest_volume is not None else None,
                "data_as_of": _to_ms(latest_date),
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
