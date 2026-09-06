"""The API must keep the exact shape the website was built against.

The frontend validates every response with Zod in
`quantpercent/lib/api/types.ts`; these tests assert the same field names
and enum values on this side, so a rename here fails here rather than in
production.
"""

from datetime import UTC, datetime

import pytest

from app.main import app
from app.schemas.common import Freshness
from app.schemas.market import MarketOverview, Quote
from app.schemas.models import ForecastRecord, ModelDetail, ModelSummary
from app.schemas.performance import Metrics, PerformanceSeries, StrategyDetail

EXPECTED_ROUTES = {
    "/api/v1/market/overview",
    "/api/v1/market/vn30/constituents",
    "/api/v1/market/risk",
    "/api/v1/market/{symbol}/quote",
    "/api/v1/market/{symbol}/history",
    "/api/v1/models",
    "/api/v1/models/{slug}",
    "/api/v1/models/{slug}/latest",
    "/api/v1/models/{slug}/history",
    "/api/v1/strategies",
    "/api/v1/strategies/{slug}",
    "/api/v1/strategies/{slug}/performance",
    "/api/v1/strategies/{slug}/metrics",
    "/api/v1/strategies/{slug}/simulations",
    "/api/v1/status",
    "/api/v1/data-freshness",
    "/api/v1/model-status",
    "/api/v1/contact",
    "/api/v1/investor-interest",
    "/api/v1/feedback",
    "/api/v1/join",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
    "/api/v1/auth/me",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/auth/verify-email",
    "/api/v1/auth/change-password",
    "/api/v1/auth/resend-verification",
    "/api/v1/auth/request-author",
    "/api/v1/admin/users",
    "/api/v1/admin/users/{user_id}",
}


def test_every_expected_route_is_mounted() -> None:
    # Read the OpenAPI document rather than app.routes: FastAPI flattens
    # included routers only when the schema is built.
    mounted = set(app.openapi()["paths"])
    missing = EXPECTED_ROUTES - mounted
    assert not missing, f"missing routes: {sorted(missing)}"


def test_freshness_block_present_on_data_payloads() -> None:
    required = set(Freshness.model_fields)
    for schema in (Quote, MarketOverview, PerformanceSeries, ForecastRecord):
        assert required <= set(schema.model_fields), schema.__name__


def test_metrics_are_all_optional() -> None:
    # A metric the run did not produce must serialise as null, never 0
    for name, field in Metrics.model_fields.items():
        assert not field.is_required(), name


def test_market_overview_model_fields_are_optional() -> None:
    """The same rule applies to the model's read on the market.

    quant.market_state is empty until an inference runner fills it. If these
    were required the service would have to invent a regime, and a made-up
    "sideways / moderate / 0" is indistinguishable from a real reading on
    the page. Quotes stay required — they come from the ingestion feed.
    """
    model_derived = {
        "regime",
        "regime_probability",
        "probability_up",
        "probability_down",
        "volatility",
        "risk_state",
        "risk_score",
        "model_consensus",
        "public_signal",
    }
    for name in model_derived:
        assert name in MarketOverview.model_fields, name
        assert not MarketOverview.model_fields[name].is_required(), name
    assert MarketOverview.model_fields["quotes"].is_required()


def test_market_overview_without_model_state_has_no_invented_values() -> None:
    overview = MarketOverview(
        data_as_of=datetime(2026, 8, 4, tzinfo=UTC),
        generated_at=datetime(2026, 8, 4, tzinfo=UTC),
        source_status="ok",
        is_stale=False,
        delay_minutes=15,
        quotes=[],
    )
    dumped = overview.model_dump()
    assert dumped["regime"] is None
    assert dumped["risk_state"] is None
    assert dumped["risk_score"] is None
    assert dumped["probability_up"] is None


def test_declared_market_delay_is_actually_applied() -> None:
    """The published delay must match what the API withholds.

    It used to announce 15 minutes on every payload while serving the newest
    bar — about a minute old — because the cutoff helper was never called from
    any query. Nothing implements withholding today, so the only honest value
    is 0, and the settings model refuses anything else.
    """
    from pydantic import ValidationError

    from app.core.config import Settings, settings

    assert settings.market_delay_minutes == 0
    with pytest.raises(ValidationError):
        Settings(market_delay_minutes=15)


def test_forecast_regime_and_risk_are_optional() -> None:
    """A distributional model publishes without calling a regime.

    MSDP forecasts return quantiles and a calibrated interval and makes no
    regime call. If these were required the loader would have to invent one,
    and an invented regime renders on the model page exactly like a real one.
    The forecast itself stays required — without a value and an interval the
    row is not a forecast.
    """
    for name in ("regime", "regime_probability", "risk_score", "risk_state"):
        assert not ForecastRecord.model_fields[name].is_required(), name
    for name in (
        "forecast_value",
        "forecast_return",
        "probability_up",
        "probability_down",
        "volatility",
        "interval_lower",
        "interval_upper",
    ):
        assert ForecastRecord.model_fields[name].is_required(), name


def test_forecast_record_excludes_internal_fields() -> None:
    # Spec §18 forbids publishing these
    forbidden = {
        "features",
        "feature_values",
        "raw_parameters",
        "entry_logic",
        "exit_logic",
        "position_size",
        "stop_loss",
        "take_profit",
        "internal_signal",
        "private_dataset_id",
        "model_file_path",
    }
    assert not (forbidden & set(ForecastRecord.model_fields))


def test_model_catalogue_carries_database_backed_research_content() -> None:
    card_fields = {
        "tagline",
        "key_output",
        "sparkline",
        "sparkline_label",
        "updated_at",
    }
    assert card_fields <= set(ModelSummary.model_fields)
    assert "research_profile" in ModelDetail.model_fields


def test_strategy_detail_carries_database_backed_report_metadata() -> None:
    assert {
        "name",
        "summary",
        "benchmark",
        "fees_note",
        "slippage_note",
        "split_note",
        "seed_note",
        "caveats",
        "provenance",
    } <= set(StrategyDetail.model_fields)


def test_openapi_generates() -> None:
    schema = app.openapi()
    assert schema["info"]["title"]
    assert "/api/v1/market/overview" in schema["paths"]
