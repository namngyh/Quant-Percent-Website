"""Latest-state generation: build the website payload, the figures and the
markdown reports from a completed `PipelineState`."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger
from dynamicgraph.outputs import figures as F
from dynamicgraph.outputs.exporters import export_frame, output_formats, write_manifest
from dynamicgraph.outputs.website_json import (
    build_edges_json,
    build_nodes_json,
    build_website_payload,
    write_website_outputs,
)

logger = get_logger(__name__)


def _model_quality(state: Any, horizon: int) -> dict[str, Any]:
    experiment = state.experiment
    if experiment is None or experiment.metrics.empty:
        return {}
    subset = experiment.metrics[
        (experiment.metrics["horizon"] == horizon)
        & (experiment.metrics["model"] != "naive_frequency")
    ].dropna(subset=["brier"])
    if subset.empty:
        return {}
    best = subset.loc[subset["brier"].idxmin()]
    return {
        "evaluation_type": "walk_forward_oos",
        "model": str(best["model"]),
        "feature_set": str(best["feature_set"]),
        "brier_score": float(best["brier"]),
        "brier_skill_score": float(best.get("brier_skill_score", np.nan)),
        "auroc": float(best.get("auroc", np.nan)),
        "auprc": float(best.get("auprc", np.nan)),
        "mcc": float(best.get("mcc", np.nan)),
        "recall_stress": float(best.get("recall_stress", np.nan)),
        "precision_stress": float(best.get("precision_stress", np.nan)),
        "false_alarms_per_year": float(best.get("false_alarms_per_year", np.nan)),
        "calibration_error": float(best.get("expected_calibration_error", np.nan)),
        "calibration_slope": float(best.get("calibration_slope", np.nan)),
        "n_oos_observations": int(best.get("n", 0)),
        "n_folds": int(best.get("n_folds", 0)),
        "graph_incremental_value": str(state.verdict.get("verdict", "unknown")),
    }


def build_stress_probabilities(state: Any, as_of: pd.Timestamp) -> dict[str, dict[str, Any]]:
    """Live probability per horizon from a model refitted up to `as_of`.

    Only horizons whose OOS evaluation actually produced a usable model are
    published, and each entry carries its own quality metadata.
    """
    from dynamicgraph.features.targets import label_by_train_quantile
    from dynamicgraph.models.baselines import build_model_zoo
    from dynamicgraph.models.registry import FeatureSetBuilder, flatten_graph_metrics
    from dynamicgraph.training.walk_forward import fit_final_model

    config = state.config
    experiment = state.experiment
    if experiment is None or experiment.metrics.empty:
        logger.info("No OOS results; publishing no stress probabilities.")
        return {}

    index = state.market_features.index
    graph_features = flatten_graph_metrics(state.metrics_by_key, index)
    if state.stress_scores is not None:
        stress = state.stress_scores.reindex(index)
        for column in ("stress_raw", "stress_score", "stress_change_5d", "stress_change_20d"):
            if column in stress.columns:
                graph_features[f"descriptive_{column}"] = stress[column]
    builder = FeatureSetBuilder(state.market_features, graph_features, index=index)
    zoo = build_model_zoo(config, "classification")

    out: dict[str, dict[str, Any]] = {}
    for horizon in [int(h) for h in config.targets.horizons]:
        quality = _model_quality(state, horizon)
        if not quality:
            continue
        model_name = quality["model"]
        feature_set = quality["feature_set"]
        if model_name not in zoo:
            continue

        forward_column = f"future_drawdown_{horizon}d"
        if forward_column not in state.targets.forward.columns:
            continue

        try:
            features = builder.build(feature_set)
        except Exception:
            continue

        # The label threshold is estimated on everything strictly before the
        # last `purge + horizon` days, so the live label definition uses no
        # information that overlaps the as-of date.
        purge = int(config.training.purge_days) + horizon
        usable = index[index <= as_of]
        if len(usable) < 300:
            continue
        train_end = usable[-purge] if len(usable) > purge else usable[len(usable) // 2]

        train_mask = pd.Series(index.isin(index[index <= train_end]), index=index)
        try:
            labels, label_threshold = label_by_train_quantile(
                state.targets.forward[forward_column],
                train_mask,
                float(config.targets.stress_quantile),
                direction="lower",
            )
        except ValueError:
            continue

        model = fit_final_model(
            features, labels, zoo[model_name], config, train_end=train_end,
            validation_days=int(config.training.validation_days),
        )
        if model is None:
            continue

        # `fit_final_model` may have narrowed the feature space; the live row
        # must be projected onto exactly the same columns.
        selected = model.feature_names or list(features.columns)
        latest_row = features.reindex(columns=selected).loc[[as_of]] if as_of in features.index else None
        if latest_row is None or latest_row.isna().all(axis=1).iloc[0]:
            continue
        try:
            probability = float(model.predict_proba(latest_row)[0])
        except Exception as exc:
            logger.warning("Live prediction failed for horizon %d: %s", horizon, exc)
            continue

        warning = None
        if quality.get("brier_skill_score", 0) is not None and quality["brier_skill_score"] <= 0:
            warning = (
                "This horizon's model did not beat a constant base-rate forecast out of sample. "
                "Treat the probability as uninformative."
            )
        elif state.verdict.get("verdict") == "no_incremental_value" and feature_set != "market":
            warning = (
                "Graph features did not show statistically significant incremental value out of "
                "sample; this probability rests mainly on market-level information."
            )

        # Clamp away from the endpoints: a calibrator can return exactly 0 or 1
        # on the training support, and publishing "0.0000" would assert that a
        # drawdown is impossible, which no model here can support.
        probability = float(np.clip(probability, 1e-4, 1 - 1e-4))

        out[f"{horizon}d"] = {
            "probability": round(probability, 5),
            "calibrated": model.method != "none",
            "calibration_method": model.method,
            "model_name": model_name,
            "feature_set": feature_set,
            "label_definition": (
                f"VN30 forward {horizon}-day drawdown at or below the training "
                f"{int(config.targets.stress_quantile * 100)}th percentile "
                f"({label_threshold:.4f})"
            ),
            "oos_brier_score": quality.get("brier_score"),
            "oos_auprc": quality.get("auprc"),
            "oos_brier_skill_score": quality.get("brier_skill_score"),
            "sample_size": quality.get("n_oos_observations"),
            "last_retraining_date": str(pd.Timestamp(train_end).date()),
            "decision_threshold": round(float(model.decision_threshold), 4),
            "confidence_warning": warning,
        }
    logger.info("Published stress probabilities for horizons: %s", list(out))
    return out


def generate_latest(state: Any) -> dict[str, Any]:
    """Build every `artifacts/latest/` file plus the figures and reports."""
    from dynamicgraph.explainability.graph import stress_contribution_breakdown
    from dynamicgraph.network.transmitters import directed_roles, influence_nodes

    config = state.config
    core_key = state.core_key if state.core_key in state.series_by_key else next(iter(state.series_by_key))
    series = state.series_by_key[core_key]
    snapshot = series.latest()
    if snapshot is None:
        raise RuntimeError("No snapshot available to publish.")

    as_of = pd.Timestamp(snapshot.date)
    sector_of = state.bundle.sectors()
    node_features_at = state.node_features.matrix_at(as_of, snapshot.nodes)
    node_features_at["sector"] = [sector_of.get(t, "UNKNOWN") for t in node_features_at.index]

    node_metrics_now = state.node_metric_history[
        state.node_metric_history["date"] == as_of
    ].copy()
    if node_metrics_now.empty:
        node_metrics_now = state.node_metric_history.sort_values("date").groupby("ticker").tail(1)

    influence = influence_nodes(node_metrics_now, top_n=int(config.output.top_n_nodes))
    if "influence_score" in influence.columns:
        node_metrics_now = node_metrics_now.merge(
            influence[["ticker", "influence_score"]], on="ticker", how="left"
        )

    directed_snapshot = state.directed_snapshots[-1] if state.directed_snapshots else None
    if state.spillover_snapshots:
        directed_snapshot = state.spillover_snapshots[-1]
    roles = directed_roles(directed_snapshot)

    core_metrics = state.metrics_by_key[core_key]
    metrics_row = core_metrics.loc[as_of] if as_of in core_metrics.index else core_metrics.iloc[-1]
    communities = state.communities_by_key[core_key].get(as_of)

    contributions = (
        stress_contribution_breakdown(state.stress_model, state.stress_scores, as_of)
        if state.stress_model is not None and as_of in state.stress_scores.index
        else pd.DataFrame()
    )
    state_label = (
        str(state.stress_scores.loc[as_of, "network_state"])
        if state.stress_scores is not None and as_of in state.stress_scores.index
        else "unknown"
    )

    last_data_date = pd.Timestamp(state.bundle.panel["date"].max())
    freshness = int((pd.Timestamp(datetime.now().date()) - last_data_date).days)

    probabilities = build_stress_probabilities(state, as_of)
    quality = _model_quality(state, int(config.targets.horizons[len(config.targets.horizons) // 2]))

    payload = build_website_payload(
        config=config,
        as_of_date=as_of,
        snapshot=snapshot,
        node_metrics=node_metrics_now,
        node_features=node_features_at,
        graph_metrics_row=metrics_row,
        stress_scores=state.stress_scores,
        stress_state=state_label,
        stress_contributions=contributions,
        communities=communities,
        universe=state.bundle.universe,
        directed_roles=roles,
        stress_probabilities=probabilities,
        model_quality=quality,
        reproducibility=state.record,
        data_freshness_days=freshness,
        warnings=list(state.bundle.warnings),
    )

    nodes = build_nodes_json(snapshot, node_metrics_now, node_features_at, sector_of, communities)
    edges = build_edges_json(snapshot, directed_snapshot)

    node_scores = node_metrics_now.merge(
        node_features_at.reset_index().rename(columns={"index": "ticker"}),
        on="ticker", how="left", suffixes=("", "_feature"),
    )
    # Lead with the columns a human actually reads, and order most-central
    # first. The remaining ~140 diagnostic columns follow, so nothing is lost.
    headline = [
        "ticker", "sector", "community", "strength", "degree", "eigenvector_centrality",
        "pagerank", "betweenness_centrality", "positive_strength", "negative_strength",
        "edge_sign_ratio", "avg_neighbor_risk", "return_20d", "volatility_20d",
        "current_drawdown", "downside_volatility_20d",
    ]
    present = [c for c in headline if c in node_scores.columns]
    node_scores = node_scores[present + [c for c in node_scores.columns if c not in present]]
    if "strength" in node_scores.columns:
        node_scores = node_scores.sort_values("strength", ascending=False).reset_index(drop=True)
    stress_forecasts = pd.DataFrame(
        [
            {"horizon": horizon, "as_of_date": str(as_of.date()), **entry}
            for horizon, entry in probabilities.items()
        ]
    )
    network_history = state.stress_scores.join(
        core_metrics[[c for c in core_metrics.columns if c not in state.stress_scores.columns]],
        how="left",
    )

    written = write_website_outputs(
        config=config,
        payload=payload,
        nodes=nodes,
        edges=edges,
        node_scores=node_scores,
        graph_metrics=core_metrics,
        stress_forecasts=stress_forecasts,
        network_history=network_history,
    )

    if config.output.create_figures:
        written.update(
            {f"figure_{k}": v for k, v in _generate_figures(state, snapshot, communities, core_key).items()}
        )

    _generate_reports(state, payload)
    if state.record is not None:
        state.record.optional_modules_skipped = list(state.skipped_modules)
        state.record.calibration_method = str(config.models.calibration_method)
        state.record.feature_list = list(state.market_features.columns)[:200]
        state.record.save(config.artifact_path("models", "reproducibility.json"))

    write_manifest(config.artifacts_dir / "latest", written)
    return payload


def _generate_figures(state: Any, snapshot: Any, communities: Any, core_key: str) -> dict[str, str]:
    config = state.config
    writer = F.FigureWriter(config.artifacts_dir / "figures", enabled=True)
    out: dict[str, str] = {}
    core_metrics = state.metrics_by_key[core_key]
    series = state.series_by_key[core_key]

    def _record(name: str, factory) -> None:
        try:
            path = writer.save(factory(), name)
            if path:
                out[name] = str(path)
        except Exception as exc:
            writer.skip(name, str(exc))

    _record("01_latest_network", lambda: F.plot_network(snapshot, communities))

    if len(series) >= 6:
        picks = np.linspace(0, len(series) - 1, min(6, len(series)), dtype=int)
        chosen = [series[int(i)] for i in picks]
        _record(
            "02_network_through_time",
            lambda: F.plot_network_grid(chosen, state.communities_by_key[core_key]),
        )

    index_price = state.bundle.panel[
        state.bundle.panel["ticker"] == state.bundle.index_ticker
    ].set_index("date")["adjusted_close"]

    if state.stress_scores is not None:
        _record(
            "03_stress_score_history",
            lambda: F.plot_stress_history(
                state.stress_scores, index_price, state.stress_scores.get("network_state")
            ),
        )
        drawdown = index_price / index_price.cummax() - 1.0
        _record("06_stress_vs_drawdown", lambda: F.plot_stress_vs_drawdown(state.stress_scores, drawdown))
        _record(
            "05_vn30_and_stress",
            lambda: F.plot_stress_history(state.stress_scores, index_price),
        )

    # Every core metric is computed on the core layer's own returns, so the
    # subtitle records which. "Market mode share" on residual returns is the
    # share of *residual* variance in the first eigenvector, which is a much
    # smaller number than the raw-return equivalent and means something
    # different: common movement that survives removing the index itself.
    context = (
        f"{series.layer.replace('_', ' ')}, {series.window}-day window, "
        f"{series.return_type} returns"
    )
    for name, column, title in (
        ("07_graph_density_history", "graph_density", "Graph density"),
        ("08_spectral_radius_history", "spectral_radius", "Spectral radius"),
        ("09_market_mode_share_history", "market_mode_share", "Market mode share"),
        ("10_centrality_concentration_history", "centrality_concentration", "Centrality concentration (Herfindahl)"),
        ("11_number_of_communities_history", "number_of_communities", "Number of communities"),
        ("15_edge_turnover_history", "edge_turnover", "Edge turnover"),
    ):
        if column in core_metrics.columns and core_metrics[column].notna().any():
            _record(
                name,
                lambda c=column, t=title: F.plot_metric_history(
                    core_metrics, c, f"{t} over time\n({context})"
                ),
            )

    history = state.node_metric_history
    if history is not None and not history.empty:
        pivot = history.pivot_table(index="date", columns="ticker", values="strength")
        # Daily centrality is very noisy; smooth before ranking so the heatmap
        # shows regime shifts rather than day-to-day reshuffling.
        smoothed = pivot.rolling(20, min_periods=5).mean()
        _record(
            "13_node_centrality_heatmap",
            lambda: F.plot_centrality_heatmap(
                smoothed.rank(axis=1, pct=True),
                "Node centrality through time (20-day smoothed, cross-sectional percentile)",
            ),
        )
        _record("14_top_influence_nodes_over_time", lambda: F.plot_top_nodes_over_time(pivot))
        community_pivot = history.pivot_table(index="date", columns="ticker", values="community")
        _record("12_community_migration", lambda: F.plot_community_migration(community_pivot))

    correlations = state.correlations_by_key.get(core_key, {})
    if snapshot.date in correlations:
        _record(
            "16_correlation_vs_partial",
            lambda: F.plot_correlation_vs_partial(
                correlations[snapshot.date], snapshot.adjacency, snapshot.nodes
            ),
        )

    raw_key = core_key.replace("__residual__", "__raw__")
    if raw_key in state.series_by_key and state.series_by_key[raw_key].latest() is not None:
        raw_snapshot = state.series_by_key[raw_key].latest()
        _record("17_raw_return_network", lambda: F.plot_network(
            raw_snapshot, title=f"Raw-return network - {pd.Timestamp(raw_snapshot.date).date()}"
        ))

    from dynamicgraph.graphs.multiscale import scale_comparison_table

    per_window = {
        s.window: s for k, s in state.series_by_key.items()
        if k.startswith(config.graph.core_layer) and f"__{config.graph.return_type}__" in k and s.window > 0
    }
    if len(per_window) > 1:
        table = scale_comparison_table(per_window)
        _record("18_multiscale_comparison", lambda: F.plot_multiscale_comparison(table))

    experiment = state.experiment
    if experiment is not None and not experiment.metrics.empty:
        _record("24_model_comparison_brier", lambda: F.plot_model_comparison(experiment.metrics, "brier"))
        best_key = None
        subset = experiment.metrics[experiment.metrics["model"] != "naive_frequency"].dropna(subset=["brier"])
        if not subset.empty:
            best = subset.loc[subset["brier"].idxmin()]
            best_key = f"{best['target']}__{best['feature_set']}__{best['model']}"
        result = experiment.results.get(best_key) if best_key else None
        if result is not None and not result.predictions.empty:
            from dynamicgraph.evaluation.calibration import reliability_table
            from dynamicgraph.evaluation.classification import (
                confusion_frame, precision_recall_frame, roc_curve_frame,
            )
            from dynamicgraph.evaluation.event_metrics import event_table

            y = result.predictions["y_true"].to_numpy()
            p = result.predictions["probability"].to_numpy()
            threshold = float(np.median(list(result.thresholds.values()))) if result.thresholds else 0.5

            _record("19_calibration_curve", lambda: F.plot_calibration_curve(
                reliability_table(y, p, int(config.evaluation.calibration_bins)),
                f"Calibration - {best_key}",
            ))
            _record("20_roc_pr_curves", lambda: F.plot_roc_pr(
                roc_curve_frame(y, p), precision_recall_frame(y, p), float(np.nanmean(y)), str(best_key)
            ))
            _record("22_confusion_matrix", lambda: F.plot_confusion_matrix(
                confusion_frame(y, p, threshold), f"Confusion matrix @ {threshold:.2f}"
            ))
            _record("26_oos_probability_timeline", lambda: F.plot_probability_timeline(
                result.predictions, threshold
            ))
            frame = result.predictions.set_index("date")
            table = event_table(frame["y_true"], frame["probability"], threshold,
                               int(config.evaluation.event_min_gap_days))
            if not table.empty:
                _record("27_event_detection", lambda: F.plot_event_detection(table))

            from dynamicgraph.explainability.tabular import permutation_importance_frame
            from dynamicgraph.models.baselines import build_model_zoo

            try:
                zoo = build_model_zoo(config, "classification")
                spec = zoo.get(result.model_name)
                if spec is not None:
                    from dynamicgraph.models.registry import FeatureSetBuilder, flatten_graph_metrics

                    graph_features = flatten_graph_metrics(state.metrics_by_key, state.market_features.index)
                    builder = FeatureSetBuilder(
                        state.market_features, graph_features, index=state.market_features.index
                    )
                    features = builder.build(result.feature_set)
                    dates = result.predictions["date"]
                    X = features.reindex(dates)
                    y_series = pd.Series(result.predictions["y_true"].to_numpy(), index=dates)
                    estimator = spec.build(seed=int(config.project.seed))
                    fit_mask = y_series.notna() & X.notna().any(axis=1)
                    if fit_mask.sum() > 100:
                        estimator.fit(X[fit_mask], y_series[fit_mask])
                        importance = permutation_importance_frame(
                            estimator, X[fit_mask], y_series[fit_mask], n_repeats=5,
                            seed=int(config.project.seed),
                        )
                        if not importance.empty:
                            importance.to_csv(
                                config.artifact_path("metrics", "permutation_importance.csv"), index=False
                            )
                            _record("23_feature_importance", lambda: F.plot_feature_importance(
                                importance, title=f"Feature importance - {best_key}"
                            ))
            except Exception as exc:
                writer.skip("23_feature_importance", str(exc))

        if not experiment.fold_metrics.empty:
            _record("25_walk_forward_performance", lambda: F.plot_walk_forward_performance(
                experiment.fold_metrics, "brier"
            ))

    if state.ablation is not None and not state.ablation.empty:
        _record("24b_ablation", lambda: F.plot_ablation(state.ablation))

    validation = state.graph_validation
    if validation.get("edge_stability") is not None and not validation["edge_stability"].empty:
        _record("28_graph_stability", lambda: F.plot_graph_stability(validation["edge_stability"]))
    if validation.get("variant_comparison") is not None and not validation["variant_comparison"].empty:
        _record("16b_graph_variant_agreement", lambda: F.plot_graph_comparison(validation["variant_comparison"]))
    if validation.get("alpha_sensitivity") is not None and not validation["alpha_sensitivity"].empty:
        _record("28b_alpha_sensitivity", lambda: F.plot_sensitivity(
            validation["alpha_sensitivity"], "alpha", "mean_density",
            "Graph density vs graphical-lasso penalty",
        ))
    if validation.get("window_sensitivity") is not None and not validation["window_sensitivity"].empty:
        _record("28c_window_sensitivity", lambda: F.plot_sensitivity(
            validation["window_sensitivity"], "window", "mean_density",
            "Graph density vs rolling window length",
        ))

    allocation = getattr(state, "allocation", None)
    if allocation:
        summary = allocation["summary"]
        verdict = allocation.get("verdict", {})
        # Highlight the benchmark, the winner, and the two portfolios the
        # project's claim actually rests on, rather than all eleven curves.
        highlight = [
            key
            for key in (
                "equal_weight__sample",
                "minimum_variance__sample",
                "minimum_variance__glasso",
                verdict.get("lowest_volatility_portfolio"),
            )
            if key and key in allocation["equity_curves"].columns
        ]
        _record("31_allocation_risk_return", lambda: F.plot_allocation_risk_return(summary))
        _record(
            "32_allocation_equity_curves",
            lambda: F.plot_allocation_equity_curves(allocation["equity_curves"], highlight),
        )
        _record(
            "33_allocation_rolling_volatility",
            lambda: F.plot_allocation_rolling_volatility(
                allocation["rolling_volatility"], highlight
            ),
        )
        diagnostics = pd.concat(
            [r.diagnostics.assign(key=r.key) for r in allocation["results"] if not r.diagnostics.empty]
        ) if allocation["results"] else pd.DataFrame()
        if not diagnostics.empty:
            _record("34_effective_bets", lambda: F.plot_effective_bets(diagnostics))

    node_frame = pd.DataFrame(
        build_nodes_json(snapshot, state.node_metric_history[
            state.node_metric_history["date"] == snapshot.date
        ], state.node_features.matrix_at(snapshot.date, snapshot.nodes),
            state.bundle.sectors(), communities)
    ).set_index("id")
    if not node_frame.empty:
        _record("29_node_risk_map", lambda: F.plot_node_risk_map(node_frame))

    try:
        sankey = F.sector_community_sankey(
            communities, state.bundle.sectors(),
            config.artifacts_dir / "figures" / "30_sector_community_sankey.html",
        )
        if sankey is not None:
            out["30_sector_community_sankey"] = str(sankey)
        else:
            writer.skip("30_sector_community_sankey", "plotly not installed")
    except Exception as exc:
        writer.skip("30_sector_community_sankey", str(exc))

    logger.info("Figures written: %d, skipped: %d", len(writer.written), len(writer.skipped))
    return out


def _generate_reports(state: Any, payload: dict[str, Any]) -> None:
    from dynamicgraph.graphs.multiscale import scale_comparison_table
    from dynamicgraph.outputs import reports

    config = state.config
    reports_dir = config.artifacts_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    inventory_path = config.artifacts_dir / "data_audit" / "data_inventory.json"
    inventory = None
    if inventory_path.exists():
        import json

        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        except Exception:
            inventory = None

    reports.write_data_audit_report(reports_dir / "data_audit_report.md", state.bundle, inventory)

    per_window = {
        s.window: s for k, s in state.series_by_key.items()
        if k.startswith(config.graph.core_layer) and s.window > 0
    }
    reports.write_graph_methodology_report(
        reports_dir / "graph_methodology.md",
        config,
        state.series_by_key,
        scale_comparison_table(per_window),
        state.graph_validation,
    )

    if state.experiment is not None:
        from dynamicgraph.training.splits import fold_summary

        reports.write_oos_evaluation_report(
            reports_dir / "oos_evaluation.md",
            state.experiment,
            state.verdict,
            config,
            fold_summary(state.folds) if state.folds else None,
            node_ranking=state.node_ranking_summary,
            node_ranking_verdict=state.node_ranking_verdict,
        )
    if state.ablation is not None and not state.ablation.empty:
        from dynamicgraph.evaluation.ablation import feature_group_contributions

        reports.write_ablation_report(
            reports_dir / "ablation_report.md",
            state.ablation,
            feature_group_contributions(state.ablation),
        )
    if state.record is not None and state.experiment is not None:
        reports.write_model_card(
            reports_dir / "model_card.md", state.record, state.experiment, state.verdict, config, state.bundle
        )
    if getattr(state, "allocation", None):
        reports.write_allocation_report(reports_dir / "allocation_report.md", state.allocation)
    reports.write_investor_summary(
        reports_dir / "investor_summary.md", payload, state.verdict, state.stress_scores
    )
    reports.write_limitations_report(
        reports_dir / "limitations.md", state.bundle, config, state.verdict, state.experiment
    )
    if state.assumptions:
        reports.write_assumptions_report(reports_dir / "assumptions.md", state.assumptions)
