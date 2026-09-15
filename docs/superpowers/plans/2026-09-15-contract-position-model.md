# Mô hình vị thế theo hợp đồng — Kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backtest và Paper tính hợp đồng tương lai chỉ số VN (VN30F, VN100F) bằng số hợp đồng nguyên, vốn bằng đồng, lãi/lỗ = điểm × hệ số nhân × số hợp đồng; mọi mã khác giữ nguyên kết quả tới từng số.

**Architecture:** Một module `backend/strategy/position_model.py` chứa hai mô hình (tuyến tính, hợp đồng) sau cùng một giao diện; engine backtest và engine Paper gọi mô hình thay vì tự tính ký quỹ, khối lượng, phí, lãi/lỗ, giá thanh lý. API chọn mô hình theo mã qua `ExecutionSettings.to_config(symbol)` và trả `execution_model` trong kết quả.

**Tech Stack:** Python 3.11, FastAPI, pydantic, numpy/pandas; JavaScript thuần; test là script tự chạy in `N passed, M failed`.

**Spec:** `docs/superpowers/specs/2026-09-15-contract-position-model-design.md`

## Global Constraints

- Mô hình tuyến tính phải cho kết quả trùng với engine hiện tại, sai số tương đối ≤ 1e-12 trên mọi lệnh và mọi điểm đường vốn (`tests/fixtures/linear_golden.json`).
- Mô hình hợp đồng chỉ áp dụng cho mã `VN:` có `market_vn.classify(tên) == "futures_vn"`.
- Không có giá trị mặc định cho `initial_margin_rate`, `maintenance_threshold`, phí. Chỉ `multiplier` mặc định `100_000` đ/điểm.
- Thiếu thông số hợp đồng khi đã gửi khối `contract` → HTTP 422 `{"code": "contract_settings_required", "missing": [...], "message": {"vi", "en"}}`.
- Không có khối `contract` trên mã phái sinh → mô hình tuyến tính, `execution_model: "contract_model_off"`.
- Mã ổn định cho `execution_model`: `"linear"`, `"contract"`, `"contract_model_off"`. Giao diện rẽ nhánh theo mã (CLAUDE.md §2.4).
- Văn bản hiển thị song ngữ: backend `bi(vi, en)`, frontend key trong `i18n.js` hoặc `L(vi, en)` (§3.2).
- Sửa file bằng khớp chính xác; không dùng regex `\s+` (§2.3).
- Chạy test: `.venv/Scripts/python.exe tests/<file>.py`; render: `NODE_PATH=./node_modules node tests/test_render.js`.
- Mỗi commit kết thúc bằng dòng `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## File Structure

| File | Trách nhiệm |
|---|---|
| `tests/make_linear_golden.py` (mới) | Ghi kết quả engine tuyến tính **trước** khi sửa |
| `tests/fixtures/linear_golden.json` (mới) | Kết quả đã ghi |
| `tests/test_position_model.py` (mới) | So mốc tuyến tính; kiểm mô hình hợp đồng bằng số tính tay; hệ thức báo cáo |
| `backend/strategy/position_model.py` (mới) | `ContractConfig`, `Sizing`, `LinearModel`, `ContractModel`, `model_for`, `is_index_future`, `execution_model_for` |
| `backend/strategy/engine.py` | `BacktestConfig.contract`, `from_dict`; `Trade.points/contracts/multiplier`; `run_backtest` gọi mô hình |
| `backend/paper/engine.py` | `PaperSession` gọi mô hình; từ chối `insufficient_margin`; snapshot thêm `contracts`, `multiplier`, `execution_model` |
| `backend/paper/manager.py` | Nạp cấu hình bằng `BacktestConfig.from_dict` |
| `tests/test_paper.py` | Paper khớp backtest với hợp đồng; từ chối thiếu ký quỹ; lưu/nạp khối `contract` |
| `backend/api/routes_strategy.py` | `ContractSettings`, `ContractSettingsRequired`, `to_config(symbol)`, `config_for`, `execution_model` |
| `backend/api/routes_validation.py`, `routes_stats.py`, `routes_paper.py` | Gọi `config_for(execution, symbol)` |
| `backend/strategy/multi.py` | Dòng thị trường mang `execution_model` |
| `tests/test_contract_api.py` (mới) | API: tắt mô hình, thiếu thông số, trộn nhiều thị trường |
| `frontend/js/i18n.js`, `strategy.js`, `paper.js`, `markets.js` | Ghi chú `contract_model_off`; lỗi song ngữ của dòng thị trường |
| `tests/test_render.js` | Ghi chú hiển thị đúng ở hai ngôn ngữ |

---

### Task 1: Ghi mốc kết quả tuyến tính trước khi sửa engine

**Files:**
- Create: `tests/make_linear_golden.py`
- Create: `tests/fixtures/linear_golden.json` (sinh bởi script)
- Create: `tests/test_position_model.py`

**Interfaces:**
- Produces: `make_linear_golden.frame(n=1500, seed=11) -> pd.DataFrame`, `make_linear_golden.signal(n=1500, seed=12) -> np.ndarray`, `make_linear_golden.CASES: dict[str, dict]`, `make_linear_golden.TRADE_FIELDS: tuple[str, ...]`, `make_linear_golden.record() -> dict`; harness `check`, `close_to` trong `tests/test_position_model.py`.

- [ ] **Step 1: Viết script ghi mốc**

`tests/make_linear_golden.py`:

```python
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
    "leverage_25_liquidates": dict(fee=0.0004, slippage=0.0002, leverage=25.0),
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
    # Regimes of 20-80 bars of long, short or flat, so entries, exits and
    # reversals all occur.
    rng = np.random.default_rng(seed)
    out = np.zeros(n, dtype="int8")
    i = 0
    while i < n:
        span = int(rng.integers(20, 80))
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
        print(f"{name}: {len(case['trades'])} trades, liquidated={case['liquidated']}")
    print(f"wrote {OUT}")
```

- [ ] **Step 2: Chạy script trên engine hiện tại**

Run: `.venv/Scripts/python.exe tests/make_linear_golden.py`
Expected: 6 dòng tóm tắt; `leverage_25_liquidates` có `liquidated=True`; `no_costs` có ≥ 20 lệnh; dòng cuối `wrote ...linear_golden.json`.

- [ ] **Step 3: Viết test so mốc**

`tests/test_position_model.py`:

```python
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
    assert golden["leverage_25_liquidates"]["liquidated"] is True
    assert any(t["exit_reason"] == "liquidation"
               for t in golden["leverage_25_liquidates"]["trades"])
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
```

- [ ] **Step 4: Chạy test**

Run: `.venv/Scripts/python.exe tests/test_position_model.py`
Expected: `2 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tests/make_linear_golden.py tests/fixtures/linear_golden.json tests/test_position_model.py
git commit -m "Record the linear engine's output before the position model" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Module `position_model` và trường `BacktestConfig.contract`

**Files:**
- Create: `backend/strategy/position_model.py`
- Modify: `backend/strategy/engine.py:29-44` (`BacktestConfig`)
- Test: `tests/test_position_model.py`

