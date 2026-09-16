"""Position models: the linear model held to a recorded run, the contract model
held to hand-computed numbers.

Run:  .venv\\Scripts\\python.exe tests/test_position_model.py

Design: docs/superpowers/specs/2026-09-15-contract-position-model-design.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import make_linear_golden  # noqa: E402

GOLDEN = HERE / "fixtures" / "linear_golden.json"

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def close_to(actual: float, expected: float, tol: float = 1e-9) -> bool:
    return abs(actual - expected) <= tol * max(1.0, abs(expected))


def same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) <= 1e-12 * max(1.0, abs(b))
    return a == b


# --------------------------------------------------------------------------

@check("the golden run exercises liquidation and many trades")
def _():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    leveraged = golden["leverage_25_liquidates"]
    liquidations = sum(t["exit_reason"] == "liquidation" for t in leveraged["trades"])
    # Several liquidations, with the account still trading after them: one
    # liquidation that wipes the account tests only the first trade.
    assert leveraged["liquidated"] is True and liquidations >= 2, liquidations
    assert leveraged["ruined"] is False and len(leveraged["trades"]) > liquidations, leveraged["trades"][-1:]
    assert len(golden["no_costs"]["trades"]) >= 20, len(golden["no_costs"]["trades"])


@check("the linear engine reproduces the recorded run, trade for trade")
def _():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    now = make_linear_golden.record()
    for name, want in golden.items():
        got = now[name]
        assert len(got["trades"]) == len(want["trades"]), (name, len(got["trades"]), len(want["trades"]))
        assert got["liquidated"] == want["liquidated"] and got["ruined"] == want["ruined"], name
        assert len(got["equity"]) == len(want["equity"]), name
        for i, (a, b) in enumerate(zip(got["equity"], want["equity"])):
            assert same(a, b), (name, "equity", i, a, b)
        for i, (ta, tb) in enumerate(zip(got["trades"], want["trades"])):
            for key in tb:
                assert same(ta[key], tb[key]), (name, i, key, ta[key], tb[key])


from backend.strategy.engine import BacktestConfig  # noqa: E402
from backend.strategy.position_model import (  # noqa: E402
    EXECUTION_CONTRACT,
    EXECUTION_CONTRACT_OFF,
    EXECUTION_LINEAR,
    ContractConfig,
    ContractModel,
    LinearModel,
    execution_model_for,
    model_for,
)


def contract_config(**contract) -> BacktestConfig:
    """100 000 000 đ, all equity per trade, margin 20%, threshold 50%, 20 000 đ/contract."""
    values = dict(initial_margin_rate=0.2, maintenance_threshold=0.5, fee_per_contract=20_000.0)
    values.update(contract)
    return BacktestConfig(initial_capital=100_000_000.0, size_pct=1.0, fee=0.0, slippage=0.0,
                          contract=ContractConfig(**values))


@check("model_for picks the contract model only when a contract block is present")
def _():
    assert isinstance(model_for(BacktestConfig()), LinearModel)
    assert isinstance(model_for(contract_config()), ContractModel)


@check("sizing by margin: 3 contracts at 1300 with 100 000 000 dong and a 20% rate")
def _():
    s = model_for(contract_config()).size(100_000_000.0, 1300.0, 1)
    assert s.contracts == 3 and s.quantity == 3.0, s
    assert close_to(s.margin, 78_000_000.0), s.margin
    assert close_to(s.notional, 390_000_000.0), s.notional


@check("fixed sizing refuses what the equity cannot margin, and allows what it can")
def _():
    assert model_for(contract_config(sizing="fixed", contracts=5)).size(100_000_000.0, 1300.0, 1) is None
    s = model_for(contract_config(sizing="fixed", contracts=3)).size(100_000_000.0, 1300.0, -1)
    assert s.contracts == 3 and s.quantity == -3.0, s


@check("P&L is points x multiplier x contracts less the exit fee, for both sides")
def _():
    m = model_for(contract_config())
    long = m.size(100_000_000.0, 1300.0, 1)
    assert close_to(m.entry_fee(long, 1300.0), 60_000.0)
    assert close_to(m.pnl(long, 1300.0, 1310.0), 2_940_000.0), m.pnl(long, 1300.0, 1310.0)
    short = m.size(100_000_000.0, 1300.0, -1)
    assert close_to(m.pnl(short, 1300.0, 1290.0), 2_940_000.0), m.pnl(short, 1300.0, 1290.0)
    assert close_to(m.unrealized(long, 1300.0, 1299.0), -300_000.0)


@check("a notional fee is the rate on contracts x price x multiplier")
def _():
    m = model_for(contract_config(fee_mode="notional", fee_rate=0.0003))
    s = m.size(100_000_000.0, 1300.0, 1)
    assert close_to(m.entry_fee(s, 1300.0), 117_000.0), m.entry_fee(s, 1300.0)


@check("slippage is in points and always adverse")
def _():
    m = model_for(contract_config(slippage_points=0.5))
    assert close_to(m.fill(1300.0, 1), 1300.5)
    assert close_to(m.fill(1310.0, -1), 1309.5)


@check("the forced-close price follows the threshold and the margin rate")
def _():
    m = model_for(contract_config())
    assert close_to(m.liquidation_price(1300.0, 1), 1170.0), m.liquidation_price(1300.0, 1)
    assert close_to(m.liquidation_price(1300.0, -1), 1430.0), m.liquidation_price(1300.0, -1)
    # The linear model keeps its rule: none at leverage 1.
    assert model_for(BacktestConfig(leverage=1.0)).liquidation_price(100.0, 1) is None
    assert close_to(model_for(BacktestConfig(leverage=10.0)).liquidation_price(100.0, 1), 90.0)


@check("restore rebuilds the sizing of a stored position")
def _():
    m = model_for(contract_config())
    s = m.restore(-3.0, 78_000_000.0, 1300.0)
    assert s.contracts == 3 and close_to(s.notional, 390_000_000.0), s


@check("execution_model_for names the model the run used")
def _():
    assert execution_model_for("VN:VN30F1M", contract_config()) == EXECUTION_CONTRACT
    assert execution_model_for("VN:VN30F1M", BacktestConfig()) == EXECUTION_CONTRACT_OFF
    assert execution_model_for("VN:VIC", contract_config()) == EXECUTION_LINEAR
    assert execution_model_for("BTCUSDT", contract_config()) == EXECUTION_LINEAR
    assert execution_model_for(None, BacktestConfig()) == EXECUTION_LINEAR


@check("the contract block survives as_dict and from_dict, and old dicts load without it")
def _():
    cfg = contract_config(sizing="fixed", contracts=2, slippage_points=0.1)
    again = BacktestConfig.from_dict(cfg.as_dict())
    assert again == cfg, (again, cfg)
    old = BacktestConfig().as_dict()
    old.pop("contract")
    assert BacktestConfig.from_dict(old).contract is None


from backend.analysis.report import build_report  # noqa: E402
from backend.strategy.engine import run_backtest  # noqa: E402

HOUR_MS = 3_600_000


def bars(rows) -> pd.DataFrame:
    """rows = [(open, high, low, close), ...]"""
    return pd.DataFrame({
        "open_time": [i * HOUR_MS for i in range(len(rows))],
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
        "volume": [1.0] * len(rows),
    })


@check("a backtest long of 3 contracts books points x multiplier x contracts, less fees")
def _():
    df = bars([(1300, 1300, 1300, 1300), (1300, 1305, 1300, 1305), (1310, 1310, 1310, 1310)])
    r = run_backtest(df, np.array([1, 0, 0], dtype="int8"), contract_config())
    assert len(r.trades) == 1, r.trades
    t = r.trades[0]
    assert t.contracts == 3 and t.multiplier == 100_000.0, t
    assert close_to(t.points, 10.0) and close_to(t.pnl, 2_940_000.0), t
    assert close_to(t.equity_after, 102_880_000.0), t.equity_after
    assert close_to(t.return_pct, 2_940_000.0 / 78_000_000.0 * 100.0), t.return_pct
    assert close_to(float(r.equity[-1]), 102_880_000.0), r.equity[-1]


@check("a backtest short earns the same points when the price falls")
def _():
    df = bars([(1300, 1300, 1300, 1300), (1300, 1300, 1295, 1295), (1290, 1290, 1290, 1290)])
    r = run_backtest(df, np.array([-1, 0, 0], dtype="int8"), contract_config())
    t = r.trades[0]
    assert t.side == "short" and close_to(t.points, 10.0) and close_to(t.pnl, 2_940_000.0), t


@check("point slippage worsens both fills")
def _():
    df = bars([(1300, 1300, 1300, 1300), (1300, 1305, 1300, 1305), (1310, 1310, 1310, 1310)])
    r = run_backtest(df, np.array([1, 0, 0], dtype="int8"), contract_config(slippage_points=0.5))
    t = r.trades[0]
    assert close_to(t.entry_price, 1300.5) and close_to(t.exit_price, 1309.5), t
    assert close_to(t.points, 9.0), t.points


@check("an unaffordable fixed size is not filled")
def _():
    df = bars([(1300, 1300, 1300, 1300), (1300, 1305, 1300, 1305), (1310, 1310, 1310, 1310)])
    r = run_backtest(df, np.array([1, 1, 1], dtype="int8"), contract_config(sizing="fixed", contracts=5))
    assert len(r.trades) == 0, r.trades
    assert all(close_to(float(e), 100_000_000.0) for e in r.equity), r.equity


@check("the margin threshold forces a close inside the bar, and only when reached")
def _():
    hit = bars([(1300, 1300, 1300, 1300), (1300, 1300, 1169, 1200), (1200, 1200, 1200, 1200)])
    r = run_backtest(hit, np.array([1, 1, 1], dtype="int8"), contract_config())
    first = r.trades[0]
    assert first.exit_reason == "liquidation" and close_to(first.exit_price, 1170.0), first
    assert r.liquidated is True

    miss = bars([(1300, 1300, 1300, 1300), (1300, 1300, 1171, 1200), (1200, 1200, 1200, 1200)])
    r = run_backtest(miss, np.array([1, 1, 1], dtype="int8"), contract_config())
    assert [t.exit_reason for t in r.trades] == ["end_of_data"], [t.exit_reason for t in r.trades]


@check("the report's net profit is the trades' P&L less entry fees, and equity telescopes")
def _():
    df = make_linear_golden.frame(n=600, seed=21)
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]] * 13.0  # ~1300
    cfg = contract_config()
    r = run_backtest(df, make_linear_golden.signal(n=600, seed=22), cfg)
    assert len(r.trades) >= 5, len(r.trades)
    report = build_report(r, df, "1h")
    entry_fees = sum(t.contracts * cfg.contract.fee_per_contract for t in r.trades)
    net = report["overview"]["net_profit"]
    assert close_to(net, report["trades"]["all"]["net_profit"] - entry_fees, tol=1e-9), (
        net, report["trades"]["all"]["net_profit"], entry_fees)
    ratio = 1.0
    for t in r.trades:
        ratio *= t.equity_after / t.equity_before
    assert close_to(cfg.initial_capital * ratio, float(r.equity[-1]), tol=1e-9), (
        cfg.initial_capital * ratio, r.equity[-1])


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
