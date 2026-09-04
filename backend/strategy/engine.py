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
    trades: list[Trade] = []
    liquidated_ever = False
    ruined = False

    def fill_price(price: float, direction: int) -> float:
        """Worsen a fill by slippage; ``direction`` is +1 when buying."""
        return price * (1.0 + config.slippage * direction)

    def close_position(exit_price: float, index: int, reason: str) -> None:
        nonlocal equity, position, quantity, entry_price, margin, entry_index
        exit_fee = abs(quantity) * exit_price * config.fee
        pnl = quantity * (exit_price - entry_price) - exit_fee
        equity += pnl

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
            )
        )

        position = 0
        quantity = 0.0
        entry_price = 0.0
        margin = 0.0
        entry_index = -1

    def open_position(price: float, index: int, direction: int) -> None:
        nonlocal equity, position, quantity, entry_price, margin, entry_index
        margin = equity * config.size_pct
        notional = margin * config.leverage
        quantity = notional / price * direction
        entry_price = price
        entry_index = index
        position = direction
        equity -= notional * config.fee   # entry fee, paid immediately

    for i in range(n):
        if not ruined:
            # 1. Act on the previous bar's signal, at this bar's open.
            if target[i] != position:
                if position != 0:
                    close_position(fill_price(open_[i], -position), i, "signal")
                if target[i] != 0 and equity > 0:
                    open_position(fill_price(open_[i], target[i]), i, target[i])

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
