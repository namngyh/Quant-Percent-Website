"""Công cụ quản trị rủi ro: CVaR nhiều mức, Kelly, ngân sách, trần đòn bẩy.

Chạy độc lập:  .venv\\Scripts\\python.exe tests/test_risk.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from backend.analysis.risk import (  # noqa: E402
    kelly,
    leverage_ceiling,
    size_for_budget,
    tail_risk,
)

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def normal(n=2000, seed=5, scale=0.01):
    return np.random.default_rng(seed).standard_normal(n) * scale


def winning_trades(n=400, p=0.6, step=0.01, seed=5):
    rng = np.random.default_rng(seed)
    out, equity = [], 10_000.0
    for _ in range(n):
        move = step if rng.random() < p else -step
        after = equity * (1.0 + move)
        out.append({"equity_before": equity, "equity_after": after})
        equity = after
    return out


# ==================================================================== tail risk

@check("CVaR is always at least as bad as VaR at the same level")
def _():
    out = tail_risk(normal(), simulations=200)
    for lv in out["levels"]:
        assert lv["cvar_pct"] <= lv["var_pct"] + 1e-9, lv


@check("a deeper level is a worse loss")
def _():
    out = tail_risk(normal(), simulations=200)
    cvar = [lv["cvar_pct"] for lv in out["levels"]]
    assert cvar[0] > cvar[1] > cvar[2], cvar


@check("the tail's own uncertainty widens as the tail thins")
def _():
    # The whole reason for reporting an interval: CVaR 99% on 2 000 bars is the
    # mean of 20 observations, and prints to two decimals exactly like the 90%
    # figure that rests on 200. Measured: interval widths 0.161 / 0.226 / 0.426.
    out = tail_risk(normal(), simulations=400)
    widths = [lv["ci95_high_pct"] - lv["ci95_low_pct"] for lv in out["levels"]]
    counts = [lv["tail_observations"] for lv in out["levels"]]
    assert counts[0] > counts[1] > counts[2], counts
    assert widths[0] < widths[1] < widths[2], widths


@check("a tail estimated from too few bars is flagged, not printed silently")
def _():
    thin = tail_risk(normal(n=200), simulations=200)
    at99 = [lv for lv in thin["levels"] if lv["level_pct"] == 99.0][0]
    assert at99["tail_observations"] < 10, at99
    assert at99["thin_tail"] is True, at99
    assert at99["note"]["vi"] and at99["note"]["en"]

    thick = tail_risk(normal(n=20000), simulations=100)
    assert all(not lv["thin_tail"] for lv in thick["levels"]), thick["levels"]


@check("Cornish-Fisher exceeds history exactly where history is too thin")
def _():
    rng = np.random.default_rng(9)
    # A sample whose worst observations understate what its own skew and
    # kurtosis imply. Measured: historical VaR99 -4.09% against C-F -7.69%.
    fat = np.concatenate([rng.standard_normal(2900) * 0.008,
                          -np.abs(rng.standard_normal(100)) * 0.05])
    out = tail_risk(fat, simulations=200)
    at99 = [lv for lv in out["levels"] if lv["level_pct"] == 99.0][0]
    assert at99["var_cornish_fisher_pct"] < at99["var_pct"], at99
    assert at99["cornish_fisher_gap_pct"] < -1.0, at99

    # And on a well-behaved sample the two agree, so the column is not just
    # always more alarming.
    plain = tail_risk(normal(n=3000), simulations=200)
    p99 = [lv for lv in plain["levels"] if lv["level_pct"] == 99.0][0]
    assert abs(p99["cornish_fisher_gap_pct"]) < 0.5, p99


@check("too few bars is refused in both languages")
def _():
    out = tail_risk(normal(n=40))
    assert out["available"] is False
    assert out["reason"]["vi"] and out["reason"]["en"]
    assert out["reason"]["vi"] != out["reason"]["en"]


# ======================================================================== Kelly

@check("Kelly recovers a known edge exactly")
def _():
    # Built rather than sampled: 60 wins and 40 losses of the same size gives
    # p = 0.6, b = 1 and f* = (p*b - q)/b = 0.20 with no sampling error at all.
    # Drawing 400 trades at p = 0.6 instead leaves a standard error of 0.025 on
    # p, so f wanders by +/-0.10 between seeds and the test measures the random
    # number generator as much as the formula.
    equity, trades = 10_000.0, []
    for i in range(100):
        move = 0.01 if i % 5 < 3 else -0.01
        after = equity * (1.0 + move)
        trades.append({"equity_before": equity, "equity_after": after})
        equity = after
    k = kelly(trades)
    assert k["available"] is True, k
    assert abs(k["win_rate"] - 0.6) < 1e-12, k["win_rate"]
    assert abs(k["payoff_ratio"] - 1.0) < 1e-9, k["payoff_ratio"]
    assert abs(k["kelly_fraction"] - 0.20) < 1e-9, k["kelly_fraction"]
    assert abs(k["half_kelly_fraction"] - 0.10) < 1e-9, k["half_kelly_fraction"]


@check("Kelly is computed on equity at the time of the trade, not on the opening balance")
def _():
    # Two trades of identical percentage size but at very different equity
    # levels must count equally. Using pnl/initial_capital they would not.
    trades = [{"equity_before": 10_000.0, "equity_after": 10_100.0},
              {"equity_before": 50_000.0, "equity_after": 50_500.0}] * 15
    trades += [{"equity_before": 10_000.0, "equity_after": 9_900.0},
               {"equity_before": 50_000.0, "equity_after": 49_500.0}] * 5
    k = kelly(trades)
    assert k["available"] is True, k
    assert abs(k["payoff_ratio"] - 1.0) < 1e-9, k["payoff_ratio"]


@check("Kelly refuses rather than dividing by an absent side")
def _():
    assert kelly([])["available"] is False
    assert kelly(winning_trades(n=5))["available"] is False
    all_wins = [{"equity_before": 100.0, "equity_after": 101.0}] * 30
    out = kelly(all_wins)
    assert out["available"] is False, out
    assert out["reason"]["en"]


# =============================================================== risk budgeting

@check("a risk budget round-trips: apply the size, measure the CVaR back")
def _():
    # The claim the card makes is exact, so the test is exact. Scaling the
    # returns by the suggested multiplier must reproduce the requested budget.
    series = normal(n=2000)
    for budget in (1.0, 2.0, 5.0):
        out = size_for_budget(series, budget)
        assert out["available"] is True, out
        back = tail_risk(series * out["size_multiplier"], simulations=200)
        cvar95 = [lv for lv in back["levels"] if lv["level_pct"] == 95.0][0]["cvar_pct"]
        assert abs(abs(cvar95) - budget) < 1e-6, (budget, cvar95)


@check("a budget too large for the strategy is capped and says so")
def _():
    out = size_for_budget(normal(), 5.0)
    assert out["size_multiplier"] > 1.0, out
    assert out["capped"] is True, out
    assert out["suggested_size_pct"] == 100.0, out


@check("a larger budget always allows a larger position")
def _():
    series = normal()
    sizes = [size_for_budget(series, b)["size_multiplier"] for b in (0.5, 1.0, 2.0)]
    assert sizes[0] < sizes[1] < sizes[2], sizes


@check("a nonsensical budget is refused")
def _():
    assert size_for_budget(normal(), 0.0)["available"] is False
    assert size_for_budget(normal(), -1.0)["available"] is False


# ============================================================ leverage ceiling

@check("deeper confidence levels allow less leverage")
def _():
    out = leverage_ceiling(normal())
    lev = [row["max_leverage"] for row in out["levels"]]
    assert lev[0] > lev[1] > lev[2], lev
    # And the worst bar ever seen is stricter than any of the quantiles.
    assert out["max_leverage_worst_bar"] < lev[2], out


@check("a more volatile strategy gets a lower ceiling")
def _():
    calm = leverage_ceiling(normal(scale=0.005))["max_leverage_worst_bar"]
    wild = leverage_ceiling(normal(scale=0.05))["max_leverage_worst_bar"]
    assert wild < calm, (wild, calm)


@check("every risk tool states its limits in both languages")
def _():
    from backend.analysis.risk import risk_tools
    out = risk_tools(normal(), winning_trades())
    assert out["tail"]["available"] and out["kelly"]["available"]
    assert out["budget"]["available"] and out["leverage"]["available"]
    for block, field in (("tail", "method"), ("kelly", "watch"),
                         ("budget", "watch"), ("leverage", "watch")):
        text = out[block][field]
        assert text["vi"] and text["en"], (block, field)
        assert text["vi"] != text["en"], (block, field)


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
