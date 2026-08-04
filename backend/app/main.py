from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.redis import close_redis, get_redis
from app.db.session import engine

configure_logging()
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("starting %s (%s)", settings.app_name, settings.environment)
    yield
    await engine.dispose()
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Public API for quantpercent.com. Serves market intelligence, model "
        "output, performance reports and account endpoints. Model internals "
        "(features, parameters, trading logic) are never exposed."
    ),
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Session cookies travel cross-origin, so credentials must be allowed
    # and the origin list cannot be a wildcard
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    max_age=600,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception(
            "unhandled error",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
            },
        )
        raise
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    log.info(
        "%s %s -> %s",
        request.method,
        request.url.path,
        response.status_code,
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "status": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    """Field-level errors, shaped like the mock API the frontend was
    built against."""
    fields: dict[str, list[str]] = {}
    for err in exc.errors():
        loc = [str(p) for p in err["loc"] if p not in ("body", "query")]
        fields.setdefault(".".join(loc) or "body", []).append(err["msg"])
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "validation", "issues": fields},
    )


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz() -> JSONResponse:
    """Readiness reflects the dependencies this service cannot serve
    without — it must fail loudly rather than serve empty pages."""
    checks: dict[str, str] = {}
    healthy = True

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc.__class__.__name__}"
        healthy = False

    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        # Redis only degrades caching and rate limiting; it is not fatal
        checks["redis"] = f"degraded: {exc.__class__.__name__}"

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "unavailable", "checks": checks},
    )


app.include_router(api_router, prefix=settings.api_prefix)
