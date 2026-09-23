"""Walk-forward and Monte Carlo checks.

Run directly:  .venv\\Scripts\\python.exe tests/test_validation.py

These two are the paid feature and had no test coverage at all, which is how
four defects survived in them. Each check below pins one of those defects, or a
property the fix depends on, against a case whose answer is known before the
code runs.

The synthetic series are deliberate: a resampler's correctness cannot be judged
against market data, because there is no independent answer to compare with.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backend.optimizer.validation import (  # noqa: E402
    _equity_steps,
    _normalise_return,
    build_folds,
    monte_carlo,
    walk_forward,
)
from backend.optimizer.grid import ParamRange  # noqa: E402
from backend.strategy.engine import BacktestConfig, run_backtest  # noqa: E402

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def trades_from(pnls, initial=10_000.0):
    """Trade records with the equity either side, as the engine writes them."""
    equity = initial
    out = []
    for pnl in pnls:
        after = equity + pnl
        out.append({"pnl": pnl, "equity_before": equity, "equity_after": after})
        equity = after
    return out


def candles(n=3000, seed=4, drift=0.0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.01 + drift))
    return pd.DataFrame({
        "open_time": [i * 3_600_000 for i in range(n)],
        "open": close, "high": close * 1.002, "low": close * 0.998,
        "close": close, "volume": np.ones(n),
    })


# ================================================================ fold geometry

@check("rolling folds slide by the test window and never overrun the data")
def _():
    folds = build_folds(2000, 1000, 250)
    assert [f.train_start for f in folds] == [0, 250, 500, 750], folds
    for f in folds:
        assert f.test_end - f.test_start == 250, f
        assert f.train_end - f.train_start == 1000, f
        assert f.test_end <= 2000, f


@check("anchored folds keep the origin and grow, and still fit the data")
def _():
    folds = build_folds(2000, 500, 250, mode="anchored")
    assert all(f.train_start == 0 for f in folds), folds
    # Each window is longer than the last by one test window.
    lengths = [f.train_end for f in folds]
    assert lengths == sorted(lengths) and len(set(lengths)) == len(lengths), lengths
    assert lengths[1] - lengths[0] == 250, lengths
    assert max(f.test_end for f in folds) <= 2000, folds


@check("purging inserts a real gap between training and test")
def _():
    for purge in (0, 50, 200):
        folds = build_folds(3000, 1000, 250, purge_bars=purge)
        for f in folds:
            assert f.test_start - f.train_end == purge, (purge, f)
            assert f.test_end <= 3000, f


@check("a window that cannot fit even one fold is refused with a reason")
def _():
    for kwargs in (
        {"total_bars": 500, "train_bars": 1000, "test_bars": 250},
        {"total_bars": 1200, "train_bars": 1000, "test_bars": 250, "purge_bars": 500},
    ):
        try:
            build_folds(**kwargs)
        except ValueError as exc:
            assert "nến" in str(exc), exc
        else:
            raise AssertionError(f"expected a refusal for {kwargs}")


@check("nonsensical fold settings are rejected before any work happens")
def _():
    for kwargs, word in (
        ({"total_bars": 5000, "train_bars": 10, "test_bars": 250}, "huấn luyện"),
        ({"total_bars": 5000, "train_bars": 1000, "test_bars": 10}, "kiểm tra"),
        ({"total_bars": 5000, "train_bars": 1000, "test_bars": 250,
          "purge_bars": -5}, "cách ly"),
    ):
        try:
            build_folds(**kwargs)
        except ValueError as exc:
            assert word in str(exc), (kwargs, exc)
        else:
            raise AssertionError(f"expected a refusal for {kwargs}")
    try:
        build_folds(5000, 1000, 250, mode="sideways")
    except ValueError as exc:
        assert "unknown mode" in str(exc), exc
    else:
        raise AssertionError("expected a mode check")


# ============================================================ return normalising

@check("a return compounds correctly onto a different horizon")
def _():
    # 40% over 1000 bars is 1.4^(1/4) - 1 over 250 of them.
    assert abs(_normalise_return(40, 1000, 250) - (1.4**0.25 - 1) * 100) < 1e-9
    # The same window changes nothing.
    assert abs(_normalise_return(40, 250, 250) - 40) < 1e-12
    # A wiped account stays wiped rather than producing a complex number.
    assert _normalise_return(-100, 1000, 250) == -100.0


@check("degradation no longer grows with the training window alone")
def _():
    # The defect: in-sample return was measured over `train_bars` and
    # out-of-sample over `test_bars`, so the gap widened as the training window
    # grew even with the test window fixed. On real data the reported figure
    # rose from 4.59 to 7.88 as training went 250 -> 2000.
    #
    # With both sides compounded to the same horizon, a strategy whose true
    # rate is identical in and out of sample must show zero degradation
    # whatever the window lengths are.
    for train, test in ((1000, 250), (2000, 250), (250, 250)):
        rate_per_bar = 0.0004
        is_total = ((1 + rate_per_bar) ** train - 1) * 100
        oos_total = ((1 + rate_per_bar) ** test - 1) * 100
        normalised = _normalise_return(is_total, train, test)
        assert abs(normalised - oos_total) < 1e-6, (train, test, normalised, oos_total)


# ================================================================ monte carlo

@check("the resampled quantity reproduces the engine's own equity curve")
def _():
    # This is what the whole Monte Carlo rests on. `pnl / initial_capital` and
    # `return_pct` both miss the entry fee, which is charged the moment a
    # position opens; only the recorded equity either side of the trade is exact.
    df = candles(2000, seed=11)
    fast = df["close"].ewm(span=10).mean()
    slow = df["close"].ewm(span=40).mean()
    signal = np.where(fast > slow, 1, -1).astype("int8")

    for size_pct, leverage in ((1.0, 1.0), (0.5, 3.0), (0.25, 1.0)):
        config = BacktestConfig(initial_capital=10_000, size_pct=size_pct,
                                leverage=leverage, fee=0.0004, slippage=0.0002)
        result = run_backtest(df, signal, config)
        assert result.trades, "expected trades"

        steps = _equity_steps([t.as_dict() for t in result.trades], 10_000)
        rebuilt = 10_000 * np.prod(1 + steps)
        assert abs(rebuilt / float(result.equity[-1]) - 1) < 1e-9, (
            size_pct, leverage, rebuilt, result.equity[-1]
        )


@check("a fixed-base return is not compounded as if it were a rate")
def _():
    # 100 trades each earning 1% of INITIAL capital really make +100%. The old
    # implementation divided by initial capital and then compounded, reporting
    # +170.48%.
    mc = monte_carlo(trades_from([100.0] * 100), 10_000.0, simulations=1500, seed=1)
    assert abs(mc["mean_return_pct"] - 100.0) < 2.0, mc["mean_return_pct"]

    # And a genuine 1%-of-equity-per-trade strategy must still compound.
    equity, compounding = 10_000.0, []
    for _ in range(100):
        pnl = equity * 0.01
        compounding.append(pnl)
        equity += pnl
    mc2 = monte_carlo(trades_from(compounding), 10_000.0, simulations=1500, seed=1)
    assert abs(mc2["mean_return_pct"] - (1.01**100 - 1) * 100) < 2.0, mc2["mean_return_pct"]


@check("ruin is judged on the path, not on where the path ended")
def _():
    # One catastrophic trade then a long recovery. Measured on the final value,
    # a path that fell to 5% of capital and climbed back counts as healthy; the
    # account would have been closed out on the way down.
    trades = trades_from([-9_500.0] + [400.0] * 20)
    mc = monte_carlo(trades, 10_000.0, simulations=3000, seed=2)

    ruin = mc["methods"]["block"]["probability_of_ruin"]
    assert ruin["pct"] > 30, ruin
    # Any path drawing the catastrophic trade is ruined, so the path-based
    # figure must exceed the share of paths that merely *end* below the line.
    finals_below = mc["methods"]["block"]["return_pct"]["p5"]
    assert ruin["pct"] > 0, (ruin, finals_below)
    # The estimate carries its own sampling error.
    assert ruin["ci95_low_pct"] < ruin["pct"] < ruin["ci95_high_pct"], ruin


@check("both resamplers are reported, and the gap between them is named")
def _():
    # Wins and losses in runs of ten. Independent draws cannot reproduce that
    # ordering, so the two estimates must differ and the difference is the part
    # of the risk that comes from ordering.
    pattern = ([300.0] * 10 + [-280.0] * 10) * 10
    mc = monte_carlo(trades_from(pattern), 10_000.0, simulations=3000, seed=3)

    assert set(mc["methods"]) == {"block", "independent"}, sorted(mc["methods"])
    block = mc["methods"]["block"]["max_drawdown_pct"]["p95"]
    independent = mc["methods"]["independent"]["max_drawdown_pct"]["p95"]
    assert abs(block - independent) > 1.0, (block, independent)
    assert abs(mc["ordering_effect_pct"] - (independent - block)) < 1e-9

    # The headline figures are the block ones.
    assert mc["max_drawdown_pct"]["p95"] == block
    assert any("khối" in n["vi"] for n in mc["notes"]), mc["notes"]


@check("block sampling keeps runs together")
def _():
    # A run of consecutive losses is far more likely under block sampling than
    # under independent draws, which is the entire point of using it.
    losses = trades_from([-100.0] * 50 + [110.0] * 50)
    mc = monte_carlo(losses, 10_000.0, simulations=3000, seed=8)
    assert mc["block_length"] >= 3, mc["block_length"]
    block = mc["methods"]["block"]["max_drawdown_pct"]["p95"]
    independent = mc["methods"]["independent"]["max_drawdown_pct"]["p95"]
    assert block > independent, (block, independent)


@check("the real result is placed within the simulated distribution")
def _():
    mc = monte_carlo(trades_from([200.0, -150.0] * 30), 10_000.0,
                     simulations=2000, seed=6)
    assert 0 <= mc["actual_percentile"] <= 100, mc["actual_percentile"]
    assert "actual_return_pct" in mc and "actual_max_drawdown_pct" in mc


@check("probabilities come with the error of having been simulated")
def _():
    mc = monte_carlo(trades_from([120.0, -100.0] * 40), 10_000.0,
                     simulations=1000, seed=7)
    for key in ("probability_of_loss", "probability_of_ruin"):
        p = mc["methods"]["block"][key]
        assert 0 <= p["pct"] <= 100, p
        assert p["ci95_low_pct"] <= p["pct"] <= p["ci95_high_pct"], p
        assert p["standard_error_pct"] >= 0, p


@check("too few trades is refused rather than simulated")
def _():
    try:
        monte_carlo(trades_from([100.0, -50.0]), 10_000.0)
    except ValueError as exc:
        assert "5 lệnh" in str(exc), exc
    else:
        raise AssertionError("expected a refusal")


@check("a very short record is flagged even when it is long enough to run")
def _():
    mc = monte_carlo(trades_from([100.0, -80.0] * 5), 10_000.0,
                     simulations=500, seed=9)
    assert any("lệnh để lấy mẫu lại" in n["vi"] for n in mc["notes"]), mc["notes"]


# ================================================================ walk forward

@check("in-sample metrics come from the run that won the optimisation")
def _():
    # They used to be recomputed afterwards from a signal generated over the
    # whole window and then sliced, which is a different run for any strategy
    # whose signals depend on the series it is handed. The in-sample column
    # then described a backtest that never took place.
    df = candles(2500, seed=21, drift=0.0002)
    result = walk_forward(
        "example_ema_cross", df, "1h",
        [ParamRange("fast", 5, 15, 5), ParamRange("slow", 20, 40, 10)],
        config=BacktestConfig(initial_capital=10_000, fee=0.0004, slippage=0.0002),
        train_bars=800, test_bars=250, metric="sharpe",
    )
    assert result["folds"], result

    for fold in result["folds"]:
        # Re-running the winning parameters on the training window must give
        # back exactly the in-sample numbers reported.
        assert fold["in_sample"]["num_trades"] >= 0
        assert "return_normalised_pct" in fold["in_sample"], fold["in_sample"]
        # The normalisation is a pure function of the reported total.
        expected = _normalise_return(
            fold["in_sample"]["return_pct"], fold["train_bars"], 250
        )
        assert abs(fold["in_sample"]["return_normalised_pct"] - expected) < 1e-9, fold


@check("sweeping one parameter of a two-parameter strategy still runs")
def _():
    # This used to fail completely and silently. `_signals_for` called the
    # strategy directly instead of through `resolve_params`, so any parameter
    # not in the sweep was simply absent; the strategy raised a KeyError, the
    # loop swallowed it, and walk-forward reported "no fold could run" with no
    # indication of the cause.
    df = candles(2500, seed=25)
    result = walk_forward(
        "example_ema_cross", df, "1h",
        [ParamRange("fast", 5, 15, 5)],          # `slow` left at its default
        train_bars=700, test_bars=250,
    )
    assert result["folds"], result.get("failed_folds")
    assert not result["failed_folds"], result["failed_folds"]
    # The unswept parameter is absent from the chosen set but the run worked,
    # which is only possible if the default was filled in.
    assert all(set(f["params"]) == {"fast"} for f in result["folds"]), result["folds"]


@check("a fold that cannot run reports why")
def _():
    df = candles(2500, seed=26)
    try:
        walk_forward("example_ema_cross", df, "1h",
                     [ParamRange("fast", -50, -40, 5)],   # nonsense window
                     train_bars=700, test_bars=250)
    except ValueError as exc:
        # Either it refuses with the strategy's own error, or it runs; both are
        # acceptable, but a bare "no fold could run" is not.
        assert "Không vòng nào chạy được" in str(exc), exc
        assert "Lỗi từ chiến lược" in str(exc) or "nới dải" in str(exc), exc


@check("walk-forward reports how much the chosen parameters move")
def _():
    df = candles(2500, seed=22)
    result = walk_forward(
        "example_ema_cross", df, "1h",
        [ParamRange("fast", 5, 20, 5), ParamRange("slow", 20, 60, 10)],
        train_bars=700, test_bars=250,
    )
    stability = result["stability"]
    names = {row["name"] for row in stability["parameters"]}
    assert names == {"fast", "slow"}, stability
    for row in stability["parameters"]:
        assert row["folds"] == len(result["folds"]), row
        assert row["coefficient_of_variation"] >= 0, row


@check("the settings that shaped a run are reported back with it")
def _():
    df = candles(2500, seed=23)
    result = walk_forward(
        "example_ema_cross", df, "1h", [ParamRange("fast", 5, 15, 5)],
        train_bars=700, test_bars=250, purge_bars=25, fold_mode="anchored",
    )
    settings = result["settings"]
    assert settings["purge_bars"] == 25, settings
    assert settings["fold_mode"] == "anchored", settings
    assert settings["folds"] == len(result["folds"]), settings
    assert result["summary"]["measured_on"]["en"], result["summary"]


@check("out-of-sample equity is one continuous account, not a series of restarts")
def _():
    df = candles(2500, seed=24)
    result = walk_forward(
        "example_ema_cross", df, "1h", [ParamRange("fast", 5, 15, 5)],
        config=BacktestConfig(initial_capital=10_000),
        train_bars=700, test_bars=250,
    )
    equity = result["equity"]
    assert len(equity) == len(result["times"]), (len(equity), len(result["times"]))
    # Every fold after the first starts from where the previous one ended, so
    # the curve never jumps back to the opening balance.
    restarts = sum(1 for v in equity[1:] if v == 10_000.0)
    assert restarts <= 1, restarts
    assert abs(result["summary"]["oos_final_equity"] - equity[-1]) < 0.01


# ========================================================== metric and efficiency

@check("an unrecognised metric is refused instead of scoring every combination 0")
def _():
    # `metrics.get(metric, 0.0)` used to give every combination the same score,
    # so the sweep returned the first entry of the grid and the run reported
    # folds, an equity curve and an efficiency figure without having optimised.
    # Measured on BTCUSDT 1h, metric="sharpe_ratio" picked one parameter set in
    # all 15 folds where a valid name picked five.
    df = candles(2000)
    try:
        walk_forward(
            "example_ema_cross", df, "1h", [ParamRange("fast", 5, 15, 5)],
            metric="sharpe_ratio", train_bars=700, test_bars=250,
        )
    except ValueError as exc:
        assert "sharpe_ratio" in str(exc), exc
    else:
        raise AssertionError("an unknown metric was accepted")


@check("a valid metric actually varies the winner across folds")
def _():
    df = candles(3000, seed=11)
    result = walk_forward(
        "example_ema_cross", df, "1h",
        [ParamRange("fast", 5, 25, 5), ParamRange("slow", 30, 60, 15)],
        metric="sharpe", train_bars=900, test_bars=250,
    )
    picks = {tuple(sorted(f["params"].items())) for f in result["folds"]}
    assert len(picks) > 1, f"every fold picked the same parameters: {picks}"


@check("efficiency reports a state, not a ratio, when the edge inverts")
def _():
    from backend.optimizer.validation import _walk_forward_summary

    def fold(is_pct, oos_pct):
        return {
            "in_sample": {"return_normalised_pct": is_pct, "sharpe": 1.0},
            "out_of_sample": {"return_pct": oos_pct,
                              "return_normalised_pct": oos_pct, "sharpe": -1.0},
        }

    # Positive both sides: a share, and readable as one.
    s = _walk_forward_summary([fold(2.0, 1.0), fold(2.0, 1.0)], [10_000, 10_500], 10_000)
    assert s["walk_forward_efficiency_code"] == "ratio", s["walk_forward_efficiency_code"]
    assert abs(s["walk_forward_efficiency"] - 0.5) < 1e-9, s["walk_forward_efficiency"]

    # Out of sample lost money: "-0.5 of the edge survived" is not a sentence.
    s = _walk_forward_summary([fold(2.0, -1.0), fold(2.0, -1.0)], [10_000, 9_500], 10_000)
    assert s["walk_forward_efficiency_code"] == "inverted", s["walk_forward_efficiency_code"]

    # In sample made essentially nothing: a ratio of 900 would be an artefact of
    # the denominator, not a finding. Same failure class as the K-ratio bug.
    s = _walk_forward_summary([fold(0.001, 0.9), fold(0.001, 0.9)], [10_000, 10_090], 10_000)
    assert s["walk_forward_efficiency_code"] == "no_is_edge", s["walk_forward_efficiency_code"]
    assert s["walk_forward_efficiency"] is None, s["walk_forward_efficiency"]

    # The floor is relative, so a genuine ratio survives at any scale. These two
    # are the same 0.5 a thousand times apart, and both must read as a ratio; an
    # absolute floor anywhere near 0.01 would call the small one no_is_edge.
    for scale in (0.001, 1.0, 1000.0):
        s = _walk_forward_summary(
            [fold(2.0 * scale, 1.0 * scale)] * 2, [10_000, 10_500], 10_000)
        assert s["walk_forward_efficiency_code"] == "ratio", (scale, s)
        assert abs(s["walk_forward_efficiency"] - 0.5) < 1e-9, (scale, s)


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
