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
