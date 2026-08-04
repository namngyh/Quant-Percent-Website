"""Summarize OOS results and apply the pre-registered default-mode rules.

Scenario-mode rule (declared before results were seen):
  1. variational_posterior if it improves CRPS or WIS vs point_estimate OOS
     AND its 90/95% coverage is closer to nominal than point_estimate.
  2. else posterior_mean if that one satisfies the same test.
  3. else keep point_estimate.

Regime-classifier rule:
  Replace the EBM only if the Bayesian regime head beats it on the majority
  of {brier, log_loss, macro_f1, recall_bear, recall_stress} on EVERY
  horizon (aggregated over folds). Otherwise EBM stays production.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def scenario_decision(summary: pd.DataFrame, bootstrap: pd.DataFrame) -> dict:
    detail = {}
    votes = []
    for horizon, group in summary.groupby("horizon"):
        rows = group.set_index("scenario_mode")
        entry = {}
        for mode in rows.index:
            entry[mode] = {
                "crps": float(rows.loc[mode, "crps"]),
                "wis": float(rows.loc[mode, "wis"]),
                "coverage_90_error": abs(float(rows.loc[mode, "coverage_90"]) - 0.90),
                "coverage_95_error": abs(float(rows.loc[mode, "coverage_95"]) - 0.95),
                "width_90": float(rows.loc[mode, "width_90"]),
            }
        point = entry.get("point_estimate")
        choice = "point_estimate"
        for candidate in ("variational_posterior", "posterior_mean_mc"):
            cand = entry.get(candidate)
            if cand is None or point is None:
                continue
            improves_score = cand["crps"] < point["crps"] or cand["wis"] < point["wis"]
            coverage_ok = (
                cand["coverage_90_error"] <= point["coverage_90_error"]
                or cand["coverage_95_error"] <= point["coverage_95_error"]
            )
            if improves_score and coverage_ok:
                choice = candidate
                break
        entry["chosen"] = choice
        ci = bootstrap[
            (bootstrap["horizon"] == horizon)
            & (bootstrap["benchmark"] == "point_estimate")
            & (bootstrap["metric"].isin(["crps", "wis"]))
        ]
        entry["vb_vs_point_ci_excludes_zero"] = {
            str(r["metric"]): bool(r["ci_excludes_zero"]) and r["mean_diff_vb_minus_benchmark"] < 0
            for _, r in ci.iterrows()
        }
        detail[str(horizon)] = entry
        votes.append(choice)
    final = max(set(votes), key=votes.count)
    return {"per_horizon": detail, "votes": votes, "default_scenario_mode": final}


def classifier_decision(aggregated: pd.DataFrame) -> dict:
    metrics_better_high = ["macro_f1", "recall_bear", "recall_stress"]
    metrics_better_low = ["brier", "log_loss"]
    detail = {}
    head_wins_all = True
    for horizon, group in aggregated.groupby("horizon"):
        rows = group.set_index("model")
        if "EBM" not in rows.index or "Bayesian regime head" not in rows.index:
            continue
        ebm = rows.loc["EBM"]
        head = rows.loc["Bayesian regime head"]
        wins = sum(float(head[m]) > float(ebm[m]) for m in metrics_better_high)
        wins += sum(float(head[m]) < float(ebm[m]) for m in metrics_better_low)
        total = len(metrics_better_high) + len(metrics_better_low)
        detail[str(horizon)] = {
            "head_wins": int(wins),
            "criteria": total,
            "ebm": {m: float(ebm[m]) for m in metrics_better_high + metrics_better_low},
            "head": {m: float(head[m]) for m in metrics_better_high + metrics_better_low},
        }
        if wins <= total / 2:
            head_wins_all = False
    return {
        "per_horizon": detail,
        "production_classifier": "Bayesian regime head" if (detail and head_wins_all) else "EBM",
        "rule": "head must win majority of {brier, log_loss, macro_f1, recall_bear, recall_stress} on every horizon",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution-dir", default="outputs/distribution_oos_vb")
    parser.add_argument("--regime-head-dir", default="outputs/regime_head_benchmark")
    parser.add_argument("--output", default="outputs/latest/vb_decisions.json")
    args = parser.parse_args()

    decisions: dict = {}
    distribution = Path(args.distribution_dir)
    if (distribution / "distribution_metrics_summary.csv").exists():
        summary = pd.read_csv(distribution / "distribution_metrics_summary.csv")
        bootstrap = pd.read_csv(distribution / "bootstrap_distribution_differences.csv")
        decisions["scenario"] = scenario_decision(summary, bootstrap)
    head_dir = Path(args.regime_head_dir)
    if (head_dir / "classification_metrics_aggregated.csv").exists():
        aggregated = pd.read_csv(head_dir / "classification_metrics_aggregated.csv")
        decisions["classifier"] = classifier_decision(aggregated)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(decisions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(decisions, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
