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

from backend.optimizer.grid import ParamRange, build_grid, build_random, grid_size
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
    train_end: int      # exclusive; also the test start
    test_end: int       # exclusive


def build_folds(total_bars: int, train_bars: int, test_bars: int) -> list[Fold]:
    """Rolling windows: train, test the stretch after it, then slide forward."""
    if train_bars < 50:
        raise ValueError("Cửa sổ huấn luyện phải từ 50 nến trở lên.")
    if test_bars < MIN_TEST_BARS:
        raise ValueError(f"Cửa sổ kiểm tra phải từ {MIN_TEST_BARS} nến trở lên.")
    if total_bars < train_bars + test_bars:
        raise ValueError(
            f"Cần ít nhất {train_bars + test_bars:,} nến cho một vòng, "
            f"hiện chỉ có {total_bars:,}. Giảm cửa sổ hoặc tăng số nến."
        )

    folds: list[Fold] = []
    start = 0
    while start + train_bars + test_bars <= total_bars and len(folds) < MAX_FOLDS:
        folds.append(
            Fold(
                index=len(folds),
                train_start=start,
                train_end=start + train_bars,
                test_end=start + train_bars + test_bars,
            )
        )
        start += test_bars

    if not folds:
        raise ValueError("Không dựng được vòng nào với cấu hình này.")
    return folds


def _signals_for(strategy_id: str, frame: pd.DataFrame, params: dict) -> np.ndarray:
    spec = registry.get_spec(strategy_id)
    prepared = frame.copy()
    prepared.index = pd.to_datetime(prepared["open_time"], unit="ms", utc=True)
    raw = spec.signals(prepared, params)
    return normalize_signals(raw, prepared.index, spec.side)