**Interfaces:**
- Consumes: không.
- Produces:
  - `ContractConfig(initial_margin_rate: float, maintenance_threshold: float, sizing: str = "margin", contracts: int = 1, multiplier: float = 100_000.0, fee_mode: str = "per_contract", fee_per_contract: float = 0.0, fee_rate: float = 0.0, slippage_points: float = 0.0)`, `.as_dict() -> dict`, `ContractConfig.from_dict(dict) -> ContractConfig`
  - `Sizing(quantity: float, margin: float, notional: float, contracts: int | None = None)` (frozen)
  - `LinearModel(config)` / `ContractModel(config)`, cả hai có: `kind: str`, `multiplier: float | None`, `fill(price, direction) -> float`, `size(equity, price, direction, size_pct=None) -> Sizing | None`, `restore(quantity, margin, entry_price) -> Sizing`, `entry_fee(sizing, price) -> float`, `exit_fee(sizing, exit_price) -> float`, `unrealized(sizing, entry_price, mark) -> float`, `pnl(sizing, entry_price, exit_price) -> float`, `liquidation_price(entry_price, direction) -> float | None`
  - `model_for(config) -> LinearModel | ContractModel`
  - `is_index_future(symbol: str | None) -> bool`
  - `execution_model_for(symbol: str | None, config) -> str`
  - Hằng `EXECUTION_LINEAR = "linear"`, `EXECUTION_CONTRACT = "contract"`, `EXECUTION_CONTRACT_OFF = "contract_model_off"`
  - `BacktestConfig.contract: ContractConfig | None = None`, `BacktestConfig.as_dict()` có khóa `"contract"`, `BacktestConfig.from_dict(dict) -> BacktestConfig`

- [ ] **Step 1: Viết test hỏng**

Thêm vào `tests/test_position_model.py`, ngay trước `def main()`:

```python
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
```

- [ ] **Step 2: Chạy để thấy hỏng**

Run: `.venv/Scripts/python.exe tests/test_position_model.py`
Expected: dừng ở import với `ModuleNotFoundError: No module named 'backend.strategy.position_model'`.

- [ ] **Step 3: Viết module**

`backend/strategy/position_model.py`:

```python
"""How a position is sized, charged and marked.

Two models behind one interface, used by both the backtest engine and the paper
engine, so the execution rules (CLAUDE.md §3.1) are written in one place.

* LinearModel: crypto, equities, indices, commodities. Margin = equity x
  size_pct, notional = margin x leverage, quantity = notional / price, fees a
  fraction of notional. The same arithmetic the engines used before this
  module; tests/test_position_model.py holds it to a recorded run.
* ContractModel: Vietnamese index futures (market_vn class ``futures_vn``).
  Capital in dong, whole contracts, P&L = points x multiplier x contracts,
  margin by rate, forced close by a margin threshold.

Design: docs/superpowers/specs/2026-09-15-contract-position-model-design.md
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

EXECUTION_LINEAR = "linear"
EXECUTION_CONTRACT = "contract"
EXECUTION_CONTRACT_OFF = "contract_model_off"


@dataclass
class ContractConfig:
    initial_margin_rate: float          # (0, 1]
    maintenance_threshold: float        # [0, 1): remaining margin share that forces a close
    sizing: str = "margin"              # "margin" | "fixed"
    contracts: int = 1                  # used when sizing == "fixed"
    multiplier: float = 100_000.0       # dong per index point
    fee_mode: str = "per_contract"      # "per_contract" | "notional"
    fee_per_contract: float = 0.0       # dong per contract, per side
    fee_rate: float = 0.0               # fraction of notional, per side
    slippage_points: float = 0.0        # adverse, per fill

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ContractConfig":
        return cls(**data)


@dataclass(frozen=True)
class Sizing:
    quantity: float           # signed: base units (linear) or contracts (contract)
    margin: float             # committed to the position
    notional: float           # at entry
    contracts: int | None = None


class LinearModel:
    kind = EXECUTION_LINEAR
    multiplier = None

    def __init__(self, config) -> None:
        self.config = config

    def fill(self, price: float, direction: int) -> float:
        return price * (1.0 + self.config.slippage * direction)

    def size(self, equity: float, price: float, direction: int,
             size_pct: float | None = None) -> Sizing | None:
        margin = equity * (self.config.size_pct if size_pct is None else size_pct)
        notional = margin * self.config.leverage
        return Sizing(quantity=notional / price * direction, margin=margin, notional=notional)

    def restore(self, quantity: float, margin: float, entry_price: float) -> Sizing:
        return Sizing(quantity=quantity, margin=margin, notional=margin * self.config.leverage)

    def entry_fee(self, sizing: Sizing, price: float) -> float:
        return sizing.notional * self.config.fee

    def exit_fee(self, sizing: Sizing, exit_price: float) -> float:
        return abs(sizing.quantity) * exit_price * self.config.fee

    def unrealized(self, sizing: Sizing, entry_price: float, mark: float) -> float:
        return sizing.quantity * (mark - entry_price)

    def pnl(self, sizing: Sizing, entry_price: float, exit_price: float) -> float:
        return sizing.quantity * (exit_price - entry_price) - self.exit_fee(sizing, exit_price)

    def liquidation_price(self, entry_price: float, direction: int) -> float | None:
        if self.config.leverage <= 1.0:
            return None
        return entry_price * (1.0 - direction / self.config.leverage)


class ContractModel:
    kind = EXECUTION_CONTRACT

    def __init__(self, config) -> None:
        self.config = config
        self.contract: ContractConfig = config.contract
        self.multiplier = self.contract.multiplier

    def fill(self, price: float, direction: int) -> float:
        return price + self.contract.slippage_points * direction

    def margin_per_contract(self, price: float) -> float:
        return price * self.multiplier * self.contract.initial_margin_rate

    def size(self, equity: float, price: float, direction: int,
             size_pct: float | None = None) -> Sizing | None:
        per = self.margin_per_contract(price)
        if per <= 0:
            return None
        if self.contract.sizing == "fixed":
            contracts = int(self.contract.contracts)
        else:
            share = self.config.size_pct if size_pct is None else size_pct
            contracts = math.floor(equity * share / per)
        # Not enough margin for one contract, or for the fixed count: no fill.
        if contracts < 1 or contracts * per > equity:
            return None
        return Sizing(quantity=float(contracts * direction), margin=contracts * per,
                      notional=contracts * price * self.multiplier, contracts=contracts)

    def restore(self, quantity: float, margin: float, entry_price: float) -> Sizing:
        contracts = int(round(abs(quantity)))
        return Sizing(quantity=quantity, margin=margin,
                      notional=contracts * entry_price * self.multiplier, contracts=contracts)

    def _fee(self, contracts: int, price: float) -> float:
        if self.contract.fee_mode == "notional":
            return contracts * price * self.multiplier * self.contract.fee_rate
        return contracts * self.contract.fee_per_contract

    def entry_fee(self, sizing: Sizing, price: float) -> float:
        return self._fee(sizing.contracts, price)

    def exit_fee(self, sizing: Sizing, exit_price: float) -> float:
        return self._fee(sizing.contracts, exit_price)

    def unrealized(self, sizing: Sizing, entry_price: float, mark: float) -> float:
        return sizing.quantity * (mark - entry_price) * self.multiplier

    def pnl(self, sizing: Sizing, entry_price: float, exit_price: float) -> float:
        return self.unrealized(sizing, entry_price, exit_price) - self.exit_fee(sizing, exit_price)

    def liquidation_price(self, entry_price: float, direction: int) -> float | None:
        # (margin + unrealized) <= threshold x margin, solved for the price.
        # Always checked: the effective leverage 1 / rate is above 1.
        c = self.contract
        return entry_price * (1.0 - direction * (1.0 - c.maintenance_threshold) * c.initial_margin_rate)


def model_for(config) -> LinearModel | ContractModel:
    return ContractModel(config) if getattr(config, "contract", None) else LinearModel(config)


def is_index_future(symbol: str | None) -> bool:
    """True for a Vietnamese index future such as ``VN:VN30F1M``."""
    name = (symbol or "").strip()
    if not name.upper().startswith("VN:"):
        return False
    # Imported here: the data module is only needed for this question.
    from backend.data.market_vn import classify
    return classify(name[3:]) == "futures_vn"


def execution_model_for(symbol: str | None, config) -> str:
    if not is_index_future(symbol):
        return EXECUTION_LINEAR
    return EXECUTION_CONTRACT if getattr(config, "contract", None) else EXECUTION_CONTRACT_OFF
```

