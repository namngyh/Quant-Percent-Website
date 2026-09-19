"""Typed configuration objects and YAML loading with `extends:` inheritance.

Pydantic is used when available (it is a declared core dependency) but the
module degrades to plain dataclass-like validation if it is missing, so that
`discover-data` still works on a bare interpreter.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Iterable

import yaml

try:  # pragma: no cover - exercised implicitly
    from pydantic import BaseModel, ConfigDict, Field

    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    _HAS_PYDANTIC = False

    class BaseModel:  # type: ignore[no-redef]
        """Minimal stand-in used only when pydantic is unavailable."""

        def __init__(self, **data: Any) -> None:
            annotations: dict[str, Any] = {}
            for cls in reversed(type(self).mro()):
                annotations.update(getattr(cls, "__annotations__", {}))
            unknown = sorted(set(data) - set(annotations))
            if unknown:
                raise ValueError(f"Unknown configuration field(s): {unknown}")
            for key in annotations:
                if hasattr(type(self), key):
                    setattr(self, key, copy.deepcopy(getattr(type(self), key)))
            for key, value in data.items():
                setattr(self, key, value)

        def model_dump(self) -> dict[str, Any]:
            return {k: v for k, v in vars(self).items() if not k.startswith("_")}

    def Field(  # type: ignore[no-redef]
        default: Any = None, *, default_factory: Any = None, **_: Any
    ) -> Any:
        return default_factory() if default_factory is not None else default

    ConfigDict = dict  # type: ignore[assignment,misc]


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


# ---------------------------------------------------------------------------
# Section models
# ---------------------------------------------------------------------------
class _Section(BaseModel):
    if _HAS_PYDANTIC:
        model_config = ConfigDict(extra="forbid")

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class ProjectConfig(_Section):
    name: str = "DynamicGraph"
    version: str = "0.1.0"
    seed: int = 42
    mode: str = "structure"


class ModulesConfig(_Section):
    """Top-level research modes; structure analysis is the safe default."""

    structure_analysis: bool = True
    stress_forecasting: bool = False
    node_return_ranking: bool = False
    allocation_validation: bool = False
    scenario_analysis: bool = False


class DataConfig(_Section):
    database_path: str | None = None
    database_url_env: str = "DYNAMICGRAPH_DATABASE_URL"
    backend: str = "auto"
    table: str | None = None
    column_map: dict[str, str] = Field(default_factory=dict)

    index_symbol: str = "VN30"
    index_source_symbol: str | None = None
    universe: str = "VN30"
    universe_method: str = "static_list"
    universe_size: int = 30
    universe_file: str = "config/vn30_universe.csv"
    liquidity_lookback_days: int = 120
    universe_rebalance_days: int = 63
    sector_map_file: str = "config/sector_map.csv"

    start_date: str | None = None
    end_date: str | None = None

    allow_unadjusted_price: bool = False
    minimum_history_days: int = 252
    max_missing_ratio_per_window: float = 0.10
    max_forward_fill_days: int = 1
    stale_price_max_run: int = 5
    jump_sigma_threshold: float = 10.0
    read_only: bool = True


class FeaturesConfig(_Section):
    return_windows: list[int] = Field(default_factory=lambda: [1, 5, 10, 20, 60])
    volatility_windows: list[int] = Field(default_factory=lambda: [5, 20, 60])
    beta_windows: list[int] = Field(default_factory=lambda: [20, 60])
    drawdown_windows: list[int] = Field(default_factory=lambda: [20, 60, 252])
    ewma_lambda: float = 0.94
    var_quantile: float = 0.05
    residualize_market: bool = True
    residualize_sector: bool = False
    residual_window: int = 60
    robust_cross_sectional_scaling: bool = True
    liquidity_features: bool = True
    winsorize_z: float = 5.0


class GraphConfig(_Section):
    windows: list[int] = Field(default_factory=lambda: [20, 60, 120, 252])
    core_window: int = 60
    core_layer: str = "partial_correlation"
    return_type: str = "residual"
    covariance_estimator: str = "ledoit_wolf"
    graphical_lasso_alpha: float = 0.02
    graphical_lasso_alpha_grid: list[float] = Field(
        default_factory=lambda: [0.002, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20]
    )
    graphical_lasso_alpha_selection: str = "fixed"
    max_graph_density: float = 0.60
    signed_graph: bool = True
    use_absolute_weight_for_centrality: bool = True

    edge_filter_method: str = "quantile"
    absolute_threshold: float = 0.10
    top_edge_quantile: float = 0.25
    bootstrap_iterations: int = 100
    block_length: Any = 10
    edge_stability_threshold: float = 0.60

    snapshot_stride: int = 1
    secondary_snapshot_stride: int = 5
    build_raw_and_residual: bool = True
    build_correlation_and_partial: bool = True

    enable_lead_lag: bool = True
    lead_lag_days: list[int] = Field(default_factory=lambda: [1, 2, 3, 5])
    lead_lag_window: int = 120
    lead_lag_threshold: float = 1.25
    lead_lag_min_abs_corr: float = 0.05
    lead_lag_fdr_alpha: float = 0.10

    enable_spillover: bool = False
    spillover_window: int = 120
    spillover_horizon: int = 10
    spillover_lags: int = 2
    spillover_estimator: str = "ridge"
    spillover_ridge_alpha: float = 1.0
    spillover_pca_components: int = 5


class NetworkConfig(_Section):
    compute_betweenness: bool = True
    compute_closeness: bool = True
    community_method: str = "auto"
    community_resolution: float = 1.0
    pagerank_alpha: float = 0.85
    neighbor_risk_feature: str = "volatility_20d"


class StressScoreConfig(_Section):
    metrics: list[str] = Field(default_factory=list)
    signs: dict[str, int] = Field(default_factory=dict)
    weights: Any = "equal"
    clip_z: float = 3.0
    redundancy_corr_threshold: float = 0.95
    state_percentiles: list[float] = Field(default_factory=lambda: [0.50, 0.80, 0.95])
    state_labels: list[str] = Field(
        default_factory=lambda: ["low_connectivity", "normal", "elevated", "high_stress"]
    )


class TargetsConfig(_Section):
    horizons: list[int] = Field(default_factory=lambda: [5, 10, 20, 40])
    stress_definition: str = "both"
    primary_stress_definition: str = "quantile"
    stress_quantile: float = 0.10
    absolute_drawdown_thresholds: dict[int, float] = Field(default_factory=dict)
    volatility_quantile: float = 0.90
    node_stress_quantile: float = 0.10
    node_absolute_drawdown_thresholds: dict[int, float] = Field(default_factory=dict)


class TrainingConfig(_Section):
    split_method: str = "purged_walk_forward"
    initial_train_days: int = 756
    validation_days: int = 126
    test_days: int = 63
    expanding_window: bool = True
    purge_days: int = 40
    embargo_days: int = 5
    min_positive_train: int = 15
    max_features: int = 60
    feature_redundancy_threshold: float = 0.95
    optuna_trials_fast: int = 20
    optuna_trials_full: int = 100
    enable_tuning: bool = False
    tuning_objective: str = "brier"
    random_seed: int = 42
    n_jobs: int = 1


class ModelsConfig(_Section):
    run_naive: bool = True
    run_logistic: bool = True
    run_random_forest: bool = True
    run_hist_gradient_boosting: bool = True
    run_ebm_if_available: bool = True
    run_xgboost_if_available: bool = True
    run_temporal_gnn: bool = False
    calibration_method: str = "isotonic"
    class_weight: str | None = "balanced"
    feature_sets: list[str] = Field(default_factory=lambda: ["market", "graph", "combined"])


class GNNConfig(_Section):
    enabled: bool = False
    sequence_lengths: list[int] = Field(default_factory=lambda: [10, 20, 60])
    sequence_length: int = 20
    hidden_dimensions: list[int] = Field(default_factory=lambda: [16, 32, 64])
    hidden_dimension: int = 32
    graph_layers: list[int] = Field(default_factory=lambda: [1, 2])
    n_graph_layers: int = 1
    temporal_model: str = "GRU"
    dropout_range: list[float] = Field(default_factory=lambda: [0.10, 0.40])
    dropout: float = 0.25
    weight_decay: float = 1e-4
    learning_rate: float = 1e-3
    max_epochs: int = 200
    batch_size: int = 32
    early_stopping_patience: int = 20
    gradient_clip_norm: float = 1.0
    loss: str = "focal"
    focal_gamma: float = 2.0
    device: str = "auto"


class EvaluationConfig(_Section):
    bootstrap_iterations: int = 500
    bootstrap_block_length: int = 20
    calibration_bins: int = 10
    event_min_gap_days: int = 20
    decision_threshold_objective: str = "f1"
    fixed_threshold: float = 0.5


class AllocationConfig(_Section):
    """Capital-allocation experiment.

    `estimation_window` defaults to the core graph window so the covariance the
    allocator sees is the same one the network layer describes; setting it to 0
    inherits `graph.core_window` explicitly.
    """

    enabled: bool = False
    estimation_window: int = 0
    rebalance_days: int = 20
    max_weight: float = 0.20
    cost_bps_per_side: float = 15.0
    min_assets: int = 10
    rolling_volatility_window: int = 126
    missing_return_policy: str = "zero"
    execution_lag_sessions: int = 1
    execution_convention: str = "next_close"


class AblationConfig(_Section):
    enabled: bool = True
    variants: list[str] = Field(default_factory=list)


class OutputConfig(_Section):
    artifacts_dir: str = "artifacts"
    export_json: bool = True
    export_csv: bool = True
    export_parquet: bool = True
    create_figures: bool = True
    create_html_report: bool = False
    top_n_nodes: int = 10
    top_n_edges: int = 60
    history_export_days: int = 750


class LoggingConfig(_Section):
    level: str = "INFO"
    file: str | None = "artifacts/reports/dynamicgraph.log"
    rich: bool = True


class DynamicGraphConfig(_Section):
    """Root configuration object."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    modules: ModulesConfig = Field(default_factory=ModulesConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    stress_score: StressScoreConfig = Field(default_factory=StressScoreConfig)
    targets: TargetsConfig = Field(default_factory=TargetsConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    gnn: GNNConfig = Field(default_factory=GNNConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    allocation: AllocationConfig = Field(default_factory=AllocationConfig)
    ablation: AblationConfig = Field(default_factory=AblationConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Populated at load time; never serialised into artifacts verbatim.
    _source_files: list[str] = []

    # -- convenience ------------------------------------------------------
    @property
    def artifacts_dir(self) -> Path:
        env = os.environ.get("DYNAMICGRAPH_ARTIFACTS_DIR")
        root = Path(env) if env else Path(self.output.artifacts_dir)
        if not root.is_absolute():
            root = REPO_ROOT / root
        return root

    def artifact_path(self, *parts: str) -> Path:
        path = self.artifacts_dir.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_path(self, value: str | None) -> Path | None:
        if not value:
            return None
        path = Path(value)
        return path if path.is_absolute() else REPO_ROOT / path

    def to_dict(self) -> dict[str, Any]:
        if _HAS_PYDANTIC:
            return self.model_dump(mode="json")  # type: ignore[call-arg]
        return {k: (v.model_dump() if isinstance(v, _Section) else v) for k, v in vars(self).items()}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _read_yaml_chain(path: Path, seen: set[Path] | None = None) -> dict[str, Any]:
    """Read a YAML file, resolving a chain of `extends:` parents first."""
    seen = seen or set()
    path = path.resolve()
    if path in seen:
        raise ValueError(f"Circular `extends` chain involving {path}")
    seen.add(path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config file {path} must contain a YAML mapping")

    parent_name = raw.pop("extends", None)
    if parent_name:
        parent_path = Path(parent_name)
        if not parent_path.is_absolute():
            parent_path = path.parent / parent_path
        parent = _read_yaml_chain(parent_path, seen)
        return _deep_merge(parent, raw)
    return raw


def _coerce_int_keys(mapping: Any) -> Any:
    """YAML mapping keys such as `5:` load as int already, but JSON round-trips
    turn them into strings. Normalise horizon-keyed dicts to int keys."""
    if not isinstance(mapping, dict):
        return mapping
    out: dict[Any, Any] = {}
    for key, value in mapping.items():
        try:
            out[int(key)] = value
        except (TypeError, ValueError):
            out[key] = value
    return out


_SECTION_TYPES: dict[str, type] = {
    "project": ProjectConfig,
    "modules": ModulesConfig,
    "data": DataConfig,
    "features": FeaturesConfig,
    "graph": GraphConfig,
    "network": NetworkConfig,
    "stress_score": StressScoreConfig,
    "targets": TargetsConfig,
    "training": TrainingConfig,
    "models": ModelsConfig,
    "gnn": GNNConfig,
    "evaluation": EvaluationConfig,
    "allocation": AllocationConfig,
    "ablation": AblationConfig,
    "output": OutputConfig,
    "logging": LoggingConfig,
}


def load_config(
    path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> DynamicGraphConfig:
    """Load configuration.

    Resolution order when `path` is None:
        config/local.yaml -> config/default.yaml
    """
    if path is None:
        local = CONFIG_DIR / "local.yaml"
        path = local if local.exists() else CONFIG_DIR / "default.yaml"
    path = Path(path)
    if not path.is_absolute():
        candidate = REPO_ROOT / path
        path = candidate if candidate.exists() else CONFIG_DIR / path.name

    raw = _read_yaml_chain(path)
    if overrides:
        raw = _deep_merge(raw, overrides)

    # Environment overrides (never printed, never persisted).
    data_raw = raw.setdefault("data", {})
    env_var = data_raw.get("database_url_env", "DYNAMICGRAPH_DATABASE_URL")
    if not os.environ.get(env_var):
        # Task Scheduler starts with a bare environment; `.env` is the fallback.
        from dynamicgraph.dotenv import load_env_file

        load_env_file(REPO_ROOT)
    env_value = os.environ.get(env_var)
    if env_value:
        data_raw["database_path"] = env_value
    log_level = os.environ.get("DYNAMICGRAPH_LOG_LEVEL")
    if log_level:
        raw.setdefault("logging", {})["level"] = log_level

    targets_raw = raw.setdefault("targets", {})
    for key in ("absolute_drawdown_thresholds", "node_absolute_drawdown_thresholds"):
        if key in targets_raw:
            targets_raw[key] = _coerce_int_keys(targets_raw[key])

    unknown_sections = sorted(set(raw) - set(_SECTION_TYPES))
    if unknown_sections:
        raise ValueError(f"Unknown configuration section(s): {unknown_sections}")

    sections: dict[str, Any] = {}
    for name, model in _SECTION_TYPES.items():
        sections[name] = model(**(raw.get(name) or {}))

    config = DynamicGraphConfig(**sections)
    _apply_run_mode(config)
    object.__setattr__(config, "_source_files", [str(path)])
    return config


def _apply_run_mode(config: DynamicGraphConfig) -> None:
    """Resolve the named mode into explicit module switches."""
    mode = str(config.project.mode)
    if mode == "structure":
        return
    if mode == "forecast_experimental":
        config.modules.structure_analysis = True
        config.modules.stress_forecasting = True
        config.modules.node_return_ranking = True
    elif mode == "allocation_validation":
        config.modules.structure_analysis = True
        config.modules.allocation_validation = True
        config.allocation.enabled = True
    elif mode == "scenario_analysis":
        config.modules.structure_analysis = True
        config.modules.scenario_analysis = True
        config.graph.enable_spillover = True
    elif mode in {"fast", "full"}:
        # Backward-compatible research profiles; their YAML files retain the
        # historical forecasting experiment but never enable the GNN implicitly.
        config.modules.stress_forecasting = True
        config.modules.node_return_ranking = True
        config.modules.allocation_validation = bool(config.allocation.enabled)
    else:
        raise ValueError(
            "Unknown project.mode; expected structure, forecast_experimental, "
            "allocation_validation, scenario_analysis, fast, or full."
        )


def config_fingerprint(config: DynamicGraphConfig) -> str:
    """Stable hash of the effective configuration, for reproducibility records.

    Secrets are excluded: `database_path` is replaced by a hash of itself so a
    connection string can never leak into an artifact.
    """
    import hashlib
    import json

    payload = config.to_dict()
    data = payload.get("data", {})
    if data.get("database_path"):
        digest = hashlib.sha256(str(data["database_path"]).encode()).hexdigest()[:16]
        data["database_path"] = f"<redacted:{digest}>"
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def redact(value: str | None) -> str:
    """Redact anything that might carry credentials before logging it."""
    if not value:
        return ""
    if "://" in value and "@" in value:
        scheme, _, rest = value.partition("://")
        _, _, host = rest.rpartition("@")
        return f"{scheme}://***@{host}"
    return value


def iter_section_names() -> Iterable[str]:
    return _SECTION_TYPES.keys()
