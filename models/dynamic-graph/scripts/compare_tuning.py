#!/usr/bin/env python
"""Does hyperparameter tuning change the out-of-sample conclusion?

The headline finding is that no configuration beats a constant base-rate
forecast. That claim is only safe if it survives tuning, so this script reruns a
focused subset of the walk-forward experiment with Optuna enabled and reports
the tuned-vs-untuned difference on identical folds.

    python scripts/compare_tuning.py --config config/local.yaml --horizon 20 --trials 15

Nested protocol, unchanged from the main pipeline: the outer loop is the purged
walk-forward, the inner loop tunes on that fold's validation block only. No
tuning decision ever sees a test row.
"""

from __future__ import annotations

import argparse
import sys
import time

import _bootstrap  # noqa: F401  (adds src/ to sys.path)
import pandas as pd

from dynamicgraph import pipeline as P
from dynamicgraph.config import load_config
from dynamicgraph.logging_config import get_logger, setup_logging
from dynamicgraph.models.baselines import build_model_zoo
from dynamicgraph.models.registry import FeatureSetBuilder, flatten_graph_metrics
from dynamicgraph.training.reproducibility import set_global_seed
from dynamicgraph.training.splits import folds_from_config
from dynamicgraph.training.tuning import make_tuner
from dynamicgraph.training.walk_forward import run_walk_forward

logger = get_logger("compare_tuning")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/local.yaml")
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--trials", type=int, default=15)
    parser.add_argument(
        "--models",
        default="logistic_elasticnet,logistic_l2,hist_gradient_boosting",
        help="Comma-separated; only models with a search space can be tuned.",
    )
    parser.add_argument("--feature-sets", default="market,graph,combined")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    setup_logging("INFO", None, False)
    set_global_seed(int(config.project.seed))

    logger.info("Rebuilding state (data -> features -> graphs -> network) ...")
    state = P.PipelineState(config=config)
    state = P.stage_data(state)
    state = P.stage_features(state)
    state = P.stage_graphs(state)
    state = P.stage_network(state)

    index = state.market_features.index
    graph_features = flatten_graph_metrics(state.metrics_by_key, index)
    if state.stress_scores is not None:
        stress = state.stress_scores.reindex(index)
        for column in ("stress_raw", "stress_score", "stress_change_5d", "stress_change_20d"):
            if column in stress.columns:
                graph_features[f"descriptive_{column}"] = stress[column]
    builder = FeatureSetBuilder(state.market_features, graph_features, index=index)
    folds = state.folds or folds_from_config(index, config)

    forward_column = f"future_drawdown_{args.horizon}d"
    if forward_column not in state.targets.forward.columns:
        logger.error("Horizon %d unavailable.", args.horizon)
        return 1
    target_values = state.targets.forward[forward_column]
    quantile = float(config.targets.stress_quantile)

    zoo = build_model_zoo(config, "classification")
    model_names = [m.strip() for m in args.models.split(",") if m.strip() in zoo]
    feature_sets = [f.strip() for f in args.feature_sets.split(",")]

    rows: list[dict] = []
    for tuned in (False, True):
        run_config = load_config(args.config)
        run_config.training.enable_tuning = tuned
        run_config.training.optuna_trials_full = args.trials
        run_config.training.optuna_trials_fast = args.trials
        tuner = make_tuner(run_config) if tuned else None

        for feature_set in feature_sets:
            features = builder.build(feature_set)
            for name in model_names:
                start = time.time()
                result = run_walk_forward(
                    features=features,
                    target_values=target_values,
                    folds=folds,
                    model_spec=zoo[name],
                    config=run_config,
                    horizon=args.horizon,
                    target_name=f"tuning_{'on' if tuned else 'off'}",
                    feature_set=feature_set,
                    quantile=quantile,
                    tuner=tuner,
                )
                if result.predictions.empty:
                    continue
                metrics = result.oos_metrics()
                rows.append(
                    {
                        "tuned": tuned,
                        "feature_set": feature_set,
                        "model": name,
                        "brier": metrics.get("brier"),
                        "brier_skill_score": metrics.get("brier_skill_score"),
                        "auprc": metrics.get("auprc"),
                        "auroc": metrics.get("auroc"),
                        "mcc": metrics.get("mcc"),
                        "n": metrics.get("n"),
                        "seconds": round(time.time() - start, 1),
                    }
                )
                logger.info(
                    "tuned=%s %s/%s -> Brier %.4f (skill %.4f) in %.0fs",
                    tuned, feature_set, name,
                    metrics.get("brier", float("nan")),
                    metrics.get("brier_skill_score", float("nan")),
                    time.time() - start,
                )

    frame = pd.DataFrame(rows)
    if frame.empty:
        logger.error("No results produced.")
        return 1

    pivot = frame.pivot_table(
        index=["feature_set", "model"], columns="tuned",
        values=["brier", "brier_skill_score", "auprc"],
    )
    pivot.columns = [f"{a}_{'tuned' if b else 'untuned'}" for a, b in pivot.columns]
    pivot["brier_improvement"] = pivot["brier_untuned"] - pivot["brier_tuned"]
    pivot["skill_improvement"] = pivot["brier_skill_score_tuned"] - pivot["brier_skill_score_untuned"]

    out = config.artifact_path("metrics", "tuning_comparison.csv")
    frame.to_csv(out, index=False)
    pivot.round(5).to_csv(out.with_name("tuning_comparison_pivot.csv"))

    print("\n" + "=" * 92)
    print(f"TUNING COMPARISON - horizon {args.horizon}d, {args.trials} trials, {len(folds)} folds")
    print("=" * 92)
    print(pivot.round(4).to_string())

    best_tuned = frame[frame["tuned"]]["brier_skill_score"].max()
    best_untuned = frame[~frame["tuned"]]["brier_skill_score"].max()
    print("\nBest Brier skill score:")
    print(f"  untuned : {best_untuned:.4f}")
    print(f"  tuned   : {best_tuned:.4f}")
    if best_tuned > 0:
        print("\n  => Tuning produced a configuration that BEATS climatology. The 'no skill' "
              "conclusion must be revised.")
    else:
        print("\n  => Even tuned, no configuration beats a constant base-rate forecast. "
              "The 'no skill' conclusion survives tuning.")
    print(f"\nWritten to {out}")
    print("=" * 92 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
