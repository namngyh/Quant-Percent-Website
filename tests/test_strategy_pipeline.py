"""End-to-end checks: load a strategy file, run it, summarise it.

Run directly:  .venv\\Scripts\\python.exe tests/test_strategy_pipeline.py

Uses synthetic price series so the expectations hold regardless of what is in
the candle store.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backend.strategy import registry  # noqa: E402
from backend.strategy.base import normalize_signals  # noqa: E402
from backend.strategy.engine import BacktestConfig  # noqa: E402

HOUR = 3_600_000

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def series_frame(closes: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time": [i * HOUR for i in range(len(closes))],
            "open": closes,
            "high": closes * 1.002,
            "low": closes * 0.998,
            "close": closes,
            "volume": np.ones(len(closes)),
        }
    )


def trending(n: int = 600, drift: float = 0.004) -> pd.DataFrame:
    """A steadily rising series with mild noise."""
    rng = np.random.default_rng(11)
    noise = rng.normal(0, 0.003, n)
    return series_frame(100.0 * np.exp(np.cumsum(drift + noise)))


def choppy(n: int = 600) -> pd.DataFrame:
    """A sideways series that whipsaws — the case that punishes trend following."""
    x = np.arange(n)
    return series_frame(100.0 + 5.0 * np.sin(x / 6.0))


# --------------------------------------------------------------------------

@check("both example strategies load with no errors")
def _():
    reg = registry.get_registry()
    assert registry.get_load_errors() == [], registry.get_load_errors()
    assert "example_ema_cross" in reg, sorted(reg)
    assert "example_rsi_reversal" in reg, sorted(reg)
    spec = reg["example_ema_cross"]
    assert [p.name for p in spec.params] == ["fast", "slow"], spec.params


@check("signals are coerced to -1 / 0 / 1 and NaN becomes flat")
def _():
    index = pd.RangeIndex(5)
    out = normalize_signals(pd.Series([2.5, -0.1, 0, np.nan, -7]), index)
    assert list(out) == [1, -1, 0, 0, -1], list(out)


@check("side='long' suppresses short signals")
def _():
    index = pd.RangeIndex(3)
    assert list(normalize_signals(pd.Series([1, -1, 1]), index, "long")) == [1, 0, 1]
    assert list(normalize_signals(pd.Series([1, -1, 1]), index, "short")) == [0, -1, 0]


@check("a mismatched signal length is rejected, not silently padded")
def _():
    try:
        normalize_signals(pd.Series([1, 1]), pd.RangeIndex(5))
    except Exception as exc:
        assert "does not match" in str(exc), exc
    else:
        raise AssertionError("expected a length error")


@check("EMA crossover makes money on a trend and loses on chop")
def _():
    cfg = BacktestConfig(fee=0.0004, slippage=0.0002)
    up = registry.run_strategy("example_ema_cross", trending(), "1h", config=cfg)
    side = registry.run_strategy("example_ema_cross", choppy(), "1h", config=cfg)

    assert up["metrics"]["total_return_pct"] > 0, up["metrics"]["total_return_pct"]
    # Whipsaw plus costs should hurt a trend follower.
    assert side["metrics"]["total_return_pct"] < 0, side["metrics"]["total_return_pct"]
    assert side["metrics"]["num_trades"] > up["metrics"]["num_trades"], "chop should trade more"


@check("result payload is internally consistent")
def _():
    r = registry.run_strategy("example_ema_cross", trending(), "1h")
    m = r["metrics"]
    assert len(r["equity"]) == len(r["times"]) == len(r["position"]) == m["bars"]
    assert len(r["trades"]) == m["num_trades"]
    assert m["num_wins"] + m["num_losses"] <= m["num_trades"]
    assert abs(r["equity"][-1] - m["final_equity"]) < 1.0
    assert 0.0 <= m["exposure_pct"] <= 100.0
    assert 0.0 <= m["win_rate_pct"] <= 100.0


@check("fees make a churning strategy strictly worse")
def _():
    df = choppy()
    free = registry.run_strategy(
        "example_ema_cross", df, "1h", config=BacktestConfig(fee=0, slippage=0)
    )
    costed = registry.run_strategy(
        "example_ema_cross", df, "1h", config=BacktestConfig(fee=0.0004, slippage=0.0002)
    )
    assert costed["metrics"]["total_return_pct"] < free["metrics"]["total_return_pct"], (
        costed["metrics"]["total_return_pct"],
        free["metrics"]["total_return_pct"],
    )


@check("RSI reversal stays out of the market some of the time")
def _():
    r = registry.run_strategy("example_rsi_reversal", trending(), "1h")
    exposure = r["metrics"]["exposure_pct"]
    assert 0.0 < exposure < 100.0, exposure


@check("an unknown strategy id is reported, not swallowed")
def _():
    try:
        registry.run_strategy("no_such_strategy", trending(), "1h")
    except Exception as exc:
        assert "unknown strategy" in str(exc), exc
    else:
        raise AssertionError("expected an unknown-strategy error")


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
