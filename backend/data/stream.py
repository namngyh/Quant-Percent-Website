"""Live candles from the Binance kline WebSocket.

One upstream connection per (symbol, timeframe) that somebody is actually
watching, fanned out to every browser tab on that pair. When the last viewer
leaves, the upstream connection closes.

Two deliberate choices about what gets written where:

* The forming candle is broadcast on every tick but **only written to DuckDB
  when it closes**. Binance updates a forming candle a few times a second;
  persisting each of those would hammer the store to record a number that is
  about to change again.
* Closed candles are written through ``store.upsert_candles``, which replaces
  by key — so the row the REST backfill would have fetched later is already
  correct, and the two paths cannot disagree.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pandas as pd
import websockets

from backend.data import store
from backend.data.binance import INTERVAL_MS

log = logging.getLogger(__name__)

# Binance's dedicated market-data host, reachable where the trading API is not.
WS_BASE = "wss://data-stream.binance.vision/ws"

RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 60.0

Broadcast = Callable[[dict], Awaitable[None]]


@dataclass(frozen=True)
class Series:
    symbol: str
    timeframe: str

    @property
    def stream_name(self) -> str:
        return f"{self.symbol.lower()}@kline_{self.timeframe}"


def parse_kline(payload: dict) -> dict | None:
    """Turn a Binance kline message into a candle dict, or None if unusable."""
    k = payload.get("k")
    if not isinstance(k, dict):
        return None

    try:
        return {
            "symbol": payload.get("s", ""),
            "timeframe": k.get("i", ""),
            "open_time": int(k["t"]),
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "closed": bool(k.get("x", False)),
        }
    except (KeyError, TypeError, ValueError):
        log.debug("unparseable kline payload: %s", payload)
        return None


def persist(candle: dict) -> int:
    """Write one closed candle to the store. Runs off the event loop."""
    frame = pd.DataFrame(
        [
            {
                "open_time": candle["open_time"],
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"],
                "volume": candle["volume"],
            }
        ]
    )
    return store.upsert_candles(candle["symbol"], candle["timeframe"], frame)


class StreamManager:
    """Tracks who is watching what, and keeps exactly the needed upstreams open."""

    def __init__(self, broadcast: Broadcast):
        self._broadcast = broadcast
        self._watchers: dict[Series, set[object]] = {}
        self._tasks: dict[Series, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        # Server-side consumers of the same candles — paper trading, for one.
        # They are not browser clients and must keep receiving even when no
        # tab is open.
        self._listeners: list[Broadcast] = []

    def add_listener(self, listener: Broadcast) -> None:
        self._listeners.append(listener)

    async def _emit(self, candle: dict) -> None:
        for listener in self._listeners:
            try:
                await listener(candle)
            except Exception:
                log.exception("a candle listener failed; continuing")
        await self._broadcast({"type": "candle", **candle})

    def watched(self) -> list[dict]:
        return [
            {"symbol": s.symbol, "timeframe": s.timeframe, "viewers": len(v)}
            for s, v in self._watchers.items()
        ]

    async def subscribe(self, client: object, symbol: str, timeframe: str) -> None:
        if timeframe not in INTERVAL_MS:
            raise ValueError(f"unsupported timeframe: {timeframe}")

        series = Series(symbol.upper(), timeframe)
        async with self._lock:
            await self._drop_client(client)

            viewers = self._watchers.setdefault(series, set())
            viewers.add(client)

            if series not in self._tasks:
                log.info("opening live stream for %s %s", series.symbol, series.timeframe)
                self._tasks[series] = asyncio.create_task(self._run(series))

    async def unsubscribe(self, client: object) -> None:
        async with self._lock:
            await self._drop_client(client)

    async def _drop_client(self, client: object) -> None:
        """Remove a client from every series, closing upstreams left unwatched."""
        for series in list(self._watchers):
            viewers = self._watchers[series]
            viewers.discard(client)
            if viewers:
                continue

            self._watchers.pop(series, None)
            task = self._tasks.pop(series, None)
            if task:
                log.info("closing live stream for %s %s", series.symbol, series.timeframe)
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def close(self) -> None:
        async with self._lock:
            for task in self._tasks.values():
                task.cancel()
            for task in self._tasks.values():
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            self._tasks.clear()
            self._watchers.clear()

    async def _run(self, series: Series) -> None:
        """Hold one upstream connection open, reconnecting with backoff."""
        url = f"{WS_BASE}/{series.stream_name}"
        delay = RECONNECT_BASE_DELAY

        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    log.info("live stream connected: %s", series.stream_name)
                    delay = RECONNECT_BASE_DELAY  # a good connection resets the backoff
                    await self._broadcast(
                        {
                            "type": "stream_status",
                            "symbol": series.symbol,
                            "timeframe": series.timeframe,
                            "connected": True,
                        }
                    )

                    async for raw in ws:
                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        candle = parse_kline(payload)
                        if candle is None:
                            continue

                        if candle["closed"]:
                            # Off the event loop: DuckDB writes are blocking.
                            await asyncio.to_thread(persist, candle)

                        await self._emit(candle)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("live stream %s dropped (%s); retrying in %.0fs",
                            series.stream_name, exc, delay)
                await self._broadcast(
                    {
                        "type": "stream_status",
                        "symbol": series.symbol,
                        "timeframe": series.timeframe,
                        "connected": False,
                        "error": str(exc),
                    }
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