- [ ] **Step 4: Thêm `contract` vào `BacktestConfig`**

Trong `backend/strategy/engine.py`, thay:

```python
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BacktestConfig:
    initial_capital: float = 10_000.0
    size_pct: float = 1.0       # fraction of equity committed as margin
    leverage: float = 1.0
    fee: float = 0.0004         # taker, per side, on notional
    slippage: float = 0.0002    # adverse price move per fill

    def as_dict(self) -> dict:
        return {
            "initial_capital": self.initial_capital,
            "size_pct": self.size_pct,
            "leverage": self.leverage,
            "fee": self.fee,
            "slippage": self.slippage,
        }
```

bằng:

```python
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.strategy.position_model import ContractConfig, Sizing, model_for


@dataclass
class BacktestConfig:
    initial_capital: float = 10_000.0
    size_pct: float = 1.0       # fraction of equity committed as margin
    leverage: float = 1.0
    fee: float = 0.0004         # taker, per side, on notional
    slippage: float = 0.0002    # adverse price move per fill
    # Index futures only: whole contracts, dong per point, margin by rate.
    # None means the linear model (backend/strategy/position_model.py).
    contract: ContractConfig | None = None

    def as_dict(self) -> dict:
        return {
            "initial_capital": self.initial_capital,
            "size_pct": self.size_pct,
            "leverage": self.leverage,
            "fee": self.fee,
            "slippage": self.slippage,
            "contract": self.contract.as_dict() if self.contract else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BacktestConfig":
        values = dict(data)
        contract = values.pop("contract", None)
        return cls(**values, contract=ContractConfig.from_dict(contract) if contract else None)
```

(`Sizing` và `model_for` được dùng ở Task 3.)

- [ ] **Step 5: Chạy test**

Run: `.venv/Scripts/python.exe tests/test_position_model.py`
Expected: `12 passed, 0 failed`.

Run: `.venv/Scripts/python.exe tests/test_engine.py`
Expected: `12 passed, 0 failed`.

- [ ] **Step 6: Commit**

```bash
git add backend/strategy/position_model.py backend/strategy/engine.py tests/test_position_model.py
git commit -m "Add linear and contract position models behind one interface" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Engine backtest gọi mô hình vị thế

**Files:**
- Modify: `backend/strategy/engine.py` (`Trade`, `run_backtest`)
- Test: `tests/test_position_model.py`

**Interfaces:**
- Consumes: `model_for`, `Sizing` (Task 2).
- Produces: `Trade.points: float = 0.0`, `Trade.contracts: int | None = None`, `Trade.multiplier: float | None = None`; `run_backtest` bỏ qua tín hiệu khi `model.size(...)` trả `None`.

- [ ] **Step 1: Viết test hỏng**

Thêm vào `tests/test_position_model.py`, trước `def main()`:

```python
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
```

- [ ] **Step 2: Chạy để thấy hỏng**

Run: `.venv/Scripts/python.exe tests/test_position_model.py`
Expected: các check mới FAIL/ERROR (ví dụ `AttributeError: 'Trade' object has no attribute 'contracts'`); hai check mốc và các check Task 2 vẫn PASS.

- [ ] **Step 3: Thêm trường vào `Trade`**

Trong `backend/strategy/engine.py`, thay:

```python
    equity_before: float = 0.0
    equity_after: float = 0.0

    def as_dict(self) -> dict:
        return self.__dict__.copy()
```

bằng:

```python
    equity_before: float = 0.0
    equity_after: float = 0.0
    # The price move in points, signed by side. Both models carry it; the
    # contract model also records the whole contracts held and the multiplier
    # (dong per point) that turned points into money.
    points: float = 0.0
    contracts: int | None = None
    multiplier: float | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()