def walk_forward(
    strategy_id: str,
    df: pd.DataFrame,
    timeframe: str,
    ranges: list[ParamRange],
    config: BacktestConfig | None = None,
    metric: str = "sharpe",
    train_bars: int = 1000,
    test_bars: int = 250,
    mode: str = "grid",
    samples: int = 200,
    seed: int | None = 7,
    progress_cb: Callable[[int, int], None] | None = None,
) -> dict:
    """Optimise on each training window, score only the window after it."""
    config = config or BacktestConfig()
    folds = build_folds(len(df), train_bars, test_bars)

    combos = (
        build_grid(ranges) if mode == "grid" else build_random(ranges, samples, seed)
    ) if ranges else [{}]

    results = []
    oos_equity: list[float] = []
    oos_times: list[int] = []
    oos_trades: list[dict] = []
    equity = config.initial_capital

    for fold in folds:
        # The strategy sees the training window as warm-up so its indicators
        # are settled by the time the test window starts; only the test window
        # is scored.
        window = df.iloc[fold.train_start : fold.test_end].reset_index(drop=True)
        train_len = fold.train_end - fold.train_start
        train_frame = window.iloc[:train_len].reset_index(drop=True)

        best_params, best_score = None, -math.inf
        for params in combos:
            try:
                signal = _signals_for(strategy_id, train_frame, params)
                result = run_backtest(train_frame, signal, config)
                score = compute_metrics(result, train_frame, timeframe).get(metric, 0.0)
            except Exception:
                continue
            if score is not None and math.isfinite(score) and score > best_score:
                best_score, best_params = score, params

        if best_params is None:
            log.warning("fold %d produced no usable parameters", fold.index)
            continue

        # Signals over the whole window, then measured on the test slice only.
        signal = _signals_for(strategy_id, window, best_params)
        test_frame = window.iloc[train_len:].reset_index(drop=True)
        test_signal = signal[train_len:]

        fold_config = BacktestConfig(
            initial_capital=equity,
            size_pct=config.size_pct,
            leverage=config.leverage,
            fee=config.fee,
            slippage=config.slippage,
        )
        test_result = run_backtest(test_frame, test_signal, fold_config)
        test_metrics = compute_metrics(test_result, test_frame, timeframe)

        # Equity carries across folds, so the curve reads as one account
        # traded continuously rather than a series of fresh starts.
        equity = float(test_result.equity[-1]) if len(test_result.equity) else equity
        oos_equity.extend(float(v) for v in test_result.equity)
        oos_times.extend(test_result.times)
        oos_trades.extend(t.as_dict() for t in test_result.trades)

        train_signal = signal[:train_len]
        train_result = run_backtest(train_frame, train_signal, config)
        train_metrics = compute_metrics(train_result, train_frame, timeframe)

        results.append(
            {
                "fold": fold.index + 1,
                "params": best_params,
                "train_from": int(window["open_time"].iloc[0]) // 1000,
                "train_to": int(window["open_time"].iloc[train_len - 1]) // 1000,
                "test_from": int(test_frame["open_time"].iloc[0]) // 1000,
                "test_to": int(test_frame["open_time"].iloc[-1]) // 1000,
                "in_sample": {
                    "return_pct": train_metrics["total_return_pct"],
                    "sharpe": train_metrics["sharpe"],
                    "max_drawdown_pct": train_metrics["max_drawdown_pct"],
                    "num_trades": train_metrics["num_trades"],
                },
                "out_of_sample": {
                    "return_pct": test_metrics["total_return_pct"],
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
        raise ValueError("Không vòng nào chạy được. Hãy nới dải tham số hoặc cửa sổ.")

    return {
        "strategy_id": strategy_id,
        "timeframe": timeframe,
        "config": config.as_dict(),
        "settings": {
            "train_bars": train_bars,
            "test_bars": test_bars,
            "folds": len(results),
            "combinations": len(combos),
            "metric": metric,
            "mode": mode,
        },
        "folds": results,
        "summary": _walk_forward_summary(results, oos_equity, config.initial_capital),
        "equity": [round(v, 2) for v in oos_equity],
        "times": oos_times,
        "trades": oos_trades,
    }


def _walk_forward_summary(folds: list[dict], equity: list[float], initial: float) -> dict:
    oos = np.array([f["out_of_sample"]["return_pct"] for f in folds], dtype="float64")
    ins = np.array([f["in_sample"]["return_pct"] for f in folds], dtype="float64")
    curve = np.array(equity, dtype="float64")

    drawdown, _, _ = max_drawdown(curve) if curve.size else (0.0, 0, 0)
    total = (float(curve[-1]) / initial - 1.0) * 100.0 if curve.size else 0.0

    # The gap between the two is the cost of hindsight. A large one means the
    # parameters were fitted to each training window rather than to the market.
    degradation = float(ins.mean() - oos.mean())

    return {
        "oos_total_return_pct": total,
        "oos_final_equity": float(curve[-1]) if curve.size else initial,
        "oos_max_drawdown_pct": drawdown,
        "oos_mean_return_pct": float(oos.mean()),
        "oos_median_return_pct": float(np.median(oos)),
        "is_mean_return_pct": float(ins.mean()),
        "degradation_pct": degradation,
        "profitable_folds": int((oos > 0).sum()),
        "total_folds": len(folds),
        "consistency_pct": float((oos > 0).mean() * 100.0),
        # A strategy that only worked in-sample is the thing this test exists
        # to catch, so it is named rather than left to be inferred.
        "overfit_warning": bool(ins.mean() > 0 and oos.mean() <= 0),
    }


# ----------------------------------------------------------------- monte carlo

def monte_carlo(
    trades: list[dict],
    initial_capital: float,
    simulations: int = DEFAULT_SIMULATIONS,
    seed: int | None = 42,
) -> dict:
    """Resample the trade sequence to put a range around a single result.

    Trades are drawn with replacement, so each simulation is a different
    plausible ordering and mix of the same edge. What varies is luck; what
    stays fixed is the strategy.
    """
    if len(trades) < 5:
        raise ValueError(
            f"Cần ít nhất 5 lệnh để mô phỏng, hiện có {len(trades)}. "
            "Kéo dài dữ liệu hoặc nới tham số."
        )

    simulations = max(100, min(simulations, MAX_SIMULATIONS))
    returns = np.array(
        [t["pnl"] / max(initial_capital, 1e-9) for t in trades], dtype="float64"
    )
    n = len(returns)
    rng = np.random.default_rng(seed)

    finals = np.empty(simulations, dtype="float64")
    drawdowns = np.empty(simulations, dtype="float64")

    for i in range(simulations):
        draw = rng.choice(returns, size=n, replace=True)
        # Compounded, matching how the engine sizes each position off equity.
        curve = initial_capital * np.cumprod(1.0 + draw)
        finals[i] = curve[-1]
        depth, _, _ = max_drawdown(np.concatenate(([initial_capital], curve)))
        drawdowns[i] = depth

    final_returns = (finals / initial_capital - 1.0) * 100.0
    percentiles = [5, 25, 50, 75, 95]

    return {
        "simulations": simulations,
        "trades_resampled": n,
        "initial_capital": initial_capital,
        "return_pct": {
            f"p{p}": float(np.percentile(final_returns, p)) for p in percentiles
        },
        "max_drawdown_pct": {
            f"p{p}": float(np.percentile(drawdowns, p)) for p in percentiles
        },
        "mean_return_pct": float(final_returns.mean()),
        "probability_of_loss_pct": float((final_returns < 0).mean() * 100.0),
        "probability_of_ruin_pct": float((finals <= initial_capital * 0.1).mean() * 100.0),
        "worst_return_pct": float(final_returns.min()),
        "best_return_pct": float(final_returns.max()),
    }
