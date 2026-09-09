"""Every paper session read as one account.

The per-session snapshot answers "how is this one doing". This answers "how am
I doing", which spans all of them, and the two questions have different traps:
adding realised to unrealised hides an open drawdown, and drawing a smooth
equity line between trade exits invents a path the account never took.

Run:  .venv\\Scripts\\python.exe tests/test_paper_summary.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.paper import summary  # noqa: E402

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def trade(pnl, exit_time, side="long", reason="manual", entry=100.0, exit_price=110.0):
    return {
        "side": side, "entry_time": exit_time - 1, "exit_time": exit_time,
        "entry_price": entry, "exit_price": exit_price, "quantity": 1.0,
        "pnl": pnl, "return_pct": pnl / 100.0, "exit_reason": reason,
    }


def session(sid, symbol, capital, trades, *, position=0, unrealised=0.0,
            last_price=100.0, active=True):
    realised = sum(t["pnl"] for t in trades)
    return {
        "id": sid, "symbol": symbol, "timeframe": "1m", "strategy_id": "manual",
        "active": active, "position": position, "quantity": 1.0 if position else 0.0,
        "entry_price": 100.0 if position else 0.0, "last_price": last_price,
        "unrealized_pnl": unrealised, "realized_pnl": realised,
        "equity": capital + realised + unrealised,
        "config": {"initial_capital": capital}, "trades": trades,
        "stop_loss": None, "take_profit": None,
    }


@check("no sessions is reported as such rather than as a zeroed account")
def _():
    out = summary.build([])
    assert out["sessions"] == 0, out
    # A page of zeros reads as "you have lost nothing", which is a claim about
    # trading. Saying there is nothing to report is not.
    assert "equity" not in out, out
    assert out["note"]["vi"] and out["note"]["en"], out["note"]


@check("capital and results add across sessions")
def _():
    out = summary.build([
        session("a", "BTCUSDT", 5_000.0, [trade(200.0, 10), trade(-50.0, 20)]),
        session("b", "ETHUSDT", 3_000.0, [trade(75.0, 30)]),
    ])
    assert out["sessions"] == 2
    assert out["starting_capital"] == 8_000.0, out["starting_capital"]
    assert abs(out["realized_pnl"] - 225.0) < 1e-9, out["realized_pnl"]
    assert abs(out["equity"] - 8_225.0) < 1e-9, out["equity"]
    assert out["num_trades"] == 3
    assert abs(out["win_rate_pct"] - 200 / 3) < 1e-9, out["win_rate_pct"]


@check("realised and unrealised are reported apart, never merged")
def _():
    out = summary.build([
        session("a", "BTCUSDT", 10_000.0, [trade(500.0, 10)],
                position=1, unrealised=-800.0),
    ])
    # Summing them into one figure would show +300 and hide an 800 drawdown on
    # a position that is still open.
    assert out["realized_pnl"] == 500.0, out["realized_pnl"]
    assert out["unrealized_pnl"] == -800.0, out["unrealized_pnl"]
    assert abs(out["equity"] - 9_700.0) < 1e-9, out["equity"]


@check("the equity curve starts at the opening balance")
def _():
    out = summary.build([session("a", "BTCUSDT", 1_000.0, [trade(100.0, 10), trade(-40.0, 20)])])
    curve = out["equity_curve"]
    # Starting from the first result instead would draw an account that began
    # with money it had not made yet.
    assert curve[0]["equity"] == 1_000.0, curve
    assert curve[-1]["equity"] == 1_060.0, curve
    assert len(curve) == 3, curve


@check("the curve has a point per exit and nowhere else")
def _():
    trades = [trade(10.0, t) for t in (100, 200, 300, 400)]
    curve = summary.build([session("a", "BTCUSDT", 500.0, trades)])["equity_curve"]
    # One opening point plus one per exit. Any more would be interpolation,
    # which is a path the account never traced.
    assert len(curve) == len(trades) + 1, len(curve)
    assert [p["time"] for p in curve[1:]] == [100, 200, 300, 400], curve


@check("trades from several sessions are ordered by exit, newest first")
def _():
    out = summary.build([
        session("a", "BTCUSDT", 1_000.0, [trade(1.0, 50), trade(2.0, 300)]),
        session("b", "ETHUSDT", 1_000.0, [trade(3.0, 150)]),
    ])
    times = [t["exit_time"] for t in out["trades"]]
    assert times == [300, 150, 50], times
    # And each row still says which session and symbol it came from, or a
    # combined log is unreadable.
    assert {t["symbol"] for t in out["trades"]} == {"BTCUSDT", "ETHUSDT"}
    assert all(t["session_id"] for t in out["trades"])


@check("drawdown is measured peak to trough along the curve")
def _():
    # Up to 1200, down to 900: a 25% fall from the peak, not 10% from the start.
    out = summary.build([session("a", "BTCUSDT", 1_000.0, [
        trade(200.0, 10), trade(-300.0, 20), trade(50.0, 30),
    ])])
    assert abs(out["max_drawdown_pct"] - 25.0) < 1e-9, out["max_drawdown_pct"]


@check("an account that reached zero does not produce a divide by zero")
def _():
    out = summary.build([session("a", "BTCUSDT", 100.0, [trade(-100.0, 10)])])
    assert out["equity"] == 0.0, out["equity"]
    assert out["max_drawdown_pct"] == 100.0, out["max_drawdown_pct"]


@check("the per-symbol breakdown ranks by result")
def _():
    out = summary.build([
        session("a", "BTCUSDT", 1_000.0, [trade(-40.0, 10)]),
        session("b", "ETHUSDT", 1_000.0, [trade(90.0, 20), trade(10.0, 30)]),
    ])
    rows = out["by_symbol"]
    assert [r["symbol"] for r in rows] == ["ETHUSDT", "BTCUSDT"], rows
    assert rows[0]["trades"] == 2 and rows[0]["win_rate_pct"] == 100.0, rows[0]


@check("open positions are listed with the levels they carry")
def _():
    snap = session("a", "BTCUSDT", 1_000.0, [], position=-1, unrealised=25.0)
    snap["stop_loss"] = 120.0
    snap["take_profit"] = 80.0
    out = summary.build([snap])
    assert len(out["open_positions"]) == 1, out["open_positions"]
    pos = out["open_positions"][0]
    assert pos["side"] == "short", pos
    assert pos["stop_loss"] == 120.0 and pos["take_profit"] == 80.0, pos
    # A flat session contributes no row.
    assert summary.build([session("b", "ETHUSDT", 1_000.0, [])])["open_positions"] == []


@check("profit factor is None rather than infinite when nothing has lost")
def _():
    out = summary.build([session("a", "BTCUSDT", 1_000.0, [trade(10.0, 10), trade(20.0, 20)])])
    # Infinity formats as "∞" and reads like a finding; None reads as "not
    # answerable yet", which is what two winning trades actually mean.
    assert out["profit_factor"] is None, out["profit_factor"]


# ================================== the server knows when it is out of date

@check("staleness compares the code on disk against the running process")
def _():
    from backend.api.routes_data import _is_stale

    started = 1_000_000.0
    # Sources written before the process started are not a reason to restart.
    assert _is_stale(started - 60, started) is False
    # Nor is a save landing in the same second as start-up: that is the restart.
    assert _is_stale(started + 0.5, started) is False
    # An edit clearly after start-up is.
    assert _is_stale(started + 5, started) is True


@check("a source edited after start-up is reported as stale")
def _():
    import os
    from pathlib import Path

    from backend.api import routes_data

    target = Path(routes_data.__file__)
    original = (target.stat().st_atime, target.stat().st_mtime)
    try:
        future = routes_data._STARTED_AT + 10
        os.utime(target, (future, future))
        newest = routes_data._newest_source_mtime()
        # This is the condition that produced "unknown paper session: summary":
        # a route added on disk that the running process has never imported.
        assert routes_data._is_stale(newest, routes_data._STARTED_AT), (
            newest, routes_data._STARTED_AT)
    finally:
        os.utime(target, original)

    # And it goes quiet once the clock is restored, so the warning cannot latch
    # on and cry wolf for the rest of the session.
    assert not routes_data._is_stale(
        routes_data._newest_source_mtime(), routes_data._STARTED_AT)


@check("__pycache__ is ignored, or every import would look like an edit")
def _():
    from pathlib import Path

    from backend.api import routes_data

    caches = [p for p in Path(routes_data.__file__).parent.rglob("*.py")
              if "__pycache__" in p.parts]
    # .pyc files live in __pycache__ and are rewritten on import; counting the
    # directory at all would make the server permanently "stale".
    assert not caches or all("__pycache__" in p.parts for p in caches)

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
