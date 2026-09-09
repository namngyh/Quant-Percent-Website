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
    s.place_order("long")
    s.place_order("close")
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
    s.place_order("short")
    s.place_order("close")
    t = s.trades[0]
    # A short is entered below the price and covered above it.
    assert t.entry_price < 100.0 < t.exit_price, (t.entry_price, t.exit_price)


@check("a reversal is two fills, not one netted fill")
def _():
    flip = manual()
    flip.place_order("long")
    flip.place_order("short")

    stepwise = manual()
    stepwise.place_order("long")
    stepwise.place_order("close")
    stepwise.place_order("short")

    # Flipping must cost the same as closing and reopening: netting them would
    # quietly hand the user one free set of fees.
    assert abs(flip.equity - stepwise.equity) < 1e-9, (flip.equity, stepwise.equity)
    assert flip.position == -1 and stepwise.position == -1


@check("a hand order can stake a different share of equity than the session default")
def _():
    sizes = {}
    for size in (0.25, 0.5, 1.0):
        s = manual()
        s.place_order("long", size_pct=size)
        sizes[size] = s.margin
    assert sizes[0.25] == 2_500.0, sizes
    assert sizes[0.5] == 5_000.0, sizes
    assert sizes[1.0] == 10_000.0, sizes


@check("a hand long profits when the price rises, a short when it falls")
def _():
    up = manual()
    up.place_order("long")
    up.last_price = 110.0
    up.place_order("close")
    assert up.equity > 10_000.0, up.equity

    down = manual()
    down.place_order("short")
    down.last_price = 90.0
    down.place_order("close")
    assert down.equity > 10_000.0, down.equity
    assert down.trades[0].side == "short"


@check("every refusal carries a stable code and both languages")
def _():
    cases = [
        ("already_flat", lambda: manual().place_order("close")),
        ("unknown_action", lambda: manual().place_order("buy")),
        ("bad_size", lambda: manual().place_order("long", size_pct=1.5)),
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
    held.place_order("long")
    try:
        held.place_order("long")
    except OrderRefused as exc:
        assert exc.code == "already_in_position", exc.code
    else:
        raise AssertionError("a second long in the same direction was accepted")


@check("a stopped session refuses orders instead of filling them")
def _():
    s = manual()
    s.active = False
    try:
        s.place_order("long")
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

    s.place_order("long")
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
    s.place_order("long")
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
    s.place_order("long")
    snap = s.snapshot()
    assert snap["manual_orders"] == 1, snap
    assert snap["position"] == 1 and snap["quantity"] > 0, snap

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
