"""Backtest metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd


def backtest_metrics(bt: pd.DataFrame, name: str) -> dict[str, float | str]:
    ret = bt["strategy_return"].fillna(0.0)
    equity = np.exp(ret.cumsum())
    dd = equity / equity.cummax() - 1
    ann_ret = float(ret.mean() * 252)
    ann_vol = float(ret.std() * np.sqrt(252))
    downside = ret[ret < 0].std() * np.sqrt(252)
    return {
        "model": name,
        "cumulative_return": float(equity.iloc[-1] - 1),
        "annualized_return": ann_ret,
        "annualized_volatility": ann_vol,
        "sharpe": ann_ret / ann_vol if ann_vol > 0 else 0.0,
        "sortino": ann_ret / downside if downside and downside > 0 else 0.0,
        "calmar": ann_ret / abs(float(dd.min())) if dd.min() < 0 else 0.0,
        "max_drawdown": float(dd.min()),
        "turnover": float(bt["turnover"].sum()),
        "total_transaction_cost": float(bt.get("transaction_cost", pd.Series(0.0, index=bt.index)).sum()),
        "hit_rate": float((ret > 0).mean()),
        "average_exposure": float(bt["exposure"].mean()),
        "time_in_market": float((bt["exposure"] > 0).mean()),
        "state_changes": int((bt["exposure"].diff().fillna(0) != 0).sum()),
    }
