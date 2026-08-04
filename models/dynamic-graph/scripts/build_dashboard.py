#!/usr/bin/env python
"""Build the offline dashboard from the artifacts on disk.

    python scripts/build_dashboard.py
    python scripts/build_dashboard.py --open

Reads `artifacts/` and writes a single self-contained `dashboard/index.html`
with the data inlined, so the page opens straight off the filesystem with no
server, no network access and no build toolchain.

Series are downsampled before they are inlined -- weekly for the graph metric
history, month-end for the allocation curves. A 3,500-point daily line is
indistinguishable from its weekly resampling at screen resolution, and carrying
the extra points would triple the file for no visible gain.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

REPO = Path(__file__).resolve().parent.parent
ARTIFACTS = REPO / "artifacts"
DASHBOARD = REPO / "dashboard"


def _round(value, digits: int = 6):
    """JSON-safe rounding; NaN and inf become null rather than invalid JSON."""
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return value
    return round(value, digits) if np.isfinite(value) else None


def _records(frame: pd.DataFrame, digits: int = 6) -> list[dict]:
    return [
        {k: _round(v, digits) if isinstance(v, (int, float, np.number, bool, np.bool_)) else v
         for k, v in row.items()}
        for _, row in frame.iterrows()
    ]


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        print(f"  ! missing {path.relative_to(REPO)}", file=sys.stderr)
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def _read_json(path: Path, default=None):
    if not path.exists():
        print(f"  ! missing {path.relative_to(REPO)}", file=sys.stderr)
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def build_payload() -> dict:
    payload: dict = {}

    # ---- allocation ------------------------------------------------------
    summary = _read_csv(ARTIFACTS / "allocation/allocation_summary.csv")
    keep = ["key", "rule", "estimator", "annual_volatility", "annual_return", "sharpe",
            "sortino", "max_drawdown", "calmar", "var_95_daily", "cvar_95_daily",
            "hit_rate", "mean_effective_n_bets", "mean_effective_n_weights",
            "mean_diversification_ratio", "mean_max_weight", "mean_turnover_traded",
            "annual_cost_drag", "realized_over_ex_ante_volatility",
            "mean_condition_number", "mean_off_diagonal_zeros", "n_days", "n_rebalances"]
    if not summary.empty:
        payload["allocation_summary"] = _records(summary[[c for c in keep if c in summary.columns]])
    payload["estimator_tests"] = _records(_read_csv(ARTIFACTS / "allocation/allocation_estimator_tests.csv"))
    payload["benchmark_tests"] = _records(_read_csv(ARTIFACTS / "allocation/allocation_vs_benchmark.csv"))

    equity = _read_csv(ARTIFACTS / "allocation/allocation_equity_curves.csv", index_col=0, parse_dates=True)
    if not equity.empty:
        monthly = equity.resample("ME").last().dropna(how="all")
        payload["equity"] = {
            "dates": [d.strftime("%Y-%m") for d in monthly.index],
            "series": {c: [_round(v, 4) for v in monthly[c]] for c in monthly.columns},
        }
    rolling = _read_csv(ARTIFACTS / "allocation/allocation_rolling_volatility.csv", index_col=0, parse_dates=True)
    if not rolling.empty:
        monthly = rolling.resample("ME").last().dropna(how="all")
        payload["rolling_vol"] = {
            "dates": [d.strftime("%Y-%m") for d in monthly.index],
            "series": {c: [_round(v, 5) for v in monthly[c]] for c in monthly.columns},
        }

    weights = _read_csv(ARTIFACTS / "allocation/allocation_latest_weights.csv", index_col=0)
    if not weights.empty:
        out = {}
        for key, group in weights.groupby("key"):
            row = group.drop(columns=["key"]).iloc[0]
            out[key] = {k: _round(v, 5) for k, v in row.items()
                        if pd.notna(v) and float(v) > 1e-6}
        payload["latest_weights"] = out
        payload["weights_date"] = str(weights.index[0])

    # ---- prediction ------------------------------------------------------
    oos = _read_csv(ARTIFACTS / "predictions/oos_metrics.csv")
    if not oos.empty:
        keep = ["horizon", "model", "feature_set", "brier", "brier_skill_score", "auroc",
                "auprc", "base_rate", "mcc", "recall_stress", "precision_stress",
                "expected_calibration_error", "false_alarms_per_year", "n", "n_folds"]
        oos = oos[[c for c in keep if c in oos.columns]].sort_values(["horizon", "brier"])
        payload["oos_metrics"] = _records(oos)

    # ---- run summary -----------------------------------------------------
    run = _read_json(ARTIFACTS / "reports/run_summary.json", {}) or {}
    payload["run"] = {
        "verdict": run.get("verdict", {}),
        "node_ranking_verdict": run.get("node_ranking_verdict", {}),
        "node_ranking_summary": run.get("node_ranking_summary"),
        "n_folds": run.get("n_folds"),
        "snapshots_per_key": run.get("snapshots_per_key"),
        "data": {k: v for k, v in (run.get("data") or {}).items()
                 if k in ("date_min", "date_max", "n_tickers", "n_rows", "index_ticker")},
    }

    # ---- network ---------------------------------------------------------
    latest = _read_json(ARTIFACTS / "latest/latest_dynamicgraph.json", {}) or {}
    payload["network_state"] = latest.get("network_state")
    payload["as_of"] = (latest.get("model") or {}).get("as_of_date")
    payload["universe"] = latest.get("universe")

    node_fields = ("id", "rank", "sector", "community", "strength", "eigenvector_centrality",
                   "pagerank", "betweenness_centrality", "degree", "volatility_20d",
                   "neighbor_risk", "participation_coefficient")
    payload["nodes"] = [
        {k: (_round(v, 5) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
         for k, v in node.items() if k in node_fields}
        for node in (_read_json(ARTIFACTS / "latest/nodes.json", []) or [])
    ]
    payload["edges"] = [
        {"s": e.get("source"), "t": e.get("target"),
         "w": _round(e.get("signed_weight", e.get("weight")), 4)}
        for e in (_read_json(ARTIFACTS / "latest/edges.json", []) or [])
    ]
    payload["communities"] = _read_json(ARTIFACTS / "latest/communities.json", []) or []

    # ---- metric history --------------------------------------------------
    history = _read_csv(ARTIFACTS / "latest/network_history.csv", index_col=0, parse_dates=True)
    if not history.empty:
        wanted = ("stress_score", "graph_density", "spectral_radius", "market_mode_share",
                  "number_of_communities", "centrality_concentration", "modularity",
                  "avg_abs_partial_correlation", "algebraic_connectivity")
        columns = [c for c in wanted if c in history.columns]
        weekly = history[columns].resample("W").last().dropna(how="all")
        payload["history"] = {
            "dates": [d.strftime("%Y-%m-%d") for d in weekly.index],
            "series": {c: [_round(v, 4) for v in weekly[c]] for c in columns},
        }

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open", action="store_true", help="Open the page when it is built.")
    parser.add_argument("--out", default=None, help="Output path (default dashboard/index.html).")
    args = parser.parse_args()

    template_path = DASHBOARD / "template.html"
    if not template_path.exists():
        print(f"Template not found: {template_path}", file=sys.stderr)
        return 1

    print("Reading artifacts ...")
    payload = build_payload()
    for key, value in payload.items():
        size = len(value) if hasattr(value, "__len__") else 1
        print(f"  {key:24s} {size}")

    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str)
    if "</script" in blob:
        print("Payload contains a closing script tag; refusing to inline.", file=sys.stderr)
        return 1

    template = template_path.read_text(encoding="utf-8")
    if "__PAYLOAD__" not in template:
        print("Template has no __PAYLOAD__ placeholder.", file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else DASHBOARD / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(template.replace("__PAYLOAD__", blob), encoding="utf-8")
    print(f"\nWrote {out}  ({out.stat().st_size / 1024:.0f} KB)")
    print(f"Open it directly:  {out}")

    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
