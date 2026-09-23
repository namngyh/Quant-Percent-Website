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

from backend.strategy.base import normalize_signals
from backend.strategy.engine import run_backtest
from backend.i18n import bi
from backend.strategy import registry
from backend.strategy.engine import BacktestConfig
from backend.strategy.metrics import BARS_PER_YEAR

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


def _key(value) -> str:
    """Grid axis values compare by rounded string, not by float identity."""
    if value is None:
        return "\x00"
    try:
        return f"{float(value):.10g}"
    except (TypeError, ValueError):
        return str(value)


def _neighbourhood(rows: list[dict], ranges: list[ParamRange], metric: str) -> dict:
    """Does the winner sit on a plateau, or on a single spike?

    Picking the best cell of a grid picks the maximum of however many random
    variables the grid has cells. The ranked table cannot tell the two apart:
    a genuine optimum and a lucky spike both appear as "highest score".

    What separates them is the neighbourhood. A real edge degrades gently when
    a parameter moves one step — the cells around it are also good. A spike is
    surrounded by ordinary cells, which means the exact winning values matter,
    which means they were fitted to this particular sample and will not
    reproduce.

    Measured as a percentile rather than a ratio: the neighbours' median score
    is placed within the score distribution of the whole grid. A ratio would
    need a denominator, and scores here are routinely negative or near zero —
    the same trap as the K-ratio (§2.6) and walk-forward efficiency.
    """
    if not ranges or len(rows) < 3:
        return {"available": False, "reason": bi(
            "Cần ít nhất 3 tổ hợp và một dải tham số để xét lân cận.",
            "Needs at least 3 combinations and a swept range to look at neighbours.",
        )}

    axes = {r.name: r.values() for r in ranges}
    names = [r.name for r in ranges]
    # Position of each value along its own axis, so "one step away" is exact
    # regardless of step size or floating point.
    index_of = {
        name: {_key(v): i for i, v in enumerate(values)} for name, values in axes.items()
    }

    def coords(params: dict) -> tuple | None:
        out = []
        for name in names:
            i = index_of[name].get(_key(params.get(name)))
            if i is None:
                return None
            out.append(i)
        return tuple(out)

    scored: dict[tuple, float] = {}
    for row in rows:
        c = coords(row["params"])
        score = _sort_key(row, metric)
        if c is not None and math.isfinite(score):
            scored[c] = score
    if len(scored) < 3:
        return {"available": False, "reason": bi(
            "Không đủ tổ hợp chấm điểm được để xét lân cận.",
            "Not enough scored combinations to look at neighbours.",
        )}

    all_scores = np.array(sorted(scored.values()), dtype="float64")

    def percentile_of(value: float) -> float:
        # Midpoint of the tied block, not its upper edge.
        #
        # `side="right"` alone counts every equal score as "below", which on a
        # grid full of ties is catastrophic: a spike of 1.0 standing on eight
        # cells all scoring 0.10 put its own neighbours (0.10) at the 89th
        # percentile, so the sharpest possible spike and a smooth hill both
        # reported "plateau, 89". Averaging the two edges puts a tied value in
        # the middle of its block, which is what a rank should mean.
        lo = float(np.searchsorted(all_scores, value, side="left"))
        hi = float(np.searchsorted(all_scores, value, side="right"))
        return (lo + hi) / 2.0 / all_scores.size * 100.0

    winner = rows[0]
    origin = coords(winner["params"])
    if origin is None:
        return {"available": False, "reason": bi(
            "Tổ hợp thắng không nằm trên lưới đang quét.",
            "The winning combination is not on the grid being swept.",
        )}

    # Immediate neighbours: one step along exactly one axis. Diagonals are left
    # out on purpose — they are two changes, and a plateau one step wide in
    # every single direction is already the thing being tested for.
    neighbours = []
    missing = 0
    for axis in range(len(names)):
        for delta in (-1, 1):
            c = list(origin)
            c[axis] += delta
            if not (0 <= c[axis] < len(axes[names[axis]])):
                continue
            value = scored.get(tuple(c))
            if value is None:
                missing += 1     # random mode never visited this cell
            else:
                neighbours.append(value)

    if not neighbours:
        return {"available": False, "reason": bi(
            "Không tổ hợp lân cận nào được chạy — chế độ ngẫu nhiên bỏ sót chúng.",
            "No neighbouring combination was run — random mode skipped them.",
        )}

    median = float(np.median(neighbours))
    pct = percentile_of(median)
    worst = float(np.min(neighbours))

    # A plateau: the cells around the winner are themselves near the top of the
    # grid. A spike: they are ordinary, so the winner's exact values carry it.
    if pct >= 75.0:
        code, verdict = "plateau", bi(
            "Các tổ hợp ngay cạnh tổ hợp thắng cũng nằm trong nhóm dẫn đầu. "
            "Lợi thế suy giảm từ từ khi tham số đổi một bước, đây là dấu hiệu "
            "của một vùng tối ưu thật chứ không phải một ô may mắn.",
            "The cells immediately next to the winner are themselves near the "
            "top of the grid. The edge degrades gently when a parameter moves "
            "one step, which is the shape of a real optimum rather than a "
            "lucky cell.",
        )
    elif pct >= 50.0:
        code, verdict = "ridge", bi(
            "Lân cận của tổ hợp thắng chỉ ở mức trên trung bình. Có thể có "
            "lợi thế, nhưng nó nhạy với tham số — đổi một bước là mất phần lớn.",
            "The winner's neighbourhood is only above average. There may be an "
            "edge, but it is parameter-sensitive: one step away loses most of it.",
        )
    else:
        code, verdict = "spike", bi(
            "Các tổ hợp ngay cạnh tổ hợp thắng chỉ ở mức tầm thường của lưới. "
            "Nghĩa là đúng bộ giá trị này mới thắng, và một bộ giá trị chỉ "
            "thắng ở đúng một điểm thì gần như chắc chắn đã khớp vào nhiễu của "
            "chính mẫu dữ liệu này. Đừng giao dịch bằng nó.",
            "The cells immediately next to the winner are merely ordinary for "
            "this grid. That means these exact values are what won, and a set "
            "of values that wins at exactly one point has almost certainly "
            "fitted the noise in this particular sample. Do not trade it.",
        )

    return {
        "available": True,
        "code": code,
        "verdict": verdict,
        "neighbours_found": len(neighbours),
        "neighbours_missing": missing,
        "neighbour_median_score": median,
        "neighbour_worst_score": worst,
        "neighbour_median_percentile": pct,
        "winner_score": _sort_key(winner, metric),
    }


