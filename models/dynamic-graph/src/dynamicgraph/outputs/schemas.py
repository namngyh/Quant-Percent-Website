"""Output schemas for the website payloads.

Pydantic models when available; otherwise plain dict builders with the same
keys. Either way, the emitted JSON matches the contract documented in the
README so a frontend can rely on it.
"""

from __future__ import annotations

from typing import Any

try:
    from pydantic import BaseModel, Field

    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    _HAS_PYDANTIC = False

    class BaseModel:  # type: ignore[no-redef]
        def __init__(self, **data: Any) -> None:
            for key, value in data.items():
                setattr(self, key, value)

        def model_dump(self, **_: Any) -> dict[str, Any]:
            return dict(vars(self))

    def Field(default: Any = None, **_: Any) -> Any:  # type: ignore[no-redef]
        return default


SCHEMA_VERSION = "1.0.0"


class ModelInfo(BaseModel):
    name: str = "DynamicGraph"
    version: str = "0.1.0"
    schema_version: str = SCHEMA_VERSION
    generated_at: str = ""
    as_of_date: str = ""
    data_source: str = "local_database"
    data_freshness_days: int = 0
    run_id: str = ""
    git_commit: str | None = None
    config_fingerprint: str = ""


class Universe(BaseModel):
    index: str = "VN30"
    node_count: int = 0
    tickers: list[str] = Field(default_factory=list)
    missing_tickers: list[str] = Field(default_factory=list)
    survivorship_bias_warning: bool = True
    universe_method: str = "static_list"


class NetworkState(BaseModel):
    label: str = "normal"
    stress_score: float = 0.0
    stress_raw: float = 0.0
    historical_percentile: float = 0.0
    change_1d: float = 0.0
    change_5d: float = 0.0
    change_20d: float = 0.0
    main_contributors: list[dict[str, Any]] = Field(default_factory=list)
    warning_flags: list[str] = Field(default_factory=list)


class StressProbability(BaseModel):
    probability: float | None = None
    calibrated: bool = False
    model_name: str | None = None
    calibration_method: str | None = None
    oos_brier_score: float | None = None
    oos_auprc: float | None = None
    sample_size: int | None = None
    last_retraining_date: str | None = None
    confidence_warning: str | None = None
    label_definition: str | None = None


class NodeRecord(BaseModel):
    """One entry in nodes.json - shaped for D3.js / Cytoscape.js."""

    id: str
    label: str
    sector: str = "UNKNOWN"
    community: int = 0
    strength: float = 0.0
    eigenvector_centrality: float = 0.0
    pagerank: float = 0.0
    betweenness_centrality: float = 0.0
    degree: float = 0.0
    risk_score: float = 0.0
    return_20d: float = 0.0
    volatility_20d: float = 0.0
    current_drawdown: float = 0.0
    role: str = "node"


class EdgeRecord(BaseModel):
    source: str
    target: str
    weight: float = 0.0
    signed_weight: float = 0.0
    absolute_weight: float = 0.0
    edge_type: str = "partial_correlation"
    window: int = 60
    stability: float | None = None
    direction: str | None = None


class CommunityRecord(BaseModel):
    community_id: int
    size: int
    members: list[str] = Field(default_factory=list)
    dominant_sector: str | None = None
    sector_composition: dict[str, int] = Field(default_factory=dict)
    sector_purity: float | None = None
    cohesion: float | None = None
    stability_nmi: float | None = None


class ModelQuality(BaseModel):
    evaluation_type: str = "walk_forward_oos"
    brier_score: float | None = None
    brier_skill_score: float | None = None
    auroc: float | None = None
    auprc: float | None = None
    mcc: float | None = None
    recall_stress: float | None = None
    precision_stress: float | None = None
    false_alarms_per_year: float | None = None
    calibration_error: float | None = None
    calibration_slope: float | None = None
    n_oos_observations: int | None = None
    n_folds: int | None = None
    graph_incremental_value: str | None = None


def empty_payload() -> dict[str, Any]:
    """The canonical top-level structure of `latest_dynamicgraph.json`."""
    return {
        "model": ModelInfo().model_dump(),
        "universe": Universe().model_dump(),
        "network_state": NetworkState().model_dump(),
        "stress_probabilities": {},
        "graph_metrics": {},
        "leading_influence_nodes": [],
        "risk_transmitters": [],
        "risk_receivers": [],
        "vulnerable_nodes": [],
        "communities": [],
        "top_edges": [],
        "model_quality": ModelQuality().model_dump(),
        "warnings": [],
        "disclaimers": [],
    }


REQUIRED_TOP_LEVEL_KEYS = tuple(empty_payload().keys())


def validate_payload(payload: dict[str, Any]) -> list[str]:
    """Return a list of schema problems (empty means valid)."""
    problems: list[str] = []
    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in payload:
            problems.append(f"missing top-level key `{key}`")

    model = payload.get("model", {})
    for key in ("name", "version", "generated_at", "as_of_date"):
        if not model.get(key):
            problems.append(f"model.{key} is empty")

    for horizon, entry in (payload.get("stress_probabilities") or {}).items():
        probability = entry.get("probability")
        if probability is not None and not (0.0 <= float(probability) <= 1.0):
            problems.append(f"stress_probabilities.{horizon}.probability outside [0, 1]")

    state = payload.get("network_state", {})
    score = state.get("stress_score")
    if score is not None and not (0.0 <= float(score) <= 100.0):
        problems.append("network_state.stress_score outside [0, 100]")

    for node in payload.get("leading_influence_nodes", []):
        if node.get("role") not in (None, "high_influence_node", "node"):
            problems.append(
                f"leading_influence_nodes carries role `{node.get('role')}`; undirected centrality "
                "may not be labelled as a transmitter"
            )
    return problems
