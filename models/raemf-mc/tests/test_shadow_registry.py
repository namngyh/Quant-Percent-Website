import pandas as pd
import pytest

from raemf_mc.shadow.registry import append_forecasts, mature_forecasts


def _forecast(probability: float = 0.4) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "forecast_origin": "2024-01-02",
                "origin_close": 100.0,
                "horizon": 2,
                "model_version": "test-v1",
                "git_sha": "abc",
                "data_checksum": "data",
                "config_checksum": "config",
                "prob_bull": 0.2,
                "prob_sideway": 0.3,
                "prob_bear": 0.3,
                "prob_stress": 0.2,
                "risk_off_probability": probability,
                "threshold": 0.35,
                "alert_state": 1,
                "prob_drawdown_5": 0.1,
                "prob_drawdown_10": 0.05,
                "prob_drawdown_15": 0.02,
                "prob_drawdown_20": 0.01,
                "var_95": -0.05,
                "cvar_95": -0.08,
                "maturity_date": "2024-01-04",
            }
        ]
    )


def test_registry_is_immutable_and_scores_only_after_h_future_sessions(tmp_path):
    path = tmp_path / "forecast_registry.csv"
    created = append_forecasts(path, _forecast())
    assert created.loc[0, "status"] == "pending"
    one_session = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-02", "2024-01-03"]), "close": [100.0, 95.0]}
    )
    pending = mature_forecasts(path, one_session, scoring_timestamp="t1")
    assert pending.loc[0, "status"] == "pending"
    enough = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "close": [100.0, 95.0, 90.0],
        }
    )
    matured = mature_forecasts(path, enough, scoring_timestamp="t2")
    assert matured.loc[0, "status"] == "matured"
    assert matured.loc[0, "realized_return"] < 0
    assert matured.loc[0, "realized_mae"] < 0

    with pytest.raises(ValueError, match="mutation"):
        append_forecasts(path, _forecast(probability=0.9))
