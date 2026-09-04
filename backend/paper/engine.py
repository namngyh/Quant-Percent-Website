"""Paper trading: a strategy run forward against live candles.

The point of paper trading is to find out whether a backtest was telling the
truth, so this must use the *same* execution rules as the backtest — otherwise
a difference in results tells you nothing about the strategy.

So the timing is identical: a signal computed at the close of bar *i* is filled
at the **open of bar i+1**. Live, that means the signal is held pending until
the next candle closes, at which point its opening price is known and the fill
is booked there. The fill price is therefore exactly the one the backtest would
have used, and ``tests/test_paper.py`` asserts that by replaying history
through both and comparing the trades.

Marking to market happens on every tick so the open position shows a live P&L,
but nothing is ever *traded* on an unfinished candle.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.strategy.base import normalize_signals
from backend.strategy.engine import BacktestConfig


@dataclass
class PaperTrade:
    side: str
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    return_pct: float
    exit_reason: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class PaperSession:
    """One strategy trading forward on one series."""

    strategy_id: str
    symbol: str
    timeframe: str
    params: dict = field(default_factory=dict)
    config: BacktestConfig = field(default_factory=BacktestConfig)

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    active: bool = True

    # --- account ---
    equity: float = 0.0
    position: int = 0          # -1 short, 0 flat, 1 long
    quantity: float = 0.0      # signed, base units
    entry_price: float = 0.0
    entry_time: int = 0
    margin: float = 0.0

    # A signal is computed when a candle closes and filled at the next open,
    # so it waits here in between.
    pending_signal: int = 0

    last_price: float = 0.0
    last_closed_time: int = 0
    bars_seen: int = 0
    trades: list[PaperTrade] = field(default_factory=list)

    # Rolling candle history the strategy is recomputed over.
    history: pd.DataFrame | None = None
    max_history: int = 3000

    def __post_init__(self) -> None:
        if self.equity == 0.0:
            self.equity = self.config.initial_capital

    # ------------------------------------------------------------------ fills

    def _fill_price(self, price: float, direction: int) -> float:
        return price * (1.0 + self.config.slippage * direction)

    def _close(self, exit_price: float, when: int, reason: str) -> PaperTrade:
        exit_fee = abs(self.quantity) * exit_price * self.config.fee
        pnl = self.quantity * (exit_price - self.entry_price) - exit_fee
        self.equity += pnl

        trade = PaperTrade(
            side="long" if self.position > 0 else "short",
            entry_time=self.entry_time,
            exit_time=when,
            entry_price=self.entry_price,
            exit_price=exit_price,
            quantity=abs(self.quantity),
            pnl=pnl,
            return_pct=(pnl / self.margin * 100.0) if self.margin > 0 else 0.0,
            exit_reason=reason,
        )
        self.trades.append(trade)

        self.position = 0
        self.quantity = 0.0
        self.entry_price = 0.0
        self.margin = 0.0
        self.entry_time = 0
        return trade

    def _open(self, price: float, when: int, direction: int) -> None:
        self.margin = self.equity * self.config.size_pct
        notional = self.margin * self.config.leverage
        self.quantity = notional / price * direction
        self.entry_price = price
        self.entry_time = when
        self.position = direction
        self.equity -= notional * self.config.fee

    # ------------------------------------------------------------------ ticks

    def on_tick(self, price: float) -> None:
        """A price update on the forming candle. Marks to market, never trades."""
        self.last_price = price

    def unrealized(self) -> float:
        if self.position == 0 or self.last_price == 0.0:
            return 0.0
        return self.quantity * (self.last_price - self.entry_price)

    def equity_now(self) -> float:
        return max(self.equity + self.unrealized(), 0.0)

    # ---------------------------------------------------------------- candles

    def on_closed_candle(self, candle: dict, signal_fn) -> list[dict]:
        """Advance one settled candle. Returns the events that occurred.

        ``signal_fn(history_df) -> Series`` recomputes the strategy over the
        rolling window; only its final value is used, as the decision made at
        this candle's close.
        """
        events: list[dict] = []
        when = int(candle["open_time"]) // 1000
        open_price = float(candle["open"])

        # 1. Fill the signal that was decided at the previous close, using this
        #    candle's open — the price a real order placed then would have got.
        if self.pending_signal != self.position:
            if self.position != 0:
                trade = self._close(
                    self._fill_price(open_price, -self.position), when, "signal"
                )
                events.append({"type": "exit", "trade": trade.as_dict()})
            if self.pending_signal != 0 and self.equity > 0:
                self._open(
                    self._fill_price(open_price, self.pending_signal),
                    when,
                    self.pending_signal,
                )
                events.append(
                    {
                        "type": "entry",
                        "side": "long" if self.position > 0 else "short",
                        "price": self.entry_price,
                        "quantity": abs(self.quantity),
                        "time": when,
                    }
                )

        # 2. Liquidation, checked against this candle's adverse extreme.
        if self.position != 0 and self.config.leverage > 1.0:
            liq = self.entry_price * (1.0 - self.position / self.config.leverage)
            hit = float(candle["low"]) <= liq if self.position > 0 else float(candle["high"]) >= liq
            if hit:
                trade = self._close(liq, when, "liquidation")
                events.append({"type": "liquidation", "trade": trade.as_dict()})

        # 3. Append to history and decide what to do at the next open.
        self._append(candle)
        self.pending_signal = self._decide(signal_fn)

        self.last_price = float(candle["close"])
        self.last_closed_time = when
        self.bars_seen += 1
        self.updated_at = int(time.time())

        return events

    def _append(self, candle: dict) -> None:
        row = {
            "open_time": int(candle["open_time"]),
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": float(candle.get("volume", 0.0)),
        }
        frame = pd.DataFrame([row])

        if self.history is None or self.history.empty:
            self.history = frame
            return

        # Replace rather than append when the same candle arrives twice, which
        # happens after a reconnect replays the most recent bar.
        self.history = self.history[self.history["open_time"] != row["open_time"]]
        self.history = pd.concat([self.history, frame], ignore_index=True)
        if len(self.history) > self.max_history:
            self.history = self.history.iloc[-self.max_history :].reset_index(drop=True)

    def _decide(self, signal_fn) -> int:
        if self.history is None or self.history.empty:
            return 0
        try:
            raw = signal_fn(self.history)
        except Exception:
            # A strategy that throws should stall the session, not crash the
            # server or silently invent a position.
            return self.pending_signal

        signals = normalize_signals(raw, self.history.index)
        return int(signals[-1]) if len(signals) else 0

    # --------------------------------------------------------------- snapshot

    def snapshot(self) -> dict:
        pnls = np.array([t.pnl for t in self.trades], dtype="float64")
        wins = pnls[pnls > 0]
        equity = self.equity_now()

        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "params": self.params,
            "config": self.config.as_dict(),
            "active": self.active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "bars_seen": self.bars_seen,
            "last_closed_time": self.last_closed_time,
            "position": self.position,
            "quantity": abs(self.quantity),
            "entry_price": self.entry_price,
            "entry_time": self.entry_time,
            "last_price": self.last_price,
            "pending_signal": self.pending_signal,
            "realized_equity": self.equity,
            "unrealized_pnl": self.unrealized(),
            "equity": equity,
            "return_pct": (equity / self.config.initial_capital - 1.0) * 100.0,
            "num_trades": len(self.trades),
            "num_wins": int(wins.size),
            "win_rate_pct": (wins.size / len(self.trades) * 100.0) if self.trades else 0.0,
            "realized_pnl": float(pnls.sum()) if pnls.size else 0.0,
            "trades": [t.as_dict() for t in self.trades],
        }
