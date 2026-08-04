"""Tests for the data merge module, WIS/Brier metrics and device policy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from raemf_mc.data.merge import merge_price_histories
from raemf_mc.evaluation.oos_distribution_benchmark import _weighted_distribution_row
from raemf_mc.runtime.hardware import GPUUnavailableError, select_device


def _write_csv(path, rows):
    frame = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    frame.to_csv(path, index=False)


def test_merge_prefers_primary_and_reports_conflicts(tmp_path):
    old = tmp_path / "old.csv"
    new = tmp_path / "new.csv"
    _write_csv(
        old,
        [
            ["01/03/2024", 10, 11, 9, 10.5, 1000],
            ["04/03/2024", 10.5, 11, 10, 10.8, 1100],
        ],
    )
    _write_csv(
        new,
        [
            ["01/03/2024", 10, 11, 9, 10.5, 1000],
            ["04/03/2024", 10.5, 11, 10, 11.5, 1100],  # conflicting close
            ["05/03/2024", 11.5, 12, 11, 11.9, 1200],  # new session
        ],
    )
    result = merge_price_histories(new, old)
    assert result.report["merged_rows"] == 3
    assert result.report["conflicting_cells"] == 1
    conflict = result.conflicts.iloc[0]
    assert conflict["column"] == "close"
    assert conflict["resolution"] == "primary"
    merged_close = result.frame.set_index("date").loc[pd.Timestamp("2024-03-04"), "close"]
    assert merged_close == pytest.approx(11.5)


def test_wis_is_consistent_with_interval_scores():
    rng = np.random.default_rng(1)
    samples = rng.normal(0, 0.05, size=4000)
    weights = np.full(4000, 1 / 4000)
    row = _weighted_distribution_row(0.01, samples, weights)
    manual = 0.5 * abs(0.01 - row["q50"])
    weight_sum = 0.5
    for level in (50, 80, 90, 95):
        alpha = 1 - level / 100
        manual += (alpha / 2) * row[f"interval_score_{level}"]
        weight_sum += 1.0
    assert row["wis"] == pytest.approx(manual / weight_sum)
    assert 0.0 <= row["prob_negative_return"] <= 1.0
    # symmetric normal centred at zero: P(X<0) near one half
    assert row["prob_negative_return"] == pytest.approx(0.5, abs=0.05)


def test_coverage_flags_and_var_signs():
    samples = np.linspace(-0.1, 0.1, 2001)
    weights = np.full(2001, 1 / 2001)
    row = _weighted_distribution_row(0.0, samples, weights)
    for level in (50, 80, 90, 95):
        assert row[f"coverage_{level}"] == 1.0
    assert row["var_95"] > 0
    assert row["expected_shortfall_95"] >= row["var_95"]


def test_device_policy():
    assert select_device("cpu") == "cpu"
    with pytest.raises(ValueError):
        select_device("tpu")
    try:
        import torch

        if not torch.cuda.is_available():
            with pytest.raises(GPUUnavailableError):
                select_device("cuda", require=True)
    except ImportError:
        with pytest.raises(GPUUnavailableError):
            select_device("cuda", require=True)
