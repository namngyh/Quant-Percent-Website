"""Paper-trading checks.

Run directly:  .venv\\Scripts\\python.exe tests/test_paper.py

The central check is that replaying history one candle at a time through the
paper session produces exactly the trades the backtest produces over the same
history. Paper trading exists to test whether a backtest was honest; if the two
disagree, a difference in results says nothing about the strategy.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backend.paper.engine import (  # noqa: E402
    MANUAL_STRATEGY_ID,
    OrderRefused,
    PaperSession,
)
from backend.strategy import registry  # noqa: E402
from backend.strategy.base import normalize_signals  # noqa: E402
from backend.strategy.engine import BacktestConfig, run_backtest  # noqa: E402

HOUR = 3_600_000


def order(session, action, **kwargs):
    """Place a hand order and deliver the next bar, whose open fills it.

    Hand orders fill at the next bar's open (2026-09-16), so a test that wants
    the fill must hand the session that bar. Its open is the session's last
    price, which keeps every cost figure below measured at an unchanged price.
    A refusal at placement raises before any bar is delivered.
    """
    placed = session.place_order(action, now=0, **kwargs)
    bar_open = (session.last_bar_open + 60) * 1000
    price = session.last_price
    events = session.on_forming_candle(
        {"open_time": bar_open, "open": price, "high": price, "low": price, "close": price})
    return {"placed": placed, "events": events, "snapshot": session.snapshot()}

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def close_to(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(b))


def series(n=400, seed=5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.012, n)))
    return pd.DataFrame(
        {
            "open_time": [i * HOUR for i in range(n)],
            "open": closes,
            "high": closes * 1.006,
            "low": closes * 0.994,
            "close": closes,
            "volume": np.ones(n),
        }
    )


def replay(df: pd.DataFrame, strategy_id: str, config: BacktestConfig, params=None):
    """Feed every candle to a fresh paper session, one at a time."""
    spec = registry.get_spec(strategy_id)
    resolved = spec.resolve_params(params)

    def signal_fn(history: pd.DataFrame):
        frame = history.copy()
        frame.index = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
        return spec.signals(frame, resolved)

    session = PaperSession(
        strategy_id=strategy_id,
        symbol="TEST",
        timeframe="1h",
        params=resolved,
        config=config,
    )

    for row in df.to_dict("records"):
        session.on_closed_candle(row, signal_fn)

    return session


# --------------------------------------------------------------------------

@check("a fresh session starts flat with the configured capital")
def _():
    s = PaperSession("example_ema_cross", "BTCUSDT", "1h",
                     config=BacktestConfig(initial_capital=25_000))
    snap = s.snapshot()
    assert snap["equity"] == 25_000 and snap["position"] == 0, snap
    assert snap["num_trades"] == 0 and snap["return_pct"] == 0.0, snap


@check("ticks mark to market but never open a position")
def _():
    s = PaperSession("example_ema_cross", "BTCUSDT", "1h")
    for price in (100.0, 120.0, 90.0):
        s.on_tick(price)
    assert s.position == 0 and not s.trades, s.snapshot()
    assert s.equity_now() == s.config.initial_capital


@check("replaying history reproduces the backtest trades exactly")
def _():
    df = series()
    cfg = BacktestConfig(fee=0.0004, slippage=0.0002)

    spec = registry.get_spec("example_ema_cross")
    resolved = spec.resolve_params(None)
    frame = df.copy()
    frame.index = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    signal = normalize_signals(spec.signals(frame, resolved), frame.index, spec.side)
    expected = run_backtest(df, signal, cfg)

    session = replay(df, "example_ema_cross", cfg)

    # The backtest force-closes whatever is open when the data runs out; a live
    # session simply still holds it. Compare only the settled trades.
    settled = [t for t in expected.trades if t.exit_reason != "end_of_data"]
    assert len(session.trades) == len(settled), (len(session.trades), len(settled))
    assert len(settled) > 3, "test data should produce several trades"

    for got, want in zip(session.trades, settled, strict=True):
        assert got.side == want.side, (got, want)
        assert got.entry_time == want.entry_time, (got.entry_time, want.entry_time)
        assert got.exit_time == want.exit_time, (got.exit_time, want.exit_time)
        assert close_to(got.entry_price, want.entry_price), (got.entry_price, want.entry_price)
        assert close_to(got.exit_price, want.exit_price), (got.exit_price, want.exit_price)
        assert close_to(got.pnl, want.pnl), (got.pnl, want.pnl)


@check("equity matches the backtest, up to the cost of the still-open position")
def _():
    # The backtest force-closes whatever is open when data runs out and pays
    # the exit costs; a live session is still holding it, marked at the close.
    # So the gap should be exactly the exit slippage plus the exit fee — an
    # equality check here would be asserting the wrong thing.
    df = series(seed=11)
    cfg = BacktestConfig(fee=0.0004, slippage=0.0002)

    spec = registry.get_spec("example_ema_cross")
    resolved = spec.resolve_params(None)
    frame = df.copy()
    frame.index = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    signal = normalize_signals(spec.signals(frame, resolved), frame.index, spec.side)
    expected = run_backtest(df, signal, cfg)

    session = replay(df, "example_ema_cross", cfg)
    final_close = float(df["close"].iloc[-1])
    session.on_tick(final_close)

    assert session.position != 0, "this fixture should end holding a position"
    qty = abs(session.quantity)
    exit_slippage = qty * final_close * cfg.slippage
    exit_fee = qty * final_close * (1 - cfg.slippage) * cfg.fee

    gap = session.equity_now() - float(expected.equity[-1])
    assert close_to(gap, exit_slippage + exit_fee, tol=1e-6), (
        gap, exit_slippage + exit_fee
    )


@check("equity matches the backtest exactly once the position is closed out")
def _():
    # A flat-ending fixture leaves nothing open, so the two must agree outright.
    df = series(n=300, seed=3)
    cfg = BacktestConfig(fee=0.0004, slippage=0.0002)

    spec = registry.get_spec("example_rsi_reversal")
    resolved = spec.resolve_params(None)
    frame = df.copy()
    frame.index = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    signal = normalize_signals(spec.signals(frame, resolved), frame.index, spec.side)
    expected = run_backtest(df, signal, cfg)

    session = replay(df, "example_rsi_reversal", cfg)
    session.on_tick(float(df["close"].iloc[-1]))

    if session.position == 0:
        assert close_to(session.equity_now(), float(expected.equity[-1]), tol=1e-6), (
            session.equity_now(), float(expected.equity[-1])
        )
    else:
        # Still holding: fall back to comparing realised trades only.
        settled = [t for t in expected.trades if t.exit_reason != "end_of_data"]
        assert len(session.trades) == len(settled), (len(session.trades), len(settled))


@check("a signal is never filled on the candle that produced it")
def _():
    # A step up on bar 2: a strategy going long at bar 2's close must be filled
    # at bar 3's open, not bar 2's close.
    closes = [100.0, 100.0, 100.0, 200.0, 200.0]
    df = pd.DataFrame({
        "open_time": [i * HOUR for i in range(5)],
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [1.0] * 5,
    })

    def always_long(history):
        return pd.Series(1, index=history.index)

    s = PaperSession("x", "T", "1h", config=BacktestConfig(fee=0, slippage=0))
    for row in df.to_dict("records"):
        s.on_closed_candle(row, always_long)

    assert s.position == 1, s.snapshot()
    # Decided at bar 0's close, filled at bar 1's open of 100 — not bar 0's.
    assert close_to(s.entry_price, 100.0), s.entry_price
    assert s.entry_time == HOUR // 1000, s.entry_time


@check("the same candle arriving twice does not double-count")
def _():
    df = series(n=120)
    cfg = BacktestConfig(fee=0.0004, slippage=0.0002)
    spec = registry.get_spec("example_ema_cross")
    resolved = spec.resolve_params(None)

    def signal_fn(history):
        frame = history.copy()
        frame.index = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
        return spec.signals(frame, resolved)

    clean = PaperSession("example_ema_cross", "T", "1h", params=resolved, config=cfg)
    dupes = PaperSession("example_ema_cross", "T", "1h", params=resolved, config=cfg)

    rows = df.to_dict("records")
    for row in rows:
        clean.on_closed_candle(row, signal_fn)
    for i, row in enumerate(rows):
        dupes.on_closed_candle(row, signal_fn)
        if i % 7 == 0:                      # a reconnect replaying the last bar
            dupes.on_closed_candle(row, signal_fn)

    assert len(dupes.history) == len(clean.history), (len(dupes.history), len(clean.history))


@check("a strategy that raises stalls the session instead of inventing a position")
def _():
    df = series(n=60)

    def explodes(history):
        raise RuntimeError("boom")

    s = PaperSession("x", "T", "1h", config=BacktestConfig(fee=0, slippage=0))
    for row in df.to_dict("records"):
        s.on_closed_candle(row, explodes)

    assert s.position == 0 and not s.trades, s.snapshot()
    assert s.bars_seen == len(df), s.bars_seen


@check("leverage liquidates a paper position on the candle low")
def _():
    closes = [100.0, 100.0, 100.0]
    df = pd.DataFrame({
        "open_time": [i * HOUR for i in range(3)],
        "open": closes, "high": [100.0, 100.0, 100.0],
        "low": [100.0, 100.0, 85.0], "close": closes, "volume": [1.0] * 3,
    })

    def always_long(history):
        return pd.Series(1, index=history.index)

    s = PaperSession("x", "T", "1h",
                     config=BacktestConfig(fee=0, slippage=0, leverage=10))
    for row in df.to_dict("records"):
        s.on_closed_candle(row, always_long)

    assert len(s.trades) == 1, s.trades
    assert s.trades[0].exit_reason == "liquidation", s.trades[0]
    assert close_to(s.trades[0].exit_price, 90.0), s.trades[0].exit_price
    assert close_to(s.equity_now(), 0.0), s.equity_now()


@check("snapshot reports an open position with live unrealized P&L")
def _():
    closes = [100.0, 100.0, 100.0]
    df = pd.DataFrame({
        "open_time": [i * HOUR for i in range(3)],
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [1.0] * 3,
    })

    def always_long(history):
        return pd.Series(1, index=history.index)

    s = PaperSession("x", "T", "1h", config=BacktestConfig(fee=0, slippage=0))
    for row in df.to_dict("records"):
        s.on_closed_candle(row, always_long)

    s.on_tick(110.0)                       # price moves on the forming candle
    snap = s.snapshot()
    assert snap["position"] == 1, snap
    assert close_to(snap["unrealized_pnl"], 1000.0), snap["unrealized_pnl"]
    assert close_to(snap["equity"], 11_000.0), snap["equity"]
    assert snap["num_trades"] == 0, "an open position is not a completed trade"


# --------------------------------------------------------------------------

# ======================================================= hand-placed orders

def manual(**over):
    """A hand-traded session sitting at a price of 100."""
    cfg = BacktestConfig(**{
        "initial_capital": 10_000.0, "size_pct": 1.0, "leverage": 1.0,
        "fee": 0.0004, "slippage": 0.0002, **over,
    })
    s = PaperSession(strategy_id=MANUAL_STRATEGY_ID, symbol="BTCUSDT",
                     timeframe="1m", config=cfg)
    s.last_price = 100.0
    return s


@check("a hand round trip at an unchanged price costs exactly fees plus slippage")
def _():
    s = manual()
    order(s, "long")
    order(s, "close")
    # Entry fills 0.02% above the price, exit 0.02% below; fees are 0.04% on
    # each side. Measured -0.119976% against a theoretical -0.120000%: the
    # remainder is the fee being charged on the *filled* notional, which is
    # what a venue actually does.
    got = (s.equity / 10_000.0 - 1.0) * 100.0
    assert abs(got - -0.12) < 0.001, got
    t = s.trades[0]
    assert t.entry_price > 100.0 > t.exit_price, (t.entry_price, t.exit_price)
    assert t.exit_reason == "manual", t.exit_reason


@check("slippage on a hand order is adverse on both sides")
def _():
    s = manual()
    order(s, "short")
    order(s, "close")
    t = s.trades[0]
    # A short is entered below the price and covered above it.
    assert t.entry_price < 100.0 < t.exit_price, (t.entry_price, t.exit_price)


@check("a reversal is two fills, not one netted fill")
def _():
    flip = manual()
    order(flip, "long")
    order(flip, "short")

    stepwise = manual()
    order(stepwise, "long")
    order(stepwise, "close")
    order(stepwise, "short")

    # Flipping must cost the same as closing and reopening: netting them would
    # quietly hand the user one free set of fees.
    assert abs(flip.equity - stepwise.equity) < 1e-9, (flip.equity, stepwise.equity)
    assert flip.position == -1 and stepwise.position == -1


@check("a hand order can stake a different share of equity than the session default")
def _():
    sizes = {}
    for size in (0.25, 0.5, 1.0):
        s = manual()
        order(s, "long", size_pct=size)
        sizes[size] = s.margin
    assert sizes[0.25] == 2_500.0, sizes
    assert sizes[0.5] == 5_000.0, sizes
    assert sizes[1.0] == 10_000.0, sizes


@check("a hand long profits when the price rises, a short when it falls")
def _():
    up = manual()
    order(up, "long")
    up.last_price = 110.0
    order(up, "close")
    assert up.equity > 10_000.0, up.equity

    down = manual()
    order(down, "short")
    down.last_price = 90.0
    order(down, "close")
    assert down.equity > 10_000.0, down.equity
    assert down.trades[0].side == "short"


@check("every refusal carries a stable code and both languages")
def _():
    cases = [
        ("already_flat", lambda: order(manual(), "close")),
        ("unknown_action", lambda: order(manual(), "buy")),
        ("bad_size", lambda: order(manual(), "long", size_pct=1.5)),
        ("no_price", lambda: PaperSession(
            strategy_id=MANUAL_STRATEGY_ID, symbol="X", timeframe="1m",
        ).place_order("long")),
    ]
    for code, fn in cases:
        try:
            fn()
        except OrderRefused as exc:
            assert exc.code == code, (code, exc.code)
            assert exc.message["vi"] and exc.message["en"], exc.message
            assert exc.message["vi"] != exc.message["en"], exc.message
        else:
            raise AssertionError(f"{code} was not refused")

    held = manual()
    order(held, "long")
    try:
        order(held, "long")
    except OrderRefused as exc:
        assert exc.code == "already_in_position", exc.code
    else:
        raise AssertionError("a second long in the same direction was accepted")


@check("a stopped session refuses orders instead of filling them")
def _():
    s = manual()
    s.active = False
    try:
        order(s, "long")
    except OrderRefused as exc:
        assert exc.code == "session_stopped", exc.code
    else:
        raise AssertionError("a stopped session filled an order")


@check("a hand order takes the position away from the strategy")
def _():
    s = PaperSession(
        strategy_id="example_ema_cross", symbol="BTCUSDT", timeframe="1m",
        config=BacktestConfig(initial_capital=10_000.0, size_pct=1.0,
                              leverage=1.0, fee=0.0004, slippage=0.0002),
    )
    s.last_price = 100.0
    assert s.manual_override is False

    order(s, "long")
    assert s.manual_override is True, "the strategy is still steering"
    # The strategy now wants the opposite side. It must not get it: otherwise
    # the next candle silently undoes what the user just did, and the trade log
    # shows a reversal nobody asked for.
    assert s._decide(lambda history: -1) == s.position, "the strategy overrode a hand order"

    s.resume_strategy()
    assert s.manual_override is False


@check("a manual session never invents a position of its own")
def _():
    s = manual()
    # No strategy, so nothing decides; a signal function that insists on going
    # long must be ignored entirely.
    assert s._decide(lambda history: 1) == 0
    order(s, "long")
    assert s._decide(lambda history: -1) == 1
    try:
        s.resume_strategy()
    except OrderRefused as exc:
        assert exc.code == "no_strategy", exc.code
    else:
        raise AssertionError("a manual session claimed to have a strategy")


@check("the snapshot says which of the two is steering")
def _():
    s = manual()
    snap = s.snapshot()
    assert snap["is_manual"] is True, snap
    assert snap["manual_override"] is False, snap
    assert snap["manual_orders"] == 0, snap
    order(s, "long")
    snap = s.snapshot()
    assert snap["manual_orders"] == 1, snap
    assert snap["position"] == 1 and snap["quantity"] > 0, snap

# ============================================ stop loss and take profit

def bar(o, h, l, c, t=1_700_000_000_000):
    return {"open_time": t, "open": o, "high": h, "low": l, "close": c, "volume": 1.0}


@check("a stop fills at the stop, not at the candle's close")
def _():
    s = manual()
    order(s, "long", stop_loss=95.0)
    s.on_closed_candle(bar(100, 101, 94, 99), lambda h: None)
    t = s.trades[0]
    # A resting order fills where it rests. Filling at the close would book 99
    # on a bar that traded down to 94 — a stop that did not stop anything.
    assert abs(t.exit_price - 95.0) < 1e-9, t.exit_price
    assert t.exit_reason == "stop_loss", t.exit_reason


@check("a target fills at the target")
def _():
    s = manual()
    order(s, "long", take_profit=110.0)
    s.on_closed_candle(bar(100, 112, 99, 104), lambda h: None)
    t = s.trades[0]
    assert abs(t.exit_price - 110.0) < 1e-9, t.exit_price
    assert t.exit_reason == "take_profit", t.exit_reason


@check("a level the candle never reached does not fire")
def _():
    s = manual()
    order(s, "long", stop_loss=90.0, take_profit=120.0)
    s.on_closed_candle(bar(100, 105, 96, 103), lambda h: None)
    assert not s.trades, s.trades
    assert s.position == 1, s.position


@check("when one candle spans both levels, the stop wins")
def _():
    s = manual()
    order(s, "long", stop_loss=95.0, take_profit=110.0)
    s.on_closed_candle(bar(100, 112, 94, 104), lambda h: None)
    # The bar says the price visited both and not in which order, so the
    # ambiguity is resolved against the account. A paper account that resolves
    # its own ambiguities favourably teaches the wrong lesson — the same reason
    # slippage is always adverse (§3.1).
    assert s.trades[0].exit_reason == "stop_loss", s.trades[0].exit_reason


@check("short exits are mirrored, not copied")
def _():
    up = manual()
    order(up, "short", stop_loss=105.0, take_profit=90.0)
    up.on_closed_candle(bar(100, 106, 99, 101), lambda h: None)
    assert up.trades[0].exit_reason == "stop_loss", up.trades[0].exit_reason

    down = manual()
    order(down, "short", stop_loss=105.0, take_profit=90.0)
    down.on_closed_candle(bar(100, 101, 88, 92), lambda h: None)
    assert down.trades[0].exit_reason == "take_profit", down.trades[0].exit_reason
    assert down.trades[0].pnl > 0, down.trades[0].pnl


@check("a level on the wrong side of the fill is refused")
def _():
    cases = [
        ("bad_stop", {"stop_loss": 105.0}, "long"),
        ("bad_target", {"take_profit": 95.0}, "long"),
        ("bad_stop", {"stop_loss": 95.0}, "short"),
        ("bad_target", {"take_profit": 105.0}, "short"),
    ]
    for code, kwargs, side in cases:
        try:
            order(manual(), side, **kwargs)
        except OrderRefused as exc:
            assert exc.code == code, (side, kwargs, exc.code)
            assert exc.message["vi"] and exc.message["en"], exc.message
        else:
            raise AssertionError(f"{side} accepted {kwargs}")


@check("exit levels are cleared with the position that carried them")
def _():
    s = manual()
    order(s, "long", stop_loss=95.0, take_profit=110.0)
    order(s, "close")
    assert s.stop_loss is None and s.take_profit is None, (s.stop_loss, s.take_profit)
    # A level left behind would fire on the next position, which is not the
    # one it was set for.
    order(s, "short")
    assert s.stop_loss is None and s.take_profit is None, (s.stop_loss, s.take_profit)


@check("exits can be attached, moved and cleared after the fact")
def _():
    s = manual()
    order(s, "long")
    s.set_exits(stop_loss=97.0, take_profit=108.0)
    assert (s.stop_loss, s.take_profit) == (97.0, 108.0)
    s.set_exits(stop_loss=None, take_profit=None)
    assert s.stop_loss is None and s.take_profit is None

    try:
        manual().set_exits(stop_loss=95.0)
    except OrderRefused as exc:
        assert exc.code == "no_position", exc.code
    else:
        raise AssertionError("exits were attached with no position open")


@check("the snapshot reports the levels the position is carrying")
def _():
    s = manual()
    order(s, "long", stop_loss=95.0, take_profit=110.0)
    snap = s.snapshot()
    assert snap["stop_loss"] == 95.0, snap["stop_loss"]
    assert snap["take_profit"] == 110.0, snap["take_profit"]

@check("a restart does not disarm the stop and target")
def _():
    """The bug this pins, found 2026-09-16.

    `_to_payload` wrote position, quantity and entry price but not the exit
    levels, so restarting the server brought the position back open with no
    stop and no target — unprotected, with nothing on screen saying so. A
    hand-placed position also lost `manual_override`, which handed it back to
    the strategy to reverse on the next bar.
    """
    from backend.paper.manager import PaperManager

    s = manual()
    order(s, "long", stop_loss=95.0, take_profit=110.0)
    s.manual_override = True

    manager = PaperManager.__new__(PaperManager)      # no store, no event loop
    payload = manager._to_payload(s)

    for field in ("stop_loss", "take_profit", "manual_override"):
        assert field in payload, f"{field} is not persisted"
    assert payload["stop_loss"] == 95.0, payload["stop_loss"]
    assert payload["take_profit"] == 110.0, payload["take_profit"]
    assert payload["manual_override"] is True, payload["manual_override"]


@check("a session saved before the levels existed still loads")
def _():
    from backend.paper.manager import PaperManager

    s = manual()
    order(s, "long", stop_loss=95.0, take_profit=110.0)
    manager = PaperManager.__new__(PaperManager)
    payload = manager._to_payload(s)

    # An older row simply has no such keys; it must come back level-free
    # rather than raising, because that is what it actually had.
    for field in ("stop_loss", "take_profit", "manual_override"):
        payload.pop(field)

    # Restoring reloads warm-up candles from the store, which the running
    # server holds a DuckDB lock on. The lock is not what is being tested.
    from backend.data import sources as data_sources
    original = data_sources.get_candles
    data_sources.get_candles = lambda *a, **k: pd.DataFrame()
    try:
        restored = manager._from_payload(payload)
    finally:
        data_sources.get_candles = original
    assert restored.stop_loss is None, restored.stop_loss
    assert restored.take_profit is None, restored.take_profit
    assert restored.manual_override is False, restored.manual_override


from backend.strategy.position_model import ContractConfig  # noqa: E402


def contract_cfg(**contract) -> BacktestConfig:
    values = dict(initial_margin_rate=0.2, maintenance_threshold=0.5,
                  fee_per_contract=20_000.0, slippage_points=0.05)
    values.update(contract)
    return BacktestConfig(initial_capital=100_000_000.0, size_pct=1.0, fee=0.0, slippage=0.0,
                          contract=ContractConfig(**values))


@check("with contracts, replaying history still reproduces the backtest trades")
def _():
    df = series()                       # prices near 100: 2 000 000 dong margin per contract
    cfg = contract_cfg()
    spec = registry.get_spec("example_ema_cross")
    resolved = spec.resolve_params(None)
    frame = df.copy()
    frame.index = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    signal = normalize_signals(spec.signals(frame, resolved), frame.index, spec.side)
    expected = run_backtest(df, signal, cfg)

    session = replay(df, "example_ema_cross", cfg)
    settled = [t for t in expected.trades if t.exit_reason != "end_of_data"]
    assert len(session.trades) == len(settled) and len(settled) > 3, (len(session.trades), len(settled))
    for got, want in zip(session.trades, settled, strict=True):
        assert got.contracts == want.contracts and got.contracts >= 1, (got, want)
        assert got.entry_time == want.entry_time and got.exit_time == want.exit_time, (got, want)
        assert close_to(got.entry_price, want.entry_price), (got.entry_price, want.entry_price)
        assert close_to(got.exit_price, want.exit_price), (got.exit_price, want.exit_price)
        assert close_to(got.pnl, want.pnl), (got.pnl, want.pnl)
        assert close_to(got.points, want.points), (got.points, want.points)


@check("a hand order the equity cannot margin is refused before anything changes")
def _():
    s = PaperSession(MANUAL_STRATEGY_ID, "VN:VN30F1M", "1m",
                     config=contract_cfg(sizing="fixed", contracts=1000))
    s.on_tick(1300.0)
    try:
        order(s, "long")
    except OrderRefused as exc:
        assert exc.code == "insufficient_margin", exc.code
        assert set(exc.message) == {"vi", "en"}, exc.message
    else:
        raise AssertionError("an unaffordable order was filled")
    assert s.position == 0 and not s.trades and s.equity == 100_000_000.0, s.snapshot()


@check("a hand order on contracts fills whole contracts and reports the model")
def _():
    s = PaperSession(MANUAL_STRATEGY_ID, "VN:VN30F1M", "1m", config=contract_cfg())
    s.on_tick(1300.0)
    order(s, "long")
    snap = s.snapshot()
    # Fill at 1300.05: margin per contract 26 010 000 dong -> 3 contracts.
    assert snap["contracts"] == 3 and snap["quantity"] == 3.0, snap
    assert snap["multiplier"] == 100_000.0 and snap["execution_model"] == "contract", snap
    s.on_tick(1310.0)
    assert close_to(s.unrealized(), 3 * (1310.0 - 1300.05) * 100_000.0), s.unrealized()


@check("a paper session without a contract block on a future says the model is off")
def _():
    s = PaperSession(MANUAL_STRATEGY_ID, "VN:VN30F1M", "1m", config=BacktestConfig())
    assert s.snapshot()["execution_model"] == "contract_model_off"


@check("a restart keeps the contract block, and an old row loads linear")
def _():
    from backend.data import sources as data_sources
    from backend.paper.manager import PaperManager

    s = PaperSession(MANUAL_STRATEGY_ID, "VN:VN30F1M", "1m", config=contract_cfg(sizing="fixed", contracts=2))
    s.on_tick(1300.0)
    order(s, "long")
    manager = PaperManager.__new__(PaperManager)
    payload = manager._to_payload(s)

    original = data_sources.get_candles
    data_sources.get_candles = lambda *a, **k: pd.DataFrame()
    try:
        restored = manager._from_payload(payload)
        assert restored.config == s.config, (restored.config, s.config)
        assert restored.snapshot()["contracts"] == 2, restored.snapshot()
        payload["config"].pop("contract")
        assert manager._from_payload(payload).config.contract is None
    finally:
        data_sources.get_candles = original


# ================================ hand orders fill at the next bar's open

MIN = 60_000
T0 = 1_789_568_340_000          # 21:19 VN on 2026-09-16, a bar open


def candle(t, o, h=None, l=None, c=None):
    h = max(o, c or o) if h is None else h
    l = min(o, c or o) if l is None else l
    return {"open_time": t, "open": o, "high": h, "low": l, "close": o if c is None else c, "volume": 1.0}


def forming_at(t, price=100.0):
    """A manual 1m session that has just seen the bar opening at ``t``."""
    s = manual()
    s.on_forming_candle(candle(t, price))
    return s


@check("a hand order does not fill on the bar it was placed in")
def _():
    s = forming_at(T0)
    s.place_order("long", now=T0 / 1000 + 39)          # 21:19:39
    assert s.position == 0 and s.pending_order is not None, s.snapshot()
    # More updates of the same bar, even at a very different price: nothing.
    assert s.on_forming_candle(candle(T0, 100.0, 104.0, 96.0, 97.0)) == []
    assert s.position == 0, s.snapshot()
    snap = s.snapshot()
    assert snap["pending_order"]["action"] == "long", snap["pending_order"]


@check("it fills at the next bar's open, with adverse slippage, timed at that open")
def _():
    s = forming_at(T0)
    s.place_order("long", now=T0 / 1000 + 39)
    s.on_forming_candle(candle(T0, 100.0, 101.0, 95.0, 96.0))   # the click bar runs on
    events = s.on_forming_candle(candle(T0 + MIN, 103.0))       # first update of 21:20
    entry = [e for e in events if e["type"] == "entry"]
    assert len(entry) == 1, events
    # The open of bar i+1, not the price at the click (96) nor the click bar's open.
    assert close_to(s.entry_price, 103.0 * 1.0002), s.entry_price
    assert s.entry_time == (T0 + MIN) // 1000, s.entry_time
    assert s.pending_order is None


@check("a short and a close fill at the next open the same way")
def _():
    s = forming_at(T0)
    s.place_order("short", now=T0 / 1000 + 5)
    s.on_forming_candle(candle(T0 + MIN, 99.0))
    assert close_to(s.entry_price, 99.0 * 0.9998), s.entry_price
    s.place_order("close", now=T0 / 1000 + 70)
    s.on_forming_candle(candle(T0 + MIN, 99.0, 100.0, 98.0, 98.5))
    assert s.position == -1, "closed inside the bar the close was clicked in"
    s.on_forming_candle(candle(T0 + 2 * MIN, 101.0))
    t = s.trades[-1]
    assert s.position == 0 and close_to(t.exit_price, 101.0 * 1.0002), t
    assert t.exit_time == (T0 + 2 * MIN) // 1000 and t.exit_reason == "manual", t


@check("a feed of closed bars only (VN) still fills at the next open, never the click bar's")
def _():
    s = manual()
    # The last bar seen closed at 21:17; the bar in progress (21:19) was never
    # delivered. The clock is what says the click belongs to 21:19.
    s.on_closed_candle(candle(T0 - 2 * MIN, 100.0), lambda h: None)
    s.place_order("long", now=T0 / 1000 + 39)
    s.on_closed_candle(candle(T0 - MIN, 100.5), lambda h: None)       # 21:18 closes late
    s.on_closed_candle(candle(T0, 101.0, 101.5, 99.0, 100.0), lambda h: None)   # 21:19
    assert s.position == 0, ("filled on a bar that opened before the click", s.snapshot())
    s.on_closed_candle(candle(T0 + MIN, 102.0, 102.5, 101.0, 102.0), lambda h: None)
    assert s.position == 1 and close_to(s.entry_price, 102.0 * 1.0002), s.snapshot()
    assert s.entry_time == (T0 + MIN) // 1000


@check("the bar a stop is judged on is the fill bar and later, never the click bar")
def _():
    s = forming_at(T0)
    s.place_order("long", now=T0 / 1000 + 10, stop_loss=95.0)
    # The next bar starts (and fills the order) before the click bar's close
    # message arrives; that close reached 90 — before the position existed.
    s.on_forming_candle(candle(T0 + MIN, 100.0))
    s.on_closed_candle(candle(T0, 100.0, 100.0, 90.0, 99.0), lambda h: None)
    assert s.position == 1 and not s.trades, ("a bar from before the fill stopped it out", s.trades)
    s.on_closed_candle(candle(T0 + MIN, 100.0, 100.0, 94.0, 96.0), lambda h: None)
    assert s.trades and s.trades[0].exit_reason == "stop_loss", s.trades


@check("a level the open has gapped past is dropped and reported, not fired")
def _():
    s = forming_at(T0)
    s.place_order("long", now=T0 / 1000 + 10, stop_loss=97.0, take_profit=110.0)
    events = s.on_forming_candle(candle(T0 + MIN, 96.0))     # gap below the stop
    entry = next(e for e in events if e["type"] == "entry")
    assert s.stop_loss is None and s.take_profit == 110.0, (s.stop_loss, s.take_profit)
    assert [d["level"] for d in entry["dropped_levels"]] == ["stop_loss"], entry


@check("an order that has nothing left to do when the bar opens is rejected with a code")
def _():
    s = forming_at(T0)
    order(s, "long", stop_loss=95.0)
    bar_open = s.last_bar_open * 1000
    s.place_order("close", now=bar_open / 1000 + 5)
    # The stop fires when the click bar closes, before the next open.
    s.on_closed_candle(candle(bar_open, 100.0, 100.0, 94.0, 95.5), lambda h: None)
    assert s.position == 0
    events = s.on_forming_candle(candle(bar_open + MIN, 96.0))
    assert [e["type"] for e in events] == ["order_rejected"], events
    assert events[0]["code"] == "already_flat" and set(events[0]["message"]) == {"vi", "en"}, events


@check("one waiting order at a time, and it can be cancelled")
def _():
    s = forming_at(T0)
    s.place_order("long", now=T0 / 1000 + 1)
    try:
        s.place_order("short", now=T0 / 1000 + 2)
    except OrderRefused as exc:
        assert exc.code == "order_pending", exc.code
    else:
        raise AssertionError("a second order was queued behind the first")
    result = s.place_order("cancel")
    assert result["events"][0]["type"] == "order_cancelled" and s.pending_order is None
    assert s.on_forming_candle(candle(T0 + MIN, 101.0)) == [] and s.position == 0
    try:
        s.place_order("cancel")
    except OrderRefused as exc:
        assert exc.code == "no_pending_order", exc.code
    else:
        raise AssertionError("cancelled an order that did not exist")


@check("the strategy cannot trade between the click and the fill")
def _():
    s = PaperSession("example_ema_cross", "BTCUSDT", "1m",
                     config=BacktestConfig(fee=0.0004, slippage=0.0002))
    s.on_forming_candle(candle(T0, 100.0))
    s.place_order("long", now=T0 / 1000 + 1)
    assert s.manual_override is True
    assert s._decide(lambda history: -1) == s.position == 0


@check("a waiting order survives a restart")
def _():
    from backend.data import sources as data_sources
    from backend.paper.manager import PaperManager

    s = forming_at(T0)
    s.place_order("short", now=T0 / 1000 + 30, take_profit=90.0)
    manager = PaperManager.__new__(PaperManager)
    original = data_sources.get_candles
    data_sources.get_candles = lambda *a, **k: pd.DataFrame()
    try:
        restored = manager._from_payload(manager._to_payload(s))
    finally:
        data_sources.get_candles = original
    assert restored.pending_order == s.pending_order, restored.pending_order
    restored.on_forming_candle(candle(T0 + MIN, 98.0))
    assert restored.position == -1 and restored.take_profit == 90.0, restored.snapshot()


def main() -> int:
    passed = failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL  {name}")
            print(f"          {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERROR {name}")
            print(f"          {type(exc).__name__}: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
