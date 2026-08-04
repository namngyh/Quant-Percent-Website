"""Conformalized quantile regression for dependent financial series.

Coverage is empirical; this module does not claim an iid finite-sample guarantee.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

def conformity_scores(lower, upper, y) -> np.ndarray:
    lower, upper, y = map(lambda z: np.asarray(z, dtype=float), (lower, upper, y))
    return np.maximum.reduce([lower-y, y-upper, np.zeros_like(y, dtype=float)])

def finite_sample_qhat(scores, alpha: float) -> np.ndarray:
    scores=np.asarray(scores,float)
    if scores.ndim==1: scores=scores[:,None]
    n=scores.shape[0]
    if n==0: raise ValueError("Calibration set is empty")
    rank=int(np.clip(np.ceil((n+1)*(1-alpha)),1,n))-1
    return np.sort(scores,axis=0)[rank].clip(min=0)

class StaticCQRCalibrator:
    def __init__(self,alpha=.1): self.alpha=float(alpha); self.qhat=None; self.metadata={}
    @property
    def q(self): return self.qhat
    def fit(self,lower,upper,y,dates=None):
        scores=conformity_scores(lower,upper,y); self.qhat=finite_sample_qhat(scores,self.alpha)
        raw=np.mean((np.asarray(y)>=lower)&(np.asarray(y)<=upper),axis=0)
        lo,hi=self.transform_all_horizons(lower,upper); calibrated=np.mean((np.asarray(y)>=lo)&(np.asarray(y)<=hi),axis=0)
        self.metadata={"method":"static_cqr","alpha":self.alpha,"target_coverage":1-self.alpha,"sample_count":len(scores),"qhat":self.qhat.tolist(),"raw_coverage":np.asarray(raw).tolist(),"calibrated_coverage":np.asarray(calibrated).tolist(),"calibration_date_range":None if dates is None else [str(dates[0]),str(dates[-1])]}
        return self
    def transform_all_horizons(self,lower,upper):
        if self.qhat is None: raise RuntimeError("Calibrator has not been fitted")
        lower=np.asarray(lower,dtype=float); upper=np.asarray(upper,dtype=float)
        if lower.shape!=upper.shape: raise ValueError(f"lower/upper shape mismatch: {lower.shape} != {upper.shape}")
        if lower.ndim==0 or lower.shape[-1]!=len(self.qhat): raise ValueError(f"Input horizon dimension must equal qhat length {len(self.qhat)}; got shape {lower.shape}. Use transform_horizon for one horizon.")
        return lower-self.qhat,upper+self.qhat
    def transform(self,lower,upper):
        """Alias tương thích; code mới phải gọi ``transform_all_horizons``."""
        return self.transform_all_horizons(lower,upper)
    def transform_horizon(self,lower,upper,horizon_index):
        if self.qhat is None: raise RuntimeError("Calibrator has not been fitted")
        if horizon_index is None: raise ValueError("horizon_index is required for scalar-horizon calibration")
        j=int(horizon_index)
        if not 0<=j<len(self.qhat): raise IndexError(f"horizon_index {j} outside [0,{len(self.qhat)-1}]")
        lower=np.asarray(lower,dtype=float); upper=np.asarray(upper,dtype=float)
        if lower.shape!=upper.shape: raise ValueError("lower and upper must have identical shapes")
        return lower-self.qhat[j],upper+self.qhat[j]
    def state_dict(self): return {"alpha":self.alpha,"qhat":self.qhat.tolist(),"metadata":self.metadata}
    @classmethod
    def from_state_dict(cls,state):
        obj=cls(state["alpha"]); obj.qhat=np.asarray(state["qhat"]); obj.metadata=state.get("metadata",{}); return obj

class RollingCQRCalibrator:
    """Online CQR whose test residual enters history only after its horizon matures."""
    def __init__(self,window=252,alpha=.1,horizons=(5,20,60)):
        self.window=int(window); self.alpha=float(alpha); self.horizons=np.asarray(horizons,int); self.history=[]; self.pending=[]; self.current_time=-1
    def seed(self,lower,upper,y): self.history=list(conformity_scores(lower,upper,y)[-self.window:]); return self
    def _mature(self,current_time):
        ready=[item for item in self.pending if item[0]<=current_time]
        self.pending=[item for item in self.pending if item[0]>current_time]
        for _,h,score in ready:
            if not self.history: self.history=[np.zeros(len(self.horizons))]
            row=np.asarray(self.history[-1]).copy(); row[h]=score; self.history.append(row)
        self.history=self.history[-self.window:]; self.current_time=current_time
    def predict(self,lower,upper,current_time=None):
        if current_time is not None: self._mature(current_time)
        q=finite_sample_qhat(np.asarray(self.history),self.alpha) if self.history else np.zeros_like(lower,dtype=float)
        return np.asarray(lower)-q,np.asarray(upper)+q
    def update(self,lower,upper,y,forecast_time=None):
        scores=conformity_scores(lower,upper,y)
        if forecast_time is None: self.history.extend(np.atleast_2d(scores)); self.history=self.history[-self.window:]; return
        for h,score in enumerate(np.ravel(scores)): self.pending.append((int(forecast_time+self.horizons[h]),h,float(score)))

class AdaptiveConformalCalibrator(RollingCQRCalibrator):
    def __init__(self,window=252,alpha=.1,gamma=.01,horizons=(5,20,60)): super().__init__(window,alpha,horizons); self.target=alpha; self.gamma=gamma
    def update(self,lower,upper,y,forecast_time=None):
        if forecast_time is None:
            miss=np.asarray((y<lower)|(y>upper),float).mean(); self.alpha=float(np.clip(self.alpha+self.gamma*(self.target-miss),.01,.5))
        super().update(lower,upper,y,forecast_time)


def causal_conformal_comparison(cal_lower,cal_upper,cal_y,test_lower,test_upper,test_y,horizons=(5,20,60),alpha=.1,window=252,gamma=.01):
    """So sánh raw/static/rolling/adaptive; residual test chỉ vào lịch sử khi target đáo hạn."""
    arrays=[np.asarray(x,float) for x in (cal_lower,cal_upper,cal_y,test_lower,test_upper,test_y)]
    if any(x.ndim!=2 for x in arrays) or len({x.shape[1] for x in arrays})!=1: raise ValueError("Mọi input phải là [N,H] cùng số horizon")
    cl,cu,cy,tl,tu,ty=arrays; h=np.asarray(horizons,int); initial=conformity_scores(cl,cu,cy); static_q=finite_sample_qhat(initial,alpha); n,H=tl.shape
    outputs={"raw":(tl.copy(),tu.copy()),"static":(tl-static_q,tu+static_q)}
    for method in ("rolling","adaptive"):
        histories=[list(initial[-window:,j]) for j in range(H)]; pending=[[] for _ in range(H)]; alphas=np.full(H,alpha); lo=np.empty_like(tl); hi=np.empty_like(tu)
        for i in range(n):
            for j in range(H):
                ready=[item for item in pending[j] if item[0]<=i]; pending[j]=[item for item in pending[j] if item[0]>i]
                for _,score,miss in ready:
                    histories[j].append(score); histories[j]=histories[j][-window:]
                    if method=="adaptive": alphas[j]=np.clip(alphas[j]+gamma*(alpha-miss),.01,.5)
                q=float(finite_sample_qhat(np.asarray(histories[j]),alphas[j])[0]); lo[i,j]=tl[i,j]-q; hi[i,j]=tu[i,j]+q
                score=float(max(tl[i,j]-ty[i,j],ty[i,j]-tu[i,j],0)); miss=float(not (lo[i,j]<=ty[i,j]<=hi[i,j])); pending[j].append((i+int(h[j]),score,miss))
        outputs[method]=(lo,hi)
    return outputs
