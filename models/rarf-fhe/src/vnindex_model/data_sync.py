"""Materialise the configured market data source as the batch input file.

Why a file at all, when the database is right there?

``run_metadata`` records ``sha256_file(data_path)``, and every report in this
repository is traceable back to that hash. A live query has no hash: two
``run-all`` invocations minutes apart would silently train on different data and
claim the same provenance. Exporting a snapshot first keeps the batch tier's
reproducibility contract intact and, as a side effect, makes the batch and the
online tier read the *same* numbers -- previously the batch used a vendor CSV
whose OHLC invariants disagree with the database on 13 sessions.

The export is atomic: a partially written file would be indistinguishable from a
truncated history, which is exactly the kind of silent corruption the online
tier's ``_assert_history_unchanged`` exists to catch.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_config
from .data import load_price_data
from .data_source import OHLCV_COLUMNS, build_market_data_source

logger = logging.getLogger("vnindex_model.data_sync")

EXPORT_HEADER = ["Date", "Open", "High", "Low", "Close", "Volume"]
SUPPORTED_EXPORT_SUFFIXES = {".csv", ".parquet"}


def _destination(config: dict[str, Any], root: Path, override: str | Path | None) -> Path:
    if override is not None:
        path = Path(override)
    else:
        configured = config.get("project", {}).get("data_path")
        if not configured:
            raise ValueError("project.data_path chưa được đặt — không biết ghi snapshot vào đâu")
        path = Path(configured)
    if not path.is_absolute():
        path = root / path
    if path.suffix.lower() not in SUPPORTED_EXPORT_SUFFIXES:
        raise ValueError(
            f"Định dạng snapshot chưa hỗ trợ: {path.suffix!r}. Hỗ trợ: .csv, .parquet"
        )
    return path


def _previous(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        frame = load_price_data(path)[0]
    except Exception as error:  # a corrupt previous snapshot must not block a resync
        logger.warning("previous_snapshot_unreadable path=%s error=%s", path, error)
        return None
    return frame[[name for name in OHLCV_COLUMNS if name in frame]].reset_index(drop=True)


def _write_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        if path.suffix.lower() == ".parquet":
            frame.to_parquet(temporary, index=False)
        else:
            export = frame.copy()
            export["date"] = pd.to_datetime(export["date"]).dt.strftime("%Y-%m-%d")
            export.columns = [column.capitalize() for column in export.columns]
            export.to_csv(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _compare(previous: pd.DataFrame | None, current: pd.DataFrame) -> dict[str, Any]:
    """Describe what the resync changed, separating growth from rewritten history.

    New sessions at the end are routine. A changed value on a date that was
    already present means the vendor restated history, and that invalidates the
    online state -- the caller is told loudly rather than left to notice later.
    """
    if previous is None or previous.empty:
        return {"rows_added": int(len(current)), "history_rewritten": False, "rewritten_dates": []}

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
        "rows_added": int(len(new.index.difference(old.index))),
        "rows_removed": int(len(old.index.difference(new.index))),
        "history_rewritten": bool(unique_rewritten),
        "rewritten_dates": unique_rewritten[:20],
        "rewritten_count": len(unique_rewritten),
    }


def sync_source(
    config_path: str | Path = "configs/default.yaml",
    *,
    destination: str | Path | None = None,
    root: str | Path = ".",
) -> dict[str, Any]:
    """Export ``data.source`` to ``project.data_path`` and report what changed."""
    started = time.perf_counter()
    root = Path(root).resolve()
    config = load_config(config_path)
    target = _destination(config, root, destination)

    source_config = dict(config.get("data", {}).get("source") or {})
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

    previous = _previous(target)
    changes = _compare(previous, frame)
    _write_atomic(frame, target)

    result = {
        "status": "synced",
        "backend": str(source_config.get("backend")),
        "symbol": source_config.get("symbol"),
        "destination": str(target),
        "rows": int(len(frame)),
        "first_date": str(pd.Timestamp(frame["date"].min()).date()),
        "last_date": str(pd.Timestamp(frame["date"].max()).date()),
        **changes,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    if changes["history_rewritten"]:
        logger.warning(
            "sync_source_history_rewritten count=%d sample=%s — chạy lại run-all + "
            "init-online-state thay vì update-latest",
            changes["rewritten_count"],
            changes["rewritten_dates"][:5],
        )
    logger.info(
        "sync_source_done rows=%d added=%d last=%s",
        result["rows"],
        changes["rows_added"],
        result["last_date"],
    )
    return result
