import numpy as np,pandas as pd
from msdp.scaling import TargetScalerSet
def test_target_scalers_fit_indices_and_transform():
    d={}
    for h in [5,20,60]: d.update({f"return_h{h}":np.arange(10.),f"direction_h{h}":np.arange(10)%2,f"mdd_h{h}":-np.arange(10.),f"volatility_h{h}":np.arange(10.)})
    frame=pd.DataFrame(d); s=TargetScalerSet().fit(frame.iloc[:7],indices=np.arange(7)); z=s.transform_frame(frame); assert np.array_equal(s.fit_indices,np.arange(7)); assert (z[[f"mdd_h{h}" for h in [5,20,60]]].to_numpy()<=0).all()
