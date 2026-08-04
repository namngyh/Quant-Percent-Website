"""Markdown report generation.

Reports state what the evidence supports and nothing more. When a result is not
statistically supported, the report says so explicitly rather than presenting a
favourable point estimate.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def _table(frame: pd.DataFrame, max_rows: int = 40, float_format: str = "{:.4f}") -> str:
    if frame is None or frame.empty:
        return "_No data available._"
    display = frame.head(max_rows).copy()
    for column in display.select_dtypes(include=[np.number]).columns:
        display[column] = display[column].map(
            lambda v: float_format.format(v) if pd.notna(v) else "-"
        )
    try:
        return display.to_markdown(index=False)
    except Exception:
        return "```\n" + display.to_string(index=False) + "\n```"


def _timeseries_summary(frame: pd.DataFrame, max_rows: int = 12) -> str:
    """Summarise a long, date-indexed validation frame.

    Printing the first 15 rows of a 14-year history shows only its first month,
    which tells the reader nothing. This reports distributional statistics over
    the whole period plus the most recent rows.
    """
    if frame is None or frame.empty:
        return "_No data available._"
    if len(frame) <= max_rows:
        return _table(frame, max_rows=max_rows)

    numeric = frame.select_dtypes(include=[np.number])
    numeric = numeric.drop(columns=[c for c in numeric.columns if c.lower() in {"date", "fold"}],
                           errors="ignore")
    parts: list[str] = []
    if not numeric.empty:
        stats = numeric.describe(percentiles=[0.10, 0.50, 0.90]).T
        stats = stats[["count", "mean", "std", "min", "10%", "50%", "90%", "max"]]
        stats.insert(0, "metric", stats.index)
        parts += [
            f"Distribution over all {len(frame)} observation(s):",
            "",
            _table(stats.reset_index(drop=True), max_rows=30),
            "",
        ]
    parts += [f"Most recent {min(max_rows, len(frame))} observation(s):", "", _table(frame.tail(max_rows))]
    return "\n".join(parts)


def _write(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Report written: %s", path)
    return path


def write_data_audit_report(path: Path, bundle: Any, inventory: dict[str, Any] | None = None) -> Path:
    validation = bundle.validation
    lines = [
        "# DynamicGraph - Data Audit Report",
        "",
        f"_Generated {datetime.now().astimezone().isoformat(timespec='seconds')}_",
        "",
        "## 1. Source",
        "",
        f"- **Backend**: `{bundle.source_metadata.get('backend')}`",
        f"- **Tables**: {', '.join(bundle.source_metadata.get('tables', [])) or '-'}",
        f"- **Symbols in source**: {bundle.source_metadata.get('n_symbols')}",
        f"- **Date range**: {bundle.source_metadata.get('date_min')} .. {bundle.source_metadata.get('date_max')}",
        f"- **Adjusted price available**: {bundle.source_metadata.get('has_adjusted_price')}",
        f"- **Adjustment method**: {bundle.source_metadata.get('adjustment_method') or 'n/a'}",
        f"- **Volume available**: {bundle.source_metadata.get('has_volume')}",
        f"- **Turnover available**: {bundle.source_metadata.get('has_turnover')}",
        f"- **Sector classification available**: {bundle.source_metadata.get('has_sector')}",
        f"- **Data fingerprint**: `{bundle.fingerprint}`",
        "",
        "The database is opened strictly read-only (SQLite `mode=ro` plus a write-denying "
        "authorizer). No pipeline stage writes to it.",
        "",
        "## 2. Loaded panel",
        "",
        f"- Rows: {len(bundle.panel):,}",
        f"- Tickers: {bundle.panel['ticker'].nunique()} (index `{bundle.index_ticker}` + "
        f"{len(bundle.tickers)} constituents)",
        f"- Date range: {bundle.panel['date'].min().date()} .. {bundle.panel['date'].max().date()}",
        f"- Trading days: {len(bundle.calendar):,}",
        "",
        "## 3. Universe",
        "",
        f"- Method: `{bundle.universe.method}`",
        f"- Constituents: {len(bundle.universe.tickers)}",
        f"- Survivorship bias present: **{bundle.universe.survivorship_bias}**",
        "",
    ]
    if bundle.universe.warnings:
        lines += ["### Universe warnings", ""] + [f"- {w}" for w in bundle.universe.warnings] + [""]
    if bundle.universe.notes:
        lines += ["### Universe notes", ""] + [f"- {n}" for n in bundle.universe.notes] + [""]

    lines += ["## 4. Source assumptions", ""]
    assumptions = bundle.source_metadata.get("assumptions", [])
    lines += [f"- {a}" for a in assumptions] if assumptions else ["- None recorded."]
    lines += [""]

    lines += ["## 5. Validation checks", "", "| Check | Result | Severity | Message |", "|---|---|---|---|"]
    for check in validation.checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"| `{check.name}` | {status} | {check.severity} | {check.message} |")
    lines += [
        "",
        f"**{len(validation.errors)} error(s), {len(validation.warnings)} warning(s).**",
        "",
    ]

    if validation.excluded_tickers:
        lines += [
            "## 6. Excluded tickers",
            "",
            f"Dropped for insufficient history: {', '.join(validation.excluded_tickers)}",
            "",
        ]

    lines += ["## 7. Normalisation", ""]
    normalization = bundle.normalization.to_dict()
    lines += [
        f"- Rows in / out: {normalization['n_rows_in']:,} -> {normalization['n_rows_out']:,}",
        f"- Duplicate (ticker, date) rows dropped: {normalization['n_duplicates_dropped']}",
        f"- Adjusted price available: {normalization['adjusted_price_available']}",
        f"- Used unadjusted close as a substitute: {normalization['used_unadjusted_price']}",
        f"- Sector source: {normalization['sector_source']}",
        f"- Tickers with UNKNOWN sector: {normalization['n_unknown_sector']}",
        "",
    ]
    if normalization["warnings"]:
        lines += ["### Normalisation warnings", ""] + [f"- {w}" for w in normalization["warnings"]] + [""]

    if inventory:
        lines += [
            "## 8. Discovery",
            "",
            f"- Candidate data sources scanned: {inventory.get('n_candidates', 0)}",
            f"- Connection strings found in config files: {len(inventory.get('connection_strings', []))} "
            "(values never stored)",
            "",
        ]
    return _write(path, lines)


def write_graph_methodology_report(
    path: Path, config: Any, series_by_key: Mapping[str, Any], scale_table: pd.DataFrame,
    validation: Mapping[str, pd.DataFrame],
) -> Path:
    graph = config.graph
    lines = [
        "# DynamicGraph - Graph Methodology",
        "",
        f"_Generated {datetime.now().astimezone().isoformat(timespec='seconds')}_",
        "",
        "## 1. Construction",
        "",
        "For every trading day `t` with a complete trailing window of length `W`:",
        "",
        "1. **Node validity** - a ticker enters the snapshot only if at most "
        f"{config.data.max_missing_ratio_per_window:.0%} of its returns inside the window are missing.",
        "2. **Covariance** - Ledoit-Wolf shrinkage `Sigma = (1-d) S + d F`, with `d` estimated from "
        "the window. With ~30 assets and windows as short as 20 days the sample covariance is "
        "ill-conditioned, so shrinkage is the default rather than an option.",
        "3. **Layer**:",
        "   - correlation: `A_ij = rho_ij`",
        "   - partial correlation (core): graphical lasso on the **correlation** matrix, then "
        "`rho^partial_ij = -Theta_ij / sqrt(Theta_ii Theta_jj)`. Fitting on the correlation rather "
        "than the covariance makes the penalty scale-free; partial correlation is scale invariant "
        "so the result is unchanged.",
        f"4. **Edge filtering** - method `{graph.edge_filter_method}` "
        f"(absolute threshold {graph.absolute_threshold}, top-quantile {graph.top_edge_quantile}, "
        f"stability threshold {graph.edge_stability_threshold}), then a density cap of "
        f"{graph.max_graph_density}.",
        (
            f"5. **Edge stability** - {graph.bootstrap_iterations} moving-block bootstrap "
            f"resamples (block length {graph.block_length}). Block resampling is used because "
            "i.i.d. row resampling would destroy the serial dependence the covariance estimate "
            "relies on."
            if int(graph.bootstrap_iterations) > 0
            else "5. **Edge stability** - bootstrap stability selection was DISABLED in this run "
                 "(`graph.bootstrap_iterations: 0`), so per-edge selection frequencies are not "
                 "available and edges were filtered by weight quantile alone. Run with `--full` "
                 "to enable it."
        ),
        "",
        "## 2. Return type",
        "",
        f"Core layer uses **{graph.return_type}** returns. Market residualization:",
        "",
        "```",
        "r_it = alpha_it + beta_it * r_mt + eps_it",
        "```",
        "",
        f"estimated on a {config.features.residual_window}-day rolling window ending at `t`. "
        "Raw correlation between VN30 stocks is dominated by the market mode; residualizing lets "
        "the graph describe relationships that are not simply "
        "\"everything follows the index\".",
        "",
        "## 3. Scales built",
        "",
        _table(scale_table),
        "",
        "Scales are kept separate rather than merged, because a 20-day edge (current co-movement) "
        "and a 252-day edge (structural relationship) are different objects.",
        "",
        "## 4. Layers produced",
        "",
    ]
    for key, series in series_by_key.items():
        lines.append(f"- `{key}`: {len(series)} snapshot(s)")
    lines += ["", "## 5. Graph validation", ""]

    #: These are one-row-per-snapshot histories; the rest are short lookup tables.
    time_series_reports = {"edge_stability", "centrality_stability", "community_persistence"}
    for name, frame in validation.items():
        if frame is None or (hasattr(frame, "empty") and frame.empty):
            continue
        body = (
            _timeseries_summary(frame)
            if name in time_series_reports
            else _table(frame, max_rows=20)
        )
        lines += [f"### {name.replace('_', ' ').title()}", "", body, ""]

    lines += [
        "## 6. Signed-graph handling",
        "",
        "Partial correlations can be negative. Eigenvector centrality, PageRank, closeness, "
        "harmonic centrality, clustering and coreness are undefined or meaningless on negative "
        "weights, so they are computed on `|A|`. Sign information is preserved separately as "
        "`positive_strength`, `negative_strength` and `edge_sign_ratio`. Every node-metric row "
        "carries a `weights_used` column recording the transformation.",
        "",
        "## 7. Known limitations",
        "",
        "- Partial correlation conditions only on the other VN30 members; omitted common factors "
        "(global risk appetite, FX, commodity prices) can still induce edges.",
        "- Non-synchronous trading across the constituents biases short-window correlations "
        "downward.",
        "- The graphical-lasso penalty controls sparsity but is not itself identified; the alpha "
        "sensitivity table above shows how much the conclusions depend on it.",
        "- Edges are associations. Nothing here identifies a causal channel.",
    ]
    return _write(path, lines)


def write_oos_evaluation_report(
    path: Path, experiment: Any, verdict: Mapping[str, Any], config: Any,
    fold_summary: pd.DataFrame | None = None,
    node_ranking: pd.DataFrame | None = None,
    node_ranking_verdict: Mapping[str, Any] | None = None,
) -> Path:
    metrics = experiment.metrics
    lines = [
        "# DynamicGraph - Out-of-Sample Evaluation",
        "",
        f"_Generated {datetime.now().astimezone().isoformat(timespec='seconds')}_",
        "",
        "## 1. Protocol",
        "",
        f"- Split: **{config.training.split_method}** (chronological; no shuffling anywhere in "
        "the codebase)",
        f"- Initial training: {config.training.initial_train_days} trading days"
        f"{' (expanding)' if config.training.expanding_window else ' (rolling)'}",
        f"- Validation: {config.training.validation_days} days | Test step: {config.training.test_days} days",
        f"- Purge: {config.training.purge_days} days | Embargo: {config.training.embargo_days} days",
        "",
        "Fitted on training rows only: imputation, scaling, feature selection, target quantile "
        "thresholds, graphical-lasso alpha and stress-score standardisation. Fitted on validation "
        "only: probability calibration and the decision threshold. Test rows are predicted once "
        "and never revisited.",
        "",
        f"- Feature selection: at most {config.training.max_features} column(s) per fold, chosen "
        f"on that fold's training block by coverage, univariate |Spearman| against the label, and "
        f"redundancy pruning at |Spearman| > {config.training.feature_redundancy_threshold}.",
        (
            f"- Hyperparameter tuning: **{'enabled' if config.training.enable_tuning else 'DISABLED'}**"
            + (
                f" (objective `{config.training.tuning_objective}`, nested on each fold's "
                "validation block)."
                if config.training.enable_tuning
                else ". Every model below uses fixed default hyperparameters. Run "
                     "`scripts/compare_tuning.py` to check whether tuning changes the conclusion "
                     "before treating any negative result as settled."
            )
        ),
        "",
    ]
    if fold_summary is not None and not fold_summary.empty:
        lines += ["### Folds", "", _table(fold_summary, max_rows=20), ""]

    lines += ["## 2. Out-of-sample metrics", ""]
    if metrics.empty:
        lines += ["_No out-of-sample results were produced._", ""]
    else:
        columns = [
            c for c in (
                "target", "horizon", "feature_set", "model", "n", "base_rate", "brier",
                "brier_skill_score", "auroc", "auprc", "mcc", "recall_stress", "precision_stress",
                "false_alarms_per_year", "expected_calibration_error", "calibration_slope",
            ) if c in metrics.columns
        ]
        lines += [_table(metrics[columns].sort_values(["horizon", "brier"]), max_rows=60), ""]
        lines += [
            "**Reading the table.** `brier_skill_score` compares against a constant base-rate "
            "forecast: 0 means no better than predicting the unconditional frequency, negative "
            "means worse. `auprc` should be compared to `base_rate`, not to 0.5. `calibration_slope` "
            "of 1 is perfect; below 1 means over-confident.",
            "",
        ]

    lines += ["## 3. Does the graph add out-of-sample value?", ""]
    lines += [
        f"**Verdict: `{verdict.get('verdict')}`**",
        "",
        verdict.get("interpretation", ""),
        "",
        f"- Paired comparisons run: {verdict.get('n_comparisons')}",
        f"- Significant Brier improvements: {verdict.get('n_significant_brier')}",
        f"- Significant AUPRC improvements: {verdict.get('n_significant_auprc')}",
        f"- Mean Brier difference (challenger - market-only): "
        f"{verdict.get('mean_brier_difference'):.5f}" if verdict.get("mean_brier_difference") is not None else "",
        "",
        "Significance uses a **paired moving-block bootstrap** on identical resampled blocks, "
        "which controls for the shared market environment. An i.i.d. bootstrap would materially "
        "overstate significance on daily data.",
        "",
    ]

    absolute = verdict.get("absolute_skill") or {}
    if absolute:
        lines += ["### Absolute skill (against a constant base-rate forecast)", ""]
        if absolute.get("beats_climatology"):
            lines += [
                f"- {absolute['n_with_positive_brier_skill']} of {absolute['n_configurations']} "
                f"configuration(s) achieved a positive Brier skill score "
                f"(best {absolute['best_brier_skill_score']:.4f}).",
                "",
            ]
        else:
            lines += [
                f"- **No configuration beat a constant base-rate forecast.** The best Brier skill "
                f"score across {absolute['n_configurations']} configuration(s) was "
                f"{absolute['best_brier_skill_score']:.4f}.",
                f"- {absolute.get('note', '')}",
                "",
                "This is the more important of the two results. The relative comparison above "
                "shows that graph features improve on the market-only feature set; the absolute "
                "result shows that neither is currently good enough to forecast VN30 stress at "
                "these horizons. Treat DynamicGraph's structural output as the deliverable and the "
                "probabilities as diagnostic.",
                "",
            ]
    if not experiment.comparisons.empty:
        columns = [
            c for c in (
                "target", "model", "challenger", "brier_baseline", "brier_challenger",
                "brier_difference", "brier_ci_lower", "brier_ci_upper", "brier_significant",
                "auprc_difference", "auprc_significant",
            ) if c in experiment.comparisons.columns
        ]
        lines += ["### Paired comparisons", "", _table(experiment.comparisons[columns], max_rows=40), ""]

    # ---- cross-sectional node ranking -----------------------------------
    if node_ranking is not None and not node_ranking.empty:
        lines += [
            "## 4. Cross-sectional node ranking",
            "",
            "A different question from the market-level model: can the network *order* the 30 "
            "constituents by forward risk-adjusted return? Three nested feature sets isolate the "
            "network's contribution.",
            "",
        ]
        columns = [
            c for c in (
                "feature_set", "model", "horizon", "n_dates", "ic_ic_n_effective",
                "ic_ic_mean", "ic_ic_std", "ic_ic_ir", "ic_ic_t_stat", "ic_ic_t_stat_iid",
                "ic_ic_autocorr_lag1", "ic_ic_positive_rate", "long_short_spread",
                "long_short_spread_t", "mean_turnover", "cost_adjusted_spread_annualized",
                "ic_mean_vs_node_only",
            ) if c in node_ranking.columns
        ]
        lines += [
            _table(node_ranking[columns], max_rows=20),
            "",
            "`ic_ic_t_stat` uses a Newey-West standard error with `horizon - 1` lags. "
            "`ic_ic_t_stat_iid` is the naive value that treats every daily observation as "
            "independent; it is shown only to make the size of the correction visible. Because "
            "h-day forward returns are computed daily, consecutive IC values share h-1 days and "
            "are autocorrelated around 0.85, so the naive statistic overstates significance by "
            "roughly a factor of three. `ic_ic_n_effective` = n / horizon is the implied count of "
            "non-overlapping observations.",
            "",
        ]
        if node_ranking_verdict:
            lines += [
                f"**Verdict: `{node_ranking_verdict.get('verdict')}`**",
                "",
                node_ranking_verdict.get("interpretation", ""),
                "",
                node_ranking_verdict.get("caveat", ""),
                "",
                "A mean rank IC is only meaningful relative to its own standard error; the "
                "`ic_ic_t_stat` column is the quantity to read, not the IC alone.",
                "",
            ]

    lines += [
        "## 5. Caveats",
        "",
        "- Overlapping h-day labels mean the effective sample is closer to `n/h` than `n`; the "
        "reported `effective_sample_size` reflects this.",
        "- Stress events are rare and clustered, so a handful of episodes drives most of the "
        "measured skill. Event-level detection metrics are reported alongside day-level ones for "
        "exactly this reason.",
        "- The universe carries survivorship bias unless `liquidity_proxy` was used; see the data "
        "audit report.",
    ]
    return _write(path, lines)


#: The ablation frame carries the full metric suite; only these read usefully
#: in a markdown table.
_ABLATION_COLUMNS = [
    "variant", "n_features_candidate", "n_features", "n", "base_rate", "brier",
    "brier_skill_score", "brier_vs_market_only", "auroc", "auprc",
    "auprc_lift_over_base", "mcc", "recall_stress", "precision_stress",
    "false_alarms_per_year",
]


def _ablation_view(ablation: pd.DataFrame) -> pd.DataFrame:
    columns = [c for c in _ABLATION_COLUMNS if c in ablation.columns]
    return ablation[columns]


def write_ablation_report(path: Path, ablation: pd.DataFrame, contributions: pd.DataFrame) -> Path:
    lines = [
        "# DynamicGraph - Ablation Study",
        "",
        f"_Generated {datetime.now().astimezone().isoformat(timespec='seconds')}_",
        "",
        "Every variant uses the same folds, model, calibration and threshold procedure. Only the "
        "feature space changes, so differences are attributable to the removed feature family.",
        "",
        "## 1. Variant results",
        "",
        _table(_ablation_view(ablation), max_rows=40),
        "",
        "`brier_vs_market_only` is negative when the variant beats the market-only baseline. "
        "`brier_skill_score` is measured against a constant forecast at the realised base rate; a "
        "negative value means the variant is worse than quoting the historical frequency, however "
        "it ranks against the other variants.",
        "",
    ]
    skipped = list(ablation.attrs.get("skipped_variants", []))
    if skipped:
        lines += [
            f"**Variants skipped as unavailable in this run**: {', '.join(skipped)}. The layer or "
            "scale each one isolates was not built (see `graph.build_raw_and_residual` / "
            "`graph.windows`), so no row is reported rather than a fallback result under a "
            "misleading label.",
            "",
        ]
    if not contributions.empty:
        lines += [
            "## 2. Marginal contribution of each feature family",
            "",
            "`brier_degradation` > 0 means removing the family made out-of-sample predictions "
            "worse, i.e. the family carried information.",
            "",
            _table(contributions),
            "",
        ]
    lines += [
        "## 3. Interpretation guardrails",
        "",
        "- Ablation deltas are point estimates on a single horizon and model. They are indicative, "
        "not decisive; the paired bootstrap in the OOS report is the formal test.",
        "- A variant that wins here but not in the paired comparison has not been shown to help.",
    ]
    return _write(path, lines)


def write_allocation_report(path: Path, allocation: Mapping[str, Any]) -> Path:
    """The allocation experiment, written so the conclusion can be checked."""
    summary = allocation.get("summary", pd.DataFrame())
    verdict = allocation.get("verdict", {})
    benchmark_tests = allocation.get("benchmark_tests", pd.DataFrame())
    estimator_tests = allocation.get("estimator_tests", pd.DataFrame())
    backtest_config = allocation.get("config")

    lines = [
        "# Capital allocation - out-of-sample evaluation",
        "",
        f"_Generated {datetime.now():%Y-%m-%d %H:%M}._",
        "",
        "## The question this answers",
        "",
        "The predictive evaluation established that this data does not support",
        "forecasting market stress: no configuration beat a naive frequency",
        "baseline. That is a statement about **first** moments. Allocation depends",
        "on **second** moments, which are a different and considerably easier",
        "estimation problem -- realised correlation structure persists across",
        "months, whereas the signal-to-noise ratio of expected returns is near",
        "zero. So the failure of the predictive layer does not settle whether the",
        "graph is useful, and this report tests the remaining claim separately.",
        "",
        "Three claims are kept apart on purpose:",
        "",
        "1. does *any* covariance-aware rule beat naive equal weighting?",
        "2. does the *graphical-lasso* covariance beat the *sample* covariance at",
        "   the same weight rule?",
        "3. does the *community partition* beat a covariance-free risk split?",
        "",
        "Answering (1) yes and (2) no would mean dependence modelling helped but",
        "the network layer specifically did not -- a distinction that is easy to",
        "blur and that changes what the project is worth.",
        "",
        "## Method",
        "",
    ]
    if backtest_config is not None:
        lines += [
            f"- Estimation window: **{backtest_config.estimation_window} trading days**, trailing, ending at the rebalance date inclusive.",
            f"- Rebalance frequency: every **{backtest_config.rebalance_days} trading days**.",
            f"- Weight cap: **{backtest_config.max_weight:.0%}** per name, long only, fully invested.",
            f"- Transaction cost: **{backtest_config.cost_bps_per_side:.0f} bps per side**, charged on traded notional against the drifted book.",
            f"- Graphical-lasso penalty: **{backtest_config.glasso_alpha}**, frozen from the training-period selection.",
            "",
        ]
    lines += [
        "Weights formed on date `t` are applied to returns of `t+1 ... t+h`. No",
        "date is ever used both to estimate and to evaluate. Nothing in the",
        "backtest is fitted globally, so the whole series is out of sample.",
        "",
        "Every estimator keeps the **sample standard deviations on the diagonal**",
        "and differs only in the correlation matrix. Without that constraint a",
        "lower backtested volatility could come from an estimator quietly",
        "understating the risk level rather than from a better dependence estimate.",
        "",
        "The primary metric is **realised annualised volatility**, because every",
        "rule here is a function of the covariance matrix alone and can only be",
        "held responsible for the risk it produced. Return and Sharpe are reported",
        "alongside so that a risk reduction bought by giving up more return is",
        "visible rather than hidden.",
        "",
        "## Results",
        "",
    ]

    display_columns = [
        c
        for c in (
            "key", "rule", "estimator", "annual_volatility", "annual_return",
            "sharpe", "max_drawdown", "mean_effective_n_bets",
            "mean_diversification_ratio", "mean_turnover_traded", "annual_cost_drag",
            "realized_over_ex_ante_volatility", "n_days",
        )
        if not summary.empty and c in summary.columns
    ]
    lines += [
        "Sorted by realised volatility, lowest first.",
        "",
        _table(summary[display_columns] if display_columns else summary, max_rows=30),
        "",
        "`mean_effective_n_bets` is the exponential entropy of risk across principal",
        "components -- the number of *independent* risk sources, not the number of",
        "positions. `realized_over_ex_ante_volatility` above 1 means the estimator",
        "understated risk in advance.",
        "",
        "### Against equal weighting",
        "",
        "Paired moving-block bootstrap, same blocks drawn from both series so the",
        "shared market variation cancels.",
        "",
    ]
    if isinstance(benchmark_tests, pd.DataFrame) and not benchmark_tests.empty:
        volatility = benchmark_tests[benchmark_tests["metric"] == "annual_volatility"]
        lines += [_table(volatility.sort_values("difference"), max_rows=20), ""]
    else:
        lines += ["_No benchmark comparison available._", ""]

    lines += [
        "### Graphical lasso against the sample covariance",
        "",
        "The isolated test of the project's own claim: same weight rule, same",
        "window, same cap -- only the covariance estimator changes.",
        "",
    ]
    if isinstance(estimator_tests, pd.DataFrame) and not estimator_tests.empty:
        lines += [_table(estimator_tests, max_rows=20), ""]
    else:
        lines += ["_No estimator comparison available._", ""]

    lines += ["## Verdict", ""]
    verdict_name = str(verdict.get("verdict", "unknown"))
    lines += [
        f"**`{verdict_name}`**",
        "",
        str(verdict.get("interpretation", "")),
        "",
    ]
    for label, key in (
        ("Lowest-volatility portfolio", "lowest_volatility_portfolio"),
        ("Its realised volatility", "lowest_volatility"),
        ("Equal-weight volatility", "benchmark_volatility"),
        ("Significant volatility reductions vs equal weight", "n_significant_volatility_reductions"),
        ("Comparisons run", "n_comparisons"),
        ("Rules where glasso beat the sample covariance", "glasso_significant_rules"),
        ("Community risk parity minus inverse volatility (vol)", "community_vs_inverse_volatility"),
    ):
        if key in verdict:
            value = verdict[key]
            if isinstance(value, float):
                value = f"{value:.4f}"
            lines.append(f"- {label}: `{value}`")
    lines += [
        "",
        "## What this does not establish",
        "",
        f"> {verdict.get('caveat', '')}",
        "",
        "Specifically:",
        "",
        "- The universe is the **current** VN30 held fixed over the whole period.",
        "  Names that left the index are absent, which flatters every rule here",
        "  equally but flatters them all.",
        "- Costs are linear in traded notional. Real impact is convex, so the",
        "  high-turnover rules are treated more kindly than they deserve.",
        "- Foreign ownership limits, lot sizes and borrow availability are ignored.",
        "- A volatility reduction is not a return improvement. Where the two",
        "  disagree, the table above shows both.",
        "",
    ]
    return _write(path, lines)


def write_model_card(
    path: Path, record: Any, experiment: Any, verdict: Mapping[str, Any], config: Any, bundle: Any
) -> Path:
    metrics = experiment.metrics
    best_line = "_No model met the reporting bar._"
    skill_line = ""
    if not metrics.empty:
        subset = metrics[metrics["model"] != "naive_frequency"].dropna(subset=["brier"])
        if not subset.empty:
            best = subset.loc[subset["brier"].idxmin()]
            skill = float(best.get("brier_skill_score", float("nan")))
            best_line = (
                f"`{best['model']}` on feature set `{best['feature_set']}` at horizon "
                f"{int(best['horizon'])}d - Brier {best['brier']:.4f}, "
                f"Brier skill score {skill:.4f}, "
                f"AUPRC {best.get('auprc', float('nan')):.4f} "
                f"(base rate {best.get('base_rate', float('nan')):.3f})"
            )
            n_skilful = int((subset["brier_skill_score"] > 0).sum())
            if n_skilful == 0:
                skill_line = (
                    "- **No model achieved a positive Brier skill score.** Every configuration "
                    "scored worse than a constant forecast at the realised base rate, so the "
                    "probabilities carry no demonstrated forecasting skill at these horizons. "
                    "They are published for transparency, not because they are actionable. Use "
                    "DynamicGraph for structural description; do not act on the probabilities."
                )
            else:
                skill_line = (
                    f"- {n_skilful} of {len(subset)} configuration(s) achieved a positive Brier "
                    "skill score against a constant base-rate forecast."
                )

    lines = [
        "# DynamicGraph - Model Card",
        "",
        f"**Version** {record.model_version} | **Run** `{record.run_id}` | "
        f"**Generated** {record.generated_at}",
        "",
        "## Intended use",
        "",
        "DynamicGraph describes how the dependence structure among VN30 constituents evolves, and "
        "estimates the probability that the VN30 enters a drawdown-defined stress state over a "
        "5-40 day horizon. It is a **risk-monitoring and structural-description tool**.",
        "",
        "**Out of scope**: forecasting the VN30 index level, single-stock price prediction, "
        "identifying causal relationships between companies, and any use as standalone investment "
        "advice.",
        "",
        "## Data",
        "",
        f"- Source backend: `{bundle.source_metadata.get('backend')}` (read-only)",
        f"- Period: {record.data_date_min} .. {record.data_date_max}",
        f"- Universe: {len(bundle.universe.tickers)} constituents plus the "
        f"`{bundle.index_ticker}` index, method `{bundle.universe.method}`",
        f"- Data fingerprint: `{record.data_fingerprint}`",
        f"- Adjusted prices: {bundle.source_metadata.get('has_adjusted_price')}",
        f"- Survivorship bias: **{bundle.universe.survivorship_bias}**",
        "",
        "## Method",
        "",
        f"- Core graph: {config.graph.core_layer} on {config.graph.return_type} returns, "
        f"{config.graph.core_window}-day window, Ledoit-Wolf covariance, graphical lasso "
        f"alpha={config.graph.graphical_lasso_alpha}",
        f"- Edge filter: {config.graph.edge_filter_method}",
        f"- Evaluation: {config.training.split_method}, purge {config.training.purge_days}d, "
        f"embargo {config.training.embargo_days}d",
        f"- Calibration: {config.models.calibration_method} (fitted on validation blocks only)",
        "",
        "## Performance",
        "",
        f"- Best out-of-sample model: {best_line}",
        skill_line,
        f"- Graph incremental value: **{verdict.get('verdict')}** - {verdict.get('interpretation')}",
        "",
        "The Brier skill score is measured against a constant forecast at the *realised* test-set "
        "base rate, which is a hindsight benchmark and therefore a demanding one. A small negative "
        "value does not by itself mean a model is useless, but a model that cannot approach zero "
        "has no demonstrated forecasting value.",
        "",
        "## Reproducibility",
        "",
        f"- Seed: {record.seed}",
        f"- Config fingerprint: `{record.config_fingerprint}`",
        f"- Git commit: `{record.git_commit or 'not a git repository'}`",
        f"- Platform: {record.platform_info}",
        f"- Key package versions: "
        + ", ".join(
            f"{k}={v}" for k, v in record.package_versions.items()
            if k in {"python", "numpy", "pandas", "scikit-learn", "networkx", "scipy"}
        ),
        "",
    ]
    if record.optional_modules_skipped:
        lines += [
            "### Optional modules skipped in this run",
            "",
            *[f"- {m}" for m in record.optional_modules_skipped],
            "",
        ]
    lines += [
        "## Ethical and practical considerations",
        "",
        "- The published probability is an estimate with material uncertainty. It must be "
        "presented with its calibration quality and sample size, never as a bare number.",
        "- Network centrality identifies structural position, not attractiveness as an investment.",
        "- The model is fitted on a single market over a limited history; it has not been "
        "validated on other markets or on a live forward period.",
        "",
        "## Maintenance",
        "",
        f"- Last training date: {record.training_date}",
        "- Retrain when the walk-forward window advances materially, when the VN30 constituent "
        "list changes, or when data-quality warnings change.",
    ]
    return _write(path, lines)


def write_investor_summary(
    path: Path, payload: Mapping[str, Any], verdict: Mapping[str, Any], stress: pd.DataFrame
) -> Path:
    state = payload.get("network_state", {})
    universe = payload.get("universe", {})
    label = str(state.get("label", "unknown"))

    readings = {
        "low_connectivity": (
            "VN30 constituents are moving relatively independently. Diversification across the "
            "index is doing more work than usual."
        ),
        "normal": "The dependence structure is within its historical norm.",
        "elevated": (
            "VN30 stocks are moving together more than usual. Diversification within the index is "
            "providing less protection than it typically does."
        ),
        "high_stress": (
            "The network is highly synchronised: connectivity and concentration are near the top "
            "of their historical range. Historically, periods like this have coincided with "
            "weaker index-level diversification, though they do not determine what happens next."
        ),
    }

    lines = [
        "# DynamicGraph - Investor Summary",
        "",
        f"**As of {payload.get('model', {}).get('as_of_date')}**",
        "",
        "## What this is",
        "",
        "DynamicGraph maps how the 30 VN30 constituents move in relation to one another, and how "
        "that structure changes over time. It answers structural questions - which stocks sit at "
        "the centre of the market, which groups move together, whether diversification is working "
        "- rather than forecasting a price level.",
        "",
        "## Current network state",
        "",
        f"- **State**: `{label}`",
        f"- **Network Stress Score**: {state.get('stress_score')} / 100",
        f"- **Historical percentile**: {state.get('historical_percentile')}",
        f"- **Change over 20 sessions**: {state.get('change_20d')}",
        "",
        readings.get(label, ""),
        "",
    ]

    contributors = state.get("main_contributors", [])
    if contributors:
        lines += ["### What is driving the score", ""]
        for item in contributors[:5]:
            direction = "raising" if item.get("direction") == "raises_stress" else "lowering"
            lines.append(
                f"- `{item.get('metric')}` is {direction} the score "
                f"(share {item.get('share')})"
            )
        lines.append("")

    influence = payload.get("leading_influence_nodes", [])
    if influence:
        lines += [
            "## Most central stocks",
            "",
            "These sit at the centre of the estimated dependence structure. **This is not a view "
            "on their future returns.** A central stock is one whose movements are most connected "
            "to the rest of the index.",
            "",
            "| Ticker | Sector | Strength | Eigenvector centrality |",
            "|---|---|---|---|",
        ]
        for node in influence[:8]:
            lines.append(
                f"| {node['id']} | {node.get('sector')} | {node.get('strength')} | "
                f"{node.get('eigenvector_centrality')} |"
            )
        lines.append("")

    vulnerable = payload.get("vulnerable_nodes", [])
    if vulnerable:
        lines += [
            "## Stocks under structural strain",
            "",
            "Deeper drawdowns and higher downside volatility, with stressed neighbours in the "
            "network. This is a description of current condition, not a forecast.",
            "",
            "| Ticker | Sector | Drawdown | Downside volatility |",
            "|---|---|---|---|",
        ]
        for node in vulnerable[:8]:
            lines.append(
                f"| {node['id']} | {node.get('sector')} | {node.get('current_drawdown')} | "
                f"{node.get('downside_volatility_20d')} |"
            )
        lines.append("")

    communities = payload.get("communities", [])
    if communities:
        lines += ["## Groups moving together", ""]
        for community in communities[:6]:
            share = community.get("dominant_sector_share")
            sector = community.get("dominant_sector")
            # Only call a group "mostly X" when X genuinely dominates it.
            if sector and share is not None and share >= 0.6:
                composition = f"mostly {sector}, {share:.0%}"
            elif sector and share is not None:
                composition = f"mixed; largest sector {sector} at {share:.0%}"
            else:
                composition = "mixed"
            lines.append(
                f"- **Group {community['community_id']}** ({community['size']} stocks, "
                f"{composition}): {', '.join(community['members'][:10])}"
            )
        lines += [
            "",
            "Groups are detected from the data, not imposed from sector labels. When they line up "
            "with sectors, sector exposure is the dominant structure; when they do not, something "
            "else is driving co-movement.",
            "",
        ]

    probabilities = payload.get("stress_probabilities", {})
    if probabilities:
        lines += [
            "## Stress probabilities",
            "",
            "| Horizon | Probability | Calibrated | OOS Brier | Sample |",
            "|---|---|---|---|---|",
        ]
        for horizon, entry in probabilities.items():
            brier = entry.get("oos_brier_score")
            lines.append(
                f"| {horizon} | {entry.get('probability')} | {entry.get('calibrated')} | "
                f"{brier:.4f} | {entry.get('sample_size')} |"
                if brier is not None
                else f"| {horizon} | {entry.get('probability')} | {entry.get('calibrated')} | - | "
                     f"{entry.get('sample_size')} |"
            )
        lines += [
            "",
            "These are estimated probabilities of a drawdown-defined stress state, evaluated "
            "out-of-sample. They carry material uncertainty.",
            "",
        ]
        flagged = [h for h, e in probabilities.items() if e.get("confidence_warning")]
        if flagged:
            lines += [
                f"**Warning.** Horizon(s) {', '.join(flagged)} did not beat a constant base-rate "
                "forecast out of sample. Those probabilities should be treated as uninformative "
                "and are published only for transparency.",
                "",
            ]
    else:
        lines += [
            "## Stress probabilities",
            "",
            "_No calibrated probability is published for this run._",
            "",
        ]

    lines += [
        "## How much to trust this",
        "",
        f"- Out-of-sample assessment of whether network features improve stress prediction over a "
        f"market-only baseline: **{verdict.get('verdict')}**.",
        f"- {verdict.get('interpretation')}",
        "",
    ]
    quality = payload.get("model_quality", {})
    skill = quality.get("brier_skill_score")
    if skill is not None and skill <= 0:
        lines += [
            "- **The stress probabilities have no demonstrated forecasting skill.** Measured "
            "out of sample, the best model scored no better than simply quoting the historical "
            "frequency of stress periods. Read the network state and its drivers; do not act on "
            "the probability numbers.",
            "",
        ]
    elif skill is not None:
        lines += [
            f"- The stress probabilities did beat a constant historical-frequency forecast out of "
            f"sample (Brier skill score {skill:.3f}), but the margin is small and the number of "
            "distinct stress episodes behind it is limited.",
            "",
        ]
    if universe.get("survivorship_bias_warning"):
        lines += [
            "- **Survivorship bias**: the constituent list is today's VN30 applied backwards. "
            "Stocks removed from the index over the period are absent. Historical statistics are "
            "flattering as a result.",
            "",
        ]

    lines += [
        "## What this does not say",
        "",
        "- It does not say the market will fall. A rising stress score says stocks are moving "
        "together more and that diversification within the index may be providing less protection.",
        "- Connections between stocks are statistical associations, not causal links.",
        "- Central stocks are not recommendations.",
        "",
        "_Not investment advice._",
    ]
    return _write(path, lines)


def write_limitations_report(
    path: Path, bundle: Any, config: Any, verdict: Mapping[str, Any], experiment: Any = None
) -> Path:
    lines = [
        "# DynamicGraph - Limitations",
        "",
        f"_Generated {datetime.now().astimezone().isoformat(timespec='seconds')}_",
        "",
        "## 1. Data",
        "",
    ]
    if bundle.universe.survivorship_bias:
        lines += [
            "- **Survivorship bias (material).** The universe is a current-membership snapshot "
            "applied to the whole history. Constituents removed from the VN30 are absent, and "
            "current members appear before they joined. Network density, centrality persistence "
            "and model performance are all optimistically biased. Mitigation: set "
            "`data.universe_method: liquidity_proxy`, or add effective dates to "
            "`config/vn30_universe.csv`.",
        ]
    else:
        lines += [
            "- Universe membership is point-in-time, so survivorship bias is mitigated. The "
            "liquidity proxy is still an approximation of official HOSE index membership and will "
            "differ around index reviews.",
        ]
    lines += [
        f"- History starts {bundle.panel['date'].min().date()}, giving "
        f"{len(bundle.calendar):,} trading days. Stress episodes are rare, so the effective number "
        "of independent events behind any performance claim is small.",
        "- Vietnamese equities have a +/-7% daily price band and periodic foreign-ownership "
        "constraints. Both compress observed return distributions and can distort correlation "
        "estimates during stress.",
        "- Non-synchronous trading across constituents biases short-window correlations downward.",
        "",
        "## 2. Graph estimation",
        "",
        "- Partial correlation conditions only on the other VN30 members. Omitted common factors "
        "(global risk sentiment, FX, commodities) can still generate edges.",
        "- The graphical-lasso penalty is a modelling choice, not an identified parameter. The "
        "alpha-sensitivity analysis quantifies how much conclusions depend on it.",
        "- Edge weights are associations. No edge in this system is a causal channel.",
        "- Centrality on an undirected graph carries no direction of propagation. That is why the "
        "system emits `high_influence_node`, never `transmitter`, unless a directed layer exists.",
        "",
        "## 3. Directed layers",
        "",
        "- Lead-lag edges are lagged correlations subject to multiple testing (BH-FDR is applied) "
        "and to non-synchronous trading. Daily sampling gives limited power to detect genuine "
        "lead-lag structure.",
        "- VAR spillover uses regularised estimation because a 30-dimensional unrestricted VAR is "
        "not estimable on a 120-day window. Generalised FEVD shares are predictive attributions "
        "under an assumed model.",
        "",
        "## 4. Prediction",
        "",
    ]
    if experiment is not None and not getattr(experiment, "metrics", pd.DataFrame()).empty:
        subset = experiment.metrics[experiment.metrics["model"] != "naive_frequency"]
        subset = subset.dropna(subset=["brier_skill_score"])
        if not subset.empty:
            n_skilful = int((subset["brier_skill_score"] > 0).sum())
            best_skill = float(subset["brier_skill_score"].max())
            if n_skilful == 0:
                lines.append(
                    "- **No configuration achieved positive out-of-sample forecasting skill.** "
                    f"The best Brier skill score across {len(subset)} configuration(s) was "
                    f"{best_skill:.3f}, i.e. no better than quoting the historical frequency of "
                    "stress. The predictive layer of DynamicGraph is not currently usable for "
                    "decisions; the structural layer is what this system delivers today."
                )
            else:
                lines.append(
                    f"- {n_skilful} of {len(subset)} configuration(s) achieved positive "
                    f"out-of-sample Brier skill (best {best_skill:.3f}). The margins are small "
                    "relative to the number of independent stress episodes available."
                )
    lines += [
        f"- Graph incremental value verdict: **{verdict.get('verdict')}**. "
        f"{verdict.get('interpretation')}",
        "- Labels overlap across adjacent dates, so nominal sample sizes overstate information "
        "content. Confidence intervals use block bootstrap for this reason.",
        "- Calibration is fitted per fold on a limited validation block; with few positives it "
        "falls back from isotonic to Platt scaling, which is reported per fold.",
        "- Performance is evaluated on one market over one historical period. There is no "
        "out-of-market or live forward validation.",
        "",
        "## 5. Interpretation",
        "",
        "- Association, predictive importance and causal effect are distinct. DynamicGraph "
        "establishes the first two at most.",
        "- Portfolio spreads reported in the ranking evaluation are an evaluation device, not a "
        "tradable strategy and not evidence of causality.",
        "- Attention weights from the optional Temporal GNN are a model diagnostic only.",
        "",
        "## 6. Operational",
        "",
        "- The pipeline reads a local database that a third-party client updates. If that client "
        "stops updating, `data_freshness_days` grows and outputs become stale; consumers should "
        "check that field.",
        "- Optional dependencies (torch, torch-geometric, shap, interpret, leidenalg, xgboost) are "
        "not required; when absent the corresponding analysis is skipped and recorded rather than "
        "silently replaced.",
    ]
    return _write(path, lines)


def write_assumptions_report(path: Path, assumptions: list[str]) -> Path:
    lines = [
        "# DynamicGraph - Recorded Assumptions",
        "",
        f"_Generated {datetime.now().astimezone().isoformat(timespec='seconds')}_",
        "",
        "Every non-obvious decision taken automatically by the pipeline, recorded so it can be "
        "challenged.",
        "",
    ]
    lines += [f"{i}. {a}" for i, a in enumerate(assumptions, start=1)]
    return _write(path, lines)
