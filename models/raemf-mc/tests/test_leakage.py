import pytest

from raemf_mc.validation.leakage_checks import assert_no_future_feature_columns


def test_no_future_feature_access():
    with pytest.raises(AssertionError):
        assert_no_future_feature_columns(["ret_1", "forward_return_20"])


def test_allowed_feature_columns():
    assert_no_future_feature_columns(["ret_1", "hmm_prob_state_0"])
