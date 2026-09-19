"""Materialise the configured market data source as the batch input file.

Every MSDP entry point takes ``--data <path>``: training, evaluation, reporting
and ``predict_latest`` all hash or quote that file, and the run manifest records
which one was used. A live query has no such identity -- two runs minutes apart
would read different data and claim the same provenance.

Exporting a snapshot first keeps that contract intact and, as a side effect,
makes MSDP and RAFF read the same numbers: both model the VN-Index, and the
vendor CSV they were trained on disagrees with the database on 13 sessions where
its OHLC invariants are violated.

The export is atomic. A half-written file is indistinguishable from a truncated
history, which is exactly the corruption the online tier's history check exists
to catch.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_config
from .data_io import load_market_data
from .data_source import OHLCV_COLUMNS, build_market_data_source

SUPPORTED_EXPORT_SUFFIXES = {".csv"}


def _destination(config: dict[str, Any], root: Path, override: str | Path | None) -> Path:
    if override is not None:
        path = Path(override)
    else:
        configured = (config.get("data") or {}).get("path")
        if not configured:
            raise ValueError("data.path chưa được đặt — không biết ghi snapshot vào đâu")
        path = Path(configured)
    if not path.is_absolute():
        path = root / path
    if path.suffix.lower() not in SUPPORTED_EXPORT_SUFFIXES:
        raise ValueError(f"Định dạng snapshot chưa hỗ trợ: {path.suffix!r}. Hỗ trợ: .csv")
    return path


def _previous(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        frame = load_market_data(path)
    except Exception:
        # A corrupt previous snapshot must not block a resync; it is about to be
        # replaced anyway, and the comparison it feeds is only advisory.
        return None
    return frame[[name for name in OHLCV_COLUMNS if name in frame]].reset_index(drop=True)


def _write_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        export = frame.copy()
        export["date"] = pd.to_datetime(export["date"]).dt.strftime("%Y-%m-%d")
        export.columns = [column.capitalize() for column in export.columns]
        export.to_csv(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _compare(previous: pd.DataFrame | None, current: pd.DataFrame) -> dict[str, Any]:
    """Separate routine growth from rewritten history.

    New sessions at the end are expected. A changed value on a date that was
    already present means the vendor restated history, which invalidates both
    the trained model's provenance and the online state, so it is reported
    rather than absorbed by the overwrite.
    """
    if previous is None or previous.empty:
        return {"rows_added": len(current), "history_rewritten": False, "rewritten_dates": []}

    old = previous.set_index(pd.to_datetime(previous["date"]))
    new = current.set_index(pd.to_datetime(current["date"]))
    shared = old.index.intersection(new.index)
    rewritten: list[str] = []
    for column in [name for name in OHLCV_COLUMNS if name != "date"]:
        if column not in old.columns or column not in new.columns:
            continue
        left = pd.to_numeric(old.loc[shared, column], errors="coerce")
        right = pd.to_numeric(new.loc[shared, column], errors="coerce")
        differs = ~((left - right).abs() <= 1e-8) & ~(left.isna() & right.isna())
        rewritten.extend(str(stamp.date()) for stamp in shared[differs])

    unique_rewritten = sorted(set(rewritten))
    return {
        "rows_added": len(new.index.difference(old.index)),
        "rows_removed": len(old.index.difference(new.index)),
        "history_rewritten": bool(unique_rewritten),
        "rewritten_dates": unique_rewritten[:20],
        "rewritten_count": len(unique_rewritten),
    }


def sync_source(
    config_path: str | Path,
    *,
    destination: str | Path | None = None,
    root: str | Path = ".",
) -> dict[str, Any]:
    """Export ``data.source`` to ``data.path`` and report what changed."""
    started = time.perf_counter()
    root = Path(root).resolve()
    config = load_config(config_path)
    target = _destination(config, root, destination)

    source_config = dict((config.get("data") or {}).get("source") or {})
    if not source_config:
        raise ValueError("data.source chưa được cấu hình — không có gì để đồng bộ")
    source_config.setdefault("backend", "csv")

    if str(source_config.get("backend")).lower() == "csv":
        origin = Path(str(source_config.get("path", "")))
        if not origin.is_absolute():
            origin = root / origin
        if origin.resolve() == target.resolve():
            raise ValueError(
                "data.source trỏ đúng vào file đích — đồng bộ sẽ ghi đè chính nó. "
                "Đặt data.source.backend thành postgres/sqlite/duckdb trước."
            )

    source = build_market_data_source(source_config)
    try:
        frame = source.fetch_since(None, None)
    finally:
        source.close()

    if frame.empty:
        raise ValueError("Nguồn dữ liệu không trả về phiên nào — dừng thay vì ghi file rỗng")

    changes = _compare(_previous(target), frame)
    _write_atomic(frame, target)

    return {
        "status": "synced",
        "backend": str(source_config.get("backend")),
        "symbol": source_config.get("symbol"),
        "destination": str(target),
        "rows": len(frame),
        "first_date": str(pd.Timestamp(frame["date"].min()).date()),
        "last_date": str(pd.Timestamp(frame["date"].max()).date()),
        **changes,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
