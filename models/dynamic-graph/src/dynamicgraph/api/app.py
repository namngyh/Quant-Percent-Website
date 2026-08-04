"""FastAPI application factory.

    uvicorn dynamicgraph.api.app:app --host 0.0.0.0 --port 8000

Read-only by construction: every handler serves a file from `artifacts/`. There
is no write path, no database connection and no way for an HTTP request to
trigger training.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dynamicgraph.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False
    FastAPI = object  # type: ignore[assignment,misc]


DESCRIPTION = """
Read-only API for **DynamicGraph**, a dynamic financial network model for the
VN30 index and its constituents.

The service exposes network structure, the Network Stress Score and calibrated
stress probabilities. It never triggers training and never touches the source
database.

**Interpretation notes**

* Edges are statistical associations (correlation / partial correlation), not
  causal links between companies.
* Centrality identifies structural position, not expected return.
* Nodes are labelled `high_influence_node` unless a directed layer exists; only
  then do `directed_risk_transmitter` / `directed_risk_receiver` appear.
* Probabilities are out-of-sample calibrated estimates with material
  uncertainty, and are not investment advice.
"""


def create_app(artifacts_dir: str | Path | None = None, version: str = "0.1.0") -> Any:
    if not _HAS_FASTAPI:
        raise ImportError(
            "FastAPI is not installed. Install with `pip install -e .[api]`. "
            "The core pipeline does not require it."
        )

    from dynamicgraph.api.models import (
        CommunityResponse,
        EdgeResponse,
        HealthResponse,
        MetricsResponse,
        ModelStatusResponse,
        NodeResponse,
        StressResponse,
        TickerDetailResponse,
    )
    from dynamicgraph.api.routes import (
        ArtifactStore,
        model_status,
        stress_history,
        stress_latest,
        ticker_detail,
    )

    setup_logging("INFO", None, False)

    if artifacts_dir is None:
        env = os.environ.get("DYNAMICGRAPH_ARTIFACTS_DIR")
        if env:
            artifacts_dir = Path(env)
        else:
            from dynamicgraph.config import REPO_ROOT

            artifacts_dir = REPO_ROOT / "artifacts"
    store = ArtifactStore(Path(artifacts_dir))

    app = FastAPI(
        title="DynamicGraph API",
        description=DESCRIPTION,
        version=version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Origins are supplied by the deployment, never hard-coded to localhost.
    origins = [o.strip() for o in os.environ.get("DYNAMICGRAPH_CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    def _require_latest() -> dict[str, Any]:
        latest = store.latest()
        if latest is None:
            raise HTTPException(
                status_code=503,
                detail="No DynamicGraph artifacts found. Run `python -m dynamicgraph.cli run-all`.",
            )
        return latest

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> dict[str, Any]:
        """Liveness probe plus whether artifacts are present."""
        return {
            "status": "ok",
            "version": version,
            "artifacts_available": store.available(),
            "artifacts_dir": str(store.artifacts_dir),
        }

    @app.get("/model/status", response_model=ModelStatusResponse, tags=["system"])
    def status() -> dict[str, Any]:
        """Model version, as-of date, data freshness and OOS quality summary."""
        return model_status(store, version)

    @app.get("/network/latest", tags=["network"])
    def network_latest() -> dict[str, Any]:
        """The complete latest state document."""
        return _require_latest()

    @app.get("/network/nodes", response_model=list[NodeResponse], tags=["network"])
    def network_nodes(
        sector: str | None = Query(None, description="Filter by sector."),
        community: int | None = Query(None, description="Filter by community id."),
    ) -> list[dict[str, Any]]:
        """Node records shaped for D3.js / Cytoscape.js."""
        nodes = store.nodes()
        if not nodes:
            raise HTTPException(status_code=503, detail="No node artifacts found.")
        if sector:
            nodes = [n for n in nodes if str(n.get("sector", "")).lower() == sector.lower()]
        if community is not None:
            nodes = [n for n in nodes if n.get("community") == community]
        return nodes

    @app.get("/network/edges", response_model=list[EdgeResponse], tags=["network"])
    def network_edges(
        min_weight: float = Query(0.0, ge=0.0, le=1.0),
        edge_type: str | None = Query(None),
        limit: int = Query(1000, ge=1, le=10000),
    ) -> list[dict[str, Any]]:
        """Edge records; filter by absolute weight or layer."""
        edges = store.edges()
        if not edges:
            raise HTTPException(status_code=503, detail="No edge artifacts found.")
        if min_weight > 0:
            edges = [e for e in edges if abs(float(e.get("absolute_weight") or 0.0)) >= min_weight]
        if edge_type:
            edges = [e for e in edges if e.get("edge_type") == edge_type]
        return edges[:limit]

    @app.get("/network/communities", response_model=list[CommunityResponse], tags=["network"])
    def network_communities() -> list[dict[str, Any]]:
        """Detected communities with their sector composition."""
        return store.communities()

    @app.get("/network/history", tags=["network"])
    def network_history(limit: int = Query(750, ge=1, le=5000)) -> list[dict[str, Any]]:
        """Historical network metrics and stress score."""
        return store.network_history()[-limit:]

    @app.get("/stress/latest", response_model=StressResponse, tags=["stress"])
    def stress_now() -> dict[str, Any]:
        """Current network state, stress score and calibrated probabilities."""
        _require_latest()
        return stress_latest(store)

    @app.get("/stress/history", tags=["stress"])
    def stress_past(limit: int = Query(750, ge=1, le=5000)) -> list[dict[str, Any]]:
        """Network Stress Score history."""
        return stress_history(store, limit)

    @app.get("/nodes/{ticker}", response_model=TickerDetailResponse, tags=["network"])
    def node_detail(ticker: str) -> dict[str, Any]:
        """One ticker: its node record, strongest neighbours and network role."""
        detail = ticker_detail(store, ticker)
        if not detail["found"]:
            raise HTTPException(status_code=404, detail=f"Ticker `{ticker}` is not in the network.")
        return detail

    @app.get("/metrics/oos", response_model=MetricsResponse, tags=["evaluation"])
    def metrics_oos() -> dict[str, Any]:
        """Out-of-sample metrics, paired comparisons and the incremental-value verdict."""
        summary = store.run_summary()
        return {
            "evaluation_type": "walk_forward_oos",
            "metrics": store.oos_metrics(),
            "comparisons": store.comparisons(),
            "verdict": summary.get("verdict", {}),
        }

    logger.info("DynamicGraph API ready. Artifacts: %s", store.artifacts_dir)
    return app


app = None
if _HAS_FASTAPI:  # pragma: no cover - import-time convenience for uvicorn
    try:
        app = create_app()
    except Exception as exc:
        logger.warning("Deferred API creation: %s", exc)