def _deflated_winner(rows: list[dict], bar_returns, timeframe: str) -> dict:
    """Deflated Sharpe on the winner, using the dispersion the sweep measured.

    `sharpe_tests` has to approximate the cross-trial Sharpe dispersion when it
    is called on a single backtest, because one backtest cannot see the other
    trials. The sweep kept every cell's Sharpe, so here it is measured.
    """
    # Imported here rather than at module scope. This module is on the server's
    # boot path; backend.analysis.stats pulls scipy.stats, which measured 561 ms
    # of the 1 244 ms it took to import the app at all. Deflation runs once per
    # sweep, so paying that cost then rather than at every start-up is free.
    from backend.analysis.stats import sharpe_tests

    sharpes = np.array(
        [r["metrics"]["sharpe"] for r in rows
         if r["metrics"]["sharpe"] is not None
         and math.isfinite(r["metrics"]["sharpe"])],
        dtype="float64",
    )
    if sharpes.size < 2 or bar_returns is None or len(bar_returns) < 30:
        return {"available": False, "reason": bi(
            "Cần ít nhất 2 tổ hợp chạy được và 30 nến để khử phồng Sharpe.",
            "Deflating Sharpe needs at least 2 completed combinations and 30 bars.",
        )}
    dispersion = float(sharpes.std(ddof=1))
    if dispersion <= 0:
        return {"available": False, "reason": bi(
            "Mọi tổ hợp cho cùng một Sharpe, không có độ phân tán để khử phồng.",
            "Every combination gave the same Sharpe; no dispersion to deflate against.",
        )}

    out = sharpe_tests(
        np.asarray(bar_returns, dtype="float64"),
        BARS_PER_YEAR.get(timeframe, 365.0),
        n_trials=sharpes.size,
        trial_dispersion=dispersion,
    )
    if "error" in out:
        return {"available": False, "reason": bi(out["error"], out["error"])}

    dsr_value = float(out["deflated_sharpe_ratio"])
    trials = int(sharpes.size)
    if dsr_value >= 0.95:
        code, verdict = "survives", bi(
            f"DSR = {dsr_value * 100:.1f}%. Sharpe của tổ hợp thắng vượt qua "
            f"ngưỡng kỳ vọng của {trials:,} phép thử — nó cao hơn mức mà chính "
            "việc quét ngần này tổ hợp tự sinh ra.",
            f"DSR = {dsr_value * 100:.1f}%. The winner's Sharpe clears the "
            f"expected maximum of {trials:,} trials — it is higher than the "
            "level that searching this many combinations produces on its own.",
        )
    elif dsr_value >= 0.5:
        code, verdict = "marginal", bi(
            f"DSR = {dsr_value * 100:.1f}%. Sharpe của tổ hợp thắng chỉ nhỉnh "
            f"hơn mức kỳ vọng khi quét {trials:,} tổ hợp. Chưa đủ để kết luận.",
            f"DSR = {dsr_value * 100:.1f}%. The winner's Sharpe is only "
            f"slightly above what searching {trials:,} combinations is "
            "expected to produce. Not enough to conclude anything.",
        )
    else:
        code, verdict = "deflated_away", bi(
            f"DSR = {dsr_value * 100:.1f}%. Sharpe cao nhất của lưới này thấp "
            f"hơn mức kỳ vọng của cực đại {trials:,} phép thử: quét ngần này "
            "tổ hợp trên dữ liệu **không có lợi thế nào** cũng cho ra một con "
            "số đẹp như vậy.",
            f"DSR = {dsr_value * 100:.1f}%. This grid's best Sharpe is below "
            f"the expected maximum of {trials:,} trials: sweeping this many "
            "combinations over data with **no edge at all** would produce a "
            "number this good.",
        )

    return {
        "available": True,
        "code": code,
        "verdict": verdict,
        "trials": trials,
        "psr": out["psr"],
        "deflated_sharpe_ratio": dsr_value,
        "cross_trial_dispersion": dispersion,
        "dispersion_measured": True,
        "note": out["trial_dispersion_note"],
    }


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

    # Two questions the ranked table cannot answer: is the winner a plateau or
    # a spike, and is its Sharpe better than the best of this many coin flips?
    summary["robustness"] = _neighbourhood(rows, ranges, metric)

    winner_returns = None
    if rows:
        try:
            spec = registry.get_spec(strategy_id)
            resolved = spec.resolve_params(rows[0]["params"])
            prepared = df.copy()
            prepared.index = pd.to_datetime(prepared["open_time"], unit="ms", utc=True)
            signal = normalize_signals(
                spec.signals(prepared, resolved), prepared.index, spec.side
            )
            equity = np.asarray(run_backtest(df, signal, config).equity, dtype="float64")
            if equity.size > 1:
                winner_returns = np.diff(equity) / equity[:-1]
        except Exception as exc:
            # Deflation is a bonus on top of the table; losing it must not lose
            # the sweep the user waited for.
            log.warning("could not re-run the winner for deflation: %s", exc)
    summary["deflated"] = _deflated_winner(rows, winner_returns, timeframe)

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
