"""Loads user-written strategies and runs them through the backtest engine.

Strategies live in ``plugins/strategies/*.py`` and follow the contract in
``backend/strategy/base.py``. Files are re-imported on every scan, so editing
one and re-running a backtest picks up the change without a restart.

These files are executed as Python — your own files on your own machine, the
same trust level as any script you would run yourself.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import traceback
from pathlib import Path

import pandas as pd

from backend.config import settings
from backend.indicators.base import ParamSpec
from backend.indicators.registry import prepare_frame
from backend.strategy.base import StrategyError, StrategySpec, normalize_signals
from backend.strategy.engine import BacktestConfig, run_backtest
from backend.strategy.metrics import compute_metrics

log = logging.getLogger(__name__)

VALID_PARAM_TYPES = ("int", "float", "bool")
VALID_SIDES = ("long", "short", "both")

_load_errors: list[dict] = []


def strategy_dir() -> Path:
    path = settings.project_root / "plugins" / "strategies"
    path.mkdir(parents=True, exist_ok=True)
    return path


class StrategyLoadError(Exception):
    """A strategy file could not be turned into a valid strategy."""


def _parse_params(raw: dict | None) -> list[ParamSpec]:
    specs: list[ParamSpec] = []
    for name, meta in (raw or {}).items():
        if not isinstance(meta, dict):
            raise StrategyLoadError(f"param '{name}' must be a dict, got {type(meta).__name__}")
        ptype = meta.get("type", "int")
        if ptype not in VALID_PARAM_TYPES:
            raise StrategyLoadError(
                f"param '{name}' has type '{ptype}'; expected one of {VALID_PARAM_TYPES}"
            )
        specs.append(
            ParamSpec(
                name=name,
                type=ptype,
                default=meta.get("default", 0 if ptype != "bool" else False),
                min=meta.get("min"),
                max=meta.get("max"),
                step=meta.get("step"),
                label=meta.get("label"),
            )
        )
    return specs


def load_strategy_file(path: Path) -> StrategySpec:
    """Import one strategy file and build its spec. Raises StrategyLoadError."""
    module_name = f"qp_strategy_{path.stem}"

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise StrategyLoadError(f"cannot import {path.name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise StrategyLoadError(
            f"error while importing {path.name}: {type(exc).__name__}: {exc}"
        ) from exc

    meta = getattr(module, "STRATEGY", None)
    if not isinstance(meta, dict):
        raise StrategyLoadError(f"{path.name} has no module-level STRATEGY dict")

    signals_fn = getattr(module, "signals", None)
    if not callable(signals_fn):
        raise StrategyLoadError(f"{path.name} has no signals(df, params) function")

    side = meta.get("side", "both")
    if side not in VALID_SIDES:
        raise StrategyLoadError(f"{path.name}: side must be one of {VALID_SIDES}, got '{side}'")

    doc = " ".join((module.__doc__ or "").split())

    return StrategySpec(
        id=path.stem,
        name=meta.get("name", path.stem),
        description=meta.get("description", ""),
        help={"what": doc[:900]},
        side=side,
        params=_parse_params(meta.get("params")),
        signals=signals_fn,
    )


def get_registry() -> dict[str, StrategySpec]:
    """Scan the strategy directory. One broken file does not hide the rest."""
    global _load_errors

    specs: dict[str, StrategySpec] = {}
    errors: list[dict] = []

    for path in sorted(strategy_dir().glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = load_strategy_file(path)
            specs[spec.id] = spec
        except StrategyLoadError as exc:
            log.warning("strategy %s failed to load: %s", path.name, exc)
            errors.append({"file": path.name, "error": str(exc)})
        except Exception as exc:  # a strategy must never crash the server
            log.error("strategy %s raised unexpectedly:\n%s", path.name, traceback.format_exc())
            errors.append({"file": path.name, "error": f"{type(exc).__name__}: {exc}"})

    _load_errors = errors
    return specs


def get_load_errors() -> list[dict]:
    return list(_load_errors)


def get_spec(strategy_id: str) -> StrategySpec:
    spec = get_registry().get(strategy_id)
    if spec is None:
        raise StrategyError(f"unknown strategy: {strategy_id}")
    return spec


def run_strategy(
    strategy_id: str,
    df: pd.DataFrame,
    timeframe: str,
    params: dict | None = None,
    config: BacktestConfig | None = None,
) -> dict:
    """Compute signals, simulate them, and summarise the outcome."""
    spec = get_spec(strategy_id)
    if spec.signals is None:
        raise StrategyError(f"strategy '{strategy_id}' has no signals function")
    if df.empty:
        raise StrategyError("no candle data to backtest over")

    resolved = spec.resolve_params(params)
    frame = prepare_frame(df)

    try:
        raw = spec.signals(frame, resolved)
    except StrategyError:
        raise
    except Exception as exc:
        raise StrategyError(f"{type(exc).__name__}: {exc}") from exc

    signal = normalize_signals(raw, frame.index, spec.side)
    result = run_backtest(df, signal, config)
    metrics = compute_metrics(result, df, timeframe)

    return {
        "id": spec.id,
        "name": spec.name,
        "params": resolved,
        "config": result.config.as_dict(),
        "metrics": metrics,
        "equity": [round(float(v), 2) for v in result.equity],
        "times": result.times,
        "position": result.position.tolist(),
        "trades": [t.as_dict() for t in result.trades],
    }
