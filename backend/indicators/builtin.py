"""Wraps the pandas-ta-classic catalog into ``IndicatorSpec`` objects.

193 indicators are exposed without hand-writing a file per indicator: the
function signature supplies each indicator's parameter *names* and its price
inputs, and the tables below supply the defaults and ranges the UI needs.

pandas-ta declares its signature defaults as ``None`` and resolves the real
default inside the function body, so introspection alone cannot recover them.
Parameters absent from ``PARAM_DEFAULTS`` are therefore left out of the UI and
fall through to the library's own default — the indicator still computes, it
just exposes fewer knobs.
"""

from __future__ import annotations

import inspect
import logging
from functools import lru_cache

import pandas as pd
import pandas_ta_classic as pta

from backend.indicators.base import IndicatorError, IndicatorSpec, ParamSpec

log = logging.getLogger(__name__)

# Signature parameters that carry price/volume data rather than settings.
PRICE_PARAMS = {"open", "open_", "high", "low", "close", "volume"}

# Settings we deliberately hide: library plumbing, or types the UI can't render.
HIDDEN_PARAMS = {
    "kwargs", "talib", "offset", "mamode", "drift", "ddof",
    "name", "benchmark", "asc", "asbool", "signed", "pandas_ta",
    "variable", "prenan", "trend_reset", "trade_offset",
}

# Defaults and ranges for the parameters worth exposing. Values match
# pandas-ta's own in-body defaults.
PARAM_DEFAULTS: dict[str, dict] = {
    "length":       {"type": "int",   "default": 14,   "min": 1,    "max": 500},
    "fast":         {"type": "int",   "default": 12,   "min": 1,    "max": 300},
    "slow":         {"type": "int",   "default": 26,   "min": 1,    "max": 500},
    "signal":       {"type": "int",   "default": 9,    "min": 1,    "max": 200},
    "scalar":       {"type": "float", "default": 100.0,"min": 0.1,  "max": 1000.0, "step": 0.1},
    "std":          {"type": "float", "default": 2.0,  "min": 0.1,  "max": 10.0,   "step": 0.1},
    "multiplier":   {"type": "float", "default": 3.0,  "min": 0.1,  "max": 20.0,   "step": 0.1},
    "factor":       {"type": "float", "default": 3.0,  "min": 0.1,  "max": 20.0,   "step": 0.1},
    "k":            {"type": "int",   "default": 14,   "min": 1,    "max": 200},
    "d":            {"type": "int",   "default": 3,    "min": 1,    "max": 100},
    "smooth_k":     {"type": "int",   "default": 3,    "min": 1,    "max": 100},
    "atr_length":   {"type": "int",   "default": 14,   "min": 1,    "max": 200},
    "lensig":       {"type": "int",   "default": 14,   "min": 1,    "max": 200},
    "bb_length":    {"type": "int",   "default": 20,   "min": 1,    "max": 300},
    "bb_std":       {"type": "float", "default": 2.0,  "min": 0.1,  "max": 10.0,   "step": 0.1},
    "kc_length":    {"type": "int",   "default": 20,   "min": 1,    "max": 300},
    "kc_scalar":    {"type": "float", "default": 1.5,  "min": 0.1,  "max": 10.0,   "step": 0.1},
    "mom_length":   {"type": "int",   "default": 12,   "min": 1,    "max": 200},
    "mom_smooth":   {"type": "int",   "default": 6,    "min": 1,    "max": 200},
    "tenkan":       {"type": "int",   "default": 9,    "min": 1,    "max": 200},
    "kijun":        {"type": "int",   "default": 26,   "min": 1,    "max": 300},
    "senkou":       {"type": "int",   "default": 52,   "min": 1,    "max": 400},
    "af0":          {"type": "float", "default": 0.02, "min": 0.001,"max": 1.0,    "step": 0.001},
    "af":           {"type": "float", "default": 0.02, "min": 0.001,"max": 1.0,    "step": 0.001},
    "max_af":       {"type": "float", "default": 0.2,  "min": 0.01, "max": 1.0,    "step": 0.01},
    "lookback":     {"type": "int",   "default": 20,   "min": 1,    "max": 400},
    "max_lookback": {"type": "int",   "default": 20,   "min": 1,    "max": 400},
    "min_lookback": {"type": "int",   "default": 5,    "min": 1,    "max": 400},
    "sigma":        {"type": "float", "default": 6.0,  "min": 0.1,  "max": 50.0,   "step": 0.1},
    "initial":      {"type": "float", "default": 1.0,  "min": 0.0,  "max": 1e6,    "step": 0.1},
    "percent":      {"type": "float", "default": 3.0,  "min": 0.1,  "max": 100.0,  "step": 0.1},
    "roc":          {"type": "int",   "default": 10,   "min": 1,    "max": 200},
    "swma_length":  {"type": "int",   "default": 10,   "min": 1,    "max": 200},
    "rvi_length":   {"type": "int",   "default": 14,   "min": 1,    "max": 200},
    "p":            {"type": "int",   "default": 10,   "min": 1,    "max": 200},
    "q":            {"type": "int",   "default": 20,   "min": 1,    "max": 200},
    "r":            {"type": "int",   "default": 30,   "min": 1,    "max": 300},
    "s":            {"type": "int",   "default": 40,   "min": 1,    "max": 300},
    "na":           {"type": "float", "default": 6.0,  "min": 0.1,  "max": 100.0,  "step": 0.1},
    "nb":           {"type": "float", "default": 3.0,  "min": 0.1,  "max": 100.0,  "step": 0.1},
    "nc":           {"type": "float", "default": 1.0,  "min": 0.1,  "max": 100.0,  "step": 0.1},
    "c":            {"type": "float", "default": 1.0,  "min": 0.1,  "max": 100.0,  "step": 0.1},
}

