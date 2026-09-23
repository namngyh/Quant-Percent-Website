"""Walk-forward validation and Monte Carlo resampling.

Both exist to answer the same question in different ways: *how much of this
backtest was skill, and how much was the parameters having been chosen with
hindsight?*

**Walk-forward** never lets a result be scored on the data that produced it.
Parameters are optimised on one window and then applied, untouched, to the
window that follows — the way they would have been used in practice. Only that
out-of-sample stretch is reported. A strategy whose in-sample numbers are
excellent and whose out-of-sample numbers are not was fitted to noise, and this
is the cheapest way to find that out.

**Monte Carlo** takes the trades a strategy produced and asks what else could
plausibly have happened. Resampling the trade sequence gives a distribution of
outcomes rather than the single path history happened to draw, which puts a
range around a return instead of a point estimate that invites false
confidence.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.i18n import bi
from backend.optimizer.grid import (
    RANKABLE_METRICS,
    ParamRange,
    build_grid,
    build_random,
    grid_size,
)
from backend.strategy import registry
from backend.strategy.base import normalize_signals
from backend.strategy.engine import BacktestConfig, run_backtest
from backend.strategy.metrics import compute_metrics, max_drawdown

log = logging.getLogger(__name__)

MAX_FOLDS = 20
MIN_TEST_BARS = 50
MAX_SIMULATIONS = 10_000
DEFAULT_SIMULATIONS = 1000


# ---------------------------------------------------------------- walk forward

@dataclass
class Fold:
    index: int
    train_start: int
    train_end: int      # exclusive
    test_start: int     # train_end + purge
    test_end: int       # exclusive


def build_folds(
    total_bars: int,
    train_bars: int,
    test_bars: int,
    purge_bars: int = 0,
    mode: str = "rolling",
) -> list[Fold]:
    """Training and test windows, with a gap between them if asked for.

    ``mode``:

    * **rolling** keeps the training window a fixed length and slides it
      forward. It answers "would this have worked using only recent history",
      and it lets the parameters follow a changing market.
    * **anchored** starts the training window at bar zero and lets it grow.
      It answers "would this have worked using everything known at the time",
      and it is the harder test: parameters must survive across regimes rather
      than being refitted to the latest one.

    ``purge_bars`` drops that many bars between training and test. An indicator
    with a lookback of L still carries training-window information L bars into
    the test window, and a strategy that fits a model on labels derived from
    future bars carries more. Purging removes the overlap instead of hoping it
    is small.
    """
    if mode not in ("rolling", "anchored"):
        raise ValueError(f"unknown mode '{mode}'; expected 'rolling' or 'anchored'")
    if train_bars < 50:
        raise ValueError("Cửa sổ huấn luyện phải từ 50 nến trở lên.")
    if test_bars < MIN_TEST_BARS:
        raise ValueError(f"Cửa sổ kiểm tra phải từ {MIN_TEST_BARS} nến trở lên.")
    if purge_bars < 0:
        raise ValueError("Số nến cách ly không được âm.")

    span = train_bars + purge_bars + test_bars
    if total_bars < span:
        raise ValueError(
            f"Cần ít nhất {span:,} nến cho một vòng "
            f"({train_bars:,} huấn luyện + {purge_bars:,} cách ly + "
            f"{test_bars:,} kiểm tra), hiện chỉ có {total_bars:,}."
        )

    # Both modes advance one test window per fold and differ only in where the
    # training window starts. Deriving `train_end` from the fold number keeps
    # the stop condition honest: an earlier version grew the window inside the
    # loop while testing against the original span, and ran off the end of the
    # data.
    folds: list[Fold] = []
    k = 0
    while len(folds) < MAX_FOLDS:
        if mode == "rolling":
            train_start = k * test_bars
            train_end = train_start + train_bars
        else:
            train_start = 0
            train_end = train_bars + k * test_bars

        test_start = train_end + purge_bars
        test_end = test_start + test_bars
        if test_end > total_bars:
            break

        folds.append(Fold(len(folds), train_start, train_end, test_start, test_end))
        k += 1

    if not folds:
        raise ValueError("Không dựng được vòng nào với cấu hình này.")
    return folds


def _signals_for(strategy_id: str, frame: pd.DataFrame, params: dict) -> np.ndarray:
    spec = registry.get_spec(strategy_id)
    # Fill in every parameter the strategy declares, not just the swept ones.
    #
    # Without this, sweeping one parameter of a strategy that takes two leaves
    # the other missing entirely: the strategy raises a KeyError, the loop's
    # `except Exception: continue` swallows it, every combination fails, and
    # walk-forward reports "no fold could run" with no indication of why. The
    # optimiser has always resolved defaults because it goes through
    # `run_strategy`; this path did not.
    resolved = spec.resolve_params(params)
    prepared = frame.copy()
    prepared.index = pd.to_datetime(prepared["open_time"], unit="ms", utc=True)
    raw = spec.signals(prepared, resolved)
    return normalize_signals(raw, prepared.index, spec.side)


def _normalise_return(total_pct: float, from_bars: int, to_bars: int) -> float:
    """Re-express a return as what its rate would produce over `to_bars` bars.

    The summary used to subtract an out-of-sample total return from an
    in-sample one, but the two windows are different lengths: at the default
    1000/250 the training window covers four times the ground. Measured on
    BTCUSDT 1h with the test window held at 250 bars, the in-sample mean rose
    from 3.64% to 8.12% as the training window grew from 250 to 2000 bars while
    out-of-sample barely moved, so the "degradation" figure climbed 72% purely
    because the window got longer.

    CAGR is not the fix. It is a rate, but annualising a 250-bar window on
    hourly data raises the return to the power of 35, and comparing one wild
    extrapolation against a milder one is less stable than the problem it
    replaces: measured that way, out-of-sample rates came back above 7 000%.

    Compounding to a common horizon keeps the units familiar, puts both sides
    on the same footing, and never extrapolates beyond the shorter window.
    """
    if from_bars <= 0 or to_bars <= 0:
        return total_pct
    growth = 1.0 + total_pct / 100.0
    if growth <= 0:
        return -100.0
    return (growth ** (to_bars / from_bars) - 1.0) * 100.0


def _parameter_stability(folds: list[dict]) -> dict:
    """How much the chosen parameters move from one fold to the next.

    A strategy with a genuine optimum picks similar values every time. One
    whose best parameters jump around each fold has no optimum: the sweep is
    fitting whatever the last window happened to contain, and the fact that
    some fold made money says nothing about the next one.
    """
    names = sorted({name for fold in folds for name in fold["params"]})
    if not names or len(folds) < 2:
        return {"parameters": [], "note": None}

    report = []
    for name in names:
        values = np.array(
            [float(f["params"][name]) for f in folds if name in f["params"]],
            dtype="float64",
        )
        if values.size < 2:
            continue
        mean = float(values.mean())
        spread = float(values.std(ddof=1))
        report.append({
            "name": name,
            "mean": mean,
            "std": spread,
            # Spread relative to level, so a parameter that lives near 200 is
            # not called unstable for moving as much as one that lives near 5.
            "coefficient_of_variation": abs(spread / mean) if mean else 0.0,
            "distinct_values": int(np.unique(values).size),
            "folds": int(values.size),
        })

    unstable = [r for r in report if r["coefficient_of_variation"] > 0.5]
    note = None
    if unstable:
        note = bi(
            "Tham số " + ", ".join(r["name"] for r in unstable) +
            " nhảy mạnh giữa các vòng (độ lệch chuẩn trên 50% giá trị trung "
            "bình). Chiến lược này không có điểm tối ưu ổn định: mỗi vòng đang "
            "khớp vào đúng cửa sổ vừa nhìn thấy, nên tham số tốt nhất của vòng "
            "cuối không có lý do gì để tốt ở vòng tiếp theo.",
            "The parameters " + ", ".join(r["name"] for r in unstable) +
            " move sharply between folds (standard deviation above 50% of the "
            "mean). This strategy has no stable optimum: each fold is fitting "
            "the window it just saw, so the last fold's best parameters have no "
            "reason to be good in the next one.",
        )
    return {"parameters": report, "note": note}


def walk_forward(
    strategy_id: str,
    df: pd.DataFrame,
    timeframe: str,
    ranges: list[ParamRange],
    config: BacktestConfig | None = None,
    metric: str = "sharpe",
    train_bars: int = 1000,
    test_bars: int = 250,
    purge_bars: int = 0,
    fold_mode: str = "rolling",
    mode: str = "grid",
    samples: int = 200,
    seed: int | None = 7,
    progress_cb: Callable[[int, int], None] | None = None,
) -> dict:
    """Optimise on each training window, score only the window after it."""
    # `optimize` has always rejected an unknown metric; this did not, and
    # `metrics.get(metric, 0.0)` then scored every combination zero. Measured on
    # BTCUSDT 1h with a 6-combination grid, metric="sharpe_ratio" — a name that
    # reads perfectly plausible — picked the same parameters in all 15 folds,
    # the first entry of the grid, exactly as metric="not_a_metric" did. A valid
    # name picked 5 different winners. The run reported folds, an equity curve
    # and a walk-forward efficiency of 8.45 without once having optimised
    # anything, which is the worst way for this to fail: it looks like a result.
    if metric not in RANKABLE_METRICS:
        raise ValueError(
            f"không xếp hạng được theo '{metric}'; chọn một trong {RANKABLE_METRICS}"
        )
    config = config or BacktestConfig()
    folds = build_folds(len(df), train_bars, test_bars, purge_bars, fold_mode)

    combos = (
        build_grid(ranges) if mode == "grid" else build_random(ranges, samples, seed)
    ) if ranges else [{}]

    results = []
    failures: list[dict] = []
    oos_equity: list[float] = []
    oos_times: list[int] = []
    oos_trades: list[dict] = []
    equity = config.initial_capital

    for fold in folds:
        window = df.iloc[fold.train_start : fold.test_end].reset_index(drop=True)
        train_len = fold.train_end - fold.train_start
        test_offset = fold.test_start - fold.train_start
        train_frame = window.iloc[:train_len].reset_index(drop=True)

        best_params, best_score = None, -math.inf
        best_metrics = None
        last_error: str | None = None

        for params in combos:
            try:
                signal = _signals_for(strategy_id, train_frame, params)
                result = run_backtest(train_frame, signal, config)
                metrics = compute_metrics(result, train_frame, timeframe)
                score = metrics.get(metric)
            except Exception as exc:
                # One bad combination must not abort the fold, but the reason is
                # kept: a fold where every combination failed used to report
                # only that it had, which is the least useful half of the fact.
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            if score is not None and math.isfinite(score) and score > best_score:
                best_score, best_params = score, params
                # Kept from the run that won, not recomputed later. The two are
                # not the same for a strategy whose signals depend on the whole
                # series it is given, and reporting one while having optimised
                # the other makes the in-sample column describe a run that never
                # took place.
                best_metrics = metrics

        if best_params is None:
            log.warning(
                "fold %d produced no usable parameters (%s)",
                fold.index, last_error or "every combination scored non-finite",
            )
            failures.append({"fold": fold.index + 1, "error": last_error})
            continue

        # Signals over the whole window so indicators are warmed up, then
        # measured only on the test slice.
        signal = _signals_for(strategy_id, window, best_params)
        test_frame = window.iloc[test_offset:].reset_index(drop=True)
        test_signal = signal[test_offset:]

        fold_config = BacktestConfig(
            initial_capital=equity,
            size_pct=config.size_pct,
            leverage=config.leverage,
            fee=config.fee,
            slippage=config.slippage,
        )
        test_result = run_backtest(test_frame, test_signal, fold_config)
        test_metrics = compute_metrics(test_result, test_frame, timeframe)

        # Equity carries across folds, so the curve reads as one account traded
        # continuously rather than a series of fresh starts.
        equity = float(test_result.equity[-1]) if len(test_result.equity) else equity
        oos_equity.extend(float(v) for v in test_result.equity)
        oos_times.extend(test_result.times)
        oos_trades.extend(t.as_dict() for t in test_result.trades)

        results.append(
            {
                "fold": fold.index + 1,
                "params": best_params,
                "train_bars": train_len,
                "purge_bars": purge_bars,
                "train_from": int(window["open_time"].iloc[0]) // 1000,
                "train_to": int(window["open_time"].iloc[train_len - 1]) // 1000,
                "test_from": int(test_frame["open_time"].iloc[0]) // 1000,
                "test_to": int(test_frame["open_time"].iloc[-1]) // 1000,
                "in_sample": {
                    "return_pct": best_metrics["total_return_pct"],
                    # The same rate compounded over a test-window-length period,
                    # so the two columns can be read against each other.
                    "return_normalised_pct": _normalise_return(
                        best_metrics["total_return_pct"], train_len, test_bars
                    ),
                    "sharpe": best_metrics["sharpe"],
                    "max_drawdown_pct": best_metrics["max_drawdown_pct"],
                    "num_trades": best_metrics["num_trades"],
                },
                "out_of_sample": {
                    "return_pct": test_metrics["total_return_pct"],
                    "return_normalised_pct": test_metrics["total_return_pct"],
                    "sharpe": test_metrics["sharpe"],
                    "max_drawdown_pct": test_metrics["max_drawdown_pct"],
                    "win_rate_pct": test_metrics["win_rate_pct"],
                    "num_trades": test_metrics["num_trades"],
                    "buy_hold_return_pct": test_metrics["buy_hold_return_pct"],
                },
            }
        )

        if progress_cb:
            progress_cb(len(results), len(folds))

    if not results:
        reason = failures[0]["error"] if failures and failures[0]["error"] else None
        raise ValueError(
            "Không vòng nào chạy được. "
            + (f"Lỗi từ chiến lược: {reason}" if reason
               else "Hãy nới dải tham số hoặc cửa sổ.")
        )

    return {
        "strategy_id": strategy_id,
        "timeframe": timeframe,
        "config": config.as_dict(),
        "settings": {
            "train_bars": train_bars,
            "test_bars": test_bars,
            "purge_bars": purge_bars,
            "fold_mode": fold_mode,
            "folds": len(results),
            "combinations": len(combos),
            "metric": metric,
            "mode": mode,
        },
        "folds": results,
        "failed_folds": failures,
        "stability": _parameter_stability(results),
        "summary": _walk_forward_summary(results, oos_equity, config.initial_capital),
        "equity": [round(v, 2) for v in oos_equity],
        "times": oos_times,
        "trades": oos_trades,
    }


def _walk_forward_summary(folds: list[dict], equity: list[float], initial: float) -> dict:
    oos = np.array([f["out_of_sample"]["return_pct"] for f in folds], dtype="float64")
    oos_rate = np.array(
        [f["out_of_sample"]["return_normalised_pct"] for f in folds], dtype="float64")
    ins_rate = np.array(
        [f["in_sample"]["return_normalised_pct"] for f in folds], dtype="float64")
    oos_sharpe = np.array([f["out_of_sample"]["sharpe"] for f in folds], dtype="float64")
    ins_sharpe = np.array([f["in_sample"]["sharpe"] for f in folds], dtype="float64")
    curve = np.array(equity, dtype="float64")

    drawdown, _, _ = max_drawdown(curve) if curve.size else (0.0, 0, 0)
    total = (float(curve[-1]) / initial - 1.0) * 100.0 if curve.size else 0.0

    # Both sides as rates, so the training window's length cannot inflate the
    # gap. This is the number that used to grow simply because the window did.
    degradation = float(ins_rate.mean() - oos_rate.mean())

    # Walk-forward efficiency: how much of the in-sample rate survived. Above
    # ~0.5 is the conventional threshold for a strategy worth trading.
    #
    # A bare ratio is only readable as "the share that survived" when both sides
    # are positive. Two other things happen often enough to need naming:
    #
    #   the in-sample rate is at or near zero -> the ratio has no denominator
    #     worth dividing by, and a rate of 0.001% against 0.9% would print an
    #     efficiency of 900 for a strategy that made nothing in training;
    #   the out-of-sample rate is negative    -> the edge did not shrink, it
    #     inverted, and "-1.18 of the edge survived" is not a sentence.
    #
    # So the caller gets a code as well as the number, and the interface says
    # which of the three it is looking at rather than printing a ratio under a
    # label the ratio does not fit.
    is_mean = float(ins_rate.mean())
    oos_mean = float(oos_rate.mean())
    # Relative floor, not an absolute one: what counts as "near zero" depends on
    # the scale of the returns being compared, as it did for the K-ratio.
    floor = 0.01 * max(abs(oos_mean), abs(is_mean), 1e-12)
    if is_mean <= 0 or is_mean < floor:
        efficiency, efficiency_code = None, "no_is_edge"
    elif oos_mean < 0:
        efficiency, efficiency_code = float(oos_mean / is_mean), "inverted"
    else:
        efficiency, efficiency_code = float(oos_mean / is_mean), "ratio"

    return {
        "oos_total_return_pct": total,
        "oos_final_equity": float(curve[-1]) if curve.size else initial,
        "oos_max_drawdown_pct": drawdown,
        "oos_mean_return_pct": float(oos.mean()),
        "oos_median_return_pct": float(np.median(oos)),
        "oos_mean_normalised_pct": float(oos_rate.mean()),
        "is_mean_normalised_pct": is_mean,
        "oos_mean_sharpe": float(oos_sharpe.mean()),
        "is_mean_sharpe": float(ins_sharpe.mean()),
        # Kept under its old name so callers do not break, but now measured on
        # rates rather than on totals over windows of different lengths.
        "degradation_pct": degradation,
        "degradation_sharpe": float(ins_sharpe.mean() - oos_sharpe.mean()),
        "walk_forward_efficiency": efficiency,
        "walk_forward_efficiency_code": efficiency_code,
        "profitable_folds": int((oos > 0).sum()),
        "total_folds": len(folds),
        "consistency_pct": float((oos > 0).mean() * 100.0),
        "overfit_warning": bool(is_mean > 0 and oos_rate.mean() <= 0),
        "measured_on": bi(
            "Suy giảm và hiệu suất walk-forward đo trên lợi nhuận đã quy về "
            "cùng độ dài cửa sổ kiểm tra. So thẳng hai con số tổng là so hai "
            "khoảng thời gian khác nhau; quy về CAGR còn tệ hơn, vì quy năm một "
            "cửa sổ vài trăm nến là phép ngoại suy rất mạnh.",
            "Degradation and walk-forward efficiency are measured on returns "
            "compounded to the same horizon as the test window. Comparing raw "
            "totals compares two different spans of time; annualising is worse "
            "still, because annualising a few hundred bars extrapolates hard.",
        ),
    }


# ----------------------------------------------------------------- monte carlo

def _equity_steps(trades: list[dict], initial_capital: float) -> np.ndarray:
    """Fractional change in account equity caused by each trade.

    This is the quantity a resampler has to work in, and getting it wrong was
    the module's largest error. `pnl / initial_capital` is a return on a fixed
    base; compounding it is a category mistake, because the engine sizes every
    position off *current* equity. A strategy earning exactly 1% of its opening
    capital on each of 100 trades really makes +100%, and compounding the fixed
    base reported +170.48%.

    `return_pct` is no better: it is measured on the margin committed and
    excludes the entry fee, which is charged the moment the position opens.
    Compounding it lands 4-7% away from the engine depending on sizing.

    So the engine records the equity either side of every trade, and
    `equity_after / equity_before - 1` reproduces its curve exactly. Older
    payloads without those fields fall back to the fixed-base form, which is
    wrong but is at least the behaviour they were computed under.
    """
    steps = []
    for trade in trades:
        before = trade.get("equity_before")
        after = trade.get("equity_after")
        if before and after and before > 0:
            steps.append(after / before - 1.0)
        else:
            steps.append(trade["pnl"] / max(initial_capital, 1e-9))
    return np.array(steps, dtype="float64")


def _resample_indices(
    n: int, simulations: int, rng: np.random.Generator, block_length: float | None
) -> np.ndarray:
    """Indices for each simulated path, shape (simulations, n).

    With `block_length` None the draws are independent. Otherwise this is a
    stationary block bootstrap (Politis-Romano): each step either continues the
    previous trade's successor or jumps somewhere new, with an expected run
    length of `block_length`.

    Blocks matter because trade outcomes are not independent. A trend follower
    wins in runs and loses in runs, and independent draws produce sequences
    that strategy could never generate. Measured on a 10-win/10-loss pattern,
    independent draws reported a 95th-percentile drawdown of 56.65% against a
    real 24.72% — so the error is not a conservative one, it is simply an
    answer to a different question.
    """
    if block_length is None or block_length <= 1:
        return rng.integers(0, n, size=(simulations, n))

    restart = 1.0 / block_length
    index = rng.integers(0, n, size=simulations)
    out = np.empty((simulations, n), dtype=np.int64)
    for step in range(n):
        out[:, step] = index
        jump = rng.random(simulations) < restart
        index = np.where(jump, rng.integers(0, n, size=simulations), (index + 1) % n)
    return out


def _paths(steps: np.ndarray, indices: np.ndarray, initial_capital: float) -> dict:
    """Terminal value, deepest drawdown and lowest point of every path."""
    drawn = steps[indices]
    curves = initial_capital * np.cumprod(1.0 + drawn, axis=1)

    # The starting capital is part of the path: a first trade that loses is a
    # drawdown from the opening balance, not from the value after it.
    with_start = np.concatenate(
        [np.full((curves.shape[0], 1), initial_capital), curves], axis=1
    )
    peak = np.maximum.accumulate(with_start, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        depth = np.where(peak > 0, with_start / peak - 1.0, -1.0)

    return {
        "final": curves[:, -1],
        "drawdown_pct": -depth.min(axis=1) * 100.0,
        # The lowest the account ever went, which is what decides ruin.
        "low": with_start.min(axis=1),
    }


def _proportion(mask: np.ndarray) -> dict:
    """A probability with the uncertainty that comes from simulating it.

    A simulated probability is itself an estimate, and reporting 3.2% off 1 000
    paths without saying it is 3.2% plus or minus 1.1 invites the reader to
    take a digit seriously that the simulation does not support.
    """
    n = mask.size
    p = float(mask.mean())
    standard_error = math.sqrt(max(p * (1.0 - p), 0.0) / n) if n else 0.0
    return {
        "pct": p * 100.0,
        "standard_error_pct": standard_error * 100.0,
        "ci95_low_pct": max(0.0, (p - 1.96 * standard_error) * 100.0),
        "ci95_high_pct": min(100.0, (p + 1.96 * standard_error) * 100.0),
    }


def monte_carlo(
    trades: list[dict],
    initial_capital: float,
    simulations: int = DEFAULT_SIMULATIONS,
    seed: int | None = 42,
    ruin_threshold: float = 0.10,
) -> dict:
    """Resample the trade sequence to put a range around a single result.

    Two resamplers run, and both are reported:

    * **block** keeps runs of consecutive trades together, so winning and
      losing streaks survive. This is the headline, because trade outcomes are
      serially dependent and a strategy's drawdowns come from its runs.
    * **independent** draws each trade separately. It is the textbook bootstrap
      and it answers a narrower question: what if the same trades had arrived
      in any order at all.

    Where the two disagree, the disagreement *is* the finding: it measures how
    much of the risk comes from the ordering rather than from the trades.
    """
    if len(trades) < 5:
        raise ValueError(
            f"Cần ít nhất 5 lệnh để mô phỏng, hiện có {len(trades)}. "
            "Kéo dài dữ liệu hoặc nới tham số."
        )

    simulations = max(100, min(simulations, MAX_SIMULATIONS))
    steps = _equity_steps(trades, initial_capital)
    n = steps.size
    rng = np.random.default_rng(seed)

    # n^(1/3) is the usual rule of thumb for block length, floored so a short
    # record still keeps some structure.
    block_length = max(3.0, round(n ** (1 / 3)))

    # The path history actually drew, for comparison against the distribution.
    actual_curve = initial_capital * np.cumprod(1.0 + steps)
    actual_return = (actual_curve[-1] / initial_capital - 1.0) * 100.0
    actual_drawdown, _, _ = max_drawdown(
        np.concatenate(([initial_capital], actual_curve))
    )

    percentiles = [5, 25, 50, 75, 95]
    ruin_level = initial_capital * ruin_threshold
    methods: dict[str, dict] = {}

    for name, length in (("block", block_length), ("independent", None)):
        paths = _paths(steps, _resample_indices(n, simulations, rng, length),
                       initial_capital)
        returns = (paths["final"] / initial_capital - 1.0) * 100.0
        methods[name] = {
            "return_pct": {f"p{p}": float(np.percentile(returns, p)) for p in percentiles},
            "max_drawdown_pct": {
                f"p{p}": float(np.percentile(paths["drawdown_pct"], p))
                for p in percentiles
            },
            "mean_return_pct": float(returns.mean()),
            "worst_return_pct": float(returns.min()),
            "best_return_pct": float(returns.max()),
            "probability_of_loss": _proportion(returns < 0),
            # Ruin is a path property. Testing the final value lets an account
            # that fell to 5% and recovered pass as healthy, when it would have
            # been closed out on the way down.
            "probability_of_ruin": _proportion(paths["low"] <= ruin_level),
            # Where the real result sits among the simulated ones. Near the top
            # means history drew a good hand, not that the strategy is good.
            "actual_percentile": float((returns < actual_return).mean() * 100.0),
        }

    headline = methods["block"]
    ordering_effect = (
        methods["independent"]["max_drawdown_pct"]["p95"]
        - headline["max_drawdown_pct"]["p95"]
    )

    return {
        "simulations": simulations,
        "trades_resampled": n,
        "initial_capital": initial_capital,
        "block_length": block_length,
        "ruin_threshold_pct": ruin_threshold * 100.0,
        "methods": methods,
        # Flattened headline figures, so a caller that wants one number does not
        # have to know which resampler to prefer.
        "return_pct": headline["return_pct"],
        "max_drawdown_pct": headline["max_drawdown_pct"],
        "mean_return_pct": headline["mean_return_pct"],
        "worst_return_pct": headline["worst_return_pct"],
        "best_return_pct": headline["best_return_pct"],
        "probability_of_loss_pct": headline["probability_of_loss"]["pct"],
        "probability_of_ruin_pct": headline["probability_of_ruin"]["pct"],
        "actual_percentile": headline["actual_percentile"],
        "actual_return_pct": actual_return,
        "actual_max_drawdown_pct": actual_drawdown,
        "ordering_effect_pct": ordering_effect,
        "notes": _monte_carlo_notes(headline, actual_return, ordering_effect, n),
    }


def _monte_carlo_notes(
    headline: dict, actual_return: float, ordering_effect: float, n: int
) -> list[dict]:
    notes = []

    percentile = headline["actual_percentile"]
    if percentile > 80:
        notes.append(bi(
            f"Kết quả thật nằm ở phân vị {percentile:.0f} của phân phối mô phỏng: "
            "lịch sử đã rút được một chuỗi thuận lợi. Kỳ vọng hợp lý cho lần "
            f"chạy tới gần với trung vị ({headline['return_pct']['p50']:.1f}%) "
            "hơn là với con số backtest.",
            f"The real result sits at the {percentile:.0f}th percentile of the "
            "simulated distribution: history drew a favourable sequence. A "
            "reasonable expectation for the next run is closer to the median "
            f"({headline['return_pct']['p50']:.1f}%) than to the backtest figure.",
        ))
    elif percentile < 20:
        notes.append(bi(
            f"Kết quả thật nằm ở phân vị {percentile:.0f}: lịch sử đã rút được "
            "một chuỗi bất lợi so với những gì chính các lệnh này có thể tạo ra.",
            f"The real result sits at the {percentile:.0f}th percentile: history "
            "drew an unfavourable sequence relative to what these same trades "
            "could produce.",
        ))

    if abs(ordering_effect) > 5:
        notes.append(bi(
            f"Lấy mẫu độc lập cho sụt giảm p95 lệch {ordering_effect:+.1f} điểm "
            "phần trăm so với lấy mẫu theo khối. Khoảng cách đó chính là phần "
            "rủi ro đến từ TRẬT TỰ các lệnh chứ không từ bản thân các lệnh, và "
            "nó là lý do con số theo khối được lấy làm chuẩn.",
            f"Independent draws put the 95th-percentile drawdown "
            f"{ordering_effect:+.1f} points away from the block estimate. That "
            "gap is the portion of risk that comes from the ORDER of the trades "
            "rather than the trades themselves, and it is why the block figure "
            "is the headline.",
        ))

    if n < 30:
        notes.append(bi(
            f"Chỉ {n} lệnh để lấy mẫu lại. Mọi đường mô phỏng đều là hoán vị của "
            "cùng một nhúm kết quả, nên bề rộng phân phối phản ánh vài lệnh "
            "riêng lẻ chứ không phải hành vi của chiến lược.",
            f"Only {n} trades to resample from. Every simulated path is a "
            "rearrangement of the same handful of outcomes, so the width of the "
            "distribution reflects a few individual trades rather than the "
            "strategy's behaviour.",
        ))

    return notes
