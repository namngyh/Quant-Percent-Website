from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from raemf_mc.reporting.current_monitor import (
    MONITOR_END,
    MONITOR_START,
    _build_monitoring_path,
    _update_readme_section,
)


def _config() -> dict[str, object]:
    return {
        "target": {
            "bull_threshold": 0.5,
            "bear_threshold": 0.5,
            "stress_threshold": 1.5,
            "volatility_window": 40,
        }
    }


def test_monitor_marks_immature_horizons_and_tracks_actual_path(tmp_path: Path):
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    outlook = {
        "as_of_date": "2026-01-30",
        "last_close": 1000.0,
        "horizons": {
            str(h): {"predicted_class": "Sideway", "confidence": "Uncertain", "probabilities": {}}
            for h in [20, 40, 60]
        },
    }
    (baseline / "latest_outlook.json").write_text(json.dumps(outlook), encoding="utf-8")
    for horizon in [20, 40, 60]:
        step = np.arange(horizon + 1)
        pd.DataFrame(
            {
                "step": step,
                "q025": 800 + step,
                "q050": 850 + step,
                "q100": 900 + step,
                "q250": 950 + step,
                "q500": 1000 + step,
                "q750": 1050 + step,
                "q900": 1100 + step,
                "q950": 1150 + step,
                "q975": 1200 + step,
            }
        ).to_csv(baseline / f"monte_carlo_quantiles_{horizon}.csv", index=False)
    dates = pd.bdate_range(end="2026-01-30", periods=281).append(pd.bdate_range(start="2026-02-02", periods=8))
    prices = pd.DataFrame({"date": dates, "close": np.linspace(900, 1010, len(dates))})

    path, summary = _build_monitoring_path(prices, baseline, outlook, _config())

    assert set(path["horizon"]) == {20, 40, 60}
    assert summary["sessions_observed"].eq(8).all()
    assert summary["sessions_remaining"].tolist() == [12, 32, 52]
    assert summary["actual_class"].isna().all()
    assert summary["status"].eq("Đang theo dõi, chưa đủ phiên").all()


def test_readme_current_section_is_inserted_and_replaced(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("# Project\n\n## Khả năng tái lập\n\nText\n", encoding="utf-8")

    _update_readme_section(readme, "## Theo dõi\n\nLần 1")
    _update_readme_section(readme, "## Theo dõi\n\nLần 2")

    content = readme.read_text(encoding="utf-8")
    assert content.count(MONITOR_START) == 1
    assert content.count(MONITOR_END) == 1
    assert "Lần 1" not in content
    assert "Lần 2" in content
    assert content.index(MONITOR_END) < content.index("## Khả năng tái lập")
