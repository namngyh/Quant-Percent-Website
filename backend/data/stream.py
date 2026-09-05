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
from datetime import datetime, timezone
from dataclasses import dataclass

import pandas as pd
import websockets

from backend.data import market_vn, sources, store
from backend.data.binance import INTERVAL_MS

log = logging.getLogger(__name__)

# Binance's dedicated market-data host, reachable where the trading API is not.
WS_BASE = "wss://data-stream.binance.vision/ws"

RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 60.0

# --- Vietnam polling ---------------------------------------------------------
#
# The HOSE database has no push channel, so live bars come from polling it. The
# floor on freshness is the data itself: there are no ticks, so a 1m chart can
# only move once a minute however often we ask. Polling every few seconds
# during the session simply means a new bar appears as soon as it is written.
#
# Outside the session nothing is being written, so the loop backs right off
# rather than asking a question with a known answer several times a minute.
VN_POLL_SECONDS = 5
VN_IDLE_POLL_SECONDS = 120

# The Vietnamese session, 09:00-15:00 local, is 02:00-08:00 UTC. A margin
# either side covers the pre-open and the ATC auction.
VN_SESSION_START_UTC = 1
VN_SESSION_END_UTC = 9

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


def _vn_session_open(now: datetime | None = None) -> bool:
    """Is the Vietnamese market plausibly trading right now?

    Used only to decide how eagerly to poll, so the bounds are generous: being
    wrong costs one unnecessary query, not a missed bar.
    """
    now = now or datetime.now(timezone.utc)
    if now.weekday() >= 5:                       # Saturday, Sunday
        return False
    return VN_SESSION_START_UTC <= now.hour < VN_SESSION_END_UTC


class StreamManager:
    """Tracks who is watching what, and keeps exactly the needed upstreams open."""

    def __init__(self, broadcast: Broadcast):
        self._broadcast = broadcast
        self._watchers: dict[Series, set[object]] = {}
        self._tasks: dict[Series, asyncio.Task] = {}
        # The last status broadcast for each series.
        #
        # "connected" is announced once, when the upstream comes up. A client
        # that subscribes to a stream already running therefore never hears it
        # and sits on "connecting" forever while candles arrive perfectly well
        # — which happens with a second tab, with a paper session holding the
        # same series open, and on reload when the new socket subscribes before
        # the old one has finished disconnecting. Keeping the state lets
        # `status_for` answer the question instead of the client having to have
        # been listening at the right moment.
        self._status: dict[Series, dict] = {}
        self._lock = asyncio.Lock()
        # Server-side consumers of the same candles — paper trading, for one.
        # They are not browser clients and must keep receiving even when no
        # tab is open.
        self._listeners: list[Broadcast] = []

    def add_listener(self, listener: Broadcast) -> None:
        self._listeners.append(listener)

    async def _announce(self, series: Series, message: dict) -> None:
        """Broadcast a stream status and remember it."""
        self._status[series] = message
        await self._broadcast(message)

    def status_for(self, symbol: str, timeframe: str) -> dict | None:
        """The last known status of a series, or None if it has yet to report."""
        return self._status.get(Series(symbol.upper(), timeframe))

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
            self._status.pop(series, None)
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
        """Feed one series, by whichever means that market offers."""
        if sources.is_vietnam(series.symbol):
            await self._run_vn_poll(series)
        else:
            await self._run_binance(series)

    async def _run_vn_poll(self, series: Series) -> None:
        """Poll the team database and emit bars as they are written.

        Only *newly closed* bars are emitted. `market_vn.get_candles` already
        excludes the minute in progress, and inventing a forming candle from
        the last quote would put a bar on the chart that the database never
        recorded.

        Nothing is written to DuckDB here: this data lives in Postgres and is
        read from there every time.
        """
        _, bare = sources.parse(series.symbol)
        last_seen: int | None = None
        announced = False
        delay = VN_POLL_SECONDS

        while True:
            try:
                frame = await asyncio.to_thread(
                    market_vn.get_candles, bare, series.timeframe, None, None, 5
                )

                if not announced:
                    await self._announce(
                        series,
                        {
                            "type": "stream_status",
                            "symbol": series.symbol,
                            "timeframe": series.timeframe,
                            "connected": True,
                            "mode": "poll",
                        }
                    )
                    announced = True
                    delay = VN_POLL_SECONDS

                if not frame.empty:
                    rows = frame.to_dict("records")
                    if last_seen is None:
                        # First pass only establishes where we are; the chart
                        # already has these bars from its initial load.
                        last_seen = int(rows[-1]["open_time"])
                    else:
                        for row in rows:
                            open_time = int(row["open_time"])
                            if open_time <= last_seen:
                                continue
                            last_seen = open_time
                            await self._emit(
                                {
                                    "symbol": series.symbol,
                                    "timeframe": series.timeframe,
                                    "open_time": open_time,
                                    "open": float(row["open"]),
                                    "high": float(row["high"]),
                                    "low": float(row["low"]),
                                    "close": float(row["close"]),
                                    "volume": float(row["volume"]),
                                    "closed": True,
                                }
                            )

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("VN poll for %s failed: %s", series.symbol, exc)
                if announced:
                    await self._announce(
                        series,
                        {
                            "type": "stream_status",
                            "symbol": series.symbol,
                            "timeframe": series.timeframe,
                            "connected": False,
                            "error": str(exc),
                        }
                    )
                    announced = False
                delay = min(max(delay * 2, VN_POLL_SECONDS), VN_IDLE_POLL_SECONDS)

            await asyncio.sleep(delay if _vn_session_open() else VN_IDLE_POLL_SECONDS)

    async def _run_binance(self, series: Series) -> None:
        """Hold one upstream connection open, reconnecting with backoff."""
        url = f"{WS_BASE}/{series.stream_name}"
        delay = RECONNECT_BASE_DELAY

        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    log.info("live stream connected: %s", series.stream_name)
                    delay = RECONNECT_BASE_DELAY  # a good connection resets the backoff
                    await self._announce(
                        series,
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
                await self._announce(
                    series,
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
