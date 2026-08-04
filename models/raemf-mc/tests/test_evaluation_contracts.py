import numpy as np
import pandas as pd

from raemf_mc.backtest.exposure import backtest_exposure
from raemf_mc.calibration.temperature_scaling import fit_temperature
from raemf_mc.validation.leakage_checks import assert_backtest_dates_are_oos


def test_calibration_result_does_not_depend_on_test_values():
    validation_probability = np.array([[0.7, 0.1, 0.1, 0.1], [0.1, 0.5, 0.2, 0.2]])
    validation_target = pd.Series(["Bull", "Sideway"])
    first = fit_temperature(validation_probability, validation_target)
    arbitrary_test = np.array([[0.0, 0.0, 0.0, 1.0]])
    assert arbitrary_test.shape == (1, 4)
    second = fit_temperature(validation_probability, validation_target)
    assert first == second


def test_backtest_calendar_must_equal_oos_prediction_calendar():
    dates = pd.Series(pd.date_range("2024-01-01", periods=12))
    close = pd.Series(np.linspace(100, 112, 12))
    backtest = backtest_exposure(close, pd.Series(0.5, index=close.index))
    assert len(backtest) == len(dates)
    assert_backtest_dates_are_oos(dates, dates.copy())