```

- [ ] **Step 4: Viết lại phần thân `run_backtest`**

Trong `backend/strategy/engine.py`, thay toàn bộ đoạn từ dòng `    config = config or BacktestConfig()` tới hết hàm `run_backtest` bằng:

```python
    config = config or BacktestConfig()
    n = len(df)
    if n == 0:
        return BacktestResult(config=config)

    # Sizing, fees, P&L and the forced-close price come from the position
    # model, shared with the paper engine (backend/strategy/position_model.py).
    model = model_for(config)

    open_ = df["open"].to_numpy(dtype="float64")
    high = df["high"].to_numpy(dtype="float64")
    low = df["low"].to_numpy(dtype="float64")
    close = df["close"].to_numpy(dtype="float64")
    times = (df["open_time"].to_numpy(dtype="int64") // 1000).tolist()

    # A signal computed on bar i is actionable only from bar i+1's open.
    target = np.zeros(n, dtype="int8")
    target[1:] = signal[:-1]

    equity = config.initial_capital
    equity_curve = np.empty(n, dtype="float64")
    position_curve = np.zeros(n, dtype="int8")

    position = 0          # -1 short, 0 flat, 1 long
    sizing: Sizing | None = None
    entry_price = 0.0
    margin = 0.0
    entry_index = -1
    entry_equity = 0.0    # account equity when the position was opened
    best_price = 0.0      # most favourable price seen since entry
    worst_price = 0.0     # least favourable
    trades: list[Trade] = []
    liquidated_ever = False
    ruined = False

    def fill_price(price: float, direction: int) -> float:
        """Worsen a fill by slippage; ``direction`` is +1 when buying."""
        return model.fill(price, direction)

    def close_position(exit_price: float, index: int, reason: str) -> None:
        nonlocal equity, position, sizing, entry_price, margin, entry_index
        nonlocal best_price, worst_price
        pnl = model.pnl(sizing, entry_price, exit_price)
        equity += pnl

        # Excursions on the same base as return_pct: unrealised P&L on the
        # committed margin, gross of the exit fee (which is not owed until the
        # trade actually closes).
        if margin > 0:
            mfe = model.unrealized(sizing, entry_price, best_price) / margin * 100.0
            mae = model.unrealized(sizing, entry_price, worst_price) / margin * 100.0
        else:
            mfe = mae = 0.0

        trades.append(
            Trade(
                side="long" if position > 0 else "short",
                entry_index=entry_index,
                exit_index=index,
                entry_time=times[entry_index],
                exit_time=times[index],
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=abs(sizing.quantity),
                pnl=pnl,
                return_pct=(pnl / margin * 100.0) if margin > 0 else 0.0,
                bars_held=index - entry_index,
                exit_reason=reason,
                # Clamped: MFE is favourable-or-nothing, MAE adverse-or-nothing,
                # so a trade that only ever moved one way reports 0 for the
                # other rather than a sign-flipped value.
                mfe_pct=max(mfe, 0.0),
                mae_pct=min(mae, 0.0),
                equity_before=entry_equity,
                equity_after=equity,
                points=(exit_price - entry_price) * position,
                contracts=sizing.contracts,
                multiplier=model.multiplier,
            )
        )

        position = 0
        sizing = None
        entry_price = 0.0
        margin = 0.0
        entry_index = -1
        best_price = worst_price = 0.0

    def open_position(price: float, index: int, direction: int) -> None:
        nonlocal equity, position, sizing, entry_price, margin, entry_index
        nonlocal best_price, worst_price, entry_equity
        new = model.size(equity, price, direction)
        if new is None:
            # Not enough margin for one contract (or for the fixed count):
            # the signal is not filled.
            return
        entry_equity = equity          # before the entry fee is taken
        sizing = new
        margin = new.margin
        entry_price = price
        entry_index = index
        position = direction
        # Start both excursions at the entry price: a trade that closes before
        # any further bar has moved neither way.
        best_price = worst_price = price
        equity -= model.entry_fee(new, price)   # entry fee, paid immediately

    for i in range(n):
        if not ruined:
            # 1. Act on the previous bar's signal, at this bar's open.
            if target[i] != position:
                if position != 0:
                    close_position(fill_price(open_[i], -position), i, "signal")
                if target[i] != 0 and equity > 0:
                    open_position(fill_price(open_[i], target[i]), i, target[i])

            # 1b. Track how far this bar took the open position either way.
            #     After the fill, so the entry bar is measured from the price
            #     actually paid; before liquidation, so the wick that ends a
            #     trade is still counted in its MAE.
            if position != 0:
                if position > 0:
                    best_price = max(best_price, high[i])
                    worst_price = min(worst_price, low[i])
                else:
                    best_price = min(best_price, low[i])
                    worst_price = max(worst_price, high[i])

            # 2. Liquidation: does this bar's adverse extreme reach the price at
            #    which the position is force-closed? None means no such price
            #    (the linear model at leverage 1).
            if position != 0:
                liq_price = model.liquidation_price(entry_price, position)
                if liq_price is not None:
                    hit = low[i] <= liq_price if position > 0 else high[i] >= liq_price
                    if hit:
                        close_position(liq_price, i, "liquidation")
                        liquidated_ever = True

            if equity <= 0:
                equity = 0.0
                ruined = True

        # 3. Mark to market on this bar's close.
        unrealized = model.unrealized(sizing, entry_price, close[i]) if position != 0 else 0.0
        equity_curve[i] = max(equity + unrealized, 0.0)
        position_curve[i] = position

    # Close any position still open, so the trade list is complete.
    if position != 0:
        close_position(fill_price(close[n - 1], -position), n - 1, "end_of_data")
        equity_curve[n - 1] = max(equity, 0.0)

    return BacktestResult(
        equity=equity_curve,
        times=times,
        trades=trades,
        position=position_curve,
        config=config,
        liquidated=liquidated_ever,
        ruined=ruined,
    )
```

- [ ] **Step 5: Chạy test**

Run: `.venv/Scripts/python.exe tests/test_position_model.py`
Expected: `18 passed, 0 failed`. Nếu check mốc tuyến tính FAIL: dừng, so thứ tự phép tính của `LinearModel` với đoạn engine cũ (`git show HEAD:backend/strategy/engine.py`), không sửa file mốc.

Run: `.venv/Scripts/python.exe tests/test_engine.py`, `tests/test_report.py`, `tests/test_validation.py`, `tests/test_optimizer.py`, `tests/test_strategy_pipeline.py`
Expected: số passed như trước (12, 23, 25, 24, 15), 0 failed.

- [ ] **Step 6: Commit**

```bash
git add backend/strategy/engine.py tests/test_position_model.py
git commit -m "Size, charge and mark backtest positions through the position model" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Engine Paper gọi mô hình vị thế, lưu/nạp khối `contract`

**Files:**
- Modify: `backend/paper/engine.py`
- Modify: `backend/paper/manager.py` (`_from_payload`)
- Test: `tests/test_paper.py`

**Interfaces:**
- Consumes: `model_for`, `execution_model_for` (Task 2); `BacktestConfig.from_dict` (Task 2).
- Produces: `PaperTrade.points/contracts/multiplier`; `PaperSession.model` (property); `PaperSession._open(...) -> bool`; `OrderRefused("insufficient_margin")`; snapshot thêm `"contracts"`, `"multiplier"`, `"execution_model"`.

- [ ] **Step 1: Viết test hỏng**

Thêm vào `tests/test_paper.py`, ngay trước `def main()`:

```python
from backend.strategy.position_model import ContractConfig  # noqa: E402


def contract_cfg(**contract) -> BacktestConfig:
    values = dict(initial_margin_rate=0.2, maintenance_threshold=0.5,
                  fee_per_contract=20_000.0, slippage_points=0.05)
    values.update(contract)
    return BacktestConfig(initial_capital=100_000_000.0, size_pct=1.0, fee=0.0, slippage=0.0,
                          contract=ContractConfig(**values))


@check("with contracts, replaying history still reproduces the backtest trades")
def _():
    df = series()                       # prices near 100: 2 000 000 dong margin per contract
    cfg = contract_cfg()
    spec = registry.get_spec("example_ema_cross")
    resolved = spec.resolve_params(None)
    frame = df.copy()
    frame.index = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    signal = normalize_signals(spec.signals(frame, resolved), frame.index, spec.side)
    expected = run_backtest(df, signal, cfg)

    session = replay(df, "example_ema_cross", cfg)
    settled = [t for t in expected.trades if t.exit_reason != "end_of_data"]
    assert len(session.trades) == len(settled) and len(settled) > 3, (len(session.trades), len(settled))
    for got, want in zip(session.trades, settled, strict=True):
        assert got.contracts == want.contracts and got.contracts >= 1, (got, want)
        assert got.entry_time == want.entry_time and got.exit_time == want.exit_time, (got, want)
        assert close_to(got.entry_price, want.entry_price), (got.entry_price, want.entry_price)
        assert close_to(got.exit_price, want.exit_price), (got.exit_price, want.exit_price)
        assert close_to(got.pnl, want.pnl), (got.pnl, want.pnl)
        assert close_to(got.points, want.points), (got.points, want.points)


@check("a hand order the equity cannot margin is refused before anything changes")
def _():
    s = PaperSession(MANUAL_STRATEGY_ID, "VN:VN30F1M", "1m",
                     config=contract_cfg(sizing="fixed", contracts=1000))
    s.on_tick(1300.0)
    try:
        s.place_order("long")
    except OrderRefused as exc:
        assert exc.code == "insufficient_margin", exc.code
        assert set(exc.message) == {"vi", "en"}, exc.message
    else:
        raise AssertionError("an unaffordable order was filled")
    assert s.position == 0 and not s.trades and s.equity == 100_000_000.0, s.snapshot()


@check("a hand order on contracts fills whole contracts and reports the model")
def _():
    s = PaperSession(MANUAL_STRATEGY_ID, "VN:VN30F1M", "1m", config=contract_cfg())
    s.on_tick(1300.0)
    s.place_order("long")
    snap = s.snapshot()
    # Fill at 1300.05: margin per contract 26 010 000 dong -> 3 contracts.
    assert snap["contracts"] == 3 and snap["quantity"] == 3.0, snap
    assert snap["multiplier"] == 100_000.0 and snap["execution_model"] == "contract", snap
    s.on_tick(1310.0)
    assert close_to(s.unrealized(), 3 * (1310.0 - 1300.05) * 100_000.0), s.unrealized()


@check("a paper session without a contract block on a future says the model is off")
def _():
    s = PaperSession(MANUAL_STRATEGY_ID, "VN:VN30F1M", "1m", config=BacktestConfig())
    assert s.snapshot()["execution_model"] == "contract_model_off"


@check("a restart keeps the contract block, and an old row loads linear")
def _():
    from backend.data import sources as data_sources
    from backend.paper.manager import PaperManager

    s = PaperSession(MANUAL_STRATEGY_ID, "VN:VN30F1M", "1m", config=contract_cfg(sizing="fixed", contracts=2))
    s.on_tick(1300.0)
    s.place_order("long")
    manager = PaperManager.__new__(PaperManager)
    payload = manager._to_payload(s)

    original = data_sources.get_candles
    data_sources.get_candles = lambda *a, **k: pd.DataFrame()
    try:
        restored = manager._from_payload(payload)
        assert restored.config == s.config, (restored.config, s.config)
        assert restored.snapshot()["contracts"] == 2, restored.snapshot()
        payload["config"].pop("contract")
        assert manager._from_payload(payload).config.contract is None
    finally:
        data_sources.get_candles = original
```

- [ ] **Step 2: Chạy để thấy hỏng**

Run: `.venv/Scripts/python.exe tests/test_paper.py`
Expected: 5 check mới FAIL/ERROR; 31 check cũ PASS.

- [ ] **Step 3: Sửa `backend/paper/engine.py`**

Thay dòng import:

```python
from backend.strategy.engine import BacktestConfig
```

bằng:

```python
from backend.strategy.engine import BacktestConfig
from backend.strategy.position_model import execution_model_for, model_for
```

Thay khối `PaperTrade`:

```python
    return_pct: float
    exit_reason: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()
```

bằng:

```python
    return_pct: float
    exit_reason: str
    # Same meaning as on the backtest Trade (backend/strategy/engine.py).
    points: float = 0.0
    contracts: int | None = None
    multiplier: float | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()
```

Thay đoạn từ `    # ------------------------------------------------------------------ fills` tới hết `_open`:

```python
    # ------------------------------------------------------------------ fills

    @property
    def model(self):
        """Sizing, fees and marking, shared with the backtest engine."""
        return model_for(self.config)

    def _sizing(self):
        return self.model.restore(self.quantity, self.margin, self.entry_price)

    def _fill_price(self, price: float, direction: int) -> float:
        return self.model.fill(price, direction)

    def _close(self, exit_price: float, when: int, reason: str) -> PaperTrade:
        model = self.model
        sizing = self._sizing()
        pnl = model.pnl(sizing, self.entry_price, exit_price)
        self.equity += pnl

        trade = PaperTrade(
            side="long" if self.position > 0 else "short",
            entry_time=self.entry_time,
            exit_time=when,
            entry_price=self.entry_price,
            exit_price=exit_price,
            quantity=abs(self.quantity),
            pnl=pnl,
            return_pct=(pnl / self.margin * 100.0) if self.margin > 0 else 0.0,
            exit_reason=reason,
            points=(exit_price - self.entry_price) * self.position,
            contracts=sizing.contracts,
            multiplier=model.multiplier,
        )
        self.trades.append(trade)

        self.position = 0
        self.quantity = 0.0
        self.entry_price = 0.0
        self.margin = 0.0
        self.entry_time = 0
        self.stop_loss = None
        self.take_profit = None
        return trade

    def _open(
        self, price: float, when: int, direction: int, size_pct: float | None = None
    ) -> bool:
        """Open at ``price``. False when the equity cannot margin the position."""
        # A hand order may stake a different share of the account than the
        # strategy's configured size; everything downstream is unchanged.
        sizing = self.model.size(self.equity, price, direction, size_pct)
        if sizing is None:
            return False
        self.margin = sizing.margin
        self.quantity = sizing.quantity
        self.entry_price = price
        self.entry_time = when
        self.position = direction
        self.equity -= self.model.entry_fee(sizing, price)
        return True
```

Trong `place_order`, thay:

```python
        when = int(time.time())
        events: list[dict] = []
```

bằng:

```python
        # Refuse before anything changes: a reversal whose new side cannot be
        # margined must not close the old side first and then fail.
        if target != 0:
            equity_after_close = self.equity
            if self.position != 0:
                equity_after_close += self.model.pnl(
                    self._sizing(), self.entry_price,
                    self._fill_price(self.last_price, -self.position),
                )
            fill = self._fill_price(self.last_price, target)
            if self.model.size(equity_after_close, fill, target, size_pct) is None:
                raise OrderRefused(
                    "insufficient_margin",
                    "Không đủ ký quỹ cho vị thế này ở giá hiện tại.",
                    "Not enough margin for this position at the current price.",
                )

        when = int(time.time())
        events: list[dict] = []
```

Trong `on_closed_candle`, thay:

```python
            if self.pending_signal != 0 and self.equity > 0:
                self._open(
                    self._fill_price(open_price, self.pending_signal),
                    when,
                    self.pending_signal,
                )
                events.append(
```

bằng:

```python
            if self.pending_signal != 0 and self.equity > 0 and self._open(
                self._fill_price(open_price, self.pending_signal),
                when,
                self.pending_signal,
            ):
                events.append(
```

Thay:

```python
        # 2. Liquidation, checked against this candle's adverse extreme.
        if self.position != 0 and self.config.leverage > 1.0:
            liq = self.entry_price * (1.0 - self.position / self.config.leverage)
            hit = float(candle["low"]) <= liq if self.position > 0 else float(candle["high"]) >= liq
            if hit:
                trade = self._close(liq, when, "liquidation")
                events.append({"type": "liquidation", "trade": trade.as_dict()})
```

bằng:

```python
        # 2. Liquidation, checked against this candle's adverse extreme. None
        #    means the model has no forced-close price (linear at leverage 1).
        liq = self.model.liquidation_price(self.entry_price, self.position) if self.position != 0 else None
        if liq is not None:
            hit = float(candle["low"]) <= liq if self.position > 0 else float(candle["high"]) >= liq
            if hit:
                trade = self._close(liq, when, "liquidation")
                events.append({"type": "liquidation", "trade": trade.as_dict()})
```

Thay:

```python
        return self.quantity * (self.last_price - self.entry_price)
```

bằng:

```python
        return self.model.unrealized(self._sizing(), self.entry_price, self.last_price)
```

Trong `snapshot`, thay:

```python
            "quantity": abs(self.quantity),
```

bằng:

```python
            "quantity": abs(self.quantity),
            "contracts": self._sizing().contracts if self.position != 0 else None,
            "multiplier": self.model.multiplier,
            "execution_model": execution_model_for(self.symbol, self.config),
```

- [ ] **Step 4: Sửa `backend/paper/manager.py`**

Thay:

```python
            params=d.get("params", {}), config=BacktestConfig(**d["config"]),
```

bằng:

```python
            params=d.get("params", {}), config=BacktestConfig.from_dict(d["config"]),
```

Run: `grep -rn "BacktestConfig(\*\*" backend tests`
Expected: không còn dòng nào. Nếu còn, đổi dòng đó sang `BacktestConfig.from_dict(...)` theo cùng cách.

- [ ] **Step 5: Chạy test**

Run: `.venv/Scripts/python.exe tests/test_paper.py`
Expected: `36 passed, 0 failed`.

Run: `.venv/Scripts/python.exe tests/test_paper_summary.py` và `tests/test_position_model.py`
Expected: `14 passed, 0 failed` và `18 passed, 0 failed`.

- [ ] **Step 6: Commit**

```bash
git add backend/paper/engine.py backend/paper/manager.py tests/test_paper.py
git commit -m "Run paper positions through the position model and persist the contract block" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: API chọn mô hình theo mã và báo `execution_model`

**Files:**
- Modify: `backend/api/routes_strategy.py`
- Modify: `backend/api/routes_validation.py`, `backend/api/routes_stats.py`, `backend/api/routes_paper.py`
- Modify: `backend/strategy/multi.py`
- Modify: `frontend/js/markets.js:218`
- Create: `tests/test_contract_api.py`

**Interfaces:**
- Consumes: `ContractConfig`, `is_index_future`, `execution_model_for` (Task 2).
- Produces: `ContractSettings` (pydantic); `ContractSettingsRequired(missing: list[str])` với `.detail: dict`; `ExecutionSettings.contract: ContractSettings | None`; `ExecutionSettings.to_config(symbol: str | None = None) -> BacktestConfig`; `config_for(execution: ExecutionSettings, symbol: str | None) -> BacktestConfig` (ném `HTTPException(422)`); kết quả `/backtest`, `/report` có `"execution_model"`; mỗi dòng `/backtest/markets` có `"execution_model"`.

- [ ] **Step 1: Viết test hỏng**

`tests/test_contract_api.py`:

```python
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
```

- [ ] **Step 2: Chạy để thấy hỏng**

Run: `.venv/Scripts/python.exe tests/test_contract_api.py`
Expected: FAIL/ERROR ở cả 6 check (thiếu `execution_model`, khối `contract` bị bỏ qua).

- [ ] **Step 3: `ContractSettings`, `to_config(symbol)`, `config_for` trong `routes_strategy.py`**

Thay:

```python
from backend.strategy import multi, registry
from backend.strategy.base import StrategyError
from backend.strategy.engine import BacktestConfig

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class ExecutionSettings(BaseModel):
    """Costs and sizing. Defaults match Binance futures taker fees."""

    initial_capital: float = Field(default=10_000.0, gt=0)
    size_pct: float = Field(default=1.0, gt=0, le=1.0)
    leverage: float = Field(default=1.0, ge=1.0, le=125.0)
    fee: float = Field(default=0.0004, ge=0, le=0.01)
    slippage: float = Field(default=0.0002, ge=0, le=0.01)

    def to_config(self) -> BacktestConfig:
        return BacktestConfig(
            initial_capital=self.initial_capital,
            size_pct=self.size_pct,
            leverage=self.leverage,
            fee=self.fee,
            slippage=self.slippage,
        )
```

bằng:

```python
from typing import Literal

from backend.i18n import bi
from backend.strategy import multi, registry
from backend.strategy.base import StrategyError
from backend.strategy.engine import BacktestConfig
from backend.strategy.position_model import ContractConfig, execution_model_for, is_index_future

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class ContractSettings(BaseModel):
    """Index-futures sizing and costs, applied only to VN30F/VN100F symbols.

    The margin rate, the forced-close threshold and the fee have no defaults:
    they are set by the exchange and the broker, and a guessed value would put
    an invented cost on the account.
    """

    sizing: Literal["margin", "fixed"] = "margin"
    contracts: int = Field(default=1, ge=1, le=10_000)
    multiplier: float = Field(default=100_000.0, gt=0)
    initial_margin_rate: float | None = Field(default=None, gt=0, le=1)
    maintenance_threshold: float | None = Field(default=None, ge=0, lt=1)
    fee_mode: Literal["per_contract", "notional"] = "per_contract"
    fee_per_contract: float | None = Field(default=None, ge=0)
    fee_rate: float | None = Field(default=None, ge=0, le=0.01)
    slippage_points: float = Field(default=0.0, ge=0)

    def missing(self) -> list[str]:
        names = []
        if self.initial_margin_rate is None:
            names.append("initial_margin_rate")
        if self.maintenance_threshold is None:
            names.append("maintenance_threshold")
        fee_field = "fee_per_contract" if self.fee_mode == "per_contract" else "fee_rate"
        if getattr(self, fee_field) is None:
            names.append(fee_field)
        return names


class ContractSettingsRequired(Exception):
    """A futures symbol whose contract block leaves a required value empty."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__(", ".join(missing))
        fields = ", ".join(missing)
        self.detail = {
            "code": "contract_settings_required",
            "missing": missing,
            "message": bi(
                f"Thiếu thông số hợp đồng: {fields}.",
                f"Missing contract settings: {fields}.",
            ),
        }


class ExecutionSettings(BaseModel):
    """Costs and sizing. Defaults match Binance futures taker fees."""

    initial_capital: float = Field(default=10_000.0, gt=0)
    size_pct: float = Field(default=1.0, gt=0, le=1.0)
    leverage: float = Field(default=1.0, ge=1.0, le=125.0)
    fee: float = Field(default=0.0004, ge=0, le=0.01)
    slippage: float = Field(default=0.0002, ge=0, le=0.01)
    contract: ContractSettings | None = None

    def to_config(self, symbol: str | None = None) -> BacktestConfig:
        """The engine config for ``symbol``.

        The contract block applies only to an index future; with any other
        symbol it is ignored. Raises ContractSettingsRequired when it applies
        but leaves a required value empty.
        """
        contract = None
        if self.contract is not None and is_index_future(symbol or settings.chart.default_symbol):
            missing = self.contract.missing()
            if missing:
                raise ContractSettingsRequired(missing)
            c = self.contract
            contract = ContractConfig(
                initial_margin_rate=c.initial_margin_rate,
                maintenance_threshold=c.maintenance_threshold,
                sizing=c.sizing,
                contracts=c.contracts,
                multiplier=c.multiplier,
                fee_mode=c.fee_mode,
                fee_per_contract=c.fee_per_contract or 0.0,
                fee_rate=c.fee_rate or 0.0,
                slippage_points=c.slippage_points,
            )
        return BacktestConfig(
            initial_capital=self.initial_capital,
            size_pct=self.size_pct,
            leverage=self.leverage,
            fee=self.fee,
            slippage=self.slippage,
            contract=contract,
        )


def config_for(execution: ExecutionSettings, symbol: str | None) -> BacktestConfig:
    """`to_config`, with a missing contract setting turned into HTTP 422.

    Call it before an endpoint's try block: a broad `except Exception` there
    would report the 422 as a 500.
    """
    try:
        return execution.to_config(symbol)
    except ContractSettingsRequired as exc:
        raise HTTPException(422, detail=exc.detail) from exc
```

- [ ] **Step 4: Đổi các chỗ gọi trong `routes_strategy.py`**

Trong `report`, thay:

```python
    config = request.execution.to_config()

    try:
        spec, resolved, result, probability = registry.simulate(
```

bằng:

```python
    config = config_for(request.execution, request.symbol)

    try:
        spec, resolved, result, probability = registry.simulate(
```

và thay:

```python
    payload["symbol"] = request.symbol
    return payload
```

bằng:

```python
    payload["symbol"] = request.symbol
    payload["execution_model"] = execution_model_for(
        request.symbol or settings.chart.default_symbol, config)
    return payload
```

Trong `backtest`, thay:

```python
    try:
        return registry.run_strategy(
            request.strategy_id, df, timeframe, request.params, request.execution.to_config()
        )
    except StrategyError as exc:
```

bằng:

```python
    config = config_for(request.execution, request.symbol)
    try:
        result = registry.run_strategy(
            request.strategy_id, df, timeframe, request.params, config
        )
        result["execution_model"] = execution_model_for(
            request.symbol or settings.chart.default_symbol, config)
        return result
    except StrategyError as exc:
```

Trong `backtest_markets`, thay:

```python
        try:
            result = registry.run_strategy(
                request.strategy_id, df, timeframe, request.params,
                request.execution.to_config(),
            )
        except StrategyError as exc:
```

bằng:

```python
        try:
            config = request.execution.to_config(symbol)
        except ContractSettingsRequired as exc:
            # Only this market lacks what it needs; the rest of the scan runs.
            runs.append(multi.MarketRun(symbol, timeframe, error=exc.detail["message"]))
            continue

        try:
            result = registry.run_strategy(
                request.strategy_id, df, timeframe, request.params, config,
            )
            result["execution_model"] = execution_model_for(symbol, config)
        except StrategyError as exc:
```

Trong `run_optimize`, thay:

```python
    ranges = [ParamRange(r.name, r.start, r.stop, r.step) for r in request.ranges]

    try:
        return optimize(
            request.strategy_id,
            df,
            timeframe,
            ranges,
            config=request.execution.to_config(),
```

bằng:

```python
    ranges = [ParamRange(r.name, r.start, r.stop, r.step) for r in request.ranges]
    config = config_for(request.execution, request.symbol)

    try:
        return optimize(
            request.strategy_id,
            df,
            timeframe,
            ranges,
            config=config,
```

- [ ] **Step 5: Đổi các chỗ gọi ở ba router còn lại**

`backend/api/routes_validation.py` — thay:

```python
from backend.api.routes_strategy import ExecutionSettings, SweepRange, _load_candles
```

bằng:

```python
from backend.api.routes_strategy import ExecutionSettings, SweepRange, _load_candles, config_for
```

Thay (walk-forward):

```python
    ranges = [ParamRange(r.name, r.start, r.stop, r.step) for r in request.ranges]

    try:
        return walk_forward(
            request.strategy_id, df, timeframe, ranges,
            config=request.execution.to_config(),
```

bằng:

```python
    ranges = [ParamRange(r.name, r.start, r.stop, r.step) for r in request.ranges]
    config = config_for(request.execution, request.symbol)

    try:
        return walk_forward(
            request.strategy_id, df, timeframe, ranges,
            config=config,
```

Dòng `    config = request.execution.to_config()` xuất hiện đúng hai lần trong file (monte-carlo và compare). Sau khi đã sửa walk-forward, chạy `grep -n "to_config()" backend/api/routes_validation.py`: phải in đúng 2 dòng đó. Thay cả hai bằng `    config = config_for(request.execution, request.symbol)`.

`backend/api/routes_stats.py` — thay dòng import `ExecutionSettings` từ `routes_strategy` (dạng `from backend.api.routes_strategy import ExecutionSettings, _load_candles`) bằng `from backend.api.routes_strategy import ExecutionSettings, _load_candles, config_for`, rồi thay `    config = request.execution.to_config()` bằng `    config = config_for(request.execution, request.symbol)`.

`backend/api/routes_paper.py` — thay:

```python
from backend.api.routes_strategy import ExecutionSettings
```

bằng:

```python
from backend.api.routes_strategy import ExecutionSettings, config_for
```

và thay:

```python
    timeframe = request.timeframe or settings.chart.default_timeframe

    try:
        session = await manager.start(
            request.strategy_id, symbol, timeframe,
            request.params, request.execution.to_config(),
        )
```

bằng:

```python
    timeframe = request.timeframe or settings.chart.default_timeframe
    config = config_for(request.execution, symbol)

    try:
        session = await manager.start(
            request.strategy_id, symbol, timeframe,
            request.params, config,
        )
```

Run: `grep -rn "to_config()" backend`
Expected: không còn dòng nào.

- [ ] **Step 6: Dòng thị trường mang `execution_model`; lỗi song ngữ trên giao diện**

`backend/strategy/multi.py` — thay:

```python
                "span_ms": _span_ms(run.result),
                "metrics": metrics,
```

bằng:

```python
                "span_ms": _span_ms(run.result),
                "execution_model": run.result.get("execution_model"),
                "metrics": metrics,
```

`frontend/js/markets.js` — thay:

```js
      r.failed.map((f) => `${esc(f.symbol)} — ${esc(f.error)}`).join('<br>') +
```

bằng:

```js
      // A market can fail with a {vi, en} pair (missing contract settings) or
      // with a plain message from the data layer.
      r.failed.map((f) => `${esc(f.symbol)} — ${esc(typeof f.error === 'object' ? tp(f.error) : f.error)}`).join('<br>') +
```

- [ ] **Step 7: Chạy test**

Run: `.venv/Scripts/python.exe tests/test_contract_api.py`
Expected: `6 passed, 0 failed`.

Run: `.venv/Scripts/python.exe tests/test_multi_market.py`, `tests/test_validation.py`, `tests/test_stats.py`
Expected: số passed như trước (9, 25, 40), 0 failed.

- [ ] **Step 8: Commit**

```bash
git add backend/api/routes_strategy.py backend/api/routes_validation.py backend/api/routes_stats.py backend/api/routes_paper.py backend/strategy/multi.py frontend/js/markets.js tests/test_contract_api.py
git commit -m "Pick the position model per symbol in the API and report which one ran" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Ghi chú `contract_model_off` trên giao diện

**Files:**
- Modify: `frontend/js/i18n.js` (sau key `'mm.medianReturn'`)
- Modify: `frontend/js/strategy.js` (`renderResult`, danh sách export)
- Modify: `frontend/js/paper.js` (render phiên)
- Test: `tests/test_render.js`

**Interfaces:**
- Consumes: `result.execution_model` (Task 5), `session.execution_model` (Task 4).
- Produces: key i18n `exec.contractOff`; `Strategy.executionNote(result) -> string` (HTML, rỗng nếu không cần ghi chú).

- [ ] **Step 1: Viết test hỏng**

Trong `tests/test_render.js`, thay dòng neo:

```js
  // ---------- Language purity ----------
```

bằng:

```js
  // ---------- Contract model off ----------
  for (const [lang, word] of [['vi', 'hệ số nhân'], ['en', 'multiplier']]) {
    window.I18n.set(lang);
    tsay(`the results say the contract model is off [${lang}]`,
         window.Strategy.executionNote({ execution_model: 'contract_model_off' }).includes(word));
  }
  tsay('no note when the contract model ran or the symbol is linear',
       window.Strategy.executionNote({ execution_model: 'contract' }) === ''
         && window.Strategy.executionNote({ execution_model: 'linear' }) === '');
  window.I18n.set('vi');
  window.API.paperSessions = async () => ({ sessions: [
    fakeSession({ id: 'off', symbol: 'VN:VN30F1M', execution_model: 'contract_model_off' }),
  ] });
  await window.Paper.refresh();
  tsay('a paper session says the contract model is off',
       psel('paper-sessions').textContent.includes('hệ số nhân'));

  // ---------- Language purity ----------
```

Run: `NODE_PATH=./node_modules node tests/test_render.js; echo exit=$?`
Expected: dừng với `TypeError: window.Strategy.executionNote is not a function`, `exit=1`.

- [ ] **Step 2: Thêm key i18n**

Trong `frontend/js/i18n.js`, thay:

```js
    'mm.medianReturn':    { vi: 'Lợi nhuận trung vị', en: 'Median return' },
```

bằng:

```js
    'mm.medianReturn':    { vi: 'Lợi nhuận trung vị', en: 'Median return' },
    'exec.contractOff':   { vi: 'Mô hình hợp đồng chưa bật: lãi/lỗ tính tuyến tính, chưa áp dụng hệ số nhân hợp đồng.',
                            en: 'Contract model off: profit and loss are computed linearly, without the contract multiplier.' },
```

- [ ] **Step 3: `executionNote` trong `strategy.js`**

Thay:

```js
  function renderResult(result) {
    const m = result.metrics;
    const sign = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');

    let html = '';
```

bằng:

```js
  /* A futures symbol run without contract settings: the figures are in account
     units without the multiplier, and the reader must know before reading them.
     Branches on the stable code from the API, never on text (§2.4). */
  function executionNote(result) {
    return result?.execution_model === 'contract_model_off'
      ? `<div class="callout warn">${esc(t('exec.contractOff'))}</div>` : '';
  }

  function renderResult(result) {
    const m = result.metrics;
    const sign = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');

    let html = executionNote(result);
```

và thay:

```js
    renderOptimize,
```

bằng:

```js
    renderOptimize,
    // Exported for tests/test_render.js, which checks the note in both languages.
    executionNote,
```

- [ ] **Step 4: Ghi chú trên phiên Paper**

Trong `frontend/js/paper.js`, thay:

```js
            `${s.num_trades} trades · ${s.win_rate_pct.toFixed(0)}% won · last bar ${ago(s.last_closed_time)}`))}</p>
```

bằng:

```js
            `${s.num_trades} trades · ${s.win_rate_pct.toFixed(0)}% won · last bar ${ago(s.last_closed_time)}`))}</p>
          ${s.execution_model === 'contract_model_off'
            ? `<p class="pp-meta">${esc(t('exec.contractOff'))}</p>` : ''}
```

- [ ] **Step 5: Chạy test**

Run: `NODE_PATH=./node_modules node tests/test_render.js; echo exit=$?`
Expected: dòng cuối `all render checks passed`, `exit=0`, có 4 dòng PASS mới về contract model.

Run: `.venv/Scripts/python.exe tests/test_i18n.py`
Expected: `2 passed, 0 failed`.

- [ ] **Step 6: Commit**

```bash
git add frontend/js/i18n.js frontend/js/strategy.js frontend/js/paper.js tests/test_render.js
git commit -m "Say on the results and paper panels when a future ran without contract settings" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Hồi quy toàn bộ và báo cáo

**Files:**
- Modify: `CLAUDE.md` (§4, mục mới đầu tiên)

**Interfaces:**
- Consumes: mọi task trước.
- Produces: không.

- [ ] **Step 1: Chạy toàn bộ test Python**

Run: `for f in tests/test_*.py; do printf "%s: " "$f"; .venv/Scripts/python.exe "$f" 2>&1 | tail -1; done`
Expected: mọi file `0 failed`; tổng passed = 326 cũ + 18 (`test_position_model.py`) + 5 (`test_paper.py`) + 6 (`test_contract_api.py`) = 355.

- [ ] **Step 2: Chạy render, i18n và các trang test biểu đồ**

Run: `NODE_PATH=./node_modules node tests/test_render.js; echo exit=$?` → `all render checks passed`, `exit=0`.
Run: `.venv/Scripts/python.exe tests/test_i18n.py` → `2 passed, 0 failed`.

- [ ] **Step 3: Ghi mục báo cáo**

Trong `CLAUDE.md`, thay dòng:

```markdown
Ghi theo thứ tự mới nhất trước. Mỗi mục: phát hiện gì, đo được gì, đã sửa chưa.
```

bằng dòng đó cộng một mục mới ngay sau, gồm: tiêu đề `### 2026-09-15 (khuya) — Mô hình vị thế theo hợp đồng cho phái sinh`; số test (điền số thật từ Step 1–2); bảng các trường hợp tính tay của `tests/test_position_model.py` với kết quả (3 hợp đồng, 2 940 000 đ, 102 880 000 đ, 3,769%, 117 000 đ, giá buộc đóng 1 170); câu "mốc tuyến tính trùng ≤ 1e-12 trên 6 cấu hình"; hệ thức `overview.net_profit = trades.all.net_profit − tổng phí vào` kèm ghi chú đã sửa bản thiết kế; và phần Giới hạn chép từ bản thiết kế.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "Report the contract position model" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```
