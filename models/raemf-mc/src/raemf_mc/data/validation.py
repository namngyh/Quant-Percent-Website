"""Data validation and profiling."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from raemf_mc.data.loader import load_price_data
from raemf_mc.data.schema import OPTIONAL_COLUMNS


def validate_data_file(data_path: str | Path, output_dir: str | Path = "outputs/data_validation") -> dict[str, object]:
    """Validate a CSV file and write a transparent quality report."""
    data_path = Path(data_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    df, meta = load_price_data(data_path)

    raw = pd.read_csv(data_path, dtype=str, engine="python", on_bad_lines="skip")
    missing = df.isna().sum().rename("missing_count").to_frame()
    missing["missing_rate"] = missing["missing_count"] / max(len(df), 1)
    missing.to_csv(output_dir / "missing_values.csv")

    duplicate_dates = df.loc[df["date"].duplicated(keep=False), ["date"]]
    duplicate_dates.to_csv(output_dir / "duplicate_dates.csv", index=False)

    suspicious_masks = []
    suspicious_masks.append(df["close"] < 0)
    for col in ["open", "high", "low", "volume"]:
        if col in df:
            suspicious_masks.append(df[col] < 0)
    if {"high", "low"}.issubset(df.columns):
        suspicious_masks.append(df["high"] < df["low"])
    suspicious = df.loc[pd.concat(suspicious_masks, axis=1).any(axis=1)] if suspicious_masks else df.iloc[0:0]
    suspicious.to_csv(output_dir / "suspicious_rows.csv", index=False)

    gaps = df["date"].diff().dt.days.dropna()
    abnormal_gaps = int((gaps > gaps.quantile(0.99)).sum()) if len(gaps) else 0
    profile = {
        **meta,
        "source_file": str(data_path),
        "raw_columns": list(raw.columns),
        "missing": missing["missing_count"].astype(int).to_dict(),
        "optional_missing_columns": [col for col in OPTIONAL_COLUMNS if col not in df.columns or df[col].isna().all()],
        "negative_or_ohlc_suspicious_rows": int(len(suspicious)),
        "abnormal_calendar_gaps": abnormal_gaps,
    }
    (output_dir / "data_profile.json").write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    report = [
        "# Báo cáo chất lượng dữ liệu",
        "",
        f"- Tệp nguồn: `{data_path}`",
        f"- Số quan sát sau chuẩn hóa: {len(df)}",
        f"- Khoảng thời gian: {profile['start_date']} đến {profile['end_date']}",
        f"- Số ngày trùng được phát hiện trước khi tổng hợp: {profile['duplicate_dates']}",
        f"- Số dòng nghi vấn về giá hoặc OHLC: {profile['negative_or_ohlc_suspicious_rows']}",
        f"- Số khoảng cách lịch bất thường: {profile['abnormal_calendar_gaps']}",
        "",
        "Dữ liệu được sắp xếp tăng dần theo thời gian. Không nội suy giá bị thiếu.",
    ]
    (output_dir / "data_quality_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return profile
