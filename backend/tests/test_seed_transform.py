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
    assert len(catalogue["strategies"]) == 3


def test_every_model_declares_access(catalogue) -> None:
    for model in catalogue["models"]:
        assert model["access"] in ("public", "members"), model["slug"]


def test_members_only_models_are_marked(catalogue) -> None:
    locked = [m["slug"] for m in catalogue["models"] if m["access"] == "members"]
    # Model Modus and the other flagship models stay previewable
    assert "model-modus" not in locked
    assert locked, "expected some models to require sign-in"


def test_validation_metrics_match_source() -> None:
    data = _perf("validation-2024.json")
    metrics = _metric_rows(data["full"], data["tier3"]["all"])
    # Values published on /performance for the 2024 validation run
    assert metrics["totalReturn"] == pytest.approx(0.205)
    assert metrics["maxDrawdown"] == pytest.approx(-0.0329)
    assert metrics["winRate"] == pytest.approx(0.398)
    assert metrics["netPoints"] == pytest.approx(204.8)
    assert metrics["trades"] == 113


def test_walk_forward_metrics_match_source() -> None:
    data = _perf("walk-forward.json")
    metrics = _metric_rows(data["full"], data["tier3"]["all"])
    assert metrics["totalReturn"] == pytest.approx(0.683)
    assert metrics["maxDrawdown"] == pytest.approx(-0.0474)
    assert metrics["sharpe"] == pytest.approx(2.14)
    assert metrics["trades"] == 353


def test_missing_metrics_are_omitted_not_zeroed() -> None:
    data = _perf("walk-forward.json")
    metrics = _metric_rows(data["full"], data["tier3"]["all"])
    # The runs exported no benchmark series; it must be absent entirely
    assert "benchmarkReturn" not in metrics
    assert all(v is not None for v in metrics.values())


def test_fold_percentages_use_the_documented_notional() -> None:
    data = _perf("walk-forward.json")
    folds = {f["test_year"]: f for f in data["folds"]}
    assert folds[2026]["net_points"] < 0, "the 2026 fold was negative"
    assert round(folds[2024]["net_points"] / NOTIONAL_POINTS, 4) == pytest.approx(
        0.1403, abs=1e-4
    )


def test_multiseed_cost_stress_is_complete() -> None:
    data = _perf("multiseed-test.json")
    scenarios = data["cost_stress"]["scenarios"]
    assert len(scenarios) == 5
    assert all(s["pct_positive"] == 100.0 for s in scenarios)
    # Higher applied cost must reduce mean profit
    profits = [s["profit_mean"] for s in scenarios]
    assert profits == sorted(profits, reverse=True)


def test_median_seed_equity_ends_at_reported_net() -> None:
    data = _perf("multiseed-test.json")
    median = data["median_seed"]
    assert median["equity"][-1]["equity"] == pytest.approx(
        median["net_points"], abs=0.1
    )
