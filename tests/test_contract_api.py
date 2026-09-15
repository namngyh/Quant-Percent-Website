"""The API picks the position model by symbol and says which one it used.

No database and no VPN: candle loading is replaced with synthetic bars, and only
the strategy router is mounted (the full app starts live streams on startup).

Run:  .venv\\Scripts\\python.exe tests/test_contract_api.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.api import routes_strategy  # noqa: E402

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def candles(n: int = 400, base: float = 1300.0, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = base * np.exp(np.cumsum(rng.normal(0.0, 0.004, n)))
    open_ = np.concatenate([[base], close[:-1]])
    return pd.DataFrame({
        "open_time": np.arange(n, dtype="int64") * 3_600_000,
        "open": open_, "high": np.maximum(open_, close) * 1.001,
        "low": np.minimum(open_, close) * 0.999, "close": close, "volume": np.ones(n),
    })


routes_strategy._load_candles = lambda symbol, timeframe, limit, start=None, end=None: (
    candles(), timeframe or "1h")
app = FastAPI()
app.include_router(routes_strategy.router)
client = TestClient(app)

CONTRACT = {"initial_margin_rate": 0.2, "maintenance_threshold": 0.5, "fee_per_contract": 20_000}
EXECUTION = {"initial_capital": 100_000_000, "size_pct": 1.0, "fee": 0, "slippage": 0}


def backtest(symbol: str, contract: dict | None):
    execution = dict(EXECUTION, **({"contract": contract} if contract is not None else {}))
    return client.post("/api/strategies/backtest", json={
        "strategy_id": "example_ema_cross", "symbol": symbol, "timeframe": "1h",
        "execution": execution,
    })


@check("a future without a contract block runs linear and says the model is off")
def _():
    r = backtest("VN:VN30F1M", None)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["execution_model"] == "contract_model_off", body["execution_model"]
    assert all(t["contracts"] is None for t in body["trades"]), body["trades"][:1]


@check("a future with a full contract block trades whole contracts")
def _():
    r = backtest("VN:VN30F1M", CONTRACT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["execution_model"] == "contract", body["execution_model"]
    assert body["trades"], "the fixture should trade"
    for t in body["trades"]:
        assert isinstance(t["contracts"], int) and t["contracts"] >= 1, t
        assert t["quantity"] == float(t["contracts"]) and t["multiplier"] == 100_000.0, t


@check("a contract block missing a required value is refused with a stable code")
def _():
    partial = {k: v for k, v in CONTRACT.items() if k != "maintenance_threshold"}
    r = backtest("VN:VN30F1M", partial)
    assert r.status_code == 422, (r.status_code, r.text)
    detail = r.json()["detail"]
    assert detail["code"] == "contract_settings_required", detail
    assert detail["missing"] == ["maintenance_threshold"], detail
    assert set(detail["message"]) == {"vi", "en"}, detail


@check("a contract block sent with a non-future symbol is ignored")
def _():
    r = backtest("BTCUSDT", CONTRACT)
    assert r.status_code == 200, r.text
    assert r.json()["execution_model"] == "linear"


@check("a scan across markets uses each market's own model")
def _():
    r = client.post("/api/strategies/backtest/markets", json={
        "strategy_id": "example_ema_cross", "symbols": ["BTCUSDT", "VN:VN30F1M"],
        "timeframe": "1h", "execution": dict(EXECUTION, contract=CONTRACT),
    })
    assert r.status_code == 200, r.text
    models = {row["symbol"]: row["execution_model"] for row in r.json()["rows"]}
    assert models == {"BTCUSDT": "linear", "VN:VN30F1M": "contract"}, models


@check("an incomplete contract block fails only the futures row of a scan")
def _():
    partial = {k: v for k, v in CONTRACT.items() if k != "initial_margin_rate"}
    r = client.post("/api/strategies/backtest/markets", json={
        "strategy_id": "example_ema_cross", "symbols": ["BTCUSDT", "VN:VN30F1M"],
        "timeframe": "1h", "execution": dict(EXECUTION, contract=partial),
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert [row["symbol"] for row in body["rows"]] == ["BTCUSDT"], body["rows"]
    failed = {f["symbol"]: f["error"] for f in body["failed"]}
    assert set(failed["VN:VN30F1M"]) == {"vi", "en"}, failed


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
