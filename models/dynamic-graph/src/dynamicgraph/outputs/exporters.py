"""Artifact writers with graceful degradation (Parquet -> CSV when pyarrow is
missing) and NaN-safe JSON serialisation."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path, PurePath
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def _sanitize(value: Any) -> Any:
    """Make a value JSON-safe: NaN/Inf -> None, NumPy scalars -> Python."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        as_float = float(value)
        return None if (math.isnan(as_float) or math.isinf(as_float)) else as_float
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (np.ndarray, list, tuple)):
        return [_sanitize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, (pd.Series,)):
        return _sanitize(value.to_dict())
    if pd.isna(value) if np.isscalar(value) else False:
        return None
    return value


def export_json(payload: Any, path: Path, indent: int = 2) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize(payload), indent=indent, default=str), encoding="utf-8")
    logger.debug("Wrote %s", path)
    return path


def export_frame(
    frame: pd.DataFrame,
    path: Path,
    formats: tuple[str, ...] = ("csv",),
    index: bool = False,
) -> list[Path]:
    """Write a DataFrame in the requested formats. Returns the paths written."""
    if frame is None or frame.empty:
        logger.debug("Skipping empty frame for %s", path)
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for fmt in formats:
        target = path.with_suffix(f".{fmt}")
        try:
            if fmt == "csv":
                frame.to_csv(target, index=index)
            elif fmt == "parquet":
                serializable = frame.copy()
                for column in serializable.columns:
                    if serializable[column].map(lambda v: isinstance(v, (list, dict, set))).any():
                        serializable[column] = serializable[column].astype(str)
                serializable.to_parquet(target, index=index)
            elif fmt == "json":
                frame.to_json(target, orient="records", date_format="iso", indent=2)
            else:
                logger.warning("Unknown export format `%s`; skipped.", fmt)
                continue
            written.append(target)
        except Exception as exc:
            logger.warning("Could not write %s (%s); falling back to CSV.", target, exc)
            if fmt != "csv":
                fallback = path.with_suffix(".csv")
                frame.to_csv(fallback, index=index)
                written.append(fallback)
    return written


def output_formats(config: Any) -> tuple[str, ...]:
    formats: list[str] = []
    if config.output.export_csv:
        formats.append("csv")
    if config.output.export_parquet:
        formats.append("parquet")
    return tuple(formats) or ("csv",)


def export_snapshot_history(
    edge_frames: dict[str, pd.DataFrame], directory: Path, formats: tuple[str, ...] = ("parquet",)
) -> list[Path]:
    written: list[Path] = []
    for key, frame in edge_frames.items():
        written += export_frame(frame, directory / f"edges_{key}", formats=formats)
    return written


def _relative_to_repo(value: Any) -> Any:
    """Rewrite an absolute artifact path as repo-relative.

    The manifest is committed, so absolute paths would publish the directory
    layout of whichever machine produced the run -- including the operating
    user's name. Repo-relative paths are also the only form a reader on another
    machine can act on.
    """
    if not isinstance(value, (str, Path)):
        return value
    from dynamicgraph.config import REPO_ROOT

    text = str(value)
    # `Path.is_absolute()` is platform-specific: on Windows a POSIX path like
    # `/var/run/x` reports False, so a manifest written on one platform and
    # inspected on another would slip through. Judge the string instead.
    looks_absolute = text.startswith(("/", "\\")) or (len(text) > 1 and text[1] == ":")
    if not looks_absolute:
        return text.replace("\\", "/")

    try:
        return Path(text).relative_to(REPO_ROOT).as_posix()
    except (ValueError, OSError):
        # Outside the repository: keep the file name only, never the parents.
        return PurePath(text.replace("\\", "/")).name


def write_manifest(directory: Path, entries: dict[str, Any]) -> Path:
    """Index of every artifact produced, for the API and the reports."""
    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "artifacts": {k: _relative_to_repo(v) for k, v in entries.items()},
    }
    return export_json(manifest, directory / "manifest.json")
