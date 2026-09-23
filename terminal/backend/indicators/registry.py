"""The indicator registry: one lookup covering builtins and user plugins.

Also owns the compute path — preparing the candle frame, resolving parameters,
running the indicator, and normalizing the result into JSON-safe series keyed
to the candle timestamps.
"""

from __future__ import annotations

import logging

import pandas as pd

from backend.indicators.base import IndicatorError, IndicatorSpec, normalize_result
from backend.indicators.builtin import build_builtin_specs
from backend.indicators.loader import load_plugin_specs

log = logging.getLogger(__name__)

_plugin_errors: list[dict] = []


def prepare_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Index candles by timestamp.

    Time-aware indicators (VWAP anchors to the session) need a DatetimeIndex,
    not the positional one that comes back from DuckDB.
    """
    frame = df.copy()
    frame.index = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame.index.name = "datetime"
    return frame


def get_registry(reload_plugins: bool = True) -> dict[str, IndicatorSpec]:
    """Full catalog. Plugins are re-scanned by default so edits show up live."""
    global _plugin_errors

    registry: dict[str, IndicatorSpec] = dict(build_builtin_specs())

    if reload_plugins:
        plugin_specs, _plugin_errors = load_plugin_specs()
        registry.update(plugin_specs)

    return registry


def get_plugin_errors() -> list[dict]:
    """Load errors from the most recent plugin scan."""
    return list(_plugin_errors)


def get_spec(indicator_id: str) -> IndicatorSpec:
    registry = get_registry()
    spec = registry.get(indicator_id)
    if spec is None:
        raise IndicatorError(f"unknown indicator: {indicator_id}")
    return spec



def _assign_panes(outputs: list[dict], values: dict[str, list], df: pd.DataFrame) -> None:
    """Mark outputs that cannot share the price axis.

    A static overlay/panel label is per-indicator, but several indicators mix
    scales inside one result: Bollinger Bands returns three price-level bands
    plus a bandwidth and a percent; SuperTrend returns a price line plus a
    direction of -1/1. Drawing those on the price axis forces it down toward
    zero and squashes the candles into a strip.

    So the decision is made per output, from the numbers themselves: an output
    whose whole range sits far off the candle range gets its own pane. Being
    data-driven rather than a hard-coded list, this also covers plugins.
    """
    low = float(df["low"].min())
    high = float(df["high"].max())

    for output in outputs:
        series = [v for v in values.get(output["key"], []) if v is not None]
        if not series:
            output["pane"] = "price"
            continue

        lo, hi = min(series), max(series)
        off_scale = hi < low * 0.5 or lo > high * 2.0
        output["pane"] = "separate" if off_scale else "price"


def compute(indicator_id: str, df: pd.DataFrame, params: dict | None = None) -> dict:
    """Run one indicator over a candle frame.

    Returns ``{id, name, kind, params, outputs, values}`` where ``values`` maps
    each output key to a list aligned one-to-one with the input candles.
    """
    spec = get_spec(indicator_id)
    if spec.calculate is None:
        raise IndicatorError(f"indicator '{indicator_id}' has no calculate function")

    if df.empty:
        raise IndicatorError("no candle data to compute over")

    resolved = spec.resolve_params(params)
    frame = prepare_frame(df)

    try:
        raw = spec.calculate(frame, resolved)
    except IndicatorError:
        raise
    except Exception as exc:
        raise IndicatorError(f"{type(exc).__name__}: {exc}") from exc

    if raw is None:
        # pandas-ta returns None rather than raising when the window is longer
        # than the data. That is by far the most common cause, so name it.
        window = max(
            (v for k, v in resolved.items() if isinstance(v, (int, float)) and not isinstance(v, bool)),
            default=0,
        )
        raise IndicatorError(
            f"không đủ dữ liệu: chỉ có {len(df)} nến, "
            f"chỉ báo cần khoảng {int(window) + 1} nến trở lên "
            f"(tăng số nến hoặc giảm chu kỳ)"
        )

    derived_outputs, values = normalize_result(raw, frame.index)

    # A plugin's declared outputs win (they carry the author's labels and
    # colors); builtins fall back to the column names pandas-ta produced.
    if spec.outputs:
        declared = {o.key for o in spec.outputs}
        produced = set(values)
        missing = declared - produced
        if missing:
            raise IndicatorError(
                f"declared outputs not produced by calculate(): {sorted(missing)}"
            )
        outputs = spec.outputs
        values = {k: v for k, v in values.items() if k in declared}
    else:
        outputs = derived_outputs

    payload_outputs = [o.as_dict(i) for i, o in enumerate(outputs)]
    if spec.kind == "overlay":
        _assign_panes(payload_outputs, values, df)
    else:
        for output in payload_outputs:
            output["pane"] = "separate"

    return {
        "id": spec.id,
        "name": spec.name,
        "kind": spec.kind,
        "source": spec.source,
        "params": resolved,
        "outputs": payload_outputs,
        "values": values,
        "times": [int(t) // 1000 for t in df["open_time"].tolist()],
    }
