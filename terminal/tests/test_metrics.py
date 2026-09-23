"""Metric checks against hand-computed values.

Run directly:  .venv\\Scripts\\python.exe tests/test_metrics.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backend.strategy.engine import BacktestConfig, BacktestResult, Trade, run_backtest  # noqa: E402
from backend.strategy.metrics import compute_metrics, max_drawdown  # noqa: E402

DAY = 86_400_000

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def close_to(actual, expected, tol=1e-6):
    return abs(actual - expected) <= tol * max(1.0, abs(expected))


def make_trade(pnl: float, reason: str = "signal") -> Trade:
    return Trade(
        side="long", entry_index=0, exit_index=1, entry_time=0, exit_time=DAY // 1000,
        entry_price=100.0, exit_price=100.0 + pnl, quantity=1.0, pnl=pnl,
        return_pct=pnl, bars_held=1, exit_reason=reason,
    )


def make_result(equity: list[float], trades: list[Trade], n_days: int | None = None):
    n = n_days or len(equity)
    return BacktestResult(
        equity=np.array(equity, dtype="float64"),
        times=[i * DAY // 1000 for i in range(n)],
        trades=trades,
        position=np.ones(len(equity), dtype="int8"),
        config=BacktestConfig(initial_capital=equity[0]),
    )


def make_df(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time": [i * DAY for i in range(len(closes))],
            "open": closes, "high": closes, "low": closes, "close": closes,
            "volume": [1.0] * len(closes),
        }
    )


# --------------------------------------------------------------------------

@check("max drawdown finds the deepest peak-to-trough fall")
def _():
    # peak 120 -> trough 60 is -50%; the later 80 -> 70 dip is shallower
    depth, peak, trough = max_drawdown(np.array([100.0, 120, 60, 80, 70]))
    assert close_to(depth, 50.0), depth
    assert peak == 1 and trough == 2, (peak, trough)


@check("a monotonically rising curve has no drawdown")
def _():
    depth, _, _ = max_drawdown(np.array([100.0, 110, 120, 130]))
    assert close_to(depth, 0.0), depth


@check("win rate and profit factor match the trade list")
def _():
    # pnl +100, -50, +50 -> gross profit 150, gross loss 50, PF = 3.0
    # 2 wins of 3 -> 66.667%
    trades = [make_trade(100), make_trade(-50), make_trade(50)]
    m = compute_metrics(make_result([10_000.0, 10_100], trades), make_df([100.0, 100]), "1d")
    assert close_to(m["profit_factor"], 3.0), m["profit_factor"]
    assert close_to(m["win_rate_pct"], 200.0 / 3.0), m["win_rate_pct"]
    assert m["num_wins"] == 2 and m["num_losses"] == 1, m
    assert close_to(m["avg_win"], 75.0), m["avg_win"]
    assert close_to(m["avg_loss"], -50.0), m["avg_loss"]
    assert close_to(m["best_trade"], 100.0) and close_to(m["worst_trade"], -50.0), m


@check("profit factor is infinite when nothing ever loses")
def _():
    m = compute_metrics(
        make_result([10_000.0, 10_100], [make_trade(100)]), make_df([100.0, 100]), "1d"
    )
    assert m["profit_factor"] == float("inf"), m["profit_factor"]


@check("total return and buy-and-hold are reported separately")
def _():
    # equity 10000 -> 11000 is +10% ; price 100 -> 130 is +30%
    # The strategy underperformed holding by 20 points, and must say so.
    m = compute_metrics(
        make_result([10_000.0, 11_000], [make_trade(1000)]), make_df([100.0, 130]), "1d"
    )
    assert close_to(m["total_return_pct"], 10.0), m["total_return_pct"]
    assert close_to(m["buy_hold_return_pct"], 30.0), m["buy_hold_return_pct"]
    assert close_to(m["vs_buy_hold_pct"], -20.0), m["vs_buy_hold_pct"]


@check("a flat equity curve has zero Sharpe rather than a divide-by-zero")
def _():
    m = compute_metrics(make_result([10_000.0] * 10, []), make_df([100.0] * 10), "1d")
    assert m["sharpe"] == 0.0, m["sharpe"]
    assert m["sortino"] == 0.0, m["sortino"]


@check("a rising curve gives positive Sharpe, a falling one negative")
def _():
    up = make_result([10_000.0 * (1.01**i) for i in range(60)], [])
    down = make_result([10_000.0 * (0.99**i) for i in range(60)], [])
    prices = make_df([100.0] * 60)
    assert compute_metrics(up, prices, "1d")["sharpe"] > 0
    assert compute_metrics(down, prices, "1d")["sharpe"] < 0


@check("exposure counts only the bars actually in a position")
def _():
    df = pd.DataFrame(
        {
            "open_time": [i * DAY for i in range(4)],
            "open": [100.0] * 4, "high": [100.0] * 4,
            "low": [100.0] * 4, "close": [100.0] * 4, "volume": [1.0] * 4,
        }
    )
    # flat, flat, long, long -> in the market for 2 of 4 bars
    sig = np.array([0, 1, 1, 1], dtype="int8")
    r = run_backtest(df, sig, BacktestConfig(fee=0, slippage=0))
    m = compute_metrics(r, df, "1d")
    assert close_to(m["exposure_pct"], 50.0), m["exposure_pct"]


@check("a ruined account reports -100% CAGR rather than a maths error")
def _():
    r = make_result([10_000.0, 5_000, 0.0], [make_trade(-10_000, "liquidation")])
    r.ruined = True
    m = compute_metrics(r, make_df([100.0, 90, 80]), "1d")
    assert close_to(m["total_return_pct"], -100.0), m["total_return_pct"]
    assert m["cagr_pct"] == -100.0, m["cagr_pct"]
    assert close_to(m["max_drawdown_pct"], 100.0), m["max_drawdown_pct"]
    assert m["liquidations"] == 1 and m["ruined"], m


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
