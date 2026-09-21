"""Performance metrics for a backtest result.

Every ratio here is reported alongside buy-and-hold over the same window.
A strategy that returns 40% on a stretch where simply holding returned 120%
has lost money in the only sense that matters, and a metrics panel that omits
the benchmark makes that easy to miss.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from backend.strategy.engine import BacktestResult

# Crypto trades continuously, so a year is the full calendar year of bars.
BARS_PER_YEAR: dict[str, float] = {
    "1m": 525_600,
    "3m": 175_200,
    "5m": 105_120,
    "15m": 35_040,
    "30m": 17_520,
    "1h": 8_760,
    "2h": 4_380,
    "4h": 2_190,
    "6h": 1_460,
    "8h": 1_095,
    "12h": 730,
    "1d": 365,
    "3d": 121.67,
    "1w": 52,
}


def max_drawdown(equity: np.ndarray) -> tuple[float, int, int]:
    """Return (depth as a positive percent, peak index, trough index)."""
    if equity.size == 0:
        return 0.0, 0, 0

    running_peak = np.maximum.accumulate(equity)
    # A zeroed account would divide by zero; treat it as a total drawdown.
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = np.where(running_peak > 0, (equity - running_peak) / running_peak, -1.0)

    trough = int(np.argmin(drawdown))
    peak = int(np.argmax(equity[: trough + 1])) if trough > 0 else 0
    return float(-drawdown[trough] * 100.0), peak, trough


def _annualised(returns: np.ndarray, timeframe: str, downside_only: bool = False) -> float:
    """Annualised Sharpe, or Sortino when ``downside_only``. Risk-free rate 0."""
    if returns.size < 2:
        return 0.0

    mean = float(np.mean(returns))
    if downside_only:
        negative = returns[returns < 0]
        deviation = float(np.sqrt(np.mean(negative**2))) if negative.size else 0.0
    else:
        deviation = float(np.std(returns, ddof=1))

    if deviation == 0 or not math.isfinite(deviation):
        return 0.0

    periods = BARS_PER_YEAR.get(timeframe, 365)
    return mean / deviation * math.sqrt(periods)


def compute_metrics(result: BacktestResult, df: pd.DataFrame, timeframe: str) -> dict:
    """Summarise a backtest into the numbers shown in the results panel."""
    equity = result.equity
    initial = result.config.initial_capital

    if equity.size == 0:
        return {"error": "no data"}

    final = float(equity[-1])
    total_return = (final / initial - 1.0) * 100.0

    # Per-bar returns of the equity curve, guarding the zeroed-account case.
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = np.diff(equity) / np.where(equity[:-1] > 0, equity[:-1], np.nan)
    returns = returns[np.isfinite(returns)]

    drawdown_pct, peak_idx, trough_idx = max_drawdown(equity)

    # Elapsed years from the actual timestamps, so CAGR reflects the real window.
    span_seconds = max(result.times[-1] - result.times[0], 1)
    years = span_seconds / (365.25 * 24 * 3600)
    if years > 0 and final > 0:
        cagr = ((final / initial) ** (1.0 / years) - 1.0) * 100.0
    else:
        cagr = -100.0 if final <= 0 else 0.0

    trades = result.trades
    pnls = np.array([t.pnl for t in trades], dtype="float64")
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    gross_profit = float(wins.sum()) if wins.size else 0.0
    gross_loss = float(-losses.sum()) if losses.size else 0.0
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = float("inf") if gross_profit > 0 else 0.0

    # Buy and hold over the identical window, paying one entry fee, for context.
    first_close = float(df["close"].iloc[0])
    last_close = float(df["close"].iloc[-1])
    buy_hold = (last_close / first_close - 1.0) * 100.0

    bars_in_market = int(np.count_nonzero(result.position))

    return {
        "initial_capital": initial,
        "final_equity": final,
        "total_return_pct": total_return,
        "buy_hold_return_pct": buy_hold,
        "vs_buy_hold_pct": total_return - buy_hold,
        "cagr_pct": cagr,
        "max_drawdown_pct": drawdown_pct,
        "drawdown_peak_index": peak_idx,
        "drawdown_trough_index": trough_idx,
        "sharpe": _annualised(returns, timeframe),
        "sortino": _annualised(returns, timeframe, downside_only=True),
        "num_trades": len(trades),
        "num_wins": int(wins.size),
        "num_losses": int(losses.size),
        "win_rate_pct": (wins.size / len(trades) * 100.0) if trades else 0.0,
        "profit_factor": profit_factor,
        "avg_win": float(wins.mean()) if wins.size else 0.0,
        "avg_loss": float(losses.mean()) if losses.size else 0.0,
        "best_trade": float(pnls.max()) if pnls.size else 0.0,
        "worst_trade": float(pnls.min()) if pnls.size else 0.0,
        "avg_bars_held": float(np.mean([t.bars_held for t in trades])) if trades else 0.0,
        "exposure_pct": bars_in_market / len(equity) * 100.0,
        "liquidations": sum(1 for t in trades if t.exit_reason == "liquidation"),
        "ruined": result.ruined,
        "bars": len(equity),
    }
