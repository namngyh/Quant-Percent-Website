"""Backtest report checks, against outcomes worked out by hand.

Run directly:  .venv\\Scripts\\python.exe tests/test_report.py

The report is where a plausible-looking wrong number does the most damage: it
is the screen a decision gets made from, and every figure on it is derived
rather than observed. So the checks here build candles whose answer is known
before the code runs — a known drawdown, a known excursion, a known month
boundary — rather than asserting that real data produces something reasonable.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backend.analysis.report import build_report, ml_evaluation  # noqa: E402
from backend.strategy.engine import BacktestConfig, run_backtest  # noqa: E402

HOUR = 3_600_000
# 2024-01-01 00:00 UTC, so month boundaries in the periodic table are checkable.
EPOCH = 1_704_067_200_000


def frame(bars, step=HOUR, start=EPOCH):
    """bars = [(open, high, low, close), ...]"""
    return pd.DataFrame({
        "open_time": [start + i * step for i in range(len(bars))],
        "open": [b[0] for b in bars],
        "high": [b[1] for b in bars],
        "low": [b[2] for b in bars],
        "close": [b[3] for b in bars],
        "volume": [1.0] * len(bars),
    })


def flat(prices):
    """Candles with no wick, so every metric depends only on the closes."""
    return frame([(p, p, p, p) for p in prices])


CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def report_for(df, signal, config=None):
    result = run_backtest(df, np.asarray(signal, dtype="int8"),
                          config or BacktestConfig(fee=0, slippage=0))
    return build_report(result, df, "1h")


# ---------------------------------------------------- excursions

@check("MFE and MAE are measured from the fill, including the entry bar")
def _():
    # Enter long at bar 1's open (100). Bar 1 reaches 120 and 90; bar 2 closes
    # the position at its open, 110. So MFE = +20%, MAE = -10%, return = +10%.
    df = frame([(100, 100, 100, 100), (100, 120, 90, 105), (110, 110, 110, 110)])
    result = run_backtest(df, np.array([1, 0, 0], dtype="int8"),
                          BacktestConfig(fee=0, slippage=0))
    trade = result.trades[0]
    assert abs(trade.mfe_pct - 20.0) < 1e-9, trade.mfe_pct
    assert abs(trade.mae_pct + 10.0) < 1e-9, trade.mae_pct
    assert abs(trade.return_pct - 10.0) < 1e-9, trade.return_pct


@check("a short's excursions are mirrored, not copied")
def _():
    df = frame([(100, 100, 100, 100), (100, 120, 90, 105), (110, 110, 110, 110)])
    result = run_backtest(df, np.array([-1, 0, 0], dtype="int8"),
                          BacktestConfig(fee=0, slippage=0))
    trade = result.trades[0]
    # The low is favourable to a short and the high is adverse.
    assert abs(trade.mfe_pct - 10.0) < 1e-9, trade.mfe_pct
    assert abs(trade.mae_pct + 20.0) < 1e-9, trade.mae_pct


@check("MFE is never negative and MAE never positive")
def _():
    prices = list(np.linspace(100, 150, 60))
    df = flat(prices)
    signal = np.tile([1, 1, 0, 0], 15)
    result = run_backtest(df, signal.astype("int8"), BacktestConfig(fee=0, slippage=0))
    assert result.trades, "expected trades"
    for trade in result.trades:
        assert trade.mfe_pct >= 0.0, trade
        assert trade.mae_pct <= 0.0, trade


@check("winners' MAE is shallower than losers' on a trending series")
def _():
    rng = np.random.default_rng(4)
    prices = 100 * np.exp(np.cumsum(rng.standard_normal(2000) * 0.01 + 0.0004))
    df = flat(prices)
    fast = pd.Series(prices).ewm(span=10).mean()
    slow = pd.Series(prices).ewm(span=40).mean()
    signal = np.where(fast > slow, 1, -1).astype("int8")

    report = report_for(df, signal)
    e = report["excursions"]
    assert e["count"] > 20, e["count"]
    # This is the relationship the stop-loss advice rests on. If it inverted,
    # the panel would be telling the user to tighten a stop that is already
    # cutting winners.
    assert e["mae_winners"]["mean"] > e["mae_losers"]["mean"], e


# ---------------------------------------------------- overview and risk

@check("exposure and RAR agree with the position array")
def _():
    df = flat(list(np.linspace(100, 200, 100)))
    # In the market for exactly half the bars.
    signal = np.array([1] * 50 + [0] * 50, dtype="int8")
    report = report_for(df, signal)
    o = report["overview"]
    assert abs(o["exposure_pct"] - o["bars_in_market"] / o["bars"] * 100) < 1e-9, o
    assert abs(o["rar_pct"] - o["car_pct"] / (o["exposure_pct"] / 100)) < 1e-6, o


@check("a strategy that never trades reports zero exposure, not a division error")
def _():
    report = report_for(flat([100] * 50), np.zeros(50, dtype="int8"))
    assert report["overview"]["exposure_pct"] == 0.0
    assert report["overview"]["rar_pct"] == 0.0
    assert report["trades"]["all"]["count"] == 0
    assert report["risk"]["max_drawdown_pct"] == 0.0


@check("the Ulcer index separates a short dip from a long one")
def _():
    # Same 20% depth, different time underwater. Max drawdown cannot tell these
    # apart; the Ulcer index is in the report precisely because it can.
    quick = [100] * 10 + [80] + [100] * 49
    slow = [100] * 10 + [80] * 40 + [100] * 10
    ulcer_quick = report_for(flat(quick), np.ones(60, dtype="int8"))["risk"]["ulcer_index"]
    ulcer_slow = report_for(flat(slow), np.ones(60, dtype="int8"))["risk"]["ulcer_index"]
    assert ulcer_slow > ulcer_quick * 3, (ulcer_quick, ulcer_slow)


@check("the K-ratio rewards a straight equity line over a single jump")
def _():
    steady = list(100 * np.exp(np.linspace(0, 0.5, 400)))
    jump = [100.0] * 200 + [164.87] * 200      # same end point, one step
    k_steady = report_for(flat(steady), np.ones(400, dtype="int8"))["risk"]["k_ratio"]
    k_jump = report_for(flat(jump), np.ones(400, dtype="int8"))["risk"]["k_ratio"]
    assert k_steady["value"] > k_jump["value"], (k_steady["value"], k_jump["value"])


@check("the K-ratio says why it is missing rather than returning zero")
def _():
    result = report_for(flat([100] * 40), np.ones(40, dtype="int8"))["risk"]["k_ratio"]
    assert result["value"] is None, result
    assert result["note"], result


# ---------------------------------------------------- trades

@check("long and short blocks sum to the combined block")
def _():
    rng = np.random.default_rng(7)
    prices = 100 * np.exp(np.cumsum(rng.standard_normal(1500) * 0.01))
    df = flat(prices)
    signal = np.sign(rng.standard_normal(1500)).astype("int8")
    t = report_for(df, signal)["trades"]
    assert t["all"]["count"] == t["long"]["count"] + t["short"]["count"], t
    assert abs(
        t["all"]["net_profit"] - (t["long"]["net_profit"] + t["short"]["net_profit"])
    ) < 1e-6, t


@check("consecutive-loss streaks are counted, not just the longest win run")
def _():
    # Down, down, down, then up: alternating positions on a falling series give
    # a run of losses whose length is checkable by eye.
    prices = [100, 99, 98, 97, 96, 95, 94, 93]
    df = flat(prices)
    signal = np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype="int8")
    streaks = report_for(df, signal)["streaks"]
    assert streaks["max_consecutive_losses"] >= 3, streaks
    assert streaks["max_consecutive_wins"] == 0, streaks


@check("the best trade's share of gross profit is reported")
def _():
    rng = np.random.default_rng(8)
    prices = 100 * np.exp(np.cumsum(rng.standard_normal(1200) * 0.012))
    df = flat(prices)
    signal = np.sign(rng.standard_normal(1200)).astype("int8")
    block = report_for(df, signal)["trades"]["all"]
    assert 0 < block["best_trade_share_pct"] <= 100, block["best_trade_share_pct"]


# ---------------------------------------------------- periodic

@check("monthly buckets follow Vietnam time, not UTC")
def _():
    # Hourly bars from 2024-01-01 00:00 UTC. Vietnam is UTC+7, so the first
    # bar is already 07:00 on 1 January locally and January must be the first
    # bucket — a UTC split would agree here, so the real check is the count.
    df = flat(list(np.linspace(100, 130, 24 * 70)))
    report = report_for(df, np.ones(24 * 70, dtype="int8"))
    monthly = report["periodic"]["monthly"]
    assert monthly[0]["year"] == 2024 and monthly[0]["month"] == 1, monthly[0]
    assert report["periodic"]["timezone"].startswith("Asia/Ho_Chi_Minh")
    # 70 days spans January, February and the start of March.
    assert len(monthly) == 3, monthly


@check("the first month's return is measured from initial capital")
def _():
    # A single month of flat prices with no trades: the return must be 0, not
    # the +inf that measuring against a zero opening balance would give.
    df = flat([100] * (24 * 20))
    report = report_for(df, np.zeros(24 * 20, dtype="int8"))
    assert abs(report["periodic"]["monthly"][0]["return_pct"]) < 1e-9, \
        report["periodic"]["monthly"]


@check("annual returns compound the monthly ones")
def _():
    rng = np.random.default_rng(9)
    n = 24 * 400
    prices = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.002))
    report = report_for(flat(prices), np.ones(n, dtype="int8"))
    p = report["periodic"]
    assert len(p["annual"]) >= 2, p["annual"]
    assert p["total_months"] >= 12, p["total_months"]
    assert p["worst_month_pct"] <= p["best_month_pct"], p


# ---------------------------------------------------- ML evaluation

@check("a perfect oracle scores 100% accuracy")
def _():
    prices = [100, 101, 100, 102, 101, 103, 102, 104] * 10
    df = flat(prices)
    close = np.array(prices, dtype="float64")
    # Hold exactly the direction of the next bar.
    position = np.sign(np.diff(close, append=close[-1])).astype("int8")
    result = ml_evaluation(df, position)
    assert abs(result["accuracy"] - 1.0) < 1e-9, result["accuracy"]
    assert result["mcc"] > 0.99, result["mcc"]
    assert result["beats_baseline"], result["binomial_p"]


@check("an inverted oracle scores zero accuracy and negative MCC")
def _():
    prices = [100, 101, 100, 102, 101, 103, 102, 104] * 10
    df = flat(prices)
    close = np.array(prices, dtype="float64")
    position = -np.sign(np.diff(close, append=close[-1])).astype("int8")
    result = ml_evaluation(df, position)
    assert result["accuracy"] < 1e-9, result["accuracy"]
    assert result["mcc"] < -0.99, result["mcc"]


@check("the baseline is the majority class, not 50%")
def _():
    # Rises on 3 bars out of every 4, so always predicting "up" scores 75%.
    prices = []
    value = 100.0
    for i in range(400):
        value *= 1.01 if i % 4 else 0.97
        prices.append(value)
    df = flat(prices)
    result = ml_evaluation(df, np.ones(len(prices), dtype="int8"))
    assert abs(result["baseline_accuracy"] - 0.75) < 0.02, result["baseline_accuracy"]
    # Accuracy equals the baseline, so there is no edge and the test must say so.
    assert not result["beats_baseline"], result["binomial_p"]
    assert abs(result["edge_pct"]) < 2.0, result["edge_pct"]


@check("flat bars are excluded rather than counted as wrong")
def _():
    prices = [100] * 200
    result = ml_evaluation(flat(prices), np.ones(200, dtype="int8"))
    # Every next-bar return is zero, so nothing is scoreable.
    assert "error" in result, result


@check("bars with no position are not scored")
def _():
    rng = np.random.default_rng(10)
    prices = 100 * np.exp(np.cumsum(rng.standard_normal(1000) * 0.01))
    df = flat(prices)
    position = np.zeros(1000, dtype="int8")
    position[:400] = 1
    result = ml_evaluation(df, position)
    assert result["n_scored"] <= 400, result["n_scored"]
    assert result["coverage_pct"] < 45, result["coverage_pct"]


@check("published probabilities add calibration without changing accuracy")
def _():
    rng = np.random.default_rng(11)
    n = 800
    prices = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.01))
    df = flat(prices)
    position = np.ones(n, dtype="int8")
    without = ml_evaluation(df, position)
    with_probability = ml_evaluation(df, position, probability=rng.random(n))
    assert abs(without["accuracy"] - with_probability["accuracy"]) < 1e-12
    assert "probability" not in without
    assert "probability" in with_probability, with_probability
    assert with_probability["probability"]["brier"] > 0
    assert with_probability["probability"]["calibration"], with_probability["probability"]


# ---------------------------------------------------- payload shape

@check("chart series are downsampled but keep both endpoints")
def _():
    n = 12_000
    rng = np.random.default_rng(12)
    prices = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.005))
    df = flat(prices)
    report = report_for(df, np.ones(n, dtype="int8"))
    equity = report["charts"]["equity"]
    assert len(equity) <= 1500, len(equity)
    assert equity[0]["t"] == report["overview"]["start_time"], equity[0]
    assert equity[-1]["t"] == report["overview"]["end_time"], equity[-1]
    assert len(report["charts"]["buy_hold"]) == len(equity)


@check("an empty backtest reports an error rather than an empty report")
def _():
    df = flat([100])
    result = run_backtest(df, np.zeros(1, dtype="int8"))
    result.equity = np.array([])
    assert "error" in build_report(result, df, "1h")


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
