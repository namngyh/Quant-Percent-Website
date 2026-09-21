"""Backtest engine checks against hand-computed outcomes.

Run directly:  .venv\\Scripts\\python.exe tests/test_engine.py

Every expected number here is worked out by hand in the comments. An engine
that silently miscounts fees or fills a bar early still produces a confident,
plausible equity curve — these cases are what stands between that and trusting
the results.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backend.strategy.engine import BacktestConfig, run_backtest  # noqa: E402

MINUTE = 60_000


def frame(bars: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """bars = [(open, high, low, close), ...]"""
    return pd.DataFrame(
        {
            "open_time": [i * MINUTE for i in range(len(bars))],
            "open": [b[0] for b in bars],
            "high": [b[1] for b in bars],
            "low": [b[2] for b in bars],
            "close": [b[3] for b in bars],
            "volume": [1.0] * len(bars),
        }
    )


def close_to(actual: float, expected: float, tol: float = 1e-6) -> bool:
    return abs(actual - expected) <= tol * max(1.0, abs(expected))


CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


# --------------------------------------------------------------------------

@check("flat signal never trades and never moves equity")
def _():
    df = frame([(100, 105, 95, 100)] * 5)
    r = run_backtest(df, np.zeros(5, dtype="int8"), BacktestConfig(fee=0, slippage=0))
    assert len(r.trades) == 0, r.trades
    assert all(close_to(e, 10_000.0) for e in r.equity), r.equity


@check("long, no costs: equity tracks the price ratio exactly")
def _():
    # Enter at bar 1 open = 100 (signal from bar 0), hold to close 110.
    # qty = 10000 / 100 = 100 ; pnl = 100 * (110 - 100) = 1000
    df = frame([(100, 100, 100, 100), (100, 110, 100, 110), (110, 110, 110, 110)])
    r = run_backtest(df, np.ones(3, dtype="int8"), BacktestConfig(fee=0, slippage=0))
    assert len(r.trades) == 1, r.trades
    t = r.trades[0]
    assert t.side == "long" and t.entry_price == 100 and t.entry_index == 1, t
    assert close_to(t.pnl, 1000.0), t.pnl
    assert close_to(r.equity[-1], 11_000.0), r.equity[-1]


@check("signal at bar i fills at bar i+1 open, never at bar i")
def _():
    # Signal fires only on the last bar: there is no next open, so no trade.
    df = frame([(100, 100, 100, 100)] * 3)
    sig = np.array([0, 0, 1], dtype="int8")
    r = run_backtest(df, sig, BacktestConfig(fee=0, slippage=0))
    assert len(r.trades) == 0, r.trades

    # A signal on bar 0 fills at the bar-1 open of 200, not the bar-0 close.
    df2 = frame([(100, 100, 100, 100), (200, 200, 200, 200), (200, 200, 200, 200)])
    r2 = run_backtest(df2, np.array([1, 1, 1], dtype="int8"), BacktestConfig(fee=0, slippage=0))
    assert r2.trades[0].entry_price == 200, r2.trades[0]


@check("short profits when price falls")
def _():
    # Enter short at bar 1 open = 100 ; qty = -100 ; close 90
    # pnl = -100 * (90 - 100) = +1000
    df = frame([(100, 100, 100, 100), (100, 100, 90, 90)])
    r = run_backtest(df, np.full(2, -1, dtype="int8"), BacktestConfig(fee=0, slippage=0))
    assert len(r.trades) == 1 and r.trades[0].side == "short", r.trades
    assert close_to(r.trades[0].pnl, 1000.0), r.trades[0].pnl
    assert close_to(r.equity[-1], 11_000.0), r.equity[-1]


@check("fees are charged on both sides, on notional")
def _():
    # fee 0.1%. entry: notional 10000 -> fee 10, equity 9990, qty 100
    # exit at 110: fee = 100*110*0.001 = 11 ; pnl = 1000 - 11 = 989
    # final equity = 9990 + 989 = 10979
    df = frame([(100, 100, 100, 100), (100, 110, 100, 110)])
    r = run_backtest(df, np.ones(2, dtype="int8"), BacktestConfig(fee=0.001, slippage=0))
    assert close_to(r.equity[-1], 10_979.0), r.equity[-1]


@check("slippage worsens both the entry and the exit")
def _():
    # slip 1%. long entry at 100*1.01 = 101 ; exit at 110*0.99 = 108.9
    # qty = 10000/101 ; pnl = qty * (108.9 - 101)
    df = frame([(100, 100, 100, 100), (100, 110, 100, 110)])
    r = run_backtest(df, np.ones(2, dtype="int8"), BacktestConfig(fee=0, slippage=0.01))
    t = r.trades[0]
    assert close_to(t.entry_price, 101.0), t.entry_price
    assert close_to(t.exit_price, 108.9), t.exit_price
    qty = 10_000.0 / 101.0
    assert close_to(t.pnl, qty * (108.9 - 101.0)), t.pnl


@check("reversal closes the old position and opens the new one on the same bar")
def _():
    df = frame([(100, 100, 100, 100), (100, 100, 100, 100), (100, 100, 100, 100)])
    sig = np.array([1, -1, -1], dtype="int8")
    r = run_backtest(df, sig, BacktestConfig(fee=0, slippage=0))
    assert len(r.trades) == 2, r.trades
    assert r.trades[0].side == "long" and r.trades[1].side == "short", r.trades
    assert r.trades[0].exit_index == r.trades[1].entry_index == 2, r.trades


@check("leveraged long is liquidated on the bar low, losing exactly the margin")
def _():
    # leverage 10, entry 100 -> liquidation at 100 * (1 - 1/10) = 90
    # margin = 10000, so the loss is the whole account.
    df = frame([(100, 100, 100, 100), (100, 100, 89, 95)])
    r = run_backtest(
        df, np.ones(2, dtype="int8"), BacktestConfig(fee=0, slippage=0, leverage=10)
    )
    assert r.liquidated, "expected a liquidation"
    t = r.trades[0]
    assert t.exit_reason == "liquidation" and close_to(t.exit_price, 90.0), t
    assert close_to(t.pnl, -10_000.0), t.pnl
    assert close_to(r.equity[-1], 0.0), r.equity[-1]
    assert r.ruined, "account should be ruined"


@check("a wick that stops short of the liquidation price does not liquidate")
def _():
    # leverage 10 -> liq at 90 ; the low only reaches 91
    df = frame([(100, 100, 100, 100), (100, 100, 91, 100)])
    r = run_backtest(
        df, np.ones(2, dtype="int8"), BacktestConfig(fee=0, slippage=0, leverage=10)
    )
    assert not r.liquidated, "should not have liquidated"
    assert not r.ruined


@check("size_pct commits only part of equity")
def _():
    # size 50%: margin 5000, qty = 50, pnl = 50 * 10 = 500
    df = frame([(100, 100, 100, 100), (100, 110, 100, 110)])
    r = run_backtest(
        df, np.ones(2, dtype="int8"), BacktestConfig(fee=0, slippage=0, size_pct=0.5)
    )
    assert close_to(r.trades[0].pnl, 500.0), r.trades[0].pnl
    assert close_to(r.equity[-1], 10_500.0), r.equity[-1]


@check("leverage multiplies exposure")
def _():
    # leverage 3, no costs: margin 10000, notional 30000, qty 300, pnl 300*10 = 3000
    df = frame([(100, 100, 100, 100), (100, 110, 100, 110)])
    r = run_backtest(
        df, np.ones(2, dtype="int8"), BacktestConfig(fee=0, slippage=0, leverage=3)
    )
    assert close_to(r.trades[0].pnl, 3000.0), r.trades[0].pnl


@check("equity curve matches the candle count and never goes negative")
def _():
    rng = np.random.default_rng(7)
    n = 500
    price = np.maximum(100 + np.cumsum(rng.normal(0, 2, n)), 1.0)
    df = frame([(p, p * 1.01, p * 0.99, p) for p in price])
    sig = rng.choice([-1, 0, 1], size=n).astype("int8")
    r = run_backtest(df, sig, BacktestConfig(leverage=5))
    assert len(r.equity) == n and len(r.position) == n
    assert (r.equity >= 0).all(), "equity went negative"


# --------------------------------------------------------------------------

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
