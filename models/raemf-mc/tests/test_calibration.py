import numpy as np
from raemf_mc.calibration.metrics import assert_probability_matrix
from raemf_mc.calibration.temperature_scaling import apply_temperature


def test_probability_sum_after_temperature():
    p = np.array([[0.7, 0.1, 0.1, 0.1], [0.2, 0.3, 0.4, 0.1]])
    out = apply_temperature(p, 1.5)
    assert_probability_matrix(out)
