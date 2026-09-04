"""The browser-facing live WebSocket.

One connection per tab carries everything that arrives without being asked
for: live candles, upstream connection status, and notice that a plugin file
on disk changed.

Watching the plugin directory is what makes editing an indicator feel live.
The catalog was always re-scanned per request, so a refresh already picked up
an edit — the watcher removes the refresh, which is the whole point when you
are iterating on a formula.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.config import settings
from backend.data import sources
from backend.data.stream import StreamManager

log = logging.getLogger(__name__)
router = APIRouter(tags=["live"])

# Debounce for file events: editors write in bursts (temp file, rename, chmod),
# and each burst should produce one reload, not five.
WATCH_DEBOUNCE_MS = 400


class Hub:
    """Fans messages out to every connected tab."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.streams = StreamManager(self.broadcast)
        self._watcher: asyncio.Task | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        log.info("live client connected (%d total)", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        await self.streams.unsubscribe(ws)
        log.info("live client disconnected (%d left)", len(self._clients))

    async def broadcast(self, message: dict) -> None:
        async with self._lock:
            targets = list(self._clients)

        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                # The socket went away between our snapshot and the send.
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    def start_plugin_watcher(self) -> None:
        if self._watcher is None:
            self._watcher = asyncio.create_task(self._watch_plugins())

    async def _watch_plugins(self) -> None:
        """Tell every tab when a plugin file changes on disk."""
        try:
            from watchfiles import awatch
        except ImportError:
            log.warning("watchfiles unavailable; plugin hot-reload is off")
            return

        directory = settings.project_root / "plugins"
        directory.mkdir(parents=True, exist_ok=True)

        try:
            async for changes in awatch(directory, debounce=WATCH_DEBOUNCE_MS):
                kinds = set()
                for _, raw_path in changes:
                    path = Path(raw_path)
                    if path.suffix != ".py" or path.name.startswith("_"):
                        continue
                    if "strategies" in path.parts:
                        kinds.add("strategies")
                    elif "indicators" in path.parts:
                        kinds.add("indicators")

                for kind in kinds:
                    log.info("plugin change detected in %s", kind)
                    await self.broadcast({"type": "plugins_changed", "kind": kind})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("plugin watcher stopped")

    async def close(self) -> None:
        if self._watcher:
            self._watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watcher
            self._watcher = None

        await self.streams.close()

        async with self._lock:
            for ws in list(self._clients):
                with contextlib.suppress(Exception):
                    await ws.close()
            self._clients.clear()


hub = Hub()


@router.websocket("/ws/live")
async def live(ws: WebSocket) -> None:
    """Live channel. Clients send {"action": "subscribe", symbol, timeframe}."""
    await hub.connect(ws)
    try:
        while True:
            message = await ws.receive_json()
            action = message.get("action")

            if action == "subscribe":
                symbol = message.get("symbol") or settings.chart.default_symbol

                # Both markets are live now: Binance pushes over a socket,
                # the HOSE database is polled. The stream manager picks the
                # right one from the symbol.
                try:
                    await hub.streams.subscribe(
                        ws,
                        symbol,
                        message.get("timeframe") or settings.chart.default_timeframe,
                    )
                except ValueError as exc:
                    await ws.send_json({"type": "error", "message": str(exc)})

            elif action == "unsubscribe":
                await hub.streams.unsubscribe(ws)

            elif action == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("live socket failed")
    finally:
        await hub.disconnect(ws)


@router.get("/api/live/status", tags=["live"])
def status() -> dict:
    """Which series currently have an upstream connection open."""
    return {"streams": hub.streams.watched()}
