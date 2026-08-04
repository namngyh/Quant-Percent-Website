from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from sklearn.preprocessing import RobustScaler, StandardScaler

def _new(kind): return RobustScaler() if kind=="robust" else StandardScaler()
def fit_feature_scaler(x,kind="robust"): scaler=_new(kind); scaler.fit(x); return scaler

class TargetScalerSet:
    """Independent development-only scalers by target type and horizon."""
    def __init__(self,horizons=(5,20,60),kind="robust"): self.horizons=list(horizons); self.kind=kind; self.return_scalers={}; self.mdd_scalers={}; self.volatility_scalers={}; self.fit_indices=None
    def fit(self,targets,indices=None):
        self.fit_indices=None if indices is None else np.asarray(indices).copy()
        for h in self.horizons:
            self.return_scalers[h]=_new(self.kind).fit(np.asarray(targets[f"return_h{h}"])[:,None])
            severity=-np.asarray(targets[f"mdd_h{h}"])
            self.mdd_scalers[h]=(RobustScaler(with_centering=False) if self.kind=="robust" else StandardScaler(with_mean=False)).fit(severity[:,None])
            logvol=np.log1p(np.asarray(targets[f"volatility_h{h}"]).clip(min=0))
            self.volatility_scalers[h]=_new(self.kind).fit(logvol[:,None])
        return self
    def transform_frame(self,targets):
        out={}
        for h in self.horizons:
            out[f"return_h{h}"]=self.return_scalers[h].transform(np.asarray(targets[f"return_h{h}"])[:,None]).ravel()
            out[f"direction_h{h}"]=np.asarray(targets[f"direction_h{h}"],float)
            out[f"mdd_h{h}"]=-self.mdd_scalers[h].transform((-np.asarray(targets[f"mdd_h{h}"]))[:,None]).ravel()
            out[f"volatility_h{h}"]=self.volatility_scalers[h].transform(np.log1p(np.asarray(targets[f"volatility_h{h}"]).clip(min=0))[:,None]).ravel()
        import pandas as pd
        return pd.DataFrame(out,index=targets.index)
    def inverse_predictions(self,out):
        result={k:np.asarray(v).copy() for k,v in out.items()}
        for j,h in enumerate(self.horizons):
            shape=result["return_quantiles"][:,j].shape; result["return_quantiles"][:,j]=self.return_scalers[h].inverse_transform(result["return_quantiles"][:,j].reshape(-1,1)).reshape(shape)
            shape=result["mdd_quantiles"][:,j].shape; severity=self.mdd_scalers[h].inverse_transform((-result["mdd_quantiles"][:,j]).reshape(-1,1)).reshape(shape); result["mdd_quantiles"][:,j]=-np.maximum(severity,0)
            lv=self.volatility_scalers[h].inverse_transform(result["volatility"][:,j,None]).ravel(); result["volatility"][:,j]=np.expm1(lv).clip(min=0)
            if "aux_return_median" in result:
                shape=result["aux_return_median"][:,j].shape; result["aux_return_median"][:,j]=self.return_scalers[h].inverse_transform(result["aux_return_median"][:,j].reshape(-1,1)).reshape(shape)
        result["return_quantiles"]=np.maximum.accumulate(result["return_quantiles"],axis=-1); result["mdd_quantiles"]=np.minimum(np.maximum.accumulate(result["mdd_quantiles"],axis=-1),0)
        if "aux_return_median" in result: result["expert_disagreement"]=result["aux_return_median"].std(axis=-1)
        return result
