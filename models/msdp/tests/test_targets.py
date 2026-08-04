import numpy as np, pandas as pd
from msdp.targets import build_targets
def test_target_alignment_and_mdd():
    c=[100,110,105,120,90,95]; t=build_targets(pd.DataFrame({"close":c}),[5]); assert np.isclose(t.loc[0,"return_h5"],100*np.log(.95)); assert np.isclose(t.loc[0,"mdd_h5"],-25.0)
def test_direction_volatility_and_mdd_sign():
    c=[100,101,102,103,104,105]; t=build_targets(pd.DataFrame({"close":c}),[5]); expected=100*np.sqrt(252/5*np.square(np.diff(np.log(c))).sum()); assert t.loc[0,"direction_h5"]==1; assert np.isclose(t.loc[0,"volatility_h5"],expected); assert (t.mdd_h5.dropna()<=0).all()
