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
    # One report is published: seed 433444 over 2024-2025.
    assert len(catalogue["strategies"]) == 1


def test_every_model_declares_access(catalogue) -> None:
    for model in catalogue["models"]:
        assert model["access"] in ("public", "members"), model["slug"]


def test_members_only_models_are_marked(catalogue) -> None:
    locked = [m["slug"] for m in catalogue["models"] if m["access"] == "members"]
    # Model Modus and the other flagship models stay previewable
    assert "model-modus" not in locked
    assert locked, "expected some models to require sign-in"


def test_modus_metrics_match_source() -> None:
    data = _perf("modus-2024-2025.json")
    metrics = _metric_rows(data["full"], data["tier3"]["all"])
    assert metrics["totalReturn"] == pytest.approx(0.974)
    assert metrics["maxDrawdown"] == pytest.approx(-0.0507)
    assert metrics["winRate"] == pytest.approx(0.443)
    assert metrics["netPoints"] == pytest.approx(974.0)
    assert metrics["trades"] == 291


def test_combined_totals_are_exact_sums_of_the_years() -> None:
    """The per-year rows are the source; the totals must not drift from them."""
    data = _perf("modus-2024-2025.json")
    years = data["years"].values()
    full = data["full"]

    assert full["net_profit"] == pytest.approx(
        sum(y["profit"] for y in years), abs=0.05
    )
    assert full["total_trades"] == sum(y["trades"] for y in years)
    assert full["long_pnl"] + full["short_pnl"] == pytest.approx(
        full["net_profit"], abs=0.5
    )


def test_reconstructed_win_loss_split_reconciles_to_net() -> None:
    """Win rate, average win and average loss are rebuilt from the per-year
    rows. If that were wrong, payoff and profit factor would be wrong too and
    nothing else would catch it."""
    data = _perf("modus-2024-2025.json")
    full = data["full"]
    wins = round(full["total_trades"] * full["win_rate"] / 100)
    losses = full["total_trades"] - wins
    rebuilt = wins * full["avg_win"] + losses * full["avg_loss"]
    assert rebuilt == pytest.approx(full["net_profit"], rel=0.02)


def test_uncombinable_ratios_are_absent_rather_than_averaged() -> None:
    """Sharpe and friends cannot be combined across separately scored years.

    Averaging two annual figures would invent a statistic nobody computed, so
    they must be missing from the report-level block entirely.
    """
    data = _perf("modus-2024-2025.json")
    metrics = _metric_rows(data["full"], data["tier3"]["all"])
    for key in ("sharpe", "sortino", "calmar", "upi", "equityR2"):
        assert key not in metrics, f"{key} cannot be combined across years"


def test_only_complete_years_are_published() -> None:
    """2026 stops in August and every annualised figure for it is scaled up to
    a full year, so it is not comparable with the two complete years."""
    data = _perf("modus-2024-2025.json")
    assert sorted(data["years"]) == ["2024", "2025"]
    assert not any(f["partial_year"] for f in data["folds"])


def test_missing_metrics_are_omitted_not_zeroed() -> None:
    data = _perf("modus-2024-2025.json")
    metrics = _metric_rows(data["full"], data["tier3"]["all"])
    assert "benchmarkReturn" not in metrics
    assert all(v is not None for v in metrics.values())


def test_fold_percentages_use_the_documented_notional() -> None:
    data = _perf("modus-2024-2025.json")
    folds = {f["test_year"]: f for f in data["folds"]}
    assert round(folds[2024]["net_points"] / NOTIONAL_POINTS, 4) == pytest.approx(
        0.3014, abs=1e-4
    )
    assert round(folds[2025]["net_points"] / NOTIONAL_POINTS, 4) == pytest.approx(
        0.6726, abs=1e-4
    )


def test_exit_reasons_account_for_every_trade() -> None:
    data = _perf("modus-2024-2025.json")
    assert sum(r["share"] for r in data["exit_reasons"]) == pytest.approx(
        100.0, abs=0.5
    )
