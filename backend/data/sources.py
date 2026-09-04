"""Routes candle requests to whichever market holds them.

Two markets now: Binance crypto in the local DuckDB store, and the team's
Vietnam (HOSE) database over the VPN. Symbols are namespaced with a prefix —
``VN:VN30F1M`` against a bare ``BTCUSDT`` — so routing is decided by the symbol
itself and no caller has to carry a separate "which market" argument.

Reading the Vietnam data directly rather than copying it into DuckDB is
deliberate. It is written to continuously during the session, DuckDB allows a
single writer, and a local copy would be one more thing to keep in step for no
gain in what you can see.

Everything below returns the same OHLCV frame — ``open_time`` in epoch
milliseconds UTC, plus open/high/low/close/volume — so indicators, backtests
and paper trading never learn which market they are looking at.
"""

from __future__ import annotations

import pandas as pd

from backend.data import market_vn, store

VN_PREFIX = "VN:"

CRYPTO = "crypto"
VIETNAM = "vn"


def parse(symbol: str) -> tuple[str, str]:
    """Split a namespaced symbol into (market, bare symbol)."""
    if symbol.upper().startswith(VN_PREFIX):
        return VIETNAM, symbol[len(VN_PREFIX):].upper()
    return CRYPTO, symbol.upper()


def qualify(market: str, symbol: str) -> str:
    return f"{VN_PREFIX}{symbol}" if market == VIETNAM else symbol


def is_vietnam(symbol: str) -> bool:
    return parse(symbol)[0] == VIETNAM


def supports_backfill(symbol: str) -> bool:
    """Only the crypto store is ours to fill; the VN database is read-only."""
    return not is_vietnam(symbol)


def supports_live_stream(symbol: str) -> bool:
    """Binance pushes over WebSocket. The VN database has no push channel."""
    return not is_vietnam(symbol)


def timeframes_for(symbol: str) -> list[str]:
    if is_vietnam(symbol):
        return list(market_vn.SUPPORTED_TIMEFRAMES)
    from backend.config import settings

    return list(settings.data.timeframes)


def get_candles(
    symbol: str,
    timeframe: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    market, bare = parse(symbol)
    if market == VIETNAM:
        return market_vn.get_candles(bare, timeframe, start_ms, end_ms, limit)
    return store.get_candles(bare, timeframe, start_ms, end_ms, limit)


def coverage(symbol: str, timeframe: str) -> dict | None:
    market, bare = parse(symbol)
    if market == VIETNAM:
        return market_vn.coverage(bare, timeframe)
    return store.get_coverage(bare, timeframe)
