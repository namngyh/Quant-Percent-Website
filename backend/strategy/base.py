"""The strategy contract.

A strategy is a ``.py`` file in ``plugins/strategies/`` that decides, for every
candle, whether the account should be long, short or flat. It does not place
orders and it does not size positions — the backtest engine owns execution, so
that every strategy is measured under identical, honest assumptions.

A strategy file declares a module-level ``STRATEGY`` dict and a ``signals``
function::

    STRATEGY = {
        "name": "RSI Reversal",
        "params": {
            "length": {"type": "int", "default": 14, "min": 2, "max": 100},
            "oversold": {"type": "int", "default": 30, "min": 5, "max": 50},
        },
    }

    def signals(df, params):
        rsi = ...
        out = pd.Series(0, index=df.index)
        out[rsi < params["oversold"]] = 1     # long
        out[rsi > 100 - params["oversold"]] = -1  # short
        return out

``signals`` returns a Series aligned to ``df``: ``1`` = long, ``-1`` = short,
``0`` = flat. The value at bar *i* may only use information available at the
close of bar *i*; the engine executes it at the open of bar *i+1*, so a
strategy cannot accidentally trade on a price it could not have seen.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from backend.indicators.base import ParamSpec

Side = Literal["long", "short", "both"]


class StrategyError(RuntimeError):
    """Raised when a strategy fails to produce usable signals."""


@dataclass
class StrategySpec:
    """Full description of a strategy plus its signal function."""

    id: str
    name: str
    description: str = ""
    side: Side = "both"
    params: list[ParamSpec] = field(default_factory=list)
    signals: Callable[[pd.DataFrame, dict], pd.Series] | None = None

    def resolve_params(self, raw: dict | None) -> dict:
        raw = raw or {}
        return {p.name: p.coerce(raw.get(p.name)) for p in self.params}

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "side": self.side,
            "params": [p.as_dict() for p in self.params],
        }


def normalize_signals(raw, index: pd.Index, side: Side = "both") -> np.ndarray:
    """Coerce whatever ``signals()`` returned into an int array of -1 / 0 / 1.

    Anything that is not clearly long or short becomes flat, and NaN — which a
    warm-up window always produces — becomes flat rather than an error.
    """
    if raw is None:
        raise StrategyError("signals() returned nothing")

    if isinstance(raw, pd.DataFrame):
        if raw.shape[1] != 1:
            raise StrategyError(
                f"signals() returned {raw.shape[1]} columns; expected a single series"
            )
        raw = raw.iloc[:, 0]

    if not isinstance(raw, pd.Series):
        try:
            raw = pd.Series(raw, index=index)
        except Exception as exc:
            raise StrategyError(f"cannot read signals: {exc}") from exc

    if len(raw) != len(index):
        raise StrategyError(f"signals length {len(raw)} does not match {len(index)} candles")

    values = pd.to_numeric(raw, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
    out = np.zeros(len(values), dtype="int8")
    out[values > 0] = 1
    out[values < 0] = -1

    if side == "long":
        out[out < 0] = 0
    elif side == "short":
        out[out > 0] = 0

    return out
