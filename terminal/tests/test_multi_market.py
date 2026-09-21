"""One strategy across many markets.

The thing being guarded here is not the arithmetic but the framing. Running a
strategy over twenty symbols and keeping the best one is a search, and a
search's winner is biased upward by the search. A table sorted by Sharpe says
nothing about that; the median, the hit rate and the deflated Sharpe do.

Run:  .venv\\Scripts\\python.exe tests/test_multi_market.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.strategy.multi import MarketRun, summarise  # noqa: E402

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


DAY = 86_400_000


def run(symbol, sharpe, ret, *, bars=1000, timeframe="1d", span_days=1000,
        equity=None):
    """A market outcome shaped like the engine's, with only what matters set."""
    start = 1_600_000_000_000
    times = [start, start + span_days * DAY]
    if equity is None:
        # A gently rising curve: enough points for PSR, no extreme moments.
        equity = [100.0 + i * 0.01 for i in range(300)]
    return MarketRun(
        symbol,
        timeframe,
        result={
            "metrics": {"sharpe": sharpe, "total_return_pct": ret, "bars": bars,
                        "num_trades": 20},
            "times": times,
            "equity": equity,
        },
    )


@check("breadth leads, not the winner")
def _():
    # Nineteen markets lose, one wins big. A ranked table shows a 400% return
    # at the top; the honest headline is that it worked on one in twenty.
    runs = [run(f"L{i}", -0.2, -10.0) for i in range(19)]
    runs.append(run("WIN", 2.0, 400.0))
    out = summarise(runs)

    assert out["markets"] == 20, out["markets"]
    assert out["profitable_markets"] == 1, out["profitable_markets"]
    assert out["median_return_pct"] == -10.0, out["median_return_pct"]
    assert out["best_return_pct"] == 400.0
    # The winner is still named — it is what the user asked for — but beside
    # a median that contradicts it.
    assert out["best_symbol"] == "WIN", out["best_symbol"]


@check("rows come back ranked by the chosen metric")
def _():
    runs = [run("A", 0.1, 5.0), run("B", 0.9, 1.0), run("C", 0.5, 90.0)]
    by_sharpe = [r["symbol"] for r in summarise(runs, "sharpe")["rows"]]
    assert by_sharpe == ["B", "C", "A"], by_sharpe
    # Changing the metric changes only the order, never the contents.
    by_return = [r["symbol"] for r in summarise(runs, "total_return_pct")["rows"]]
    assert by_return == ["C", "A", "B"], by_return


@check("a market that fails does not take the scan with it")
def _():
    runs = [
        run("OK1", 0.5, 10.0),
        MarketRun("BROKEN", "1d", error="Không có nến cho BROKEN 1d"),
        run("OK2", 0.3, 5.0),
    ]
    out = summarise(runs)
    assert out["markets"] == 2, out["markets"]
    assert len(out["failed"]) == 1, out["failed"]
    # And the reason travels with it rather than vanishing into a log.
    assert "BROKEN" in out["failed"][0]["error"], out["failed"][0]


@check("mismatched windows are called out rather than compared")
def _():
    # Same timeframe, same bar count, wildly different spans: a VN equity with
    # thin trading covers far less calendar than BTC over 1,000 bars.
    runs = [run("LONG", 0.4, 50.0, span_days=1000),
            run("SHORT", 0.6, 60.0, span_days=300)]
    comp = summarise(runs)["comparability"]
    assert comp["comparable"] is False, comp
    assert comp["span_ratio"] < 0.75, comp["span_ratio"]
    assert comp["note"]["vi"] and comp["note"]["en"], comp["note"]


@check("mixed timeframes are never called comparable")
def _():
    runs = [run("A", 0.4, 10.0, timeframe="1d", span_days=1000),
            run("B", 0.5, 12.0, timeframe="1h", span_days=1000)]
    comp = summarise(runs)["comparability"]
    # The spans agree here, so only the timeframe mismatch can be failing it.
    assert comp["span_ratio"] == 1.0, comp["span_ratio"]
    assert comp["comparable"] is False, comp
    assert "1d" in comp["note"]["vi"] and "1h" in comp["note"]["vi"]


@check("two markets are too few to deflate against")
def _():
    out = summarise([run("A", 0.5, 10.0), run("B", 1.5, 90.0)])
    assert out["deflated"]["available"] is False, out["deflated"]
    # Refused with a reason, not silently absent.
    assert out["deflated"]["reason"]["vi"], out["deflated"]


@check("a wider search demands a higher bar of its winner")
def _():
    """The whole point: the same best Sharpe is worth less when more were tried.

    Three markets and twelve markets, with the winner identical in both. The
    deflation threshold has to rise with the number of trials, or the scan is
    a machine for finding lucky symbols.
    """
    winner = run("WIN", 1.2, 100.0)

    narrow = summarise([winner, run("A", 0.1, 2.0), run("B", -0.3, -5.0)])
    wide = summarise(
        [winner, run("A", 0.1, 2.0), run("B", -0.3, -5.0)]
        + [run(f"X{i}", 0.05 * i - 0.3, i - 4.0) for i in range(9)]
    )

    assert narrow["deflated"]["available"] and wide["deflated"]["available"]
    assert narrow["deflated"]["trials"] == 3
    assert wide["deflated"]["trials"] == 12

    narrow_bar = narrow["deflated"]["tests"]["deflation_threshold_sharpe"]
    wide_bar = wide["deflated"]["tests"]["deflation_threshold_sharpe"]
    assert wide_bar > narrow_bar, (narrow_bar, wide_bar)

    # And the dispersion is measured across the markets themselves, not
    # approximated the way a lone backtest has to.
    assert wide["deflated"]["trial_dispersion"] > 0


@check("equity curves do not travel in the payload")
def _():
    # Twenty markets times two thousand points is megabytes nobody reads.
    out = summarise([run(f"S{i}", 0.2, 5.0) for i in range(4)])
    for row in out["rows"]:
        assert "equity" not in row, row.keys()


@check("no markets at all is reported as such")
def _():
    out = summarise([MarketRun("A", "1d", error="down"),
                     MarketRun("B", "1d", error="down")])
    assert out["markets"] == 0, out
    assert out["rows"] == []
    assert len(out["failed"]) == 2
    assert out["note"]["vi"] and out["note"]["en"]


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
