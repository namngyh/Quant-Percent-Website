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

# ============================================== the date window on a run

def _window_probe():
    """`_load_candles` with the data layer replaced, so no database is needed.

    Returns (loader, calls) where `calls` records exactly what reached
    sources.get_candles — the point of these checks is that the window travels
    intact from the request to the query, not that DuckDB can filter.
    """
    from backend.api import routes_strategy

    calls = []
    hours = pd.date_range("2024-01-01", periods=500, freq="h", tz="UTC")
    frame = pd.DataFrame({
        # Converted through datetime64[ms] rather than by dividing the int64.
        # pandas 3 backs a DatetimeIndex with microseconds, not nanoseconds, so
        # the usual // 1_000_000 silently yields seconds — a thousand-fold
        # error that still looks like a plausible timestamp.
        "open_time": hours.tz_localize(None).astype("datetime64[ms]").astype("int64"),
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0,
    })

    def fake(symbol, timeframe, start_ms=None, end_ms=None, limit=None):
        calls.append({"symbol": symbol, "timeframe": timeframe,
                      "start_ms": start_ms, "end_ms": end_ms, "limit": limit})
        out = frame
        if start_ms is not None:
            out = out[out["open_time"] >= start_ms]
        if end_ms is not None:
            out = out[out["open_time"] <= end_ms]
        if limit:
            out = out.tail(limit)
        return out.reset_index(drop=True)

    original = routes_strategy.sources.get_candles
    routes_strategy.sources.get_candles = fake
    return routes_strategy, calls, original


@check("a run with no window asks for the most recent bars, as before")
def _():
    mod, calls, original = _window_probe()
    try:
        df, _ = mod._load_candles("BTCUSDT", "1h", 200)
    finally:
        mod.sources.get_candles = original
    assert calls[0]["start_ms"] is None and calls[0]["end_ms"] is None, calls[0]
    assert calls[0]["limit"] == 200, calls[0]
    assert len(df) == 200, len(df)


@check("a date window reaches the query as milliseconds")
def _():
    mod, calls, original = _window_probe()
    try:
        df, _ = mod._load_candles(
            "BTCUSDT", "1h", None,
            "2024-01-05T00:00:00+00:00", "2024-01-08T00:00:00+00:00")
    finally:
        mod.sources.get_candles = original
    call = calls[0]
    assert call["start_ms"] == 1704412800000, call["start_ms"]
    assert call["end_ms"] == 1704672000000, call["end_ms"]
    # Inclusive at both ends: 3 days of hourly bars plus the closing bar.
    assert len(df) == 73, len(df)
    first = int(df["open_time"].iloc[0])
    last = int(df["open_time"].iloc[-1])
    assert first == call["start_ms"], (first, call["start_ms"])
    assert last == call["end_ms"], (last, call["end_ms"])


@check("a limit inside a window takes the last bars of it, not the first")
def _():
    mod, calls, original = _window_probe()
    try:
        df, _ = mod._load_candles(
            "BTCUSDT", "1h", 10,
            "2024-01-05T00:00:00+00:00", "2024-01-08T00:00:00+00:00")
    finally:
        mod.sources.get_candles = original
    assert len(df) == 10, len(df)
    assert int(df["open_time"].iloc[-1]) == calls[0]["end_ms"], "did not end at the window end"


@check("an open-ended window is allowed at either end")
def _():
    mod, calls, original = _window_probe()
    try:
        mod._load_candles("BTCUSDT", "1h", None, "2024-01-05T00:00:00+00:00", None)
        mod._load_candles("BTCUSDT", "1h", None, None, "2024-01-05T00:00:00+00:00")
    finally:
        mod.sources.get_candles = original
    assert calls[0]["start_ms"] and calls[0]["end_ms"] is None, calls[0]
    assert calls[1]["start_ms"] is None and calls[1]["end_ms"], calls[1]


@check("a backwards or unparseable window is refused with a reason")
def _():
    from fastapi import HTTPException
    mod, _calls, original = _window_probe()
    try:
        for start, end, expect in (
            ("2024-02-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00", 400),
            ("not-a-date", None, 400),
            # A window with no bars in it is a 404, not an empty successful run:
            # an empty backtest reports zero trades, which reads like a finding.
            ("1990-01-01T00:00:00+00:00", "1990-02-01T00:00:00+00:00", 404),
        ):
            try:
                mod._load_candles("BTCUSDT", "1h", None, start, end)
            except HTTPException as exc:
                assert exc.status_code == expect, (start, end, exc.status_code)
                assert exc.detail, "refused without saying why"
            else:
                raise AssertionError(f"accepted {start} -> {end}")
    finally:
        mod.sources.get_candles = original


@check("every request model that loads candles accepts the window")
def _():
    from backend.api.routes_stats import SeriesRequest, StrategyStatsRequest
    from backend.api.routes_strategy import BacktestRequest, OptimizeRequest
    from backend.api.routes_validation import (
        CompareRequest, MonteCarloRequest, WalkForwardRequest,
    )
    for model in (BacktestRequest, OptimizeRequest, SeriesRequest,
                  StrategyStatsRequest, WalkForwardRequest, MonteCarloRequest,
                  CompareRequest):
        fields = model.model_fields
        assert "start" in fields and "end" in fields, model.__name__
        # And they stay optional, so nothing that worked before now fails.
        assert fields["start"].default is None, model.__name__
        assert fields["end"].default is None, model.__name__

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
