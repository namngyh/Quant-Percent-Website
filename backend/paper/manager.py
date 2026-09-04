"""Owns the running paper-trading sessions.

A session must keep trading whether or not a browser is open — that is the
whole point of running one — so the manager holds its own subscription to the
live stream rather than piggybacking on a viewer's.

Sessions are written to DuckDB after every settled candle, so a restart resumes
with the same equity, position and trade history rather than starting over.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import pandas as pd

from backend.data import sources, store
from backend.notify import telegram
from backend.paper.engine import PaperSession, PaperTrade
from backend.strategy import registry
from backend.strategy.engine import BacktestConfig

log = logging.getLogger(__name__)

# Candles loaded when a session starts, so indicators are past their warm-up
# and the first live signal is as good as any later one.
WARMUP_BARS = 2000

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_sessions (
    id          VARCHAR PRIMARY KEY,
    symbol      VARCHAR NOT NULL,
    timeframe   VARCHAR NOT NULL,
    strategy_id VARCHAR NOT NULL,
    active      BOOLEAN NOT NULL,
    updated_at  BIGINT  NOT NULL,
    payload     VARCHAR NOT NULL
);
"""


class PaperManager:
    """Creates, feeds, persists and stops paper sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, PaperSession] = {}
        self._lock = asyncio.Lock()
        self._streams = None      # set by attach()
        self._notify = None       # async callable for pushing updates to tabs

    # ------------------------------------------------------------- lifecycle

    def attach(self, streams, notify) -> None:
        """Wire the manager to the stream manager and the broadcast channel."""
        self._streams = streams
        self._notify = notify

    def _ensure_schema(self) -> None:
        with store.transaction() as conn:
            conn.execute(SCHEMA)

    async def restore(self) -> None:
        """Reload sessions saved before the last shutdown and resubscribe."""
        self._ensure_schema()
        with store.transaction() as conn:
            rows = conn.execute(
                "SELECT payload FROM paper_sessions WHERE active = TRUE"
            ).fetchall()

        for (payload,) in rows:
            try:
                session = self._from_payload(json.loads(payload))
            except Exception:
                log.exception("could not restore a paper session; skipping it")
                continue

            self._sessions[session.id] = session
            await self._subscribe(session)
            log.info(
                "restored paper session %s (%s %s, %d trades)",
                session.id, session.symbol, session.timeframe, len(session.trades),
            )

    async def _subscribe(self, session: PaperSession) -> None:
        if self._streams is None:
            return
        # Keyed on the session, so a viewer closing their tab cannot take the
        # feed away from a session that is still trading.
        await self._streams.subscribe(("paper", session.id), session.symbol, session.timeframe)

    async def _unsubscribe(self, session: PaperSession) -> None:
        if self._streams is None:
            return
        await self._streams.unsubscribe(("paper", session.id))

    # ---------------------------------------------------------------- create

    async def start(
        self,
        strategy_id: str,
        symbol: str,
        timeframe: str,
        params: dict | None,
        config: BacktestConfig,
    ) -> PaperSession:
        spec = registry.get_spec(strategy_id)       # raises if unknown
        resolved = spec.resolve_params(params)

        session = PaperSession(
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            params=resolved,
            config=config,
        )

        # Seed with recent history so the strategy is warm from the first
        # candle rather than sitting flat through its own warm-up window.
        history = await asyncio.to_thread(
            sources.get_candles, symbol, timeframe, None, None, WARMUP_BARS
        )
        if not history.empty:
            session.history = history[
                ["open_time", "open", "high", "low", "close", "volume"]
            ].reset_index(drop=True)
            session.last_price = float(history["close"].iloc[-1])
            session.last_closed_time = int(history["open_time"].iloc[-1]) // 1000
            session.pending_signal = session._decide(self._signal_fn(session))

        async with self._lock:
            self._sessions[session.id] = session

        await self._subscribe(session)
        await asyncio.to_thread(self._persist, session)
        log.info("paper session %s started (%s %s %s)", session.id, strategy_id, symbol, timeframe)
        return session

    async def stop(self, session_id: str) -> PaperSession:
        session = self._require(session_id)
        session.active = False
        await self._unsubscribe(session)
        await asyncio.to_thread(self._persist, session)
        log.info("paper session %s stopped", session_id)
        return session

    async def resume(self, session_id: str) -> PaperSession:
        session = self._require(session_id)
        session.active = True
        await self._subscribe(session)
        await asyncio.to_thread(self._persist, session)
        return session

    async def delete(self, session_id: str) -> None:
        session = self._require(session_id)
        await self._unsubscribe(session)
        async with self._lock:
            self._sessions.pop(session_id, None)
        await asyncio.to_thread(self._delete_row, session_id)
        log.info("paper session %s deleted", session_id)

    def _require(self, session_id: str) -> PaperSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"unknown paper session: {session_id}")
        return session

    # ------------------------------------------------------------------ feed

    def _signal_fn(self, session: PaperSession):
        spec = registry.get_spec(session.strategy_id)

        def signal_fn(history: pd.DataFrame):
            frame = history.copy()
            frame.index = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
            return spec.signals(frame, session.params)

        return signal_fn

    async def on_candle(self, candle: dict) -> None:
        """Called for every candle the stream delivers, forming or closed."""
        symbol = candle.get("symbol")
        timeframe = candle.get("timeframe")
        closed = bool(candle.get("closed"))

        targets = [
            s for s in self._sessions.values()
            if s.active and s.symbol == symbol and s.timeframe == timeframe
        ]
        if not targets:
            return

        for session in targets:
            if not closed:
                session.on_tick(float(candle["close"]))
                continue

            # Strategy evaluation is pandas work; keep it off the event loop so
            # a slow strategy cannot stall the price feed for everything else.
            events = await asyncio.to_thread(
                session.on_closed_candle, candle, self._signal_fn(session)
            )
            await asyncio.to_thread(self._persist, session)

            # Push to the phone as well. Failures are logged inside the
            # notifier and never interrupt trading.
            if events and telegram.configured():
                snapshot = session.snapshot()
                for event in events:
                    text = telegram.format_paper_event(snapshot, event)
                    if text:
                        await telegram.send(text)

            if self._notify:
                for event in events:
                    await self._notify(
                        {"type": "paper_event", "session_id": session.id, "event": event}
                    )
                await self._notify(
                    {"type": "paper_update", "session": session.snapshot()}
                )

    # ----------------------------------------------------------- persistence

    def _persist(self, session: PaperSession) -> None:
        self._ensure_schema()
        payload = json.dumps(self._to_payload(session))
        with store.transaction() as conn:
            conn.execute("DELETE FROM paper_sessions WHERE id = ?", [session.id])
            conn.execute(
                "INSERT INTO paper_sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    session.id, session.symbol, session.timeframe, session.strategy_id,
                    session.active, int(time.time()), payload,
                ],
            )

    def _delete_row(self, session_id: str) -> None:
        with store.transaction() as conn:
            conn.execute("DELETE FROM paper_sessions WHERE id = ?", [session_id])

    def _to_payload(self, s: PaperSession) -> dict:
        # History is deliberately not saved: it is reloaded from the candle
        # store on restore, which is the same data and always current.
        return {
            "id": s.id, "strategy_id": s.strategy_id, "symbol": s.symbol,
            "timeframe": s.timeframe, "params": s.params, "config": s.config.as_dict(),
            "created_at": s.created_at, "updated_at": s.updated_at, "active": s.active,
            "equity": s.equity, "position": s.position, "quantity": s.quantity,
            "entry_price": s.entry_price, "entry_time": s.entry_time, "margin": s.margin,
            "pending_signal": s.pending_signal, "last_price": s.last_price,
            "last_closed_time": s.last_closed_time, "bars_seen": s.bars_seen,
            "trades": [t.as_dict() for t in s.trades],
        }

    def _from_payload(self, d: dict) -> PaperSession:
        session = PaperSession(
            strategy_id=d["strategy_id"], symbol=d["symbol"], timeframe=d["timeframe"],
            params=d.get("params", {}), config=BacktestConfig(**d["config"]),
            id=d["id"], created_at=d["created_at"], updated_at=d["updated_at"],
            active=d.get("active", True),
        )
        session.equity = d["equity"]
        session.position = d["position"]
        session.quantity = d["quantity"]
        session.entry_price = d["entry_price"]
        session.entry_time = d["entry_time"]
        session.margin = d["margin"]
        session.pending_signal = d["pending_signal"]
        session.last_price = d["last_price"]
        session.last_closed_time = d["last_closed_time"]
        session.bars_seen = d["bars_seen"]
        session.trades = [PaperTrade(**t) for t in d.get("trades", [])]

        history = sources.get_candles(session.symbol, session.timeframe, limit=WARMUP_BARS)
        if not history.empty:
            session.history = history[
                ["open_time", "open", "high", "low", "close", "volume"]
            ].reset_index(drop=True)

        return session

    # -------------------------------------------------------------- readouts

    def list(self) -> list[dict]:
        return [s.snapshot() for s in sorted(
            self._sessions.values(), key=lambda s: s.created_at, reverse=True
        )]

    def get(self, session_id: str) -> dict:
        return self._require(session_id).snapshot()

    async def close(self) -> None:
        for session in self._sessions.values():
            try:
                self._persist(session)
            except Exception:
                log.exception("could not persist paper session %s", session.id)


manager = PaperManager()
