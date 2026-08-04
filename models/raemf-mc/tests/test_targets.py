import pandas as pd

from raemf_mc.targets.regime_targets import create_multihorizon_targets


def test_targets_have_end_dates():
    df = pd.DataFrame({"date": pd.date_range("2020-01-01", periods=90), "close": range(100, 190)})
    out = create_multihorizon_targets(df)
    assert out.loc[0, "target_end_date_20"] == df.loc[20, "date"]
    assert out["target_20"].notna().sum() == 70
