"""Record what the linear engine produces today, before the position model.

tests/test_position_model.py compares the refactored engine against this file,
so every trade and every equity point must come out the same.

Run once, before changing backend/strategy/engine.py:
    .venv\\Scripts\\python.exe tests/make_linear_golden.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backend.strategy.engine import BacktestConfig, run_backtest  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures" / "linear_golden.json"

TRADE_FIELDS = (
    "side", "entry_index", "exit_index", "entry_price", "exit_price", "quantity",
    "pnl", "return_pct", "bars_held", "exit_reason", "mfe_pct", "mae_pct",
    "equity_before", "equity_after",
)

CASES = {
    "no_costs": dict(fee=0.0, slippage=0.0),
    "fees_and_slippage": dict(fee=0.0004, slippage=0.0002),
    "half_size": dict(fee=0.0004, slippage=0.0002, size_pct=0.5),
    "leverage_5": dict(fee=0.0004, slippage=0.0002, leverage=5.0),
    # A fifth of equity per trade, so a liquidation does not end the run and
    # trading continues after it.
    "leverage_25_liquidates": dict(fee=0.0004, slippage=0.0002, size_pct=0.2, leverage=25.0),
    "high_cost": dict(fee=0.002, slippage=0.001, size_pct=0.8, leverage=2.0),
}


def frame(n: int = 1500, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.015, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    spread = np.abs(rng.normal(0.0, 0.01, n)) * close
    return pd.DataFrame({
        "open_time": np.arange(n, dtype="int64") * 3_600_000,
        "open": open_,
        "high": np.maximum(open_, close) + spread,
        "low": np.minimum(open_, close) - spread,
        "close": close,
        "volume": np.ones(n),
    })


def signal(n: int = 1500, seed: int = 12) -> np.ndarray:
    # Regimes of 5-30 bars of long, short or flat, so entries, exits and
    # reversals all occur many times. (20-80 bar regimes gave only 15 trades.)
    rng = np.random.default_rng(seed)
    out = np.zeros(n, dtype="int8")
    i = 0
    while i < n:
        span = int(rng.integers(5, 30))
        out[i:i + span] = int(rng.choice([-1, 0, 1]))
        i += span
    return out


def record() -> dict:
    df, sig = frame(), signal()
    cases = {}
    for name, kwargs in CASES.items():
        result = run_backtest(df, sig, BacktestConfig(**kwargs))
        cases[name] = {
            "equity": [float(v) for v in result.equity],
            "trades": [{k: getattr(t, k) for k in TRADE_FIELDS} for t in result.trades],
            "liquidated": bool(result.liquidated),
            "ruined": bool(result.ruined),
        }
    return cases


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    data = record()
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    for name, case in data.items():
        liquidations = sum(t["exit_reason"] == "liquidation" for t in case["trades"])
        print(f"{name}: {len(case['trades'])} trades, {liquidations} liquidations, "
              f"ruined={case['ruined']}")
    print(f"wrote {OUT}")
