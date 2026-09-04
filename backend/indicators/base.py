"""The indicator contract.

Every indicator — the 193 wrapped from pandas-ta-classic and every ``.py`` file
you drop into ``plugins/indicators/`` — is described by one ``IndicatorSpec``.
The spec is what the UI reads to build parameter controls and to decide whether
the indicator draws over the candles or in its own pane below them.

A plugin file declares a module-level ``INDICATOR`` dict and a ``calculate``
function::

    INDICATOR = {
        "name": "My EMA",
        "type": "overlay",                 # "overlay" | "panel"
        "params": {
            "period": {"type": "int", "default": 20, "min": 2, "max": 400},
        },
        "outputs": [
            {"key": "ema", "label": "EMA", "color": "#2962FF"},
        ],
    }

    def calculate(df, params):
        return {"ema": df["close"].ewm(span=params["period"]).mean()}

``calculate`` receives the OHLCV frame and the resolved parameters, and returns
either a Series, a DataFrame, or a dict of named Series.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

IndicatorKind = Literal["overlay", "panel"]
PlotType = Literal["line", "histogram", "area"]

# Assigned in order to outputs that don't specify a color.
PALETTE = [
    "#2962FF", "#FF6D00", "#00C853", "#D50000", "#AA00FF",
    "#00B8D4", "#FFD600", "#6D4C41", "#C51162", "#64DD17",
]


@dataclass
class ParamSpec:
    """One user-adjustable parameter, rendered as a control in the UI."""

    name: str
    type: Literal["int", "float", "bool"] = "int"
    default: Any = 14
    min: float | None = None
    max: float | None = None
    step: float | None = None
    label: str | None = None

    def coerce(self, value: Any) -> Any:
        """Cast an incoming value to this parameter's type and clamp to range."""
        if value is None:
            return self.default
        try:
            if self.type == "int":
                value = int(float(value))
            elif self.type == "float":
                value = float(value)
            elif self.type == "bool":
                if isinstance(value, str):
                    value = value.strip().lower() in ("1", "true", "yes", "on")
                else:
                    value = bool(value)
        except (TypeError, ValueError):
            return self.default

        if self.type in ("int", "float"):
            if self.min is not None:
                value = max(value, self.min)
            if self.max is not None:
                value = min(value, self.max)
            if self.type == "int":
                value = int(value)
        return value

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "default": self.default,
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "label": self.label or self.name.replace("_", " ").title(),
        }


@dataclass
class OutputSpec:
    """One plotted line produced by an indicator."""

    key: str
    label: str | None = None
    color: str | None = None
    plot_type: PlotType = "line"

    def as_dict(self, index: int = 0) -> dict:
        return {
            "key": self.key,
            "label": self.label or self.key,
            "color": self.color or PALETTE[index % len(PALETTE)],
            "plot_type": self.plot_type,
        }


@dataclass
class IndicatorSpec:
    """Full description of an indicator plus its compute function."""

    id: str
    name: str
    kind: IndicatorKind = "panel"
    category: str = "custom"
    source: Literal["builtin", "plugin"] = "builtin"
    description: str = ""
    params: list[ParamSpec] = field(default_factory=list)
    outputs: list[OutputSpec] = field(default_factory=list)
    calculate: Callable[[pd.DataFrame, dict], Any] | None = None

    def resolve_params(self, raw: dict | None) -> dict:
        """Validate and fill in incoming parameter values."""
        raw = raw or {}
        return {p.name: p.coerce(raw.get(p.name)) for p in self.params}

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "category": self.category,
            "source": self.source,
            "description": self.description,
            "params": [p.as_dict() for p in self.params],
            "outputs": [o.as_dict(i) for i, o in enumerate(self.outputs)],
        }


class IndicatorError(RuntimeError):
    """Raised when an indicator fails to compute; carries a UI-safe message."""


def _clean_values(series: pd.Series, target: pd.Index) -> list[float | None]:
    """Align to the candle index and make JSON-safe.

    NaN and infinities become None so the chart breaks the line instead of
    drawing through a gap. Indicators that return a shifted or projected index
    (ichimoku's forward span) are reindexed onto the candles; values that fall
    outside the visible range are dropped.
    """
    series = pd.to_numeric(series, errors="coerce")

    if not series.index.equals(target):
        # Reindexing only makes sense between comparable index types. Some
        # indicators (td_seq) return a positional index; reindexing that onto
        # timestamps silently yields all-NaN, so align by position instead.
        comparable = series.index.dtype == target.dtype
        aligned = series.reindex(target) if comparable else None

        if aligned is None or (aligned.isna().all() and not series.isna().all()):
            values = series.to_numpy(dtype="float64", na_value=np.nan)
            padded = np.full(len(target), np.nan)
            n = min(len(values), len(target))
            padded[:n] = values[:n]
            series = pd.Series(padded, index=target)
        else:
            series = aligned

    values = series.to_numpy(dtype="float64", na_value=np.nan)
    return [None if (math.isnan(v) or math.isinf(v)) else float(v) for v in values]


def normalize_result(result: Any, target_index: pd.Index) -> tuple[list[OutputSpec], dict[str, list]]:
    """Turn whatever ``calculate`` returned into named, JSON-safe series.

    Accepts a Series, a DataFrame, or a dict of Series. Returns the derived
    output specs alongside the values, so builtin indicators — whose column
    names depend on their parameters — need not declare outputs up front.
    """
    if result is None:
        raise IndicatorError("indicator returned nothing")

    # A few indicators (ichimoku) return a tuple of frames: the historical span
    # and a forward-projected one. Only the historical part aligns with our
    # candles, so later elements are merged in only where the index matches.
    if isinstance(result, (tuple, list)):
        parts = [r for r in result if isinstance(r, (pd.Series, pd.DataFrame))]
        if not parts:
            raise IndicatorError("indicator returned no usable frames")
        result = parts[0]

    if isinstance(result, pd.Series):
        columns = {str(result.name or "value"): result}
    elif isinstance(result, pd.DataFrame):
        columns = {str(c): result[c] for c in result.columns}
    elif isinstance(result, dict):
        columns = {}
        for key, value in result.items():
            if isinstance(value, pd.DataFrame):
                for c in value.columns:
                    columns[f"{key}_{c}"] = value[c]
            elif isinstance(value, pd.Series):
                columns[str(key)] = value
            else:
                columns[str(key)] = pd.Series(value, index=target_index)
    else:
        raise IndicatorError(f"unsupported return type: {type(result).__name__}")

    if not columns:
        raise IndicatorError("indicator produced no output columns")

    specs = [OutputSpec(key=name, label=name) for name in columns]
    values = {name: _clean_values(series, target_index) for name, series in columns.items()}
    return specs, values
