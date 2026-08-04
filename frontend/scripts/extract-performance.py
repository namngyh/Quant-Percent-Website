"""Extract real Model-Modus results into static JSON for the website.

Run once; the output is committed to the site repo so the pages never
depend on the research project being present.
"""

import json
import os

SRC = r"D:\VuaBip123\Model-Modus\results"
OUT = r"D:\VuaBip123\quantpercent\config\performance"

os.makedirs(OUT, exist_ok=True)

PROVENANCE = {
    "source_project": "Model-Modus (mlforquant)",
    "source_files": [],
    "generated_by": "MODE=final, SEED=31, brain frozen 2026-07-02",
    "code_version": "pre-2026-07-04",
    "extracted_at": "2026-07-25",
    "notional_points": 1000,
    "point_value_vnd": 100000,
}


def histogram(values, bin_size):
    """Bucket per-trade returns; bucket label = lower edge."""
    buckets = {}
    for v in values:
        b = round((v // bin_size) * bin_size, 4)
        buckets[b] = buckets.get(b, 0) + 1
    return [
        {"bucket": k, "count": buckets[k]} for k in sorted(buckets)
    ]


# The research project reports percentages against a fixed notional of
# 1,000 VN30 index points (= 100,000,000 VND at 100k VND/point) with
# drawdown taken against the running equity peak. Verified: this
# reproduces both net_pct and max_dd_pct of the source reports exactly.
NOTIONAL_POINTS = 1000.0


def equity_from_returns(returns):
    """Cumulative points/percent + drawdown from peak, per trade number."""
    points = []
    equity = 0.0
    peak_equity = NOTIONAL_POINTS
    for i, r in enumerate(returns, start=1):
        equity += r
        account = NOTIONAL_POINTS + equity
        peak_equity = max(peak_equity, account)
        points.append(
            {
                "trade": i,
                "equity": round(equity, 2),
                "equity_pct": round(equity / NOTIONAL_POINTS, 5),
                "drawdown": round(account - peak_equity, 2),
                "drawdown_pct": round((account - peak_equity) / peak_equity, 5),
            }
        )
    return points


# --- 1. Validation 2024 -------------------------------------------------
val = json.load(open(os.path.join(SRC, "last_validation.json"), encoding="utf-8"))
returns = [round(r, 4) for r in val["returns"]]

validation = {
    "provenance": {**PROVENANCE, "source_files": ["results/last_validation.json"]},
    "period": {"start": "2024-01-02", "end": "2024-12-31", "years": 1.0},
    "trades": {
        "total": val["trades"],
        "long": val["long"],
        "short": val["short"],
        "skipped": val["skip"],
    },
    "returns": returns,
    "equity": equity_from_returns(returns),
    "distribution": histogram(returns, 2.0),
    "exit_reasons": [
        {"id": "sl", "share": val["er_sl"]},
        {"id": "signal", "share": val["er_signal"]},
        {"id": "brain", "share": val["er_brain"]},
        {"id": "expiry", "share": val["er_expiry"]},
        {"id": "trail", "share": val["er_trail"]},
    ],
    "tier3": val["tier3"],
    "full": val["full"],
}
json.dump(
    validation,
    open(os.path.join(OUT, "validation-2024.json"), "w", encoding="utf-8"),
    ensure_ascii=False,
    indent=1,
)

# --- 2. Walk-forward 2024-2026 -----------------------------------------
wf = json.load(open(os.path.join(SRC, "walk_forward.json"), encoding="utf-8"))
walk = {
    "provenance": {**PROVENANCE, "source_files": ["results/walk_forward.json"],
                   "generated_by": "anchored walk-forward, SEED=100"},
    "period": {"start": "2024-01-02", "end": "2026-06-30", "years": 2.5},
    "folds": [
        {
            "fold": f["fold"],
            "train_from": f["train"][0],
            "train_to": f["train"][1],
            "test_year": f["test"],
            "net_points": round(f["net"], 1),
            "trades": f["n"],
            "long": f["nL"],
            "short": f["nS"],
            "win_rate": round(f["wr"], 1),
            "payoff": round(f["rr"], 2),
            "max_drawdown_points": round(f["mdd"], 1),
            "partial_year": f["test"] == 2026,
        }
        for f in wf["folds"]
    ],
    "combined": wf["combined"],
    "tier3": wf["tier3"],
    "full": wf["full"],
}
json.dump(
    walk,
    open(os.path.join(OUT, "walk-forward.json"), "w", encoding="utf-8"),
    ensure_ascii=False,
    indent=1,
)

# --- 3. Multi-seed test 2025-2026 --------------------------------------
ms = json.load(open(os.path.join(SRC, "multiseed_test.json"), encoding="utf-8"))
boot = json.load(open(os.path.join(SRC, "bootstrap.json"), encoding="utf-8"))
stress = json.load(open(os.path.join(SRC, "cost_stress.json"), encoding="utf-8"))

ci = {}
with open(os.path.join(SRC, "ci_metrics.csv"), encoding="utf-8") as fh:
    header = fh.readline()
    for line in fh:
        parts = line.strip().split(",")
        if len(parts) < 6:
            continue
        ci[parts[0]] = {
            "mean": float(parts[1]),
            "ci95_lo": float(parts[2]),
            "ci95_hi": float(parts[3]),
        }

rows = sorted(ms["rows"], key=lambda r: r["profit"])
median_row = rows[len(rows) // 2]
median_returns = [round(r, 4) for r in median_row["returns"]]

seed_profits = sorted(r["profit"] for r in ms["rows"])
seed_hist = histogram(seed_profits, 50.0)

multiseed = {
    "provenance": {
        **PROVENANCE,
        "source_files": [
            "results/multiseed_test.json",
            "results/ci_metrics.csv",
            "results/bootstrap.json",
            "results/cost_stress.json",
        ],
        "generated_by": "50 seeds, MODE=final (test opened once)",
    },
    "period": {"start": "2025-01-02", "end": "2026-06-30", "years": 1.4},
    "n_seeds": len(ms["rows"]),
    "pct_positive": ms["pct_positive"],
    "long_bias_seeds": ms["long_bias"],
    "short_bias_seeds": ms["short_bias"],
    "profit": ms["profit"],
    "payoff": ms["rr"],
    "ci95": {
        k: ci[k]
        for k in [
            "net_profit", "profit_factor", "sharpe", "sortino", "max_dd",
            "win_rate", "rr", "upi", "calmar", "total_trades", "exposure",
            "annual_ret", "ulcer", "expectancy", "recovery", "avg_win",
            "avg_loss", "max_cons_l", "pct_months", "equity_r2",
        ]
        if k in ci
    },
    "bootstrap": {
        "n": boot["B"],
        "block_len": boot.get("block_len"),
        "final_median": round(boot["final_median"], 1),
        "final_mean": round(boot["final_mean"], 1),
        "var5": round(boot["final_5pct_var"], 1),
        "payoff_mean": boot["rr_mean"],
        "payoff_ci90": [round(x, 2) for x in boot["rr_mean_ci90"]],
        "prob_payoff_gt1": boot["mean_P_rr_gt1"],
    },
    "cost_stress": {
        "fee_tax_points": stress["fee_tax_pts"],
        "slippage_points": stress["slippage_pts"],
        "scenarios": [
            {
                "cost_points": s["cost"],
                "profit_mean": round(s["profit_mean"], 1),
                "profit_min": round(s["profit_min"], 1),
                "ci95": [round(s["profit_ci95"][0], 1), round(s["profit_ci95"][1], 1)],
                "pct_positive": s["pct_pos"],
                "payoff_mean": round(s["rr_mean"], 2),
                "win_rate": round(s["wr_mean"], 1),
                "max_drawdown_points": round(s["maxdd_mean"], 1),
            }
            for s in stress["scenarios"]
        ],
    },
    "seed_distribution": seed_hist,
    "median_seed": {
        "seed": median_row["seed"],
        "trades": median_row["trades"],
        "long": median_row["long"],
        "short": median_row["short"],
        "net_points": median_row["profit"],
        "win_rate": median_row["wr"],
        "payoff": median_row["rr"],
        "max_drawdown_points": round(median_row["maxdd"], 1),
        "full": median_row["full"],
        "equity": equity_from_returns(median_returns),
        "distribution": histogram(median_returns, 5.0),
    },
}
json.dump(
    multiseed,
    open(os.path.join(OUT, "multiseed-test.json"), "w", encoding="utf-8"),
    ensure_ascii=False,
    indent=1,
)

print("validation trades:", validation["trades"], "equity pts:", len(validation["equity"]))
print("walk folds:", len(walk["folds"]), "combined net:", walk["combined"]["net"])
print("multiseed seeds:", multiseed["n_seeds"], "median seed:", multiseed["median_seed"]["seed"],
      "equity pts:", len(multiseed["median_seed"]["equity"]))
