"""Ingest DataPro exports from `incoming/` into the canonical price history file.

Quy trình mỗi ngày: người dùng xuất toàn bộ lịch sử VN-Index từ DataPro thành
một file CSV bất kỳ trong thư mục `incoming/`. Hàm `ingest_latest` chọn file
mới nhất, parse bằng loader chống lỗi phẩy nghìn, đối chiếu với lịch sử hiện
tại để chặn file hỏng hoặc thiếu dữ liệu, backup file cũ rồi mới thay thế.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from raemf_mc.data.loader import load_price_data, sha256_file

INCOMING_DIR = Path("incoming")
BACKUP_DIR = Path("backups")
PROCESSED_DIR = INCOMING_DIR / "processed"
CSV_PATTERNS = ("*.csv", "*.txt")

# Sai lệch tương đối tối đa cho phép khi so close của cùng một ngày giữa
# file mới và lịch sử hiện tại (DataPro có thể làm tròn khác nhau).
CLOSE_MISMATCH_TOLERANCE = 0.005
# Số ngày trùng nhau bị lệch quá tolerance được phép trước khi từ chối file.
MAX_MISMATCHED_DAYS = 5
# File mới không được thiếu quá số phiên này so với lịch sử hiện tại.
MAX_MISSING_DAYS = 5


class IngestError(RuntimeError):
    """Raised when the incoming file must not replace the current history."""


@dataclass
class IngestResult:
    status: str  # "updated" | "no_new_file" | "unchanged"
    source_file: str | None = None
    previous_end_date: str | None = None
    new_end_date: str | None = None
    new_rows: int = 0
    added_rows: int = 0
    backup_file: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "source_file": self.source_file,
            "previous_end_date": self.previous_end_date,
            "new_end_date": self.new_end_date,
            "new_rows": self.new_rows,
            "added_rows": self.added_rows,
            "backup_file": self.backup_file,
            "warnings": list(self.warnings),
        }


def find_latest_incoming(incoming_dir: Path = INCOMING_DIR) -> Path | None:
    """Return the newest CSV/TXT file in the incoming directory, if any."""
    if not incoming_dir.is_dir():
        return None
    candidates: list[Path] = []
    for pattern in CSV_PATTERNS:
        candidates.extend(p for p in incoming_dir.glob(pattern) if p.is_file())
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _compare_histories(current: pd.DataFrame, new: pd.DataFrame) -> list[str]:
    """Validate the new full-history export against the current history.

    Returns warnings; raises IngestError when the new file would lose data or
    conflicts with the existing history beyond tolerance.
    """
    warnings: list[str] = []
    current_dates = set(current["date"])
    new_dates = set(new["date"])

    if new["date"].max() < current["date"].max():
        raise IngestError(
            "File mới có ngày cuối "
            f"{new['date'].max():%Y-%m-%d} cũ hơn lịch sử hiện tại ({current['date'].max():%Y-%m-%d}). Từ chối thay thế."
        )

    missing = sorted(current_dates - new_dates)
    if len(missing) > MAX_MISSING_DAYS:
        raise IngestError(
            f"File mới thiếu {len(missing)} phiên đã có trong lịch sử hiện tại "
            f"(ví dụ {missing[0]:%Y-%m-%d}). Có thể file xuất không đủ toàn bộ lịch sử. Từ chối thay thế."
        )
    if missing:
        warnings.append(
            f"File mới thiếu {len(missing)} phiên so với lịch sử cũ: " + ", ".join(f"{d:%Y-%m-%d}" for d in missing)
        )

    overlap = current.merge(new, on="date", suffixes=("_old", "_new"))
    if len(overlap):
        rel = (overlap["close_new"] - overlap["close_old"]).abs() / overlap["close_old"].clip(lower=1e-9)
        mismatched = overlap.loc[rel > CLOSE_MISMATCH_TOLERANCE, "date"]
        if len(mismatched) > MAX_MISMATCHED_DAYS:
            raise IngestError(
                f"Giá close của {len(mismatched)} phiên trùng nhau lệch quá {CLOSE_MISMATCH_TOLERANCE:.1%} "
                f"so với lịch sử hiện tại (ví dụ {mismatched.iloc[0]:%Y-%m-%d}). Từ chối thay thế."
            )
        if len(mismatched):
            warnings.append(
                f"{len(mismatched)} phiên có close lệch nhẹ so với lịch sử cũ: "
                + ", ".join(f"{d:%Y-%m-%d}" for d in mismatched)
            )
    return warnings


def ingest_latest(
    target_csv: str | Path = "VNINDEX_Daily.csv",
    incoming_dir: str | Path = INCOMING_DIR,
    backup_dir: str | Path = BACKUP_DIR,
    archive: bool = True,
) -> IngestResult:
    """Ingest the newest DataPro export into `target_csv`.

    The raw incoming file replaces `target_csv` verbatim (the robust loader
    handles DataPro's split thousands separators), after validation against
    the current history. The previous file is backed up with a timestamp and
    the processed export is moved to `incoming/processed/`.
    """
    target_csv = Path(target_csv)
    incoming_dir = Path(incoming_dir)
    backup_dir = Path(backup_dir)

    source = find_latest_incoming(incoming_dir)
    if source is None:
        return IngestResult(status="no_new_file")

    new_df, new_meta = load_price_data(source)
    if len(new_df) < 100:
        raise IngestError(f"File mới chỉ parse được {len(new_df)} dòng hợp lệ, quá ít cho toàn bộ lịch sử VN-Index.")

    result = IngestResult(
        status="updated",
        source_file=str(source),
        new_end_date=new_meta["end_date"],
        new_rows=len(new_df),
    )

    if target_csv.exists():
        if sha256_file(source) == sha256_file(target_csv):
            result.status = "unchanged"
            result.previous_end_date = new_meta["end_date"]
            if archive:
                _archive_processed(source, incoming_dir)
            return result
        current_df, current_meta = load_price_data(target_csv)
        result.previous_end_date = current_meta["end_date"]
        result.warnings.extend(_compare_histories(current_df, new_df))
        result.added_rows = int((new_df["date"] > current_df["date"].max()).sum())
        if result.added_rows == 0 and new_meta["end_date"] == current_meta["end_date"]:
            result.warnings.append("Không có phiên mới so với lịch sử hiện tại; dữ liệu vẫn được thay thế để đồng bộ.")
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{target_csv.stem}_{stamp}{target_csv.suffix}"
        shutil.copy2(target_csv, backup_path)
        result.backup_file = str(backup_path)
    else:
        result.added_rows = len(new_df)

    shutil.copy2(source, target_csv)
    if archive:
        _archive_processed(source, incoming_dir)
    return result


def _archive_processed(source: Path, incoming_dir: Path) -> None:
    processed_dir = incoming_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = processed_dir / f"{source.stem}_{stamp}{source.suffix}"
    shutil.move(str(source), destination)
