from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.freshness import build_freshness
from app.db.models import Model
from app.schemas.models import (
    ForecastHistory,
    ForecastHistoryPoint,
    ForecastRecord,
    ModelDetail,
    ModelList,
    ModelSummary,
)


def is_locked(model: Model, authenticated: bool) -> bool:
    """Members-only output stays closed until the visitor signs in.

    This is the real gate: the frontend blur is presentation only.
    """
    return model.access == "members" and not authenticated


async def last_output_by_model(session: AsyncSession) -> dict[str, object]:
    """Latest published output per model, from the forecast table itself.

    The card used to date every model from `web.models.updated_at`, which is
    the day someone last edited its catalogue entry. Eleven of the twelve
    models have never written a forecast, so that label put a recent-looking
    date beside models that have produced nothing. This reads the only source
    that can answer the question honestly, and returns nothing for a model
    that has never run.
    """
    rows = (
        await session.execute(
            text(
                "SELECT model_id, max(data_as_of) AS last_output "
                "FROM quant.model_forecasts GROUP BY model_id"
            )
        )
    ).mappings().all()
    return {r["model_id"]: r["last_output"] for r in rows}


async def list_models(
    session: AsyncSession, *, authenticated: bool
) -> ModelList:
    rows = (
        await session.scalars(
            select(Model)
            .where(Model.visibility == "public")
            .order_by(Model.sort_order, Model.slug)
        )
    ).all()

    last_output = await last_output_by_model(session)

    freshness = build_freshness(
        max((m.updated_at for m in rows), default=None),
        stale_after_minutes=365 * 24 * 60,
    )
    return ModelList(
        **freshness.model_dump(),
        models=[
            ModelSummary(
                slug=m.slug,
                name=m.name,
                code=m.code,
                markets=m.markets,
                category=m.category,
                status=m.status,
                version=m.version,
                horizons=m.horizons,
                access=m.access,
                locked=is_locked(m, authenticated),
                featured=m.featured,
                tagline=m.tagline,
                key_output=m.key_output,
                sparkline=m.sparkline,
                sparkline_label=m.sparkline_label,
                updated_at=m.updated_at,
                last_output_at=last_output.get(m.slug),
            )
            for m in rows
        ],
    )


async def get_model(session: AsyncSession, slug: str) -> Model | None:
    return await session.scalar(
        select(Model).where(Model.slug == slug, Model.visibility == "public")
    )


def to_detail(
    model: Model, *, authenticated: bool, last_output_at: object = None
) -> ModelDetail:
    return ModelDetail(
        slug=model.slug,
        name=model.name,
        code=model.code,
        markets=model.markets,
        category=model.category,
        status=model.status,
        version=model.version,
        horizons=model.horizons,
        access=model.access,
        locked=is_locked(model, authenticated),
        featured=model.featured,
        show_forecast=model.show_forecast,
        show_performance=model.show_performance,
        tagline=model.tagline,
        key_output=model.key_output,
        description=model.description,
        architecture=model.architecture,
        sparkline=model.sparkline,
        sparkline_label=model.sparkline_label,
        research_profile=model.research_profile,
        updated_at=model.updated_at,
        last_output_at=last_output_at,
    )


async def latest_forecasts(
    session: AsyncSession, model: Model, symbol: str | None
) -> list[ForecastRecord]:
    target = (symbol or model.markets[0]).upper()
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM api.v_model_forecast_latest
                WHERE model_id = :model_id AND symbol = :symbol
                ORDER BY horizon
                """
            ),
            {"model_id": model.slug, "symbol": target},
        )
    ).mappings().all()

    records: list[ForecastRecord] = []
    for r in rows:
        freshness = build_freshness(
            r["data_as_of"], r["generated_at"], stale_after_minutes=3 * 24 * 60
        )
        records.append(
            ForecastRecord(
                **freshness.model_dump(),
                model_id=r["model_id"],
                model_name=model.name,
                model_version=r["model_version"],
                symbol=r["symbol"],
                timeframe=r["timeframe"],
                horizon=r["horizon"],
                forecast_value=float(r["forecast_value"]),
                forecast_return=float(r["forecast_return"]),
                probability_up=float(r["probability_up"]),
                probability_down=float(r["probability_down"]),
                volatility=float(r["volatility"]),
                interval_level=float(r["interval_level"]),
                interval_lower=float(r["interval_lower"]),
                interval_upper=float(r["interval_upper"]),
                # A model that forecasts a distribution and calls no regime
                # leaves these null; do not coerce, or None becomes 0.
                regime=r["regime"],
                regime_probability=(
                    None
                    if r["regime_probability"] is None
                    else float(r["regime_probability"])
                ),
                risk_score=(
                    None if r["risk_score"] is None else int(r["risk_score"])
                ),
                risk_state=r["risk_state"],
                status=r["status"],
            )
        )
    return records


async def forecast_history(
    session: AsyncSession, model: Model, symbol: str | None, limit: int = 60
) -> ForecastHistory:
    """Past forecasts against what actually happened.

    Only rows whose realised value has been filled in are returned, so
    interval coverage is computed on settled outcomes only.
    """
    target = (symbol or model.markets[0]).upper()
    rows = (
        await session.execute(
            text(
                """
                SELECT data_as_of, horizon, forecast_value, interval_lower,
                       interval_upper, interval_level, actual_value
                FROM api.v_forecast_history
                WHERE model_id = :model_id AND symbol = :symbol
                  AND actual_value IS NOT NULL
                ORDER BY data_as_of DESC
                LIMIT :limit
                """
            ),
            {"model_id": model.slug, "symbol": target, "limit": limit},
        )
    ).mappings().all()

    points: list[ForecastHistoryPoint] = []
    covered = 0
    level = 0.95
    for r in rows:
        actual = float(r["actual_value"])
        predicted = float(r["forecast_value"])
        lower = float(r["interval_lower"])
        upper = float(r["interval_upper"])
        level = float(r["interval_level"])
        in_interval = lower <= actual <= upper
        covered += int(in_interval)
        points.append(
            ForecastHistoryPoint(
                forecast_at=r["data_as_of"].date().isoformat(),
                horizon=int(r["horizon"]),
                predicted=predicted,
                interval_lower=lower,
                interval_upper=upper,
                actual=actual,
                error_percent=round((predicted - actual) / actual * 100, 2)
                if actual
                else 0.0,
                in_interval=in_interval,
            )
        )

    points.reverse()
    freshness = build_freshness(
        max((r["data_as_of"] for r in rows), default=None),
        stale_after_minutes=7 * 24 * 60,
    )
    return ForecastHistory(
        **freshness.model_dump(),
        model_id=model.slug,
        symbol=target,
        interval_level=level,
        coverage=round(covered / len(points), 3) if points else 0.0,
        points=points,
    )
