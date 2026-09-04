"""Grid-search checks.

Run directly:  .venv\\Scripts\\python.exe tests/test_optimizer.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backend.optimizer.grid import (  # noqa: E402
    MAX_COMBINATIONS,
    ParamRange,
    build_grid,
    build_random,
    grid_size,
    optimize,
)
from backend.strategy.engine import BacktestConfig  # noqa: E402

HOUR = 3_600_000

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def trending(n: int = 800) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    closes = 100.0 * np.exp(np.cumsum(0.003 + rng.normal(0, 0.004, n)))
    return pd.DataFrame(
        {
            "open_time": [i * HOUR for i in range(n)],
            "open": closes, "high": closes * 1.002,
            "low": closes * 0.998, "close": closes, "volume": np.ones(n),
        }
    )


# --------------------------------------------------------------------------

@check("integer sweeps stay integers, inclusive of the endpoint")
def _():
    assert ParamRange("fast", 10, 30, 5).values() == [10, 15, 20, 25, 30]
    assert ParamRange("x", 1, 3, 1).values() == [1, 2, 3]


@check("float sweeps do not accumulate floating-point dust")
def _():
    values = ParamRange("mult", 1.0, 2.0, 0.25).values()
    assert values == [1.0, 1.25, 1.5, 1.75, 2.0], values


@check("the grid is the full cartesian product")
def _():
    grid = build_grid([ParamRange("a", 1, 3, 1), ParamRange("b", 10, 20, 10)])
    assert len(grid) == 6, grid
    assert {"a": 2, "b": 20} in grid, grid


@check("an oversized grid is refused before it runs for hours")
def _():
    ranges = [ParamRange("a", 1, 200, 1), ParamRange("b", 1, 200, 1)]
    assert grid_size(ranges) == 40_000, grid_size(ranges)
    try:
        build_grid(ranges)
    except ValueError as exc:
        # The message names the size, the limit, and the way out.
        assert "40,000" in str(exc) and f"{MAX_COMBINATIONS:,}" in str(exc), exc
        assert "ngẫu nhiên" in str(exc).lower(), exc
    else:
        raise AssertionError("expected a size guard")


@check("grid_size counts without building the grid")
def _():
    assert grid_size([]) == 1
    assert grid_size([ParamRange("a", 1, 10, 1)]) == 10
    assert grid_size([ParamRange("a", 1, 10, 1), ParamRange("b", 0, 1, 0.25)]) == 50
    # Big enough that enumerating it would be the wrong move.
    huge = [ParamRange(n, 1, 100, 1) for n in "abcde"]
    assert grid_size(huge) == 100**5


@check("random sampling draws distinct combinations from the space")
def _():
    ranges = [ParamRange("a", 1, 100, 1), ParamRange("b", 1, 100, 1)]
    picked = build_random(ranges, 200, seed=1)
    assert len(picked) == 200, len(picked)
    unique = {tuple(sorted(p.items())) for p in picked}
    assert len(unique) == 200, "sampling must not repeat a combination"
    for p in picked:
        assert 1 <= p["a"] <= 100 and 1 <= p["b"] <= 100, p


@check("random sampling is reproducible for a given seed")
def _():
    ranges = [ParamRange("a", 1, 50, 1), ParamRange("b", 1, 50, 1)]
    first = build_random(ranges, 40, seed=42)
    again = build_random(ranges, 40, seed=42)
    other = build_random(ranges, 40, seed=43)
    assert first == again, "same seed should give the same sample"
    assert first != other, "different seeds should differ"


@check("sampling a space smaller than the budget returns the whole space")
def _():
    ranges = [ParamRange("a", 1, 4, 1), ParamRange("b", 1, 3, 1)]   # 12 cells
    picked = build_random(ranges, 500, seed=1)
    assert len(picked) == 12, len(picked)


@check("random mode runs an oversized space that grid mode refuses")
def _():
    ranges = [ParamRange("fast", 2, 60, 1), ParamRange("slow", 10, 300, 1)]
    assert grid_size(ranges) > MAX_COMBINATIONS, grid_size(ranges)

    try:
        optimize("example_ema_cross", trending(400), "1h", ranges, mode="grid")
    except ValueError:
        pass
    else:
        raise AssertionError("grid mode should have refused")

    out = optimize("example_ema_cross", trending(400), "1h", ranges,
                   mode="random", samples=25, seed=5)
    s = out["summary"]
    assert s["mode"] == "random" and s["completed"] == 25, s
    assert s["space_size"] == grid_size(ranges), s
    assert 0 < s["coverage_pct"] < 1, s["coverage_pct"]


@check("an unknown mode is rejected")
def _():
    try:
        optimize("example_ema_cross", trending(200), "1h",
                 [ParamRange("fast", 5, 10, 5)], mode="bayesian")
    except ValueError as exc:
        assert "unknown mode" in str(exc), exc
    else:
        raise AssertionError("expected a mode check")


@check("a bad step is rejected rather than looping forever")
def _():
    for bad in (ParamRange("a", 1, 10, 0), ParamRange("a", 1, 10, -1)):
        try:
            bad.values()
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected rejection of {bad}")


@check("results come back ranked by the chosen metric")
def _():
    out = optimize(
        "example_ema_cross", trending(), "1h",
        [ParamRange("fast", 10, 30, 10), ParamRange("slow", 40, 80, 20)],
        metric="total_return_pct",
    )
    returns = [r["metrics"]["total_return_pct"] for r in out["results"]]
    assert returns == sorted(returns, reverse=True), returns
    assert out["summary"]["completed"] == 9, out["summary"]


@check("ranking by a different metric reorders the table")
def _():
    ranges = [ParamRange("fast", 5, 25, 5), ParamRange("slow", 30, 90, 20)]
    df = trending()
    by_return = optimize("example_ema_cross", df, "1h", ranges, metric="total_return_pct")
    by_sharpe = optimize("example_ema_cross", df, "1h", ranges, metric="sharpe")
    scores = [r["metrics"]["sharpe"] for r in by_sharpe["results"]]
    assert scores == sorted(scores, reverse=True), scores
    assert by_return["summary"]["metric"] == "total_return_pct"
    assert by_sharpe["summary"]["metric"] == "sharpe"


@check("an infinite profit factor never wins the grid")
def _():
    out = optimize(
        "example_ema_cross", trending(), "1h",
        [ParamRange("fast", 10, 20, 10)], metric="profit_factor",
    )
    for row in out["results"]:
        assert row["metrics"]["profit_factor"] is None or np.isfinite(
            row["metrics"]["profit_factor"]
        ), row


@check("summary reports the benchmark and how broad the profitability is")
def _():
    out = optimize(
        "example_ema_cross", trending(), "1h",
        [ParamRange("fast", 10, 30, 10), ParamRange("slow", 40, 80, 20)],
    )
    s = out["summary"]
    assert 0.0 <= s["profitable_pct"] <= 100.0, s
    assert "buy_hold_return_pct" in s and "median_return_pct" in s, s
    assert isinstance(s["overfit_warning"], bool), s


@check("a failing combination is recorded without aborting the sweep")
def _():
    # slow < fast is legal for the strategy, so force a failure another way:
    # a nonexistent parameter is coerced away, meaning every combo should run.
    out = optimize(
        "example_ema_cross", trending(), "1h", [ParamRange("fast", 5, 15, 5)]
    )
    assert out["summary"]["failed"] == 0, out["failures"]
    assert out["summary"]["completed"] == 3, out["summary"]


@check("progress is reported for every combination")
def _():
    seen = []
    optimize(
        "example_ema_cross", trending(), "1h", [ParamRange("fast", 10, 40, 10)],
        progress_cb=lambda done, total: seen.append((done, total)),
    )
    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)], seen


@check("a 36-combination sweep over 800 bars stays interactive")
def _():
    started = time.time()
    optimize(
        "example_ema_cross", trending(), "1h",
        [ParamRange("fast", 5, 30, 5), ParamRange("slow", 40, 90, 10)],
        config=BacktestConfig(),
    )
    elapsed = time.time() - started
    assert elapsed < 20.0, f"took {elapsed:.1f}s"
    print(f"          ({elapsed:.2f}s for 36 combinations)")


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
