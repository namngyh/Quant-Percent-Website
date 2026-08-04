"""Markdown table helpers."""

from __future__ import annotations

import pandas as pd


def markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    """Render a compact Markdown table without optional dependencies."""
    if df.empty:
        return "_Không có dữ liệu._"
    small = df.head(max_rows).copy()
    cols = list(small.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in small.iterrows():
        vals = []
        for col in cols:
            val = row[col]
            vals.append(f"{val:.4f}" if isinstance(val, float) else str(val))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)
