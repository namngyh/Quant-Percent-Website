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

**Manual orders are the one deliberate exception to that timing**, and the
reason is worth stating. The bar-i to bar-i+1 rule exists to stop a *strategy*
using a price it could not have known at decision time. A person clicking Buy
has no such problem: they are acting on a price on their screen, right now.
Holding their order until the next candle opens would fill them at a price they
never saw, which is a worse lie than the one the rule prevents. So a manual
order fills at the last traded price, immediately — with the same adverse
slippage and the same both-sides fees as everything else.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.i18n import bi
from backend.strategy.base import normalize_signals
from backend.strategy.engine import BacktestConfig

# The strategy id a hand-traded session carries.
MANUAL_STRATEGY_ID = "manual"


class OrderRefused(Exception):
    """A hand order that will not be filled, and why.

    Carries a stable ``code`` alongside the text. The interface must colour and
    branch on the code, never on the sentence: the statistics panel already
    broke once by matching a Vietnamese string that later became a {vi, en}
    pair, and it broke silently (§2.4).
    """

    def __init__(self, code: str, vi: str, en: str) -> None:
        super().__init__(vi)
        self.code = code
        self.message = bi(vi, en)

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


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

    # "manual" for a hand-traded session with no strategy behind it. The
    # persisted table declares this column NOT NULL, so a sentinel keeps manual
    # sessions on the existing schema rather than forcing a migration.
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

    # Set the moment a hand order is placed on a session that has a strategy.
    # Two things must not both be steering one position: if the strategy kept
    # deciding, the next candle would quietly undo whatever the user just did,
    # and the trade log would show a reversal nobody asked for. While this is
    # on, the strategy is still computed and reported but no longer trades.
    manual_override: bool = False
    manual_orders: int = 0

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

    def _open(
        self, price: float, when: int, direction: int, size_pct: float | None = None
    ) -> None:
        # A hand order may stake a different share of the account than the
        # strategy's configured size; everything downstream is unchanged.
        self.margin = self.equity * (
            self.config.size_pct if size_pct is None else size_pct
        )
        notional = self.margin * self.config.leverage
        self.quantity = notional / price * direction
        self.entry_price = price
        self.entry_time = when
        self.position = direction
        self.equity -= notional * self.config.fee

    # ------------------------------------------------------------- hand orders

    @property
    def is_manual(self) -> bool:
        return self.strategy_id == MANUAL_STRATEGY_ID

    def place_order(self, action: str, size_pct: float | None = None) -> dict:
        """Open, reverse or close a position by hand, at the live price.

        ``action`` is "long", "short" or "close". Returns the events booked, in
        the same shape ``on_closed_candle`` returns them, so both paths reach
        the interface identically.

        Raises ValueError with a reason a person can act on. Refusing loudly
        matters more here than anywhere else in the system: this is the one
        place a user's own money-shaped intention enters, and a silently
        swallowed order looks exactly like an order that was filled.
        """
        if action not in ("long", "short", "close"):
            raise OrderRefused(
                "unknown_action",
                f"Lệnh không hợp lệ: '{action}'. Chọn long, short hoặc close.",
                f"Unknown order: '{action}'. Choose long, short or close.",
            )
        if not self.active:
            raise OrderRefused(
                "session_stopped",
                "Phiên đã dừng. Hãy chạy lại phiên trước khi đặt lệnh.",
                "This session is stopped. Resume it before placing an order.",
            )
        if self.last_price <= 0:
            raise OrderRefused(
                "no_price",
                "Chưa có giá nào cho mã này. Hãy đợi nến đầu tiên về.",
                "No price has arrived for this symbol yet. Wait for the first candle.",
            )
        if size_pct is not None and not (0.0 < size_pct <= 1.0):
            raise OrderRefused(
                "bad_size",
                "Cỡ vị thế phải nằm trong khoảng 0 đến 100% vốn.",
                "Position size must be above 0 and at most 100% of equity.",
            )

        target = {"long": 1, "short": -1, "close": 0}[action]
        if target == self.position:
            raise OrderRefused(
                "already_flat" if target == 0 else "already_in_position",
                "Đang không có vị thế nào để đóng." if target == 0
                else "Vị thế hiện tại đã đúng như vậy rồi.",
                "There is no position to close." if target == 0
                else "The position is already in that direction.",
            )

        when = int(time.time())
        events: list[dict] = []

        # Close first, then open — a reversal is two fills, and both pay their
        # own fee. Netting them into one would understate the cost of flipping.
        if self.position != 0:
            trade = self._close(
                self._fill_price(self.last_price, -self.position), when, "manual"
            )
            events.append({"type": "exit", "trade": trade.as_dict()})

        if target != 0:
            if self.equity <= 0:
                raise OrderRefused(
                    "no_equity",
                    "Tài khoản đã hết vốn.",
                    "The account has no equity left.",
                )
            self._open(
                self._fill_price(self.last_price, target), when, target,
                size_pct=size_pct,
            )
            events.append({
                "type": "entry",
                "side": "long" if target > 0 else "short",
                "price": self.entry_price,
                "quantity": abs(self.quantity),
                "time": when,
                "manual": True,
            })

        self.manual_orders += 1
        if not self.is_manual:
            self.manual_override = True
        # Whatever the strategy last wanted is no longer what the account holds.
        self.pending_signal = self.position
        self.updated_at = when
        return {"events": events, "snapshot": self.snapshot()}

    def resume_strategy(self) -> None:
        """Hand the position back to the strategy after a manual intervention."""
        if self.is_manual:
            raise OrderRefused(
                "no_strategy",
                "Phiên này không có chiến lược nào để trả lại quyền.",
                "This session has no strategy to hand control back to.",
            )
        self.manual_override = False

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
        # A manual session has no strategy, and a session under manual override
        # has one that is no longer allowed to trade. Both hold the position
        # exactly as the user left it.
        if self.is_manual or self.manual_override:
            return self.position
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
            "is_manual": self.is_manual,
            "manual_override": self.manual_override,
            "manual_orders": self.manual_orders,
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
