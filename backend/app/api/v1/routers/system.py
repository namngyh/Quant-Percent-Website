from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select, text

from app.core.config import settings
from app.core.deps import SessionDep
from app.db.models import Model, ModelRun
from app.schemas.models import ModelStatusReport, ModelStatusRow
from app.schemas.system import (
    DataFreshnessReport,
    FeedFreshness,
    ServiceStatus,
    SystemStatus,
)

router = APIRouter(tags=["system"])

WATCHED_FEEDS = ("VNINDEX", "VN30", "VN30F1M")


async def _feed_rows(session) -> list[FeedFreshness]:
    rows = (
        await session.execute(
            text(
                """
                SELECT symbol, data_as_of
                FROM api.v_data_freshness
                WHERE symbol = ANY(:symbols)
                """
            ),
            {"symbols": list(WATCHED_FEEDS)},
        )
    ).mappings().all()

    now = datetime.now(UTC)
    threshold = timedelta(minutes=settings.stale_after_minutes)
    feeds: list[FeedFreshness] = []
    for r in rows:
        as_of = r["data_as_of"]
        feeds.append(
            FeedFreshness(
                id=r["symbol"].lower(),
                symbol=r["symbol"],
                data_as_of=as_of,
                is_stale=(now - as_of) > threshold,
                delay_minutes=settings.market_delay_minutes,
            )
        )
    return feeds


@router.get("/status", response_model=SystemStatus)
async def status_report(session: SessionDep) -> SystemStatus:
    """Derived from real signals: an open gap in the ingestion log and a
    stalled feed both degrade the reported status."""
    open_gap = (
        await session.execute(
            text(
                """
                SELECT count(*) FROM api.v_ingestion_gaps
                WHERE reconnect_ts IS NULL
                """
            )
        )
    ).scalar_one_or_none() or 0

    feeds = await _feed_rows(session)
    stale = any(f.is_stale for f in feeds) or not feeds
    market_status = "down" if open_gap else ("degraded" if stale else "operational")

    models_healthy = (
        await session.execute(
            text("SELECT bool_and(healthy) FROM quant.model_runs")
        )
    ).scalar_one_or_none()

    return SystemStatus(
        generated_at=datetime.now(UTC),
        services=[
            ServiceStatus(
                id="market_data", name="Market Data Service", status=market_status
            ),
            ServiceStatus(
                id="model_output",
                name="Model Output Service",
                status="operational" if models_healthy is not False else "degraded",
            ),
            ServiceStatus(
                id="performance", name="Performance Service", status="operational"
            ),
            ServiceStatus(
                id="public_api", name="Public API Gateway", status="operational"
            ),
            ServiceStatus(
                id="contact", name="Contact Service", status="operational"
            ),
        ],
    )


@router.get("/data-freshness", response_model=DataFreshnessReport)
async def data_freshness(session: SessionDep) -> DataFreshnessReport:
    return DataFreshnessReport(
        generated_at=datetime.now(UTC),
        feeds=await _feed_rows(session),
    )


@router.get("/model-status", response_model=ModelStatusReport)
async def model_status(session: SessionDep) -> ModelStatusReport:
    models = (
        await session.scalars(
            select(Model).where(Model.visibility == "public").order_by(Model.slug)
        )
    ).all()
    runs = {
        r.model_id: r
        for r in (await session.scalars(select(ModelRun))).all()
    }

    rows = []
    for m in models:
        run = runs.get(m.slug)
        rows.append(
            ModelStatusRow(
                model_id=m.slug,
                status=m.status,
                last_run_at=run.last_run_at if run else None,
                # An archived model is not expected to run at all
                healthy=(run.healthy if run else m.status != "archived"),
            )
        )
    return ModelStatusReport(
        generated_at=datetime.now(UTC), models=rows
    )
