"""Robust VN-Index CSV loader."""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from raemf_mc.data.schema import CANONICAL_COLUMNS, COLUMN_ALIASES, REQUIRED_COLUMNS


def sha256_file(path: str | Path) -> str:
    """Return SHA-256 checksum for a file."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalise_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.strip().lower())


def _canonicalise_header(header: Iterable[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, raw in enumerate(header):
        norm = _normalise_name(raw)
        if not norm:
            continue
        for canonical, aliases in COLUMN_ALIASES.items():
            if norm in aliases and canonical not in mapping:
                mapping[canonical] = idx
    missing = [col for col in REQUIRED_COLUMNS if col not in mapping]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return mapping


def _clean_number(value: object) -> float:
    if value is None:
        return np.nan
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if text == "":
        return np.nan
    text = text.replace(",", "")
    return float(text)


def _join_split_number(tokens: list[str], start: int, stop: int | None = None) -> str:
    values = [x.strip() for x in tokens[start:stop] if x.strip()]
    return "".join(values)


def _join_thousands_group(values: list[str]) -> str:
    cleaned = [v.strip().replace(" ", "") for v in values if v.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0].replace(",", "")
    first, *rest = cleaned
    pieces = [first]
    for token in rest:
        if "." in token:
            whole, frac = token.split(".", 1)
            pieces.append(whole.zfill(3) + "." + frac)
        else:
            pieces.append(token.zfill(3))
    return "".join(pieces).replace(",", "")


def _parse_ohlcv_tokens(tokens: list[str]) -> dict[str, object] | None:
    parts = [t.strip() for t in tokens[1:] if t.strip()]
    if len(parts) < 5:
        return None
    best: tuple[int, dict[str, object]] | None = None
    n = len(parts)
    for l1 in range(1, 4):
        for l2 in range(1, 4):
            for l3 in range(1, 4):
                for l4 in range(1, 4):
                    cuts = [l1, l1 + l2, l1 + l2 + l3, l1 + l2 + l3 + l4]
                    if cuts[-1] >= n:
                        continue
                    groups = [
                        parts[: cuts[0]],
                        parts[cuts[0] : cuts[1]],
                        parts[cuts[1] : cuts[2]],
                        parts[cuts[2] : cuts[3]],
                        parts[cuts[3] :],
                    ]
                    try:
                        vals = [_clean_number(_join_thousands_group(g)) for g in groups]
                    except Exception:
                        continue
                    open_, high, low, close, volume = vals
                    if not all(np.isfinite(vals)):
                        continue
                    score = 0
                    volume_tokens = groups[4]
                    if high >= low:
                        score += 3
                    if high + 0.5 >= max(open_, close) and low - 0.5 <= min(open_, close):
                        score += 4
                    ratio = high / max(low, 1e-12)
                    if 0.5 <= ratio <= 1.5:
                        score += 5
                    elif ratio > 3.0:
                        score -= 5
                    if volume >= 0 and abs(volume - round(volume)) < 1e-6:
                        score += 3
                    if all("." not in t for t in volume_tokens):
                        score += 3
                    else:
                        score -= 4
                    score -= sum(len(g) for g in groups[:4]) - 4
                    if best is None or score > best[0]:
                        best = (
                            score,
                            {"date": tokens[0], "open": open_, "high": high, "low": low, "close": close, "volume": volume},
                        )
    return best[1] if best is not None else None


def load_price_data(path: str | Path) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load VN-Index data with defensive parsing for split thousands separators.

    The common local `data.csv` stores values such as `4,200` without quotes,
    causing the CSV reader to split volume across adjacent fields. The parser
    maps known OHLC columns first, then joins residual tokens for volume.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise ValueError("Empty CSV file")
    header = rows[0]
    mapping = _canonicalise_header(header)
    raw_records: list[dict[str, object]] = []
    malformed_rows: list[int] = []
    max_named_idx = max(mapping.values())
    for line_no, tokens in enumerate(rows[1:], start=2):
        if not any(x.strip() for x in tokens):
            continue
        record = _parse_ohlcv_tokens(tokens)
        if record is not None:
            raw_records.append(record)
            continue
        record = {}
        for col in CANONICAL_COLUMNS:
            if col in mapping and mapping[col] < len(tokens):
                record[col] = tokens[mapping[col]]
            else:
                record[col] = np.nan
        if "volume" in mapping and len(tokens) > mapping["volume"] + 1:
            record["volume"] = _join_split_number(tokens, mapping["volume"])
        elif "volume" not in mapping and len(tokens) > max_named_idx + 1:
            record["volume"] = _join_split_number(tokens, max_named_idx + 1)
        if len(tokens) <= max_named_idx:
            malformed_rows.append(line_no)
        raw_records.append(record)

    df = pd.DataFrame(raw_records)
    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df:
            df[col] = df[col].map(_clean_number)
    df = df.dropna(subset=["date", "close"]).copy()
    df = df.sort_values("date")
    duplicate_count = int(df["date"].duplicated(keep=False).sum())
    exact_duplicate_count = int(df.duplicated(subset=CANONICAL_COLUMNS, keep="first").sum())
    if exact_duplicate_count:
        df = df.drop_duplicates(subset=CANONICAL_COLUMNS, keep="first")
    conflicting_duplicate_count = int(df["date"].duplicated(keep=False).sum())
    if conflicting_duplicate_count:
        df = (
            df.groupby("date", as_index=False)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .sort_values("date")
        )
    df = df.reset_index(drop=True)
    meta = {
        "rows_loaded": int(len(df)),
        "duplicate_dates": duplicate_count,
        "exact_duplicate_records_removed": exact_duplicate_count,
        "conflicting_duplicate_records_aggregated": conflicting_duplicate_count,
        "malformed_rows": malformed_rows,
        "columns": list(df.columns),
        "start_date": df["date"].min().strftime("%Y-%m-%d") if len(df) else None,
        "end_date": df["date"].max().strftime("%Y-%m-%d") if len(df) else None,
        "sha256": sha256_file(path),
    }
    return df, meta
