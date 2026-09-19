"""End-to-end pipeline stages.

Each stage is independently callable from the CLI and caches its artifacts, so
`run-all` can resume rather than recompute. Stage order mirrors the project
phases: data -> features -> graphs -> network -> predictive -> directed ->
GNN -> website.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.config import DynamicGraphConfig
from dynamicgraph.logging_config import get_logger
from dynamicgraph.training.reproducibility import ReproducibilityRecord

logger = get_logger(__name__)


@dataclass
class PipelineState:
    """Everything produced so far, threaded through the stages."""

    config: DynamicGraphConfig
    bundle: Any = None
    node_features: Any = None
    market_features: pd.DataFrame | None = None
    targets: Any = None
    series_by_key: dict[str, Any] = field(default_factory=dict)
    build_configs: dict[str, Any] = field(default_factory=dict)
    correlations_by_key: dict[str, dict] = field(default_factory=dict)
    metrics_by_key: dict[str, pd.DataFrame] = field(default_factory=dict)
    communities_by_key: dict[str, dict] = field(default_factory=dict)
    node_metric_history: pd.DataFrame | None = None
    stress_model: Any = None
    stress_scores: pd.DataFrame | None = None
    #: Network-state boundaries estimated on training folds only. Frozen for the
    #: online tier, which must classify against these and never re-derive them.
    stress_state_cutoffs: list[float] = field(default_factory=list)
    stress_state_labels: list[str] = field(default_factory=list)
    folds: list = field(default_factory=list)
    experiment: Any = None
    verdict: dict[str, Any] = field(default_factory=dict)
    node_ranking: dict[str, Any] = field(default_factory=dict)
    node_ranking_summary: pd.DataFrame | None = None
    node_ranking_verdict: dict[str, Any] = field(default_factory=dict)
    ablation: pd.DataFrame | None = None
    graph_validation: dict[str, pd.DataFrame] = field(default_factory=dict)
    market_structure_state: pd.DataFrame | None = None
    node_roles: pd.DataFrame | None = None
    community_state: pd.DataFrame | None = None
    structural_breaks: pd.DataFrame | None = None
    graph_robustness: pd.DataFrame | None = None
    scenario_report: pd.DataFrame | None = None
    fitted_graph_spec: Any = None
    allocation: dict[str, Any] | None = None
    allocation_verdict: dict[str, Any] = field(default_factory=dict)
    directed_snapshots: list = field(default_factory=list)
    spillover_snapshots: list = field(default_factory=list)
    gnn_result: dict[str, Any] | None = None
    record: ReproducibilityRecord | None = None
    assumptions: list[str] = field(default_factory=list)
    skipped_modules: list[str] = field(default_factory=list)

    @property
    def core_key(self) -> str:
        graph = self.config.graph
        return f"{graph.core_layer}__{graph.return_type}__w{graph.core_window}"


# ---------------------------------------------------------------------------
# Stage 1 - data
# ---------------------------------------------------------------------------
def stage_data(state: PipelineState, force: bool = False) -> PipelineState:
    from dynamicgraph.data.loader import load_panel

    logger.info("=== Stage: data ===")
    state.bundle = load_panel(state.config, force=force)
    state.assumptions += list(state.bundle.source_metadata.get("assumptions", []))
    state.record = ReproducibilityRecord.build(
        state.config,
        data_fingerprint=state.bundle.fingerprint,
        date_min=str(state.bundle.panel["date"].min().date()),
        date_max=str(state.bundle.panel["date"].max().date()),
        n_tickers=int(state.bundle.panel["ticker"].nunique()),
    )
    return state


# ---------------------------------------------------------------------------
# Stage 2 - features and targets
# ---------------------------------------------------------------------------
def stage_features(state: PipelineState, force: bool = False) -> PipelineState:
    from dynamicgraph.features.market_features import build_market_features
    from dynamicgraph.features.node_features import build_node_features
    from dynamicgraph.features.targets import build_targets

    logger.info("=== Stage: features ===")
    bundle = state.bundle
    state.node_features = build_node_features(
        bundle.panel, state.config, bundle.index_ticker, bundle.sectors()
    )
    state.assumptions += list(state.node_features.assumptions)
    state.market_features = build_market_features(
        bundle.panel, state.config, bundle.index_ticker, state.node_features.returns_raw
    )
    state.targets = build_targets(bundle.panel, state.config, bundle.index_ticker)

    processed = state.config.artifacts_dir / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    try:
        state.market_features.to_parquet(processed / "market_features.parquet")
        state.targets.forward.to_parquet(processed / "targets_forward.parquet")
        state.node_features.to_long().to_parquet(processed / "node_features_long.parquet", index=False)
    except Exception as exc:
        logger.warning("Could not cache features to parquet (%s); continuing.", exc)
    return state


# ---------------------------------------------------------------------------
# Stage 3 - graphs
# ---------------------------------------------------------------------------
def stage_graphs(state: PipelineState, force: bool = False, resume: bool = False) -> PipelineState:
    from dynamicgraph.graphs.base import SnapshotSeries
    from dynamicgraph.graphs.correlation import correlation_matrix
    from dynamicgraph.graphs.graphical_lasso import select_alpha
    from dynamicgraph.graphs.snapshots import (
        SnapshotBuildConfig,
        training_windows,
    )
    from dynamicgraph.graphs.specification import FittedGraphSpecification
    from dynamicgraph.online.incremental import extend_snapshot_series
    from dynamicgraph.training.splits import folds_from_config

    logger.info("=== Stage: graphs ===")
    config = state.config
    graph = config.graph
    node_features = state.node_features

    returns_by_type: dict[str, pd.DataFrame] = {"raw": node_features.returns_raw}
    if node_features.returns_residual is not None:
        returns_by_type["residual"] = node_features.returns_residual

    # Folds are needed before graphs so that alpha selection sees training data only.
    index = state.market_features.index
    try:
        state.folds = folds_from_config(index, config)
    except ValueError as exc:
        logger.warning("Walk-forward folds unavailable (%s); using the first 60%% as training.", exc)
        state.folds = []

    if state.folds:
        train_end = state.folds[0].train_dates.max()
    else:
        train_end = index[int(0.6 * len(index))]
    logger.info("Training period for all fitted graph choices ends %s.", train_end.date())

    alpha = float(graph.graphical_lasso_alpha)
    alpha_diagnostics = pd.DataFrame()
    if str(graph.graphical_lasso_alpha_selection) != "fixed":
        base_returns = returns_by_type.get(graph.return_type, returns_by_type["raw"])
        try:
            blocks = training_windows(base_returns, int(graph.core_window), train_end, n_windows=10)
            alpha, alpha_diagnostics = select_alpha(
                blocks,
                graph.graphical_lasso_alpha_grid,
                method=str(graph.graphical_lasso_alpha_selection),
                max_density=float(graph.max_graph_density),
            )
            if not alpha_diagnostics.empty:
                alpha_diagnostics.to_csv(
                    config.artifact_path("metrics", "graphical_lasso_alpha_selection.csv"), index=False
                )
            state.assumptions.append(
                f"Graphical-lasso alpha={alpha:.4g} selected by `{graph.graphical_lasso_alpha_selection}` "
                f"on training data ending {train_end.date()}; frozen for all later periods."
            )
        except Exception as exc:
            logger.warning("Alpha selection failed (%s); using the configured value %.4g.", exc, alpha)

    first_fold = state.folds[0] if state.folds else None
    training_start = (
        first_fold.train_dates.min() if first_fold is not None else index.min()
    )
    validation_start = (
        first_fold.validation_dates.min() if first_fold is not None else None
    )
    validation_end = (
        first_fold.validation_dates.max() if first_fold is not None else None
    )
    state.fitted_graph_spec = FittedGraphSpecification(
        selected_alpha=alpha,
        selection_method=str(graph.graphical_lasso_alpha_selection),
        estimator="graphical_lasso_on_correlation",
        training_start=str(pd.Timestamp(training_start).date()),
        training_end=str(pd.Timestamp(train_end).date()),
        validation_start=(
            str(pd.Timestamp(validation_start).date())
            if validation_start is not None
            else None
        ),
        validation_end=(
            str(pd.Timestamp(validation_end).date())
            if validation_end is not None
            else None
        ),
        universe_definition=state.bundle.universe.to_dict(),
        feature_specification={
            "return_type": str(graph.return_type),
            "core_layer": str(graph.core_layer),
            "core_window": int(graph.core_window),
            "covariance_estimator": str(graph.covariance_estimator),
            "residualize_market": bool(config.features.residualize_market),
            "residualize_sector": bool(config.features.residualize_sector),
            "sector_factor": "leave_one_out",
        },
        diagnostics=alpha_diagnostics.to_dict(orient="records"),
    )
    state.fitted_graph_spec.save(
        config.artifact_path("metrics", "fitted_graph_specification.json")
    )

    state.assumptions.append(
        "The graphical lasso is fitted on the CORRELATION matrix rather than the covariance. "
        "Daily return covariances are ~1e-4, so a penalty on the covariance scale would zero every "
        "off-diagonal term; partial correlation is scale invariant, so the estimate is unchanged "
        "while alpha becomes comparable across windows and regimes."
    )
    state.assumptions.append(
        "Centrality measures that are undefined on negative weights (eigenvector, PageRank, "
        "closeness, harmonic, betweenness, clustering, coreness) are computed on |A|. Sign "
        "information is preserved separately as positive/negative strength and edge sign ratio."
    )
    if str(config.data.universe_method) == "static_list":
        state.assumptions.append(
            "The universe is the static VN30 list in config/vn30_universe.csv applied to all of "
            "history, because the database carries no index-membership table. This is "
            "survivorship-biased; `data.universe_method: liquidity_proxy` builds a point-in-time "
            "alternative from trailing market cap x turnover."
        )

    layers = ["partial_correlation"]
    if graph.build_correlation_and_partial:
        layers.append("correlation")
    return_types = [graph.return_type]
    if graph.build_raw_and_residual:
        return_types = [t for t in ("residual", "raw") if t in returns_by_type]

    graph_dir = config.artifacts_dir / "graphs"
    convergence_diagnostics: list[dict[str, Any]] = []
    for layer in layers:
        for return_type in return_types:
            returns = returns_by_type.get(return_type)
            if returns is None:
                continue
            windows = list(graph.windows) if layer == graph.core_layer else [graph.core_window]
            for window in windows:
                key = f"{layer}__{return_type}__w{window}"
                build = SnapshotBuildConfig.from_config(config, layer, window, return_type)
                build.alpha = alpha
                if key != state.core_key:
                    # Bootstrap stability is expensive; only the core layer gets it.
                    build.bootstrap_iterations = 0
                    # Secondary layers feed only graph-LEVEL features, which are
                    # forward-filled onto the daily index anyway. Building them
                    # daily multiplies runtime and memory (tens of thousands of
                    # retained matrices) for information the model never sees.
                    # The core layer keeps the configured stride because it
                    # drives node metrics and the published network snapshot.
                    build.stride = max(build.stride, int(graph.secondary_snapshot_stride))

                # Frozen for the online tier: the penalty and every build
                # parameter came from training windows only.
                state.build_configs[key] = build
                logger.info("Building %s ...", key)
                cached = None
                if resume and not force:
                    # Reuse persisted snapshots and build only the tail. The
                    # cache is discarded unless it came from an identical build
                    # config AND its last snapshot still reproduces exactly.
                    try:
                        cached = SnapshotSeries.load(graph_dir, key)
                    except Exception as exc:
                        logger.debug("No reusable cache for %s (%s).", key, exc)
                series, built = extend_snapshot_series(returns, build, cached)
                if resume:
                    logger.info("%s: built %d new snapshot(s).", key, built)
                if not len(series):
                    logger.warning("%s produced no snapshots; skipping.", key)
                    continue
                state.series_by_key[key] = series
                for snapshot in series:
                    if "glasso_converged" not in snapshot.metadata:
                        continue
                    convergence_diagnostics.append(
                        {
                            "graph_key": key,
                            "date": str(pd.Timestamp(snapshot.date).date()),
                            "converged": bool(snapshot.metadata.get("glasso_converged")),
                            "iterations": snapshot.metadata.get("glasso_n_iter"),
                            "dual_gap": snapshot.metadata.get("glasso_dual_gap"),
                            "warning": snapshot.metadata.get("glasso_warning", ""),
                            "retry_count": snapshot.metadata.get("glasso_retry_count", 0),
                            "fallback_reason": snapshot.metadata.get(
                                "glasso_fallback_reason", ""
                            ),
                        }
                    )

                # Correlations for the market-mode / MST / diversification metrics.
                correlations = {}
                for snapshot in series:
                    window_returns = returns.loc[: snapshot.date].tail(window)[snapshot.nodes]
                    block = window_returns.dropna(axis=0, how="any")
                    if len(block) >= max(10, window // 3):
                        try:
                            correlations[snapshot.date] = correlation_matrix(
                                block, str(graph.covariance_estimator)
                            )[0].astype(np.float32)
                        except Exception:
                            continue
                state.correlations_by_key[key] = correlations
                try:
                    series.save(graph_dir)
                except Exception as exc:
                    logger.warning("Could not persist %s (%s).", key, exc)

    state.fitted_graph_spec = replace(
        state.fitted_graph_spec,
        convergence_diagnostics=convergence_diagnostics,
    )
    state.fitted_graph_spec.save(
        config.artifact_path("metrics", "fitted_graph_specification.json")
    )

    if state.core_key not in state.series_by_key and state.series_by_key:
        fallback = next(iter(state.series_by_key))
        logger.warning("Core key %s missing; falling back to %s.", state.core_key, fallback)
    return state


# ---------------------------------------------------------------------------
# Stage 4 - network metrics, communities, stress score
# ---------------------------------------------------------------------------
def stage_network(state: PipelineState) -> PipelineState:
    from dynamicgraph.network.graph_metrics import compute_metric_series
    from dynamicgraph.network.node_metrics import add_temporal_node_metrics, compute_node_metrics
    from dynamicgraph.network.stress_score import build_descriptive_stress_score
    from dynamicgraph.training.splits import global_train_mask

    logger.info("=== Stage: network metrics ===")
    config = state.config
    sector_of = state.bundle.sectors()
    seed = int(config.project.seed)

    core_key_name = state.core_key
    for key, series in state.series_by_key.items():
        # Community results are only needed downstream for the core layer (the
        # published network and its migration history). Retaining one per
        # snapshot for every layer is a large amount of memory for data nothing
        # reads.
        keep_communities = key == core_key_name
        metrics, communities = compute_metric_series(
            list(series),
            correlations=state.correlations_by_key.get(key),
            sector_of=sector_of,
            seed=seed,
            return_communities=keep_communities,
        )
        state.metrics_by_key[key] = metrics
        state.communities_by_key[key] = communities
        # Correlation matrices are consumed by the metric computation above.
        # The core layer's are kept for the correlation-vs-partial figure; the
        # rest are released rather than held for the remainder of the run.
        if not keep_communities:
            state.correlations_by_key.pop(key, None)

    core_key = state.core_key if state.core_key in state.series_by_key else next(iter(state.series_by_key), None)
    if core_key is None:
        raise RuntimeError("No graph snapshots were produced; cannot compute network metrics.")

    core_series = state.series_by_key[core_key]
    core_communities = state.communities_by_key[core_key]

    logger.info("Computing node metrics for %d core snapshot(s) ...", len(core_series))
    node_rows: list[pd.DataFrame] = []
    for snapshot in core_series:
        features_at = state.node_features.matrix_at(snapshot.date, snapshot.nodes)
        node_rows.append(
            compute_node_metrics(
                snapshot,
                node_features=features_at,
                community=core_communities.get(snapshot.date),
                compute_betweenness=bool(config.network.compute_betweenness),
                compute_closeness=bool(config.network.compute_closeness),
                pagerank_alpha=float(config.network.pagerank_alpha),
                risk_column=str(config.network.neighbor_risk_feature),
                sector_of=sector_of,
                seed=seed,
            )
        )
    history = pd.concat(node_rows, ignore_index=True)
    state.node_metric_history = add_temporal_node_metrics(history)

    metric_dir = config.artifacts_dir / "metrics"
    metric_dir.mkdir(parents=True, exist_ok=True)
    for key, frame in state.metrics_by_key.items():
        frame.to_csv(metric_dir / f"graph_metrics_{key}.csv")
    state.node_metric_history.to_csv(metric_dir / "node_metrics_history.csv", index=False)

    # ---- descriptive stress score, standardised on TRAINING data only ----
    core_metrics = state.metrics_by_key[core_key]
    train_mask = (
        global_train_mask(state.folds, core_metrics.index)
        if state.folds
        else pd.Series(True, index=core_metrics.index)
    )
    if not state.folds:
        state.assumptions.append(
            "No walk-forward folds were available, so the descriptive stress score was "
            "standardised in-sample. It must not be reported as an out-of-sample quantity."
        )
    state.stress_model, state.stress_scores, _ = build_descriptive_stress_score(
        core_metrics, config, train_mask
    )
    # Freeze the state cutoffs. `classify_state` recomputes them from whatever
    # mask it is handed, so an online tier calling it without the training mask
    # would derive thresholds from the full series -- a leak, and the published
    # label would drift as each new session shifted the quantiles.
    state.stress_state_cutoffs = [
        float(
            state.stress_scores.loc[
                train_mask.reindex(state.stress_scores.index, fill_value=False), "stress_raw"
            ].quantile(p)
        )
        for p in list(config.stress_score.state_percentiles)
    ]
    state.stress_state_labels = list(config.stress_score.state_labels)
    state.stress_scores.to_csv(metric_dir / "stress_score_history.csv")
    _write_batch_handoff(state, core_key)
    return state


def _write_batch_handoff(state: PipelineState, core_key: str) -> None:
    """Hand the frozen objects to the online tier (`init-online-state`).

    Nothing is recomputed here; the bundle is what lets a session update run in
    seconds without reselecting alpha or refitting the stress model.
    """
    from dynamicgraph.online.handoff import BatchHandoff, save_batch_handoff

    config = state.config
    try:
        path = save_batch_handoff(
            config.artifacts_dir,
            BatchHandoff(
                core_key=core_key,
                build_configs=dict(state.build_configs),
                residual_window=int(config.features.residual_window),
                sector_of=dict(state.bundle.sectors()),
                seed=int(config.project.seed),
                metric_history=state.metrics_by_key[core_key].copy(),
                metric_history_by_key={
                    key: frame.copy() for key, frame in state.metrics_by_key.items()
                },
                stress_model=state.stress_model,
                run_metadata={
                    "core_key": core_key,
                    "last_data_date": str(pd.Timestamp(state.metrics_by_key[core_key].index[-1]).date()),
                    "config_path": str(getattr(config, "source_path", "")),
                    "seed": int(config.project.seed),
                },
            ),
        )
    except Exception as exc:  # the research run must not fail because of the online bundle
        logger.warning("Không ghi được batch handoff cho tầng online: %s", exc)
        return
    logger.info("Batch handoff cho tầng online: %s", path)


# ---------------------------------------------------------------------------
# Structure observatory
# ---------------------------------------------------------------------------
def stage_observatory(state: PipelineState) -> PipelineState:
    """Build the structure-first state, role, community and robustness tables."""
    if not bool(state.config.modules.structure_analysis):
        logger.info("Structure analysis disabled by run mode; skipping.")
        return state
    from dynamicgraph.observatory import (
        build_market_structure_state,
        build_node_roles,
        build_robustness_report,
        run_shock_scenario,
        structural_break_table,
        track_communities,
    )

    logger.info("=== Stage: market structure observatory ===")
    core_key = (
        state.core_key
        if state.core_key in state.series_by_key
        else next(iter(state.series_by_key), None)
    )
    if core_key is None:
        raise RuntimeError("No graph series available for structure analysis.")
    core_series = state.series_by_key[core_key]
    communities = state.communities_by_key.get(core_key, {})
    coverage = getattr(state.bundle.universe, "daily_coverage", None)

    state.graph_robustness = build_robustness_report(
        state.series_by_key, coverage=coverage
    )
    agreement = {}
    if not state.graph_robustness.empty:
        agreement = (
            state.graph_robustness.groupby("date")[
                "cross_method_rank_correlation"
            ]
            .mean()
            .to_dict()
        )
    state.market_structure_state = build_market_structure_state(
        list(core_series),
        communities=communities,
        coverage=coverage,
        estimator=str(state.config.graph.covariance_estimator),
        cross_method_agreement=agreement,
    )
    state.structural_breaks = structural_break_table(state.market_structure_state)
    directed = state.spillover_snapshots or state.directed_snapshots
    state.node_roles = build_node_roles(
        state.node_metric_history,
        list(core_series),
        directed_snapshots=directed,
        cross_method_agreement=agreement,
    )
    state.community_state = track_communities(
        communities,
        snapshots=list(core_series),
        sector_of=state.bundle.sectors(),
        node_roles=state.node_roles,
    )

    root = state.config.artifacts_dir
    state.market_structure_state.to_parquet(
        root / "market_structure_state.parquet", index=False
    )
    state.node_roles.to_parquet(root / "node_roles.parquet", index=False)
    state.community_state.to_parquet(root / "community_state.parquet", index=False)
    state.graph_robustness.to_parquet(
        root / "graph_robustness.parquet", index=False
    )
    state.structural_breaks.to_csv(root / "structural_breaks.csv", index=False)

    if bool(state.config.modules.scenario_analysis) and directed:
        latest = directed[-1]
        source = latest.out_strength.idxmax()
        state.scenario_report = run_shock_scenario(
            latest,
            {source: 1.0},
            horizon=5,
            scenario_type="largest_transmitter_unit_shock",
            estimator=str(latest.metadata.get("estimator", latest.layer)),
        )
        state.scenario_report.to_parquet(
            root / "scenario_report.parquet", index=False
        )
    return state


# ---------------------------------------------------------------------------
# Stage 5 - predictive models
# ---------------------------------------------------------------------------
def stage_predictive(state: PipelineState) -> PipelineState:
    from dynamicgraph.evaluation.ablation import feature_group_contributions, run_ablation
    from dynamicgraph.models.registry import FeatureSetBuilder, flatten_graph_metrics
    from dynamicgraph.training.splits import folds_from_config
    from dynamicgraph.training.trainer import run_experiment, summarize_incremental_value

    logger.info("=== Stage: predictive baselines ===")
    config = state.config
    if not bool(config.modules.stress_forecasting):
        logger.info("Stress forecasting disabled in `%s` mode; skipping.", config.project.mode)
        state.skipped_modules.append("stress_forecasting (disabled by run mode)")
        if bool(config.modules.node_return_ranking):
            if not state.folds:
                try:
                    state.folds = folds_from_config(state.market_features.index, config)
                except ValueError as exc:
                    logger.error("Cannot run node ranking: %s", exc)
                    state.node_ranking_verdict = {
                        "verdict": "inconclusive",
                        "reason": str(exc),
                    }
                    return state
            _run_node_ranking_stage(state)
        else:
            state.skipped_modules.append(
                "node_return_ranking (disabled by run mode)"
            )
        return state
    index = state.market_features.index

    graph_features = flatten_graph_metrics(state.metrics_by_key, index)
    if state.stress_scores is not None:
        stress = state.stress_scores.reindex(index)
        for column in ("stress_raw", "stress_score", "stress_change_5d", "stress_change_20d"):
            if column in stress.columns:
                graph_features[f"descriptive_{column}"] = stress[column]

    builder = FeatureSetBuilder(state.market_features, graph_features, index=index)
    logger.info("Feature counts: %s", builder.describe().to_dict(orient="records"))

    if not state.folds:
        try:
            state.folds = folds_from_config(index, config)
        except ValueError as exc:
            logger.error("Cannot run the predictive stage: %s", exc)
            state.verdict = {"verdict": "inconclusive", "reason": str(exc)}
            return state

    state.experiment = run_experiment(
        builder=builder,
        forward_values=state.targets.forward,
        absolute_labels=state.targets.labels,
        folds=state.folds,
        config=config,
    )
    state.verdict = summarize_incremental_value(
        state.experiment.comparisons, state.experiment.metrics
    )
    logger.info("Incremental-value verdict: %s", state.verdict.get("verdict"))
    absolute = state.verdict.get("absolute_skill") or {}
    if absolute and not absolute.get("beats_climatology", True):
        logger.warning(
            "No configuration beat a constant base-rate forecast (best Brier skill %.4f). "
            "Relative gains over the market-only baseline do not imply usable forecasting skill.",
            absolute.get("best_brier_skill_score", float("nan")),
        )
    state.experiment.save(config.artifacts_dir / "predictions")

    # ---- cross-sectional node ranking (brief 21.4 / 22) ------------------
    if bool(config.modules.node_return_ranking):
        _run_node_ranking_stage(state)
    else:
        state.skipped_modules.append("node_return_ranking (disabled by run mode)")

    if bool(config.ablation.enabled):
        logger.info("Running ablation study ...")
        state.ablation = run_ablation(builder, state.targets.forward, state.folds, config)
        if state.ablation is not None and not state.ablation.empty:
            state.ablation.to_csv(config.artifact_path("metrics", "ablation.csv"), index=False)
            contributions = feature_group_contributions(state.ablation)
            if not contributions.empty:
                contributions.to_csv(
                    config.artifact_path("metrics", "ablation_group_contributions.csv"), index=False
                )
    return state


def _run_node_ranking_stage(state: PipelineState) -> None:
    """Run ranking independently of the market-stress forecasting switch."""
    try:
        from dynamicgraph.training.node_ranking import (
            node_ranking_verdict,
            run_node_ranking,
            summarize_node_ranking,
        )

        logger.info("Running cross-sectional node ranking ...")
        state.node_ranking = run_node_ranking(state, state.folds)
        state.node_ranking_summary = summarize_node_ranking(state.node_ranking)
        state.node_ranking_verdict = node_ranking_verdict(
            state.node_ranking_summary
        )
        if (
            state.node_ranking_summary is not None
            and not state.node_ranking_summary.empty
        ):
            state.node_ranking_summary.to_csv(
                state.config.artifact_path("metrics", "node_ranking.csv"),
                index=False,
            )
            for name, result in state.node_ranking.items():
                result.ic_series.rename("rank_ic").to_csv(
                    state.config.artifact_path(
                        "metrics", f"node_ranking_ic_{name}.csv"
                    )
                )
        logger.info(
            "Node ranking verdict: %s",
            state.node_ranking_verdict.get("verdict"),
        )
    except Exception as exc:
        logger.warning(
            "Node ranking stage failed (%s); the rest of the pipeline is unaffected.",
            exc,
        )
        state.skipped_modules.append(f"node_ranking: {exc}")


# ---------------------------------------------------------------------------
# Stage 6 - directed layers
# ---------------------------------------------------------------------------
def stage_directed(state: PipelineState) -> PipelineState:
    from dynamicgraph.graphs.lead_lag import build_lead_lag_series
    from dynamicgraph.graphs.spillover import build_spillover_series

    config = state.config
    graph = config.graph
    if not (graph.enable_lead_lag or graph.enable_spillover):
        logger.info("Directed layers disabled in config; skipping.")
        return state

    logger.info("=== Stage: directed layers ===")
    returns = state.node_features.returns_residual
    if returns is None:
        returns = state.node_features.returns_raw

    if graph.enable_lead_lag:
        stride = max(1, int(graph.snapshot_stride) * 5)
        state.directed_snapshots = build_lead_lag_series(
            returns,
            window=int(graph.lead_lag_window),
            lags=tuple(int(k) for k in graph.lead_lag_days),
            threshold=float(graph.lead_lag_threshold),
            min_abs_corr=float(graph.lead_lag_min_abs_corr),
            fdr_alpha=float(graph.lead_lag_fdr_alpha),
            stride=stride,
            max_missing_ratio=float(config.data.max_missing_ratio_per_window),
        )
        if state.directed_snapshots:
            frames = [s.edge_list() for s in state.directed_snapshots[-60:]]
            pd.concat(frames, ignore_index=True).to_csv(
                config.artifact_path("graphs", "lead_lag_edges_recent.csv"), index=False
            )

    if graph.enable_spillover:
        volatility = (
            state.node_features.frames.get("volatility_20d")
            if state.node_features.frames.get("volatility_20d") is not None
            else returns.rolling(20).std()
        )
        state.spillover_snapshots = build_spillover_series(volatility.dropna(how="all"), config, stride=10)
        if state.spillover_snapshots:
            from dynamicgraph.network.transmitters import total_connectedness_series

            total_connectedness_series(state.spillover_snapshots).to_csv(
                config.artifact_path("metrics", "total_connectedness.csv")
            )
    return state


# ---------------------------------------------------------------------------
# Stage 7 - graph validation
# ---------------------------------------------------------------------------
def stage_graph_validation(state: PipelineState) -> PipelineState:
    from dynamicgraph.evaluation.graph_validation import run_graph_validation

    logger.info("=== Stage: graph validation ===")
    returns_by_type = {"raw": state.node_features.returns_raw}
    if state.node_features.returns_residual is not None:
        returns_by_type["residual"] = state.node_features.returns_residual

    core_key = state.core_key if state.core_key in state.series_by_key else None
    state.graph_validation = run_graph_validation(
        state.series_by_key,
        returns_by_type,
        state.config,
        sector_of=state.bundle.sectors(),
        core_key=core_key,
    )
    metric_dir = state.config.artifacts_dir / "metrics"
    metric_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in state.graph_validation.items():
        if frame is not None and not frame.empty:
            frame.to_csv(metric_dir / f"graph_validation_{name}.csv", index=False)
    return state


# ---------------------------------------------------------------------------
# Stage 8 - capital allocation
# ---------------------------------------------------------------------------
def stage_allocation(state: PipelineState) -> PipelineState:
    """Does the estimated dependence structure improve capital allocation?

    Separate from `stage_predictive` because it tests a different claim. The
    predictive stage asked whether the graph forecasts stress and found it does
    not; this stage asks whether the graph estimates covariance well enough to
    allocate on, which is a question about second moments rather than first and
    can come out differently.

    Allocation uses **raw** returns, not the market-residualised ones the graph
    layer is built on: capital is exposed to total return, so the covariance
    that governs portfolio variance is the covariance of total returns. The
    graphical-lasso sparsity idea carries over unchanged; only the input does.
    """
    config = state.config
    if not bool(config.modules.allocation_validation):
        logger.info("Allocation validation disabled in `%s` mode; skipping.", config.project.mode)
        state.skipped_modules.append("allocation_validation (disabled by run mode)")
        return state
    allocation = getattr(config, "allocation", None)
    if allocation is not None and not allocation.enabled:
        logger.info("Allocation module disabled; skipping.")
        state.skipped_modules.append("allocation (disabled in config)")
        return state

    from dynamicgraph.allocation.runner import (
        _communities_by_date,
        run_allocation_experiment,
        write_allocation_artifacts,
    )

    logger.info("=== Stage: capital allocation ===")
    returns = state.node_features.returns_raw
    if returns is None or returns.empty:
        logger.warning("No raw returns available; skipping allocation.")
        state.skipped_modules.append("allocation (no returns)")
        return state

    try:
        state.allocation = run_allocation_experiment(
            returns,
            config,
            communities_by_date=_communities_by_date(state),
            fitted_graph_spec=state.fitted_graph_spec,
        )
    except Exception as exc:
        logger.warning("Allocation experiment failed (%s); the rest of the run is unaffected.", exc)
        state.skipped_modules.append(f"allocation runtime failure: {exc}")
        return state

    write_allocation_artifacts(state.allocation, config.artifacts_dir / "allocation")
    state.allocation_verdict = state.allocation["verdict"]
    state.assumptions.append(
        "Allocation signals use data through close t, execute at the next close "
        f"after {state.allocation['config'].execution_lag_sessions} session(s), "
        "and accrue returns only after execution, with a linear cost of "
        f"{state.allocation['config'].cost_bps_per_side:.0f} bps per side and no "
        "market impact. They ignore foreign-ownership limits and VN30 constituent "
        "changes, both of which would bind for a real book."
    )
    logger.info(
        "Allocation verdict: %s (%s)",
        state.allocation_verdict.get("verdict"),
        state.allocation_verdict.get("lowest_volatility_portfolio"),
    )
    return state


# ---------------------------------------------------------------------------
# Stage 9 - Temporal GNN (optional)
# ---------------------------------------------------------------------------
def stage_gnn(state: PipelineState) -> PipelineState:
    config = state.config
    if not (config.models.run_temporal_gnn or config.gnn.enabled):
        logger.info("Temporal GNN disabled; skipping (baselines are the reference).")
        return state

    try:
        from dynamicgraph.models.temporal_gnn import run_temporal_gnn_experiment
    except ImportError as exc:
        logger.warning("Temporal GNN unavailable (%s); skipping.", exc)
        state.skipped_modules.append(f"temporal_gnn ({exc})")
        return state

    logger.info("=== Stage: Temporal GNN ===")
    try:
        state.gnn_result = run_temporal_gnn_experiment(state)
    except Exception as exc:
        logger.warning("Temporal GNN run failed (%s); the statistical pipeline is unaffected.", exc)
        state.skipped_modules.append(f"temporal_gnn runtime failure: {exc}")
    return state


_PATH_KEYS = ("path", "database_path", "source_path", "file")


def _redact_source_paths(data: Any) -> Any:
    """Replace database locations with a fingerprint of themselves.

    `run_summary.json` is committed, and the raw value is the absolute path of
    a file on the operating machine. `ReproducibilityRecord` already hashes it
    for exactly this reason; the run summary was writing it in the clear, which
    made the hashing elsewhere pointless.

    The walk is recursive because the connector nests its metadata one level
    down under `source`, and a redaction that only checks the top level is a
    redaction that silently does nothing.

    The digest still serves the purpose the path served: two runs can be shown
    to have read the same source without disclosing where that source lives.
    """
    if isinstance(data, list):
        return [_redact_source_paths(item) for item in data]
    if not isinstance(data, dict):
        return data

    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in _PATH_KEYS and isinstance(value, (str, Path)) and str(value):
            digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]
            out[key] = f"<redacted:sha256:{digest}>"
            out[f"{key}_name"] = Path(str(value)).name
        else:
            out[key] = _redact_source_paths(value)
    return out


def write_state_summary(state: PipelineState) -> Path:
    """Machine-readable summary of the whole run."""
    summary = {
        "config_mode": str(state.config.project.mode),
        "data": _redact_source_paths(state.bundle.to_dict()) if state.bundle else None,
        "graph_keys": list(state.series_by_key),
        "snapshots_per_key": {k: len(v) for k, v in state.series_by_key.items()},
        "n_folds": len(state.folds),
        "verdict": state.verdict,
        "node_ranking_verdict": state.node_ranking_verdict,
        "fitted_graph_specification": (
            state.fitted_graph_spec.to_dict()
            if state.fitted_graph_spec is not None
            else None
        ),
        "structure_observatory": {
            "n_state_rows": (
                len(state.market_structure_state)
                if state.market_structure_state is not None
                else 0
            ),
            "n_node_role_rows": (
                len(state.node_roles) if state.node_roles is not None else 0
            ),
            "n_community_rows": (
                len(state.community_state) if state.community_state is not None else 0
            ),
            "n_structural_breaks": (
                len(state.structural_breaks)
                if state.structural_breaks is not None
                else 0
            ),
        },
        "assumptions": state.assumptions,
        "skipped_modules": state.skipped_modules,
        "gnn": state.gnn_result,
    }
    path = state.config.artifact_path("reports", "run_summary.json")
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    from dynamicgraph.outputs.artifact_contract import write_run_manifest

    write_run_manifest(state)
    return path
