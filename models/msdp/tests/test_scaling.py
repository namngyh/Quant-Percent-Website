import numpy as np
from msdp.scaling import fit_feature_scaler
def test_scaler_train_only():
    s=fit_feature_scaler(np.array([[0.],[1.],[2.]])); assert float(s.center_[0])==1.; assert float(s.transform([[100.]])[0,0])>1
