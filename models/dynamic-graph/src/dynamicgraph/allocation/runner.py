r"""Orchestration for the allocation experiment.

The grid is deliberately not a full cross product. Three of the five weight
rules are functions of the covariance *diagonal* only, and every estimator in
`covariance.py` keeps the sample standard deviations on the diagonal by
construction -- so running `inverse_volatility` under four estimators would
produce four identical return streams and four identical rows in the summary,
inviting the reader to count the same result four times.

Only `risk_parity` and `minimum_variance` consume off-diagonal structure, so
only those are crossed with the estimators. That is also where the project's
claim lives: if the sparse precision matrix is a better description of
dependence, it has to show up in a rule that uses dependence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from dynamicgraph.allocation.backtest import (
    AllocationBacktestConfig,
    AllocationBacktestResult,
    run_allocation_backtest,
)
from dynamicgraph.allocation.evaluation import (
    allocation_verdict,
    build_equity_curves,
    compare_against_benchmark,
    estimator_comparison,
    rolling_volatility_comparison,
    summarize_results,
)
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

# (rule, estimators). A rule that ignores off-diagonal terms is run once.
DEFAULT_GRID: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("equal_weight", ("sample",)),
    ("inverse_volatility", ("sample",)),
    ("community_risk_parity", ("sample",)),
    ("risk_parity", ("sample", "ledoit_wolf", "glasso", "diagonal")),
    ("minimum_variance", ("sample", "ledoit_wolf", "glasso", "diagonal")),
)

BENCHMARK_KEY = "equal_weight__sample"


def _communities_by_date(state: Any) -> Mapping[pd.Timestamp, dict[str, int]] | None:
    """Ticker -> community label per date, from the core graph layer."""
    key = state.core_key
    results = state.communities_by_key.get(key) or {}
    if not results:
        logger.info("No community partitions available; community_risk_parity will degrade.")
        return None
    out: dict[pd.Timestamp, dict[str, int]] = {}
    for date, result in results.items():
        labels = getattr(result, "labels", None)
        if labels:
            out[pd.Timestamp(date)] = dict(labels)
    return out or None


def run_allocation_experiment(
    log_returns: pd.DataFrame,
    config: Any,
    communities_by_date: Mapping[pd.Timestamp, dict[str, int]] | None = None,
    grid: tuple[tuple[str, tuple[str, ...]], ...] = DEFAULT_GRID,
) -> dict[str, Any]:
    """Run every (rule, estimator) pair and score them against each other."""
    backtest_config = AllocationBacktestConfig.from_config(config)
    evaluation = getattr(config, "evaluation", None)
    n_bootstrap = int(getattr(evaluation, "bootstrap_iterations", 500) or 500)
    block_length = int(getattr(evaluation, "bootstrap_block_length", 20) or 20)
    seed = int(getattr(config.project, "seed", 42))

    results: list[AllocationBacktestResult] = []
    failures: list[str] = []
    for rule, estimators in grid:
        for estimator in estimators:
            try:
                result = run_allocation_backtest(
                    log_returns,
                    estimator=estimator,
                    rule=rule,
                    config=backtest_config,
                    communities_by_date=communities_by_date,
                )
            except Exception as exc:
                logger.warning("Allocation backtest failed for %s/%s: %s", rule, estimator, exc)
                failures.append(f"{rule}__{estimator}: {exc}")
                continue
            logger.info(
                "%-24s %-12s vol=%.2f%% n=%d rebalances=%d",
                rule,
                estimator,
                100.0 * result.portfolio_returns.std(ddof=1) * np.sqrt(252.0),
                len(result.portfolio_returns),
                len(result.weights),
            )
            results.append(result)

    if not results:
        raise RuntimeError("Every allocation backtest failed; see the warnings above.")

    summary = summarize_results(results)
    benchmark_tests = (
        compare_against_benchmark(
            results, BENCHMARK_KEY, n_bootstrap=n_bootstrap, block_length=block_length, seed=seed
        )
        if any(r.key == BENCHMARK_KEY for r in results)
        else pd.DataFrame()
    )
    estimator_tests = pd.concat(
        [
            estimator_comparison(
                results,
                rule=rule,
                baseline_estimator="sample",
                n_bootstrap=n_bootstrap,
                block_length=block_length,
                seed=seed,
            )
            for rule in ("minimum_variance", "risk_parity")
        ],
        ignore_index=True,
    )
    verdict = allocation_verdict(summary, estimator_tests, benchmark_tests, BENCHMARK_KEY)
    if failures:
        verdict["failed_configurations"] = failures

    return {
        "results": results,
        "summary": summary,
        "benchmark_tests": benchmark_tests,
        "estimator_tests": estimator_tests,
        "verdict": verdict,
        "equity_curves": build_equity_curves(results),
        "rolling_volatility": rolling_volatility_comparison(results),
        "config": backtest_config,
    }


def write_allocation_artifacts(experiment: dict[str, Any], directory: Path) -> list[Path]:
    """Persist the tables a reader needs to check the conclusion themselves."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    frames = {
        "allocation_summary.csv": experiment["summary"],
        "allocation_vs_benchmark.csv": experiment["benchmark_tests"],
        "allocation_estimator_tests.csv": experiment["estimator_tests"],
        "allocation_equity_curves.csv": experiment["equity_curves"],
        "allocation_rolling_volatility.csv": experiment["rolling_volatility"],
    }
    for name, frame in frames.items():
        if frame is None or frame.empty:
            continue
        path = directory / name
        frame.to_csv(path, index=name.endswith(("equity_curves.csv", "rolling_volatility.csv")))
        written.append(path)

    diagnostics = [
        result.diagnostics.assign(key=result.key)
        for result in experiment["results"]
        if not result.diagnostics.empty
    ]
    if diagnostics:
        path = directory / "allocation_diagnostics.csv"
        pd.concat(diagnostics).to_csv(path)
        written.append(path)

    weights = experiment["results"][0]
    latest_weights = weights.weights.tail(1)
    if not latest_weights.empty:
        path = directory / "allocation_latest_weights.csv"
        pd.concat(
            [
                result.weights.tail(1).assign(key=result.key)
                for result in experiment["results"]
                if not result.weights.empty
            ]
        ).to_csv(path)
        written.append(path)

    logger.info("Wrote %d allocation artifact(s) to %s.", len(written), directory)
    return written
