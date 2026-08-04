"""Merge the two local VN-Index history files into one canonical series.

``data.csv`` is the frozen research snapshot; ``VNINDEX_Daily.csv`` is the
DataPro-refreshed operational history. Both are parsed with the defensive
loader; overlapping dates are compared field by field and every conflict is
reported instead of being silently overwritten. For conflicting dates the
newer operational file wins, because it is the corrected export.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from raemf_mc.data.loader import load_price_data, sha256_file

PRICE_COLUMNS = ("open", "high", "low", "close", "volume")
# Relative tolerance for treating overlapping values as equal (DataPro rounding).
RELATIVE_TOLERANCE = 0.001


@dataclass
class MergeResult:
    frame: pd.DataFrame
    conflicts: pd.DataFrame
    report: dict[str, object] = field(default_factory=dict)


def merge_price_histories(
    primary_path: str | Path,
    secondary_path: str | Path,
) -> MergeResult:
    """Merge ``secondary`` (older snapshot) under ``primary`` (preferred file).

    Rows only present in either file are kept. For dates present in both,
    the primary file's values are used and disagreements beyond the relative
    tolerance are recorded in the conflicts frame.
    """
    primary, primary_meta = load_price_data(primary_path)
    secondary, secondary_meta = load_price_data(secondary_path)
    primary = primary.set_index("date")
    secondary = secondary.set_index("date")
    overlap = primary.index.intersection(secondary.index)
    conflict_rows: list[dict[str, object]] = []
    for date in overlap:
        for column in PRICE_COLUMNS:
            left = float(primary.loc[date, column])
            right = float(secondary.loc[date, column])
            if not np.isfinite(left) and not np.isfinite(right):
                continue
            denominator = max(abs(left), abs(right), 1e-12)
            if abs(left - right) / denominator > RELATIVE_TOLERANCE:
                conflict_rows.append(
                    {
                        "date": date,
                        "column": column,
                        "primary_value": left,
                        "secondary_value": right,
                        "relative_difference": abs(left - right) / denominator,
                        "resolution": "primary",
                    }
                )
    conflicts = pd.DataFrame(
        conflict_rows,
        columns=["date", "column", "primary_value", "secondary_value", "relative_difference", "resolution"],
    )
    only_secondary = secondary.loc[secondary.index.difference(primary.index)]
    merged = pd.concat([primary, only_secondary]).sort_index().reset_index()
    merged = merged.dropna(subset=["date", "close"]).reset_index(drop=True)
    report = {
        "primary_file": str(primary_path),
        "secondary_file": str(secondary_path),
        "primary_sha256": sha256_file(primary_path),
        "secondary_sha256": sha256_file(secondary_path),
        "primary_rows": int(len(primary)),
        "secondary_rows": int(len(secondary)),
        "overlap_dates": int(len(overlap)),
        "conflicting_cells": int(len(conflicts)),
        "conflicting_dates": int(conflicts["date"].nunique()) if len(conflicts) else 0,
        "rows_only_in_primary": int(len(primary.index.difference(secondary.index))),
        "rows_only_in_secondary": int(len(only_secondary)),
        "merged_rows": int(len(merged)),
        "merged_start": str(merged["date"].min().date()),
        "merged_end": str(merged["date"].max().date()),
        "primary_meta": primary_meta,
        "secondary_meta": secondary_meta,
    }
    return MergeResult(frame=merged, conflicts=conflicts, report=report)


def write_merge_artifacts(result: MergeResult, output_dir: str | Path) -> Path:
    """Persist canonical parquet, conflicts CSV and a Markdown report."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    parquet_path = destination / "canonical_vnindex.parquet"
    result.frame.to_parquet(parquet_path, index=False)
    # A CSV twin so every downstream loader (and the human user) can read it.
    csv_path = destination / "canonical_vnindex.csv"
    result.frame.to_csv(csv_path, index=False)
    result.conflicts.to_csv(destination / "data_conflicts.csv", index=False)
    report = dict(result.report)
    report["canonical_parquet_sha256"] = sha256_file(parquet_path)
    report["canonical_csv_sha256"] = sha256_file(csv_path)
    (destination / "data_merge_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    lines = [
        "# Báo cáo hợp nhất dữ liệu VN-Index",
        "",
        f"- File ưu tiên (primary): `{report['primary_file']}` — {report['primary_rows']} phiên",
        f"- File thứ cấp (secondary): `{report['secondary_file']}` — {report['secondary_rows']} phiên",
        f"- Số ngày chồng lấn: {report['overlap_dates']}",
        f"- Số ô giá trị xung đột (> {RELATIVE_TOLERANCE:.1%} tương đối): {report['conflicting_cells']}"
        f" trên {report['conflicting_dates']} ngày",
        f"- Phiên chỉ có trong primary: {report['rows_only_in_primary']}",
        f"- Phiên chỉ có trong secondary: {report['rows_only_in_secondary']}",
        f"- Chuỗi hợp nhất: {report['merged_rows']} phiên, {report['merged_start']} → {report['merged_end']}",
        "",
        "Quy tắc xử lý: với ngày xung đột, giá trị của file primary (bản DataPro"
        " cập nhật) được dùng; mọi xung đột được liệt kê trong `data_conflicts.csv`,"
        " không có ghi đè âm thầm. File gốc không bị sửa.",
    ]
    (destination / "data_merge_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
