"""Response models for the read-only API (OpenAPI schema generation)."""

from __future__ import annotations

from typing import Any

try:
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover
    class BaseModel:  # type: ignore[no-redef]
        pass

    def Field(default: Any = None, **_: Any) -> Any:  # type: ignore[no-redef]
        return default


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    artifacts_available: bool = False
    artifacts_dir: str = ""


class ModelStatusResponse(BaseModel):
    model_name: str = "DynamicGraph"
    version: str = ""
    as_of_date: str | None = None
    generated_at: str | None = None
    data_freshness_days: int | None = None
    run_id: str | None = None
    git_commit: str | None = None
    evaluation_type: str | None = None
    graph_incremental_value: str | None = None
    warnings: list[str] = Field(default_factory=list)


class NodeResponse(BaseModel):
    id: str
    label: str
    sector: str = "UNKNOWN"
    community: int = 0
    strength: float = 0.0
    eigenvector_centrality: float = 0.0
    pagerank: float = 0.0
    risk_score: float = 0.0
    return_20d: float = 0.0
    volatility_20d: float = 0.0


class EdgeResponse(BaseModel):
    source: str
    target: str
    weight: float = 0.0
    signed_weight: float = 0.0
    absolute_weight: float = 0.0
    edge_type: str = "partial_correlation"
    window: int = 60
    stability: float | None = None
    direction: str | None = None


class CommunityResponse(BaseModel):
    community_id: int
    size: int
    members: list[str] = Field(default_factory=list)
    dominant_sector: str | None = None
    cohesion: float | None = None


class StressResponse(BaseModel):
    as_of_date: str | None = None
    network_state: str | None = None
    stress_score: float | None = None
    historical_percentile: float | None = None
    change_1d: float | None = None
    change_5d: float | None = None
    change_20d: float | None = None
    probabilities: dict[str, Any] = Field(default_factory=dict)
    main_contributors: list[dict[str, Any]] = Field(default_factory=list)
    disclaimers: list[str] = Field(default_factory=list)


class TickerDetailResponse(BaseModel):
    ticker: str
    found: bool = True
    node: dict[str, Any] = Field(default_factory=dict)
    neighbours: list[dict[str, Any]] = Field(default_factory=list)
    role: str | None = None


class MetricsResponse(BaseModel):
    evaluation_type: str = "walk_forward_oos"
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    comparisons: list[dict[str, Any]] = Field(default_factory=list)
    verdict: dict[str, Any] = Field(default_factory=dict)
