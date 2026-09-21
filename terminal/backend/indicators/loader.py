"""Loads user-written indicators from ``plugins/indicators/*.py``.

Each file declares an ``INDICATOR`` dict and a ``calculate(df, params)``
function; see ``backend/indicators/base.py`` for the contract. Files are
re-imported on every scan so editing one and refreshing the browser picks up
the change without restarting the server.

These files are executed as Python. They are your own files on your own
machine — the same trust level as any script you would run yourself.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import traceback
from pathlib import Path

from backend.config import settings
from backend.indicators.base import IndicatorSpec, OutputSpec, ParamSpec

log = logging.getLogger(__name__)

VALID_KINDS = ("overlay", "panel")
VALID_PARAM_TYPES = ("int", "float", "bool")


class PluginLoadError(Exception):
    """A plugin file could not be turned into a valid indicator."""


def _parse_params(raw: dict | None) -> list[ParamSpec]:
    specs: list[ParamSpec] = []
    for name, meta in (raw or {}).items():
        if not isinstance(meta, dict):
            raise PluginLoadError(f"param '{name}' must be a dict, got {type(meta).__name__}")
        ptype = meta.get("type", "int")
        if ptype not in VALID_PARAM_TYPES:
            raise PluginLoadError(
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


def _parse_outputs(raw: list | None) -> list[OutputSpec]:
    specs: list[OutputSpec] = []
    for item in raw or []:
        if isinstance(item, str):
            specs.append(OutputSpec(key=item))
            continue
        if not isinstance(item, dict) or "key" not in item:
            raise PluginLoadError("each output needs a 'key'")
        specs.append(
            OutputSpec(
                key=item["key"],
                label=item.get("label"),
                color=item.get("color"),
                plot_type=item.get("plot_type", "line"),
            )
        )
    return specs


def load_plugin_file(path: Path) -> IndicatorSpec:
    """Import one plugin file and build its spec. Raises PluginLoadError."""
    module_name = f"qp_plugin_{path.stem}"

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PluginLoadError(f"cannot import {path.name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise PluginLoadError(
            f"error while importing {path.name}: {type(exc).__name__}: {exc}"
        ) from exc

    meta = getattr(module, "INDICATOR", None)
    if not isinstance(meta, dict):
        raise PluginLoadError(f"{path.name} has no module-level INDICATOR dict")

    calculate = getattr(module, "calculate", None)
    if not callable(calculate):
        raise PluginLoadError(f"{path.name} has no calculate(df, params) function")

    kind = meta.get("type", "panel")
    if kind not in VALID_KINDS:
        raise PluginLoadError(f"{path.name}: type must be 'overlay' or 'panel', got '{kind}'")

    # The file's own docstring is the explanation; nobody else can write it.
    doc = " ".join((module.__doc__ or "").split())

    return IndicatorSpec(
        id=f"plugin:{path.stem}",
        name=meta.get("name", path.stem),
        kind=kind,
        category=meta.get("category", "custom"),
        source="plugin",
        description=meta.get("description", ""),
        help={
            "source": "docstring" if doc else "none",
            "what": doc[:900],
            "how": "",
            "watch": "",
        },
        params=_parse_params(meta.get("params")),
        outputs=_parse_outputs(meta.get("outputs")),
        calculate=calculate,
    )


def load_plugin_specs() -> tuple[dict[str, IndicatorSpec], list[dict]]:
    """Scan the plugin directory.

    Returns the specs that loaded plus a list of errors, so one broken file
    surfaces in the UI instead of taking the whole catalog down.
    """
    specs: dict[str, IndicatorSpec] = {}
    errors: list[dict] = []

    directory = settings.plugin_indicator_dir
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = load_plugin_file(path)
            specs[spec.id] = spec
        except PluginLoadError as exc:
            log.warning("plugin %s failed to load: %s", path.name, exc)
            errors.append({"file": path.name, "error": str(exc)})
        except Exception as exc:  # defensive: a plugin must never crash the server
            log.error("plugin %s raised unexpectedly:\n%s", path.name, traceback.format_exc())
            errors.append({"file": path.name, "error": f"{type(exc).__name__}: {exc}"})

    return specs, errors
