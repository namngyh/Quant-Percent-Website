"""Tests for the daily DataPro ingest flow."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from raemf_mc.ops.ingest import IngestError, find_latest_incoming, ingest_latest


def _make_history(n_rows: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-01-02", periods=n_rows)
    close = 900 + np.cumsum(rng.normal(0.3, 5.0, size=n_rows))
    return pd.DataFrame(
        {
            "Date": dates.strftime("%d/%m/%Y"),
            "Open": np.round(close - 1.0, 2),
            "High": np.round(close + 2.0, 2),
            "Low": np.round(close - 2.0, 2),
            "Close": np.round(close, 2),
            "Volume": rng.integers(100_000, 900_000, size=n_rows),
        }
    )


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "target": tmp_path / "VNINDEX_Daily.csv",
        "incoming": tmp_path / "incoming",
        "backup": tmp_path / "backups",
    }


def _run(tmp_path: Path) -> object:
    p = _paths(tmp_path)
    return ingest_latest(target_csv=p["target"], incoming_dir=p["incoming"], backup_dir=p["backup"])


def test_no_new_file(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.status == "no_new_file"


def test_first_ingest_creates_target(tmp_path: Path) -> None:
    p = _paths(tmp_path)
    history = _make_history(150)
    _write_csv(history, p["incoming"] / "export.csv")
    result = _run(tmp_path)
    assert result.status == "updated"
    assert result.added_rows == 150
    assert p["target"].exists()
    assert (p["incoming"] / "processed").is_dir()
    assert not (p["incoming"] / "export.csv").exists()


def test_full_history_update_appends_and_backs_up(tmp_path: Path) -> None:
    p = _paths(tmp_path)
    history = _make_history(160)
    _write_csv(history.iloc[:150], p["target"])
    _write_csv(history, p["incoming"] / "export_new.csv")
    result = _run(tmp_path)
    assert result.status == "updated"
    assert result.added_rows == 10
    assert result.backup_file is not None
    assert Path(result.backup_file).exists()
    assert list(p["backup"].glob("VNINDEX_Daily_*.csv"))


def test_rejects_stale_export(tmp_path: Path) -> None:
    p = _paths(tmp_path)
    history = _make_history(160)
    _write_csv(history, p["target"])
    _write_csv(history.iloc[:150], p["incoming"] / "old_export.csv")
    with pytest.raises(IngestError, match="cũ hơn"):
        _run(tmp_path)
    assert not list(p["backup"].glob("*.csv")) if p["backup"].exists() else True


def test_rejects_truncated_history(tmp_path: Path) -> None:
    p = _paths(tmp_path)
    history = _make_history(200)
    _write_csv(history, p["target"])
    truncated = pd.concat([history.iloc[:100], history.iloc[190:]])
    _write_csv(truncated, p["incoming"] / "truncated.csv")
    with pytest.raises(IngestError, match="thiếu"):
        _run(tmp_path)


def test_rejects_conflicting_prices(tmp_path: Path) -> None:
    p = _paths(tmp_path)
    history = _make_history(150)
    _write_csv(history, p["target"])
    corrupted = history.copy()
    corrupted.loc[corrupted.index[:20], "Close"] = corrupted.loc[corrupted.index[:20], "Close"] * 1.5
    _write_csv(corrupted, p["incoming"] / "corrupted.csv")
    with pytest.raises(IngestError, match="lệch"):
        _run(tmp_path)


def test_identical_file_is_unchanged(tmp_path: Path) -> None:
    p = _paths(tmp_path)
    history = _make_history(150)
    _write_csv(history, p["target"])
    _write_csv(history, p["incoming"] / "same.csv")
    result = _run(tmp_path)
    assert result.status == "unchanged"


def test_find_latest_incoming_picks_newest(tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    old = incoming / "a.csv"
    new = incoming / "b.csv"
    old.write_text("Date,Close\n", encoding="utf-8")
    new.write_text("Date,Close\n", encoding="utf-8")
    import os

    os.utime(old, (1_600_000_000, 1_600_000_000))
    os.utime(new, (1_700_000_000, 1_700_000_000))
    assert find_latest_incoming(incoming) == new
