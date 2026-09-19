"""Probe a market-data source and report the `data.source` block it needs.

The VPS schema is not known to whoever writes the config, and guessing table or
column names would be exactly the kind of silent assumption this repository
refuses elsewhere. This module instead *reads* a database - strictly read-only,
through the same connectors the online tier uses - and reports what it found,
so the config is filled in from evidence.

Nothing here writes to the source, and nothing here modifies a config file: it
prints a suggestion for a human (or an agent) to paste.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .data import ALIASES, normalize_column
from .data_source import OHLCV_COLUMNS, open_sqlite_readonly

REQUIRED = ("date", "close")


def _backend_of(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".xlsx", ".xls", ".parquet"}:
        return "csv" if suffix == ".csv" else "file"
    if suffix in {".duckdb", ".ddb"}:
        return "duckdb"
    # Vendor files often use an opaque suffix (.dat); sniff the SQLite header.
    try:
        with path.open("rb") as handle:
            if handle.read(16).startswith(b"SQLite format 3"):
                return "sqlite"
    except OSError:
        pass
    return "unknown"


def _map_columns(columns: list[str]) -> dict[str, str]:
    """Map canonical OHLCV names onto the source's own column names."""
    mapping: dict[str, str] = {}
    for column in columns:
        normalized = normalize_column(column)
        for canonical, aliases in ALIASES.items():
            if normalized in aliases and canonical not in mapping:
                mapping[canonical] = column
    return {name: mapping[name] for name in OHLCV_COLUMNS if name in mapping}


def _sqlite_tables(path: Path) -> list[dict[str, Any]]:
    connection = open_sqlite_readonly(path)
    try:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            )
        ]
        tables = []
        for name in names:
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{name}")')]
            sample = pd.read_sql(f'SELECT * FROM "{name}" LIMIT 5', connection)
            tables.append({"table": name, "columns": columns, "sample": sample})
        return tables
    finally:
        connection.close()


def _duckdb_tables(path: Path) -> list[dict[str, Any]]:
    import duckdb

    connection = duckdb.connect(str(path), read_only=True)
    try:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        ]
        tables = []
        for name in names:
            sample = connection.execute(f'SELECT * FROM "{name}" LIMIT 5').fetch_df()
            tables.append({"table": name, "columns": list(sample.columns), "sample": sample})
        return tables
    finally:
        connection.close()


def describe_source(path: str | Path) -> dict[str, Any]:
    """Read-only inventory of a source: backend, tables, columns, samples."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Không thấy nguồn dữ liệu: {path}")
    backend = _backend_of(path)
    if backend == "sqlite":
        tables = _sqlite_tables(path)
    elif backend == "duckdb":
        tables = _duckdb_tables(path)
    elif backend in {"csv", "file"}:
        from .data import load_price_data

        frame = load_price_data(path)[0]
        tables = [{"table": None, "columns": list(frame.columns), "sample": frame.head()}]
    else:
        raise LookupError(
            f"Chưa nhận dạng được backend cho {path}. Hỗ trợ: .csv/.parquet/.xlsx, "
            "SQLite (kể cả đuôi lạ như .dat), .duckdb."
        )
    for entry in tables:
        entry["column_map"] = _map_columns(entry["columns"])
        entry["mapped"] = sorted(entry["column_map"])
    return {"path": str(path), "backend": backend, "tables": tables}


def _date_unit(sample: pd.DataFrame, date_column: str | None) -> str | None:
    """Epoch-day integers are common in vendor stores; text dates need no unit."""
    if date_column is None or date_column not in sample.columns:
        return None
    values = pd.to_numeric(sample[date_column], errors="coerce").dropna()
    if len(values) == 0:
        return None
    # Plausible epoch-day range: 1990-01-01 (7305) to 2100-01-01 (47482).
    if values.between(7305, 47482).all() and (values % 1 == 0).all():
        return "D"
    return None


def suggest_source_config(path: str | Path) -> dict[str, Any]:
    """Best-supported `data.source` block for this store, from what it contains."""
    described = describe_source(path)
    candidates = [
        entry
        for entry in described["tables"]
        if all(name in entry["column_map"] for name in REQUIRED)
    ]
    if not candidates:
        raise LookupError(
            f"Trong {path} không tìm thấy bảng nào có đủ cột ngày và giá đóng cửa. "
            "Chạy describe_source() để xem toàn bộ bảng/cột rồi map tay."
        )
    best = max(candidates, key=lambda entry: len(entry["column_map"]))
    date_column = best["column_map"].get("date")
    return {
        "backend": described["backend"],
        "path": str(path),
        "table": best["table"],
        "column_map": {
            canonical: source
            for canonical, source in best["column_map"].items()
            if canonical != source
        },
        "date_unit": _date_unit(best["sample"], date_column),
    }


def suggested_yaml(path: str | Path) -> str:
    """The suggestion as a YAML fragment ready to paste into a config."""
    import yaml

    return yaml.safe_dump(
        {"data": {"source": suggest_source_config(path)}}, sort_keys=False, allow_unicode=True
    )


def report(path: str | Path) -> str:
    """Human-readable summary: every table, what mapped, and the suggestion."""
    described = describe_source(path)
    lines = [f"Nguồn: {described['path']}", f"Backend: {described['backend']}", ""]
    for entry in described["tables"]:
        name = entry["table"] or "(file)"
        lines.append(f"  Bảng {name}: {len(entry['columns'])} cột")
        lines.append(f"    cột      : {', '.join(map(str, entry['columns'][:12]))}")
        lines.append(f"    map được : {', '.join(entry['mapped']) or '(không có OHLCV)'}")
    lines.append("")
    try:
        lines.append("Đề xuất data.source (dán vào configs/default.yaml):")
        lines.append("")
        lines.append(suggested_yaml(path))
    except LookupError as error:
        lines.append(f"Chưa đề xuất được: {error}")
    return "\n".join(lines)