# Indicators that share the price scale and therefore draw over the candles.
# The whole `overlap` category qualifies; these sit in other categories.
OVERLAY_EXTRAS = {
    "bbands", "kc", "donchian", "accbands", "aberration", "hwc", "ce",
    "psar", "pmax", "sarext", "cksp", "cpr",
}

# `overlap`-category members that are not price-scale after all. Linear
# regression angle is degrees and slope is a rate of change; neither belongs
# on the price axis despite pandas-ta filing them under `overlap`.
PANEL_EXTRAS: set[str] = {"linregangle", "linregslope"}

# Parameters whose sensible default differs from the shared table. `scalar`
# means "scale to 0-100" for RSI-like indicators but "band width in ATRs" for
# Keltner Channels, where 100 produces bands hundreds of thousands wide.
PARAM_OVERRIDES: dict[str, dict[str, dict]] = {
    "kc": {"scalar": {"type": "float", "default": 2.0, "min": 0.1, "max": 10.0, "step": 0.1}},
}

# Left out of the catalog:
#   beta, correl — need a second, external price series (a market benchmark);
#                  we only carry one symbol.
#   vp           — volume profile bins by price, not by time, so it has no
#                  one-value-per-candle series to plot on a time axis.
EXCLUDED = {"beta", "correl", "vp"}


@lru_cache(maxsize=1)
def _category_index() -> dict[str, str]:
    return {name: cat for cat, names in pta.Category.items() for name in names}


def _classify(name: str, category: str) -> str:
    if name in OVERLAY_EXTRAS:
        return "overlay"
    if name in PANEL_EXTRAS:
        return "panel"
    return "overlay" if category == "overlap" else "panel"


def _build_param_specs(sig: inspect.Signature, indicator: str) -> list[ParamSpec]:
    specs: list[ParamSpec] = []
    overrides = PARAM_OVERRIDES.get(indicator, {})
    for param in sig.parameters.values():
        name = param.name
        if name in PRICE_PARAMS or name in HIDDEN_PARAMS:
            continue
        meta = overrides.get(name) or PARAM_DEFAULTS.get(name)
        if meta is None:
            continue  # unknown knob: let pandas-ta use its own default
        specs.append(ParamSpec(name=name, **meta))
    return specs


def _price_inputs(sig: inspect.Signature) -> list[str]:
    return [p.name for p in sig.parameters.values() if p.name in PRICE_PARAMS]


def _make_calculate(fn, price_inputs: list[str]):
    """Build a ``calculate(df, params)`` closure for one pandas-ta function."""

    def calculate(df: pd.DataFrame, params: dict):
        kwargs: dict = {}
        for name in price_inputs:
            column = "open" if name == "open_" else name
            if column not in df.columns:
                raise IndicatorError(f"missing '{column}' column in candle data")
            kwargs[name] = df[column]
        kwargs.update(params)

        try:
            return fn(**kwargs)
        except Exception as exc:
            raise IndicatorError(f"{type(exc).__name__}: {exc}") from exc

    return calculate


@lru_cache(maxsize=1)
def build_builtin_specs() -> dict[str, IndicatorSpec]:
    """Introspect the pandas-ta catalog into specs, keyed by indicator id."""
    specs: dict[str, IndicatorSpec] = {}
    categories = _category_index()

    for name in sorted(categories):
        if name in EXCLUDED:
            continue
        fn = getattr(pta, name, None)
        if fn is None or not callable(fn):
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            log.debug("skipping %s: signature not introspectable", name)
            continue

        price_inputs = _price_inputs(sig)
        if not price_inputs:
            continue  # not a price-series indicator (e.g. helpers)

        category = categories[name]
        doc = (inspect.getdoc(fn) or "").strip().split("\n")[0][:200]

        specs[name] = IndicatorSpec(
            id=name,
            name=name.upper(),
            kind=_classify(name, category),
            category=category,
            source="builtin",
            description=doc,
            params=_build_param_specs(sig, name),
            calculate=_make_calculate(fn, price_inputs),
        )

    return specs
