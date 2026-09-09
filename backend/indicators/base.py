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

# Assigned in order to outputs that don't specify a colour.
#
# Eight rather than ten, and chosen on three constraints rather than by eye:
#
#   * **Even weight.** All eight sit within a narrow lightness band, so no line
#     shouts louder than another. The old set mixed a pale mustard (#a16207)
#     with a near-black slate (#475569); on one chart the mustard vanished and
#     the slate read as the most important series on screen.
#   * **Away from the market hues.** Nothing in the green band around 160° or
#     the red band around 0°, because those two mean price direction here and
#     an indicator line must never be read as one (see frontend/styles.css).
#     That is also what caps the set at eight: with two wide bands excluded
#     there is not room for ten hues that stay far enough apart.
#   * **Separable without hue alone.** No red/green pair, so the set survives
#     the common colour vision deficiencies; the brown and the blue-grey are
#     also separated by chroma, not just by hue.
PALETTE = [
    "#2962ff",  # blue
    "#ef6c00",  # orange
    "#7b1fa2",  # purple
    "#0097a7",  # cyan
    "#f9a825",  # amber
    "#c2185b",  # magenta
    "#5d4037",  # brown
    "#455a64",  # blue grey
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
            # Whether that colour was chosen by the indicator or handed out by
            # the palette. The interface rotates the automatic ones per drawn
            # instance: `index` counts outputs *within* one indicator, so
            # without this every indicator's first line is the same blue and a
            # chart with EMA, VWAP and a Bollinger mid is three blue lines.
            "color_auto": self.color is None,
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
    # Longer, plain-language explanation shown behind the ⓘ button.
    help: dict = field(default_factory=dict)
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
            "help": self.help,
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
