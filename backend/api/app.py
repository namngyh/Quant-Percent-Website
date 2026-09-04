"""FastAPI application: JSON API plus the static frontend."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.api import (
    routes_data,
    routes_indicators,
    routes_market,
    routes_notify,
    routes_paper,
    routes_plugins,
    routes_stats,
    routes_strategy,
    routes_stream,
    routes_validation,
)
from backend.data import market_vn
from backend.paper.manager import manager as paper_manager
from backend.data import store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("qp")

FRONTEND_DIR = settings.project_root / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.get_connection()  # create the schema before the first request
    routes_stream.hub.start_plugin_watcher()

    # Paper sessions consume the same candle feed as the browser, but through
    # their own subscription: closing the last tab must not stop a session that
    # is still trading.
    paper_manager.attach(routes_stream.hub.streams, routes_stream.hub.broadcast)
    routes_stream.hub.streams.add_listener(paper_manager.on_candle)
    await paper_manager.restore()

    log.info("QP-TRACKING ready at http://%s:%s", settings.server.host, settings.server.port)
    yield

    await paper_manager.close()
    await routes_stream.hub.close()
    market_vn.close_pool()
    store.close_connection()


def create_app() -> FastAPI:
    app = FastAPI(
        title="QP-TRACKING",
        description="Indicator research platform — chart, test and tune indicators on BTC data.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(routes_data.router)
    app.include_router(routes_indicators.router)
    app.include_router(routes_strategy.router)
    app.include_router(routes_stream.router)
    app.include_router(routes_paper.router)
    app.include_router(routes_plugins.router)
    app.include_router(routes_market.router)
    app.include_router(routes_validation.router)
    app.include_router(routes_stats.router)
    app.include_router(routes_notify.router)

    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

        @app.middleware("http")
        async def no_cache_static(request, call_next):
            """Serve frontend files uncached.

            This is a local research tool that you edit while it runs; a stale
            cached stylesheet or script is pure friction, and there is no CDN
            or bandwidth cost to weigh against it.
            """
            response = await call_next(request)
            if request.url.path.startswith("/static") or request.url.path == "/":
                response.headers["Cache-Control"] = "no-store, must-revalidate"
            return response

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

    return app


app = create_app()
