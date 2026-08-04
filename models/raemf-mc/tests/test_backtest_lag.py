import numpy as np
import pandas as pd

from raemf_mc.backtest.exposure import backtest_exposure
from raemf_mc.validation.leakage_checks import assert_backtest_one_day_lag


def test_backtest_uses_one_day_lag():
    close = pd.Series([100, 101, 103, 102, 104], dtype=float)
    exposure = pd.Series([1, 1, 0, 0.5, 1], dtype=float)
    bt = backtest_exposure(close, exposure, cost_bps=0)
    ret = np.log(close / close.shift(1)).fillna(0)
    assert_backtest_one_day_lag(exposure, ret, bt["strategy_return"])
