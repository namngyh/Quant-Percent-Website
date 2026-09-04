"""Grid-search parameter optimisation.

Sweeps a strategy across every combination in the given ranges and ranks the
results by a chosen metric.

A word on what this is for. Picking the single best cell of a grid is the
easiest way to fool yourself: with enough combinations, some of them look
excellent purely by luck. So the result carries the whole ranked table plus
summary statistics — how many combinations were profitable, the median result,
and how far the winner sits above that median. A winner that towers over the
median on an otherwise unprofitable grid is usually noise, not an edge.
"""

from __future__ import annotations

import itertools
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.strategy import registry
from backend.strategy.engine import BacktestConfig

log = logging.getLogger(__name__)

# Guards against a sweep that would run for hours by accident.
MAX_COMBINATIONS = 2000

RANKABLE_METRICS = (
    "sharpe",
    "sortino",
    "total_return_pct",
    "cagr_pct",
    "profit_factor",
    "win_rate_pct",
    "vs_buy_hold_pct",
)


@dataclass
class ParamRange:
    """An inclusive sweep for one parameter."""

    name: str
    start: float
    stop: float
    step: float

    def values(self) -> list[float | int]:
        if self.step <= 0:
            raise ValueError(f"'{self.name}': step must be positive")
        if self.stop < self.start:
            raise ValueError(f"'{self.name}': stop is below start")

        count = int(math.floor((self.stop - self.start) / self.step)) + 1
        raw = [self.start + i * self.step for i in range(count)]

        # Integer-looking sweeps should stay integers so the UI and the
        # strategy see 20, not 20.000000000000004.
        if all(float(v).is_integer() for v in (self.start, self.stop, self.step)):
            return [int(round(v)) for v in raw]
        return [round(v, 10) for v in raw]


def build_grid(ranges: list[ParamRange]) -> list[dict]:
    """Cartesian product of every range, as a list of parameter dicts."""
    if not ranges:
        return [{}]

    names = [r.name for r in ranges]
    axes = [r.values() for r in ranges]

    total = 1
    for axis in axes:
        total *= len(axis)
    if total > MAX_COMBINATIONS:
        raise ValueError(
            f"{total:,} combinations exceeds the limit of {MAX_COMBINATIONS:,}. "
            "Widen the steps or sweep fewer parameters at once."
        )

    return [dict(zip(names, combo, strict=True)) for combo in itertools.product(*axes)]


def _sort_key(row: dict, metric: str) -> float:
    value = row["metrics"].get(metric, 0.0)
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        # Infinite profit factor means "no losing trades", usually off one or
        # two trades. Rank it last rather than letting it win the grid.
        return float("-inf")
    return float(value)


def optimize(
    strategy_id: str,
    df: pd.DataFrame,
    timeframe: str,
    ranges: list[ParamRange],
    config: BacktestConfig | None = None,
    metric: str = "sharpe",
    top_n: int = 50,
    progress_cb: Callable[[int, int], None] | None = None,
) -> dict:
    """Run the sweep and return the ranked table plus summary statistics."""
    if metric not in RANKABLE_METRICS:
        raise ValueError(f"cannot rank by '{metric}'; choose from {RANKABLE_METRICS}")

    grid = build_grid(ranges)
    total = len(grid)
    rows: list[dict] = []
    failures: list[dict] = []

    for i, params in enumerate(grid):
        try:
            result = registry.run_strategy(strategy_id, df, timeframe, params, config)
        except Exception as exc:
            # One bad parameter combination must not abort the sweep.
            failures.append({"params": params, "error": f"{type(exc).__name__}: {exc}"})
            continue

        m = result["metrics"]
        rows.append(
            {
                "params": params,
                "metrics": {
                    "sharpe": m["sharpe"],
                    "sortino": m["sortino"],
                    "total_return_pct": m["total_return_pct"],
                    "cagr_pct": m["cagr_pct"],
                    "max_drawdown_pct": m["max_drawdown_pct"],
                    "win_rate_pct": m["win_rate_pct"],
                    "profit_factor": (
                        m["profit_factor"] if math.isfinite(m["profit_factor"]) else None
                    ),
                    "num_trades": m["num_trades"],
                    "vs_buy_hold_pct": m["vs_buy_hold_pct"],
                    "exposure_pct": m["exposure_pct"],
                    "ruined": m["ruined"],
                },
            }
        )

        if progress_cb:
            progress_cb(i + 1, total)

    rows.sort(key=lambda r: _sort_key(r, metric), reverse=True)

    returns = np.array([r["metrics"]["total_return_pct"] for r in rows], dtype="float64")
    scores = np.array([_sort_key(r, metric) for r in rows], dtype="float64")
    finite = scores[np.isfinite(scores)]

    summary = {
        "combinations": total,
        "completed": len(rows),
        "failed": len(failures),
        "profitable": int((returns > 0).sum()) if returns.size else 0,
        "profitable_pct": float((returns > 0).mean() * 100.0) if returns.size else 0.0,
        "median_return_pct": float(np.median(returns)) if returns.size else 0.0,
        "best_score": float(finite[0]) if finite.size else 0.0,
        "median_score": float(np.median(finite)) if finite.size else 0.0,
        "metric": metric,
    }

    # A winner far above the median of a mostly-losing grid is the classic
    # shape of an overfit result. Say so rather than leaving it to be noticed.
    spread = np.std(finite, ddof=1) if finite.size > 1 else 0.0
    summary["best_z_score"] = (
        float((summary["best_score"] - summary["median_score"]) / spread) if spread > 0 else 0.0
    )
    summary["overfit_warning"] = bool(
        summary["profitable_pct"] < 30.0 and summary["best_z_score"] > 2.5
    )

    # Buy-and-hold over the same window, so a "winning" grid can still be
    # recognised as worse than doing nothing.
    first_close = float(df["close"].iloc[0])
    last_close = float(df["close"].iloc[-1])
    summary["buy_hold_return_pct"] = (last_close / first_close - 1.0) * 100.0

    return {
        "strategy_id": strategy_id,
        "timeframe": timeframe,
        "summary": summary,
        "results": rows[:top_n],
        "failures": failures[:20],
    }
