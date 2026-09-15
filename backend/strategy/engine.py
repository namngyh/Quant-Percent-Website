"""The backtest engine.

Execution model — the assumptions every result rests on:

* A signal produced at the close of bar *i* is executed at the **open of bar
  i+1**. Nothing is ever filled at a price the strategy could already see, so
  results carry no look-ahead bias.
* Fills are worsened by ``slippage`` in the direction that hurts, and both
  entries and exits pay ``fee`` on notional.
* Each position commits ``size_pct`` of current equity as margin and controls
  ``margin * leverage`` of notional.
* A leveraged position is liquidated intrabar when the loss reaches the
  committed margin — checked against the bar's low (long) or high (short),
  so a wick that would have wiped the position out is not skipped over.
* Only one position at a time; a reversal closes and reopens at the same bar.

The engine deliberately owns all of this rather than the strategy, so two
strategies are always compared under identical rules.
"""

from __future__ import annotations

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


@dataclass
class Trade:
    side: str            # "long" | "short"
    entry_index: int
    exit_index: int
    entry_time: int      # epoch seconds
    exit_time: int
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    return_pct: float    # on the margin committed
    bars_held: int
    exit_reason: str     # "signal" | "liquidation" | "end_of_data"
    # Excursions, in percent of the margin committed — the same base as
    # ``return_pct``, so the three numbers are directly comparable.
    #
    # MFE is how far the trade went in your favour before it closed, MAE how
    # far against. They are what turns "this stop is too tight" from an opinion
    # into a measurement: if winning trades routinely sit 4% underwater first,
    # a 3% stop cuts the winners, not the losers.
    #
    # The entry bar counts. The fill happens at its open, so the rest of that
    # bar's range genuinely occurs while the position is held; the only thing
    # the engine cannot know is the order of that bar's high and low, and order
    # does not change a maximum. Excluding it would understate MAE — and an
    # understated MAE is the dangerous direction, because it makes a stop look
    # safer than it is. This also matches the liquidation check, which already
    # tests the entry bar's own extreme.
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    # Account equity immediately before this trade was opened, and immediately
    # after it closed.
    #
    # These exist so a resampler can work in the same units the engine does.
    # `return_pct` is measured on the margin committed and excludes the entry
    # fee, which is charged the moment the position opens — so compounding it
    # does not reproduce the equity curve (measured 4-7% out). The fractional
    # change the account actually saw is `equity_after / equity_before - 1`,
    # and nothing else in the record carries it.
    equity_before: float = 0.0
    equity_after: float = 0.0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class BacktestResult:
    equity: np.ndarray = field(default_factory=lambda: np.array([]))
    times: list[int] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    position: np.ndarray = field(default_factory=lambda: np.array([]))
    config: BacktestConfig = field(default_factory=BacktestConfig)
    liquidated: bool = False
    ruined: bool = False     # equity hit zero; trading stopped


def run_backtest(
    df: pd.DataFrame,
    signal: np.ndarray,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Simulate ``signal`` over ``df`` and return equity, positions and trades.

    ``signal`` holds -1 / 0 / 1 per candle, aligned to ``df``. ``df`` needs
    ``open_time, open, high, low, close``.
    """
    config = config or BacktestConfig()
    n = len(df)
    if n == 0:
        return BacktestResult(config=config)

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
    quantity = 0.0        # signed, in base units
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
        return price * (1.0 + config.slippage * direction)

    def close_position(exit_price: float, index: int, reason: str) -> None:
        nonlocal equity, position, quantity, entry_price, margin, entry_index
        nonlocal best_price, worst_price
        exit_fee = abs(quantity) * exit_price * config.fee
        pnl = quantity * (exit_price - entry_price) - exit_fee
        equity += pnl

        # Excursions on the same base as return_pct: unrealised P&L on the
        # committed margin, gross of the exit fee (which is not owed until the
        # trade actually closes).
        if margin > 0:
            mfe = quantity * (best_price - entry_price) / margin * 100.0
            mae = quantity * (worst_price - entry_price) / margin * 100.0
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
                quantity=abs(quantity),
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
            )
        )

        position = 0
        quantity = 0.0
        entry_price = 0.0
        margin = 0.0
        entry_index = -1
        best_price = worst_price = 0.0

    def open_position(price: float, index: int, direction: int) -> None:
        nonlocal equity, position, quantity, entry_price, margin, entry_index
        nonlocal best_price, worst_price, entry_equity
        entry_equity = equity          # before the entry fee is taken
        margin = equity * config.size_pct
        notional = margin * config.leverage
        quantity = notional / price * direction
        entry_price = price
        entry_index = index
        position = direction
        # Start both excursions at the entry price: a trade that closes before
        # any further bar has moved neither way.
        best_price = worst_price = price
        equity -= notional * config.fee   # entry fee, paid immediately

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

            # 2. Liquidation: does this bar's adverse extreme wipe out the margin?
            if position != 0 and config.leverage > 1.0:
                liq_price = entry_price * (1.0 - position / config.leverage)
                hit = low[i] <= liq_price if position > 0 else high[i] >= liq_price
                if hit:
                    close_position(liq_price, i, "liquidation")
                    liquidated_ever = True

            if equity <= 0:
                equity = 0.0
                ruined = True

        # 3. Mark to market on this bar's close.
        unrealized = quantity * (close[i] - entry_price) if position != 0 else 0.0
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
