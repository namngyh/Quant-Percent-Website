"""The seeder must reproduce the published numbers exactly.

These run against the real exported catalogue and the real extracted
research data, so a mistake in the mapping shows up here rather than as a
wrong figure on the website.
"""

import json
from pathlib import Path

import pytest

from scripts.seed_catalogue import NOTIONAL_POINTS, _metric_rows, load_catalogue


def _find_frontend() -> Path:
    """Locate the website repo next to this one.

    It is `frontend/` in the monorepo and `quantpercentFE/` in the older
    split-repo layout. Picking the wrong name does not fail loudly — the
    whole module just skips, which is how these checks stopped running.
    """
    root = Path(__file__).resolve().parents[2]
    for name in ("frontend", "quantpercentFE"):
        if (root / name / "config" / "catalogue.json").exists():
            return root / name
    return root / "frontend"


FRONTEND = _find_frontend()
CATALOGUE = FRONTEND / "config" / "catalogue.json"

pytestmark = pytest.mark.skipif(
    not CATALOGUE.exists(),
    reason="run `npx tsx scripts/export-catalogue.ts` in the website repo",
)


@pytest.fixture(scope="module")
def catalogue() -> dict:
    return load_catalogue(FRONTEND)


def _perf(name: str) -> dict:
    return json.loads(
        (FRONTEND / "config" / "performance" / name).read_text(encoding="utf-8")
    )


def test_catalogue_has_models_and_strategies(catalogue) -> None:
    assert len(catalogue["models"]) >= 10
    # One report is published: the frozen brain scored over 2024-2026.
    assert len(catalogue["strategies"]) == 1


def test_every_model_declares_access(catalogue) -> None:
    for model in catalogue["models"]:
        assert model["access"] in ("public", "members"), model["slug"]


def test_members_only_models_are_marked(catalogue) -> None:
    locked = [m["slug"] for m in catalogue["models"] if m["access"] == "members"]
    # Model Modus and the other flagship models stay previewable
    assert "model-modus" not in locked
    assert locked, "expected some models to require sign-in"


def test_frozen_brain_metrics_match_source() -> None:
    data = _perf("frozen-brain.json")
    metrics = _metric_rows(data["full"], data["tier3"]["all"])
    # Values published on /performance for the frozen-brain run
    assert metrics["totalReturn"] == pytest.approx(1.192)
    assert metrics["annualizedReturn"] == pytest.approx(0.474)
    assert metrics["maxDrawdown"] == pytest.approx(-0.0781)
    assert metrics["winRate"] == pytest.approx(0.391)
    assert metrics["payoff"] == pytest.approx(2.77)
    assert metrics["netPoints"] == pytest.approx(1192.0)
    assert metrics["trades"] == 366


def test_combined_totals_are_exact_sums_of_the_years() -> None:
    """The per-year rows are the source; the totals must not drift from them."""
    data = _perf("frozen-brain.json")
    years = data["years"]
    full = data["full"]

    assert full["net_profit"] == pytest.approx(
        sum(y["net_points"] for y in years), abs=0.05
    )
    assert full["total_trades"] == sum(y["trades"] for y in years)
    assert full["long_pnl"] == pytest.approx(
        sum(y["long_pnl"] for y in years), abs=0.05
    )
    assert full["short_pnl"] == pytest.approx(
        sum(y["short_pnl"] for y in years), abs=0.05
    )
    # Long and short must together account for the whole result.
    assert full["long_pnl"] + full["short_pnl"] == pytest.approx(
        full["net_profit"], abs=0.2
    )


def test_reconstructed_win_loss_split_reconciles_to_net() -> None:
    """Win rate, average win and average loss are reconstructed per year.

    If that reconstruction were wrong, the payoff and profit factor shown on
    the site would be wrong too, and nothing else would catch it. Rebuilding
    the net from the reconstructed pieces is the check.
    """
    data = _perf("frozen-brain.json")
    full = data["full"]
    wins = round(full["total_trades"] * full["win_rate"] / 100)
    losses = full["total_trades"] - wins
    rebuilt = wins * full["avg_win"] + losses * full["avg_loss"]
    assert rebuilt == pytest.approx(full["net_profit"], rel=0.01)


def test_uncombinable_ratios_are_absent_rather_than_averaged() -> None:
    """Sharpe and friends are not combinable across separately scored years.

    Reporting a plausible-looking average of three annual Sharpe figures would
    be inventing a statistic nobody computed, so they must be missing from the
    report-level block entirely.
    """
    data = _perf("frozen-brain.json")
    metrics = _metric_rows(data["full"], data["tier3"]["all"])
    for key in ("sharpe", "sortino", "calmar", "ulcer", "upi", "equityR2"):
        assert key not in metrics, f"{key} cannot be combined across years"


def test_missing_metrics_are_omitted_not_zeroed() -> None:
    data = _perf("frozen-brain.json")
    metrics = _metric_rows(data["full"], data["tier3"]["all"])
    # The run exported no benchmark series; it must be absent entirely
    assert "benchmarkReturn" not in metrics
    assert all(v is not None for v in metrics.values())


def test_fold_percentages_use_the_documented_notional() -> None:
    data = _perf("frozen-brain.json")
    folds = {f["test_year"]: f for f in data["folds"]}
    assert round(folds[2024]["net_points"] / NOTIONAL_POINTS, 4) == pytest.approx(
        0.0314, abs=1e-4
    )
    assert round(folds[2025]["net_points"] / NOTIONAL_POINTS, 4) == pytest.approx(
        0.8434, abs=1e-4
    )


def test_only_the_unfinished_year_is_flagged_partial() -> None:
    """2026 stops in August, and every annualised figure for it is scaled up.

    A reader comparing it with 2025 without that flag would be comparing seven
    months against twelve.
    """
    data = _perf("frozen-brain.json")
    partial = {f["test_year"] for f in data["folds"] if f["partial_year"]}
    assert partial == {2026}


def test_exit_reasons_account_for_every_trade() -> None:
    data = _perf("frozen-brain.json")
    total = sum(r["share"] for r in data["exit_reasons"])
    assert total == pytest.approx(100.0, abs=0.5)
