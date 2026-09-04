"""Binance market-data client.

Only public market data is used, so no API key is ever needed. The default
host is ``data-api.binance.vision`` — Binance's dedicated public market-data
endpoint, which is reachable from regions where the trading API is blocked.

Rate limits: a klines call with limit=1000 costs 2 request-weight against a
6000/minute budget, so paginated backfill is bounded by ``MIN_REQUEST_INTERVAL``
rather than by the budget itself. 429 and 418 responses are respected via the
``Retry-After`` header.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
import pandas as pd

log = logging.getLogger(__name__)

BASE_URL = "https://data-api.binance.vision"
FALLBACK_URLS = ["https://api.binance.com", "https://api-gcp.binance.com"]

MAX_LIMIT = 1000
MIN_REQUEST_INTERVAL = 0.10  # seconds between paginated calls
MAX_RETRIES = 5

# Milliseconds per candle, per supported timeframe.
INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}

# Binance kline payload columns; we keep the first six.
_RAW_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_base", "taker_quote", "ignore",
]


def to_ms(value: str | datetime) -> int:
    """Convert an ISO date string or datetime to epoch milliseconds (UTC)."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def klines_to_frame(raw: list[list]) -> pd.DataFrame:
    """Turn a raw Binance klines payload into a typed OHLCV frame."""
    if not raw:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(raw, columns=_RAW_COLUMNS[: len(raw[0])])
    df = df[["open_time", "open", "high", "low", "close", "volume"]]
    df["open_time"] = df["open_time"].astype("int64")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    return df.dropna().reset_index(drop=True)


class BinanceClient:
    """Async client for Binance public klines."""

    def __init__(self, base_url: str = BASE_URL, timeout: float = 20.0):
        self.base_url = base_url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BinanceClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self._timeout,
            headers={"User-Agent": "qp-tracking/1.0"},
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: dict) -> list | dict:
        assert self._client is not None, "use BinanceClient as an async context manager"

        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._client.get(path, params=params)
            except httpx.RequestError as exc:
                wait = 2 ** attempt
                log.warning("network error (%s), retrying in %ss", exc, wait)
                await asyncio.sleep(wait)
                continue

            if resp.status_code in (429, 418):
                wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                log.warning("rate limited, sleeping %ss", wait)
                await asyncio.sleep(wait)
                continue

            resp.raise_for_status()
            return resp.json()

        raise RuntimeError(f"Binance request failed after {MAX_RETRIES} attempts: {path}")

    async def ping(self) -> bool:
        try:
            await self._get("/api/v3/ping", {})
            return True
        except Exception:
            return False

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = MAX_LIMIT,
    ) -> pd.DataFrame:
        """Fetch up to ``limit`` candles in one call."""
        params: dict = {"symbol": symbol, "interval": interval, "limit": min(limit, MAX_LIMIT)}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms

        raw = await self._get("/api/v3/klines", params)
        return klines_to_frame(raw)

    async def iter_klines(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int | None = None,
    ):
        """Yield OHLCV frames page by page from ``start_ms`` to ``end_ms``.

        Stops when Binance returns nothing or stops advancing, which is how the
        listing date is discovered without knowing it up front.
        """
        step = INTERVAL_MS.get(interval)
        if step is None:
            raise ValueError(f"unsupported interval: {interval}")

        end_ms = end_ms or now_ms()
        cursor = start_ms

        while cursor < end_ms:
            df = await self.fetch_klines(symbol, interval, start_ms=cursor, end_ms=end_ms)
            if df.empty:
                break

            yield df

            last_open = int(df["open_time"].iloc[-1])
            next_cursor = last_open + step
            if next_cursor <= cursor:  # no forward progress; avoid an infinite loop
                break
            cursor = next_cursor

            if len(df) < MAX_LIMIT:  # partial page means we reached the head
                break

            await asyncio.sleep(MIN_REQUEST_INTERVAL)
