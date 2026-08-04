import numpy as np
from msdp.interpretation import artifact_confidence,latest_seed_dispersions
def _prediction(value):
    return {"return_quantiles":np.full((1,3,5),value),"direction_prob":np.full((1,3),value/10),"mdd_quantiles":np.full((1,3,3),-value),"volatility":np.full((1,3),value)}
def test_latest_seed_dispersion_uses_supplied_latest_predictions():
    d=latest_seed_dispersions([_prediction(1),_prediction(3)]); assert np.isclose(d[0]["return"],1) and np.isclose(d[2]["mdd"],1)
def test_confidence_reweights_missing_components_without_defaults():
    c=artifact_confidence({"interval":.2,"coverage":None,"disagreement":.4,"seed":None,"drift":.6},{})
    expected=100*(1-(.3*.2+.2*.4+.15*.6)/(.3+.2+.15)); assert np.isclose(c["score"],expected); assert set(c["missing_components"])=={"coverage","seed"}
