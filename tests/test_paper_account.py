"""Settlement accounting and live simulated-account updates.

Run: .venv\\Scripts\\python.exe tests/test_paper_account.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.paper import summary
from backend.paper.engine import MANUAL_STRATEGY_ID, PaperSession
from backend.paper.manager import PaperManager
from backend.strategy.engine import BacktestConfig


def close_to(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_settlement_breaks_out_both_fees():
    session = PaperSession(
        MANUAL_STRATEGY_ID, "BTCUSDT", "1m",
        config=BacktestConfig(initial_capital=10_000, size_pct=1, leverage=1,
                              fee=0.001, slippage=0),
    )
    session.on_tick(100)
    session.place_order("long")
    session.on_tick(110)
    session.place_order("close")

    trade = session.trades[0]
    assert close_to(trade.gross_pnl, 1_000)
    assert close_to(trade.entry_fee, 10)
    assert close_to(trade.exit_fee, 11)
    assert close_to(trade.net_pnl, 979)
    assert close_to(trade.balance_before, 10_000)
    assert close_to(trade.balance_after, 10_979)
    assert close_to(trade.balance_after,
                    trade.balance_before + trade.gross_pnl - trade.entry_fee - trade.exit_fee)

    account = summary.build([session.snapshot()])
    row = account["balance_history"][0]
    assert close_to(row["balance_before"], 10_000)
    assert close_to(row["gross_pnl"], 1_000)
    assert close_to(row["fee"], 21)
    assert close_to(row["balance_after"], 10_979)
    assert close_to(account["profitable_trades_pnl"], 979)
    assert close_to(account["expectancy_money"], 979)
    assert close_to(account["expectancy_pct"], 9.79)


def test_legacy_trade_gets_an_auditable_fee_breakdown():
    snapshot = {
        "id": "legacy", "symbol": "BTCUSDT", "timeframe": "1m",
        "strategy_id": "manual", "active": True, "position": 0,
        "quantity": 0, "entry_price": 0, "last_price": 110,
        "unrealized_pnl": 0, "realized_pnl": 979, "equity": 10_979,
        "config": {"initial_capital": 10_000, "fee": 0.001},
        "stop_loss": None, "take_profit": None,
        # Old payload: pnl includes the exit fee, but has no fee fields.
        "trades": [{
            "side": "long", "entry_time": 1, "exit_time": 2,
            "entry_price": 100, "exit_price": 110, "quantity": 100,
            "pnl": 989, "return_pct": 9.89, "exit_reason": "manual",
        }],
    }
    row = summary.build([snapshot])["balance_history"][0]
    assert close_to(row["gross_pnl"], 1_000)
    assert close_to(row["entry_fee"], 10)
    assert close_to(row["exit_fee"], 11)
    assert close_to(row["net_pnl"], 979)


def test_forming_tick_publishes_without_a_fill():
    async def run():
        manager = PaperManager.__new__(PaperManager)
        session = PaperSession(MANUAL_STRATEGY_ID, "BTCUSDT", "1m")
        manager._sessions = {session.id: session}
        messages = []

        async def notify(message):
            messages.append(message)

        manager._notify = notify
        await manager.on_candle({
            "symbol": "BTCUSDT", "timeframe": "1m", "closed": False,
            "open_time": 1_700_000_000_000, "open": 100, "high": 101,
            "low": 99, "close": 100.5, "volume": 1,
        })
        assert [m["type"] for m in messages] == ["paper_update"]
        assert messages[0]["session"]["last_price"] == 100.5

    asyncio.run(run())


def main():
    tests = [
        test_settlement_breaks_out_both_fees,
        test_legacy_trade_gets_an_auditable_fee_breakdown,
        test_forming_tick_publishes_without_a_fill,
    ]
    for test in tests:
        test()
        print(f"  PASS  {test.__name__}")
    print(f"\n{len(tests)} passed, 0 failed")


if __name__ == "__main__":
    main()
