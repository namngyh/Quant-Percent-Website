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
import random
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.strategy import registry
from backend.strategy.engine import BacktestConfig

log = logging.getLogger(__name__)

# A full grid runs about 10 ms per combination on 2 000 candles and 37 ms on
# 20 000, so this cap is roughly a minute of waiting. Beyond it, sweeping every
# cell stops being the right tool.
MAX_COMBINATIONS = 5000

# Random search samples the same space instead of enumerating it. When only a
# couple of parameters actually matter — the usual case — sampling finds the
# good region far sooner than marching through every cell of a large grid.
MAX_SAMPLES = 5000
DEFAULT_SAMPLES = 500

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


def grid_size(ranges: list[ParamRange]) -> int:
    """How many combinations a full sweep of these ranges would produce."""
    total = 1
    for r in ranges:
        total *= len(r.values())
    return total


def build_grid(ranges: list[ParamRange]) -> list[dict]:
    """Cartesian product of every range, as a list of parameter dicts."""
    if not ranges:
        return [{}]

    names = [r.name for r in ranges]
    axes = [r.values() for r in ranges]

    total = grid_size(ranges)
    if total > MAX_COMBINATIONS:
        raise ValueError(
            f"Quét toàn bộ {total:,} tổ hợp sẽ mất quá lâu "
            f"(giới hạn {MAX_COMBINATIONS:,}). "
            "Hãy nới bước nhảy, thu hẹp dải, hoặc chuyển sang chế độ ngẫu nhiên."
        )

    return [dict(zip(names, combo, strict=True)) for combo in itertools.product(*axes)]


def build_random(ranges: list[ParamRange], samples: int, seed: int | None = None) -> list[dict]:
    """Draw distinct random combinations from the same space a grid would cover.

    Returns unique combinations: sampling with replacement would waste the
    budget re-testing cells, and the whole point of the budget is coverage.
    If the space is smaller than the requested sample count, the full space is
    returned — there is nothing to sample.
    """
    if not ranges:
        return [{}]

    samples = max(1, min(samples, MAX_SAMPLES))
    names = [r.name for r in ranges]
    axes = [r.values() for r in ranges]

    if grid_size(ranges) <= samples:
        return [dict(zip(names, combo, strict=True)) for combo in itertools.product(*axes)]

    rng = random.Random(seed)
    seen: set[tuple] = set()
    picked: list[dict] = []

    # Bounded attempts: near-saturated spaces would otherwise spin looking for
    # the last few unseen combinations.
    attempts = 0
    while len(picked) < samples and attempts < samples * 20:
        attempts += 1
        combo = tuple(rng.choice(axis) for axis in axes)
        if combo in seen:
            continue
        seen.add(combo)
        picked.append(dict(zip(names, combo, strict=True)))

    return picked


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
    mode: str = "grid",
    samples: int = DEFAULT_SAMPLES,
    seed: int | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> dict:
    """Run the sweep and return the ranked table plus summary statistics.

    ``mode`` is "grid" (every combination) or "random" (a sample of them).
    """
    if metric not in RANKABLE_METRICS:
        raise ValueError(f"cannot rank by '{metric}'; choose from {RANKABLE_METRICS}")
    if mode not in ("grid", "random"):
        raise ValueError(f"unknown mode '{mode}'; expected 'grid' or 'random'")

    full_size = grid_size(ranges) if ranges else 1
    grid = build_grid(ranges) if mode == "grid" else build_random(ranges, samples, seed)
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
        "mode": mode,
        "space_size": full_size,
        "coverage_pct": (len(rows) / full_size * 100.0) if full_size else 100.0,
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
