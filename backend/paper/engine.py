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
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from backend.i18n import bi
from backend.strategy.base import normalize_signals
from backend.strategy.engine import BacktestConfig
from backend.strategy.position_model import execution_model_for, model_for

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
    # Same meaning as on the backtest Trade (backend/strategy/engine.py).
    points: float = 0.0
    contracts: int | None = None
    multiplier: float | None = None
    leverage: float | None = None

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

    # Exit levels attached to the open position, as prices. None means the leg
    # is not armed. They are cleared with the position, because a level for a
    # position that no longer exists would fire on the next one.
    stop_loss: float | None = None
    take_profit: float | None = None

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

    # Live-price bookkeeping for exits (on_tick). Not persisted: after a
    # restart the first tick starts a fresh range at the current price.
    _bar: dict | None = field(default=None, repr=False)
    _entry_bar: dict | None = field(default=None, repr=False)
    _reach: tuple | None = field(default=None, repr=False)
    _reach_bar: int | None = field(default=None, repr=False)

    # Rolling candle history the strategy is recomputed over.
    history: pd.DataFrame | None = None
    max_history: int = 3000

    def __post_init__(self) -> None:
        if self.equity == 0.0:
            self.equity = self.config.initial_capital

    # ------------------------------------------------------------------ fills

    @property
    def model(self):
        """Sizing, fees and marking, shared with the backtest engine."""
        return model_for(self.config)

    def _sizing(self):
        return self.model.restore(self.quantity, self.margin, self.entry_price)

    def _fill_price(self, price: float, direction: int) -> float:
        return self.model.fill(price, direction)

    def _close(self, exit_price: float, when: int, reason: str) -> PaperTrade:
        model = self.model
        sizing = self._sizing()
        pnl = model.pnl(sizing, self.entry_price, exit_price)
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
            points=(exit_price - self.entry_price) * self.position,
            contracts=sizing.contracts,
            multiplier=model.multiplier,
            leverage=(1 / self.config.contract.initial_margin_rate
                      if self.config.contract else self.config.leverage),
        )
        self.trades.append(trade)

        self.position = 0
        self.quantity = 0.0
        self.entry_price = 0.0
        self.margin = 0.0
        self.entry_time = 0
        self.stop_loss = None
        self.take_profit = None
        return trade

    def _open(
        self, price: float, when: int, direction: int, size_pct: float | None = None
    ) -> bool:
        """Open at ``price``. False when the equity cannot margin the position."""
        # A hand order may stake a different share of the account than the
        # strategy's configured size; everything downstream is unchanged.
        sizing = self.model.size(self.equity, price, direction, size_pct)
        if sizing is None:
            return False
        self.margin = sizing.margin
        self.quantity = sizing.quantity
        self.entry_price = price
        self.entry_time = when
        self.position = direction
        self.equity -= self.model.entry_fee(sizing, price)
        # The range the position has lived through starts at its own fill,
        # not at the extremes the bar had already printed before it.
        self._reach = (price, price)
        self._entry_bar = dict(self._bar) if self._bar else None
        return True

    # ------------------------------------------------------------- hand orders

    @property
    def is_manual(self) -> bool:
        return self.strategy_id == MANUAL_STRATEGY_ID

    def place_order(
        self,
        action: str,
        size_pct: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        leverage: float | None = None,
    ) -> dict:
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
        next_config = self.config
        if leverage is not None and target != 0:
            if not np.isfinite(leverage) or not 1 <= leverage <= 125:
                raise OrderRefused("bad_leverage", "Đòn bẩy phải từ 1x đến 125x.",
                                   "Leverage must be between 1x and 125x.")
            if self.config.contract:
                raise OrderRefused("contract_leverage", "Đòn bẩy hợp đồng do tỷ lệ ký quỹ quyết định.",
                                   "Contract leverage is determined by its margin rate.")
            next_config = replace(self.config, leverage=float(leverage))

        # Levels are checked against the price the order will fill at, not
        # against the last trade: a stop 1 tick under the last price is under
        # the fill too, and refusing on the wrong reference would reject an
        # order that is actually fine.
        if target != 0:
            self._validate_exits(
                target, self._fill_price(self.last_price, target), stop_loss, take_profit
            )

        if target == self.position:
            raise OrderRefused(
                "already_flat" if target == 0 else "already_in_position",
                "Đang không có vị thế nào để đóng." if target == 0
                else "Vị thế hiện tại đã đúng như vậy rồi.",
                "There is no position to close." if target == 0
                else "The position is already in that direction.",
            )

        # Refuse before anything changes: a reversal whose new side cannot be
        # margined must not close the old side first and then fail.
        if target != 0:
            equity_after_close = self.equity
            if self.position != 0:
                equity_after_close += self.model.pnl(
                    self._sizing(), self.entry_price,
                    self._fill_price(self.last_price, -self.position),
                )
            fill = self._fill_price(self.last_price, target)
            next_model = model_for(next_config)
            if equity_after_close <= 0 or next_model.size(equity_after_close, fill, target, size_pct) is None:
                if hasattr(next_model, "margin_per_contract"):
                    # Name both amounts: "not enough margin" alone does not say
                    # by how much, and on futures the gap is usually large.
                    c = next_config.contract
                    wanted = int(c.contracts) if c.sizing == "fixed" else 1
                    share = next_config.size_pct if size_pct is None else size_pct
                    need = wanted * next_model.margin_per_contract(fill) / 1e6
                    have = max(equity_after_close, 0.0) * (1.0 if c.sizing == "fixed" else share) / 1e6
                    raise OrderRefused(
                        "insufficient_margin",
                        f"Không đủ ký quỹ: {wanted} hợp đồng cần {need:,.2f} triệu VND ở giá {fill:,.1f}, "
                        f"vốn dành cho lệnh này chỉ có {have:,.2f} triệu VND.",
                        f"Not enough margin: {wanted} contract(s) need {need:,.2f} million VND at {fill:,.1f}, "
                        f"and the capital available to this order is {have:,.2f} million VND.",
                    )
                raise OrderRefused(
                    "insufficient_margin",
                    "Không đủ ký quỹ cho vị thế này ở giá hiện tại.",
                    "Not enough margin for this position at the current price.",
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
            # The old position closes under its original terms. Only the new
            # entry uses the selected leverage; config is persisted with it.
            self.config = next_config
            self._open(
                self._fill_price(self.last_price, target), when, target,
                size_pct=size_pct,
            )
            self.stop_loss = stop_loss
            self.take_profit = take_profit
            events.append({
                "type": "entry",
                "side": "long" if target > 0 else "short",
                "price": self.entry_price,
                "quantity": abs(self.quantity),
                "time": when,
                "manual": True,
                "leverage": (1 / self.config.contract.initial_margin_rate
                             if self.config.contract else self.config.leverage),
                "stop_loss": self.stop_loss,
                "take_profit": self.take_profit,
            })

        self.manual_orders += 1
        if not self.is_manual:
            self.manual_override = True
        # Whatever the strategy last wanted is no longer what the account holds.
        self.pending_signal = self.position
        self.updated_at = when
        return {"events": events, "snapshot": self.snapshot()}

    def _exit_level_hit(self, candle: dict) -> tuple[float, str] | None:
        """Which of stop loss / take profit this candle reached, if either.

        Both are filled **at their own price**, not at the candle's close: a
        resting order fills where it rests. Slippage is not applied on top,
        because the level is already the worst case the user asked for.

        When one candle spans both levels the stop wins. From daily OHLC there
        is no way to know which came first — the bar says the price visited
        both, not in what order — so the choice is between guessing favourably
        and guessing unfavourably, and a paper account that resolves its own
        ambiguities in the user's favour teaches the wrong lesson. This is the
        same reason slippage is always adverse (§3.1).
        """
        if self.position == 0:
            return None

        low = float(candle["low"])
        high = float(candle["high"])

        if self.position > 0:
            stop_hit = self.stop_loss is not None and low <= self.stop_loss
            target_hit = self.take_profit is not None and high >= self.take_profit
        else:
            stop_hit = self.stop_loss is not None and high >= self.stop_loss
            target_hit = self.take_profit is not None and low <= self.take_profit

        if stop_hit:
            return (self.stop_loss, "stop_loss")
        if target_hit:
            return (self.take_profit, "take_profit")
        return None

    def set_exits(
        self, stop_loss: float | None = None, take_profit: float | None = None
    ) -> dict:
        """Attach, move or clear the exit levels on the open position."""
        if self.position == 0:
            raise OrderRefused(
                "no_position",
                "Chưa có vị thế nào để đặt cắt lỗ hay chốt lời.",
                "There is no open position to attach a stop or a target to.",
            )
        self._validate_exits(self.position, self.entry_price, stop_loss, take_profit)
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.updated_at = int(time.time())
        return {"events": [], "snapshot": self.snapshot()}

    def _validate_exits(
        self,
        direction: int,
        reference: float,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> None:
        """Refuse a level that is already on the wrong side of the price.

        A stop above the entry on a long is not a stop — it fills instantly on
        the next candle and books a win as a "stop loss". Refusing is the only
        honest answer: silently accepting it produces a trade log that says
        something untrue about what the user intended.
        """
        for value, name, code in (
            (stop_loss, "stop_loss", "bad_stop"),
            (take_profit, "take_profit", "bad_target"),
        ):
            if value is None:
                continue
            if value <= 0:
                raise OrderRefused(
                    code,
                    "Giá phải lớn hơn 0.",
                    "The price must be above zero.",
                )
            # A stop sits below a long and above a short; a target is the
            # reverse. `direction` is +1 long, -1 short.
            wants_below = (name == "stop_loss") == (direction > 0)
            if wants_below and value >= reference:
                raise OrderRefused(
                    code,
                    f"{'Cắt lỗ' if name == 'stop_loss' else 'Chốt lời'} phải thấp hơn "
                    f"giá {reference:.8g} cho lệnh {'mua' if direction > 0 else 'bán'}.",
                    f"The {'stop' if name == 'stop_loss' else 'target'} must be below "
                    f"{reference:.8g} for a {'long' if direction > 0 else 'short'}.",
                )
            if not wants_below and value <= reference:
                raise OrderRefused(
                    code,
                    f"{'Cắt lỗ' if name == 'stop_loss' else 'Chốt lời'} phải cao hơn "
                    f"giá {reference:.8g} cho lệnh {'mua' if direction > 0 else 'bán'}.",
                    f"The {'stop' if name == 'stop_loss' else 'target'} must be above "
                    f"{reference:.8g} for a {'long' if direction > 0 else 'short'}.",
                )

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

    def on_tick(self, price: float, candle: dict | None = None) -> list[dict]:
        """A price update on the forming candle: marks to market, and fills a
        stop, a target or a liquidation the price has reached.

        Until 2026-09-17 this only marked to market and every exit waited for
        the bar to close: on a 5m chart a short's stop at 76 661.17 was crossed
        at 76 741 and the position stayed open until 19:15 (Nam's screenshot).
        A resting order fills when the price reaches it, so it is checked here,
        and filled at its own level exactly as the closed-bar check does (§3.1).

        ``candle`` is the forming bar the price came with. Its high and low
        count only from the fill onwards: a bar that opened before the entry
        has extremes the position never lived through, so for that bar the
        range is the ticks since the fill, widened by any new high or low the
        bar prints after it.
        """
        self.last_price = price
        bar_open = int(candle["open_time"]) // 1000 if candle else None
        if candle:
            self._bar = {"open_time": bar_open, "high": float(candle["high"]),
                         "low": float(candle["low"])}
        if self.position == 0:
            return []

        low, high = self._reach or (price, price)
        low, high = min(low, price), max(high, price)
        if candle:
            if bar_open >= self.entry_time:
                low, high = min(low, float(candle["low"])), max(high, float(candle["high"]))
            else:
                entry_bar = self._entry_bar if (self._entry_bar or {}).get("open_time") == bar_open else None
                if entry_bar and float(candle["high"]) > entry_bar["high"]:
                    high = max(high, float(candle["high"]))
                if entry_bar and float(candle["low"]) < entry_bar["low"]:
                    low = min(low, float(candle["low"]))
        self._reach = (low, high)
        self._reach_bar = bar_open

        events = self._exits_within(low, high, int(time.time()))
        if events:
            # Flat now: an old pending signal must not reopen at this bar's
            # open, which is already in the past. The strategy decides again
            # at the close.
            self.pending_signal = self.position
            self.updated_at = int(time.time())
        return events

    def _exits_within(self, low: float, high: float, when: int) -> list[dict]:
        """Liquidation, then stop and target, over a range the position lived through."""
        events: list[dict] = []
        if self.position == 0:
            return events
        liq = self.model.liquidation_price(self.entry_price, self.position)
        if liq is not None and (low <= liq if self.position > 0 else high >= liq):
            trade = self._close(liq, when, "liquidation")
            events.append({"type": "liquidation", "trade": trade.as_dict()})
            return events
        exit_hit = self._exit_level_hit({"low": low, "high": high})
        if exit_hit is not None:
            level, reason = exit_hit
            trade = self._close(level, when, reason)
            events.append({"type": "exit", "trade": trade.as_dict(), "reason": reason})
        return events

    def unrealized(self) -> float:
        if self.position == 0 or self.last_price == 0.0:
            return 0.0
        return self.model.unrealized(self._sizing(), self.entry_price, self.last_price)

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
            if self.pending_signal != 0 and self.equity > 0 and self._open(
                self._fill_price(open_price, self.pending_signal),
                when,
                self.pending_signal,
            ):
                events.append(
                    {
                        "type": "entry",
                        "side": "long" if self.position > 0 else "short",
                        "price": self.entry_price,
                        "quantity": abs(self.quantity),
                        "time": when,
                    }
                )

        # 2-3. Liquidation, then stop loss and take profit, against this
        #    candle's extremes: resting orders fill when the price *reaches*
        #    them, not when the candle happens to close past them. Live ticks
        #    usually got there first (on_tick); this catches a feed with no
        #    ticks (the VN poll) and a wick between two updates.
        #
        #    A position opened inside this bar only lived through the part of
        #    it after the fill. When ticks followed that part, their range is
        #    used; the bar's full high and low would include prices from
        #    before the position existed.
        #
        #    With no ticks at all for that bar (the VN poll delivers closed
        #    bars only), nothing is known about the part after the fill, so the
        #    bar is not judged: judging it measured a short at 1 978 with a
        #    stop at 1 985 as stopped by a 1 990 high printed before the click.
        #    The next bar, wholly after the entry, is judged in full.
        if self.position != 0:
            low, high = float(candle["low"]), float(candle["high"])
            judge = True
            if self.entry_time > when:
                if self._reach and self._reach_bar == when:
                    low, high = self._reach
                    if self._entry_bar and self._entry_bar.get("open_time") == when:
                        if high < float(candle["high"]) and float(candle["high"]) > self._entry_bar["high"]:
                            high = float(candle["high"])
                        if low > float(candle["low"]) and float(candle["low"]) < self._entry_bar["low"]:
                            low = float(candle["low"])
                else:
                    judge = False
            if judge:
                events.extend(self._exits_within(low, high, when))

        # 4. Append to history and decide what to do at the next open.
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
            "contracts": self._sizing().contracts if self.position != 0 else None,
            "multiplier": self.model.multiplier,
            "execution_model": execution_model_for(self.symbol, self.config),
            "entry_price": self.entry_price,
            "entry_time": self.entry_time,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
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
