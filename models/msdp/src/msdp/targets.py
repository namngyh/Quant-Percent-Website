from __future__ import annotations
import numpy as np
import pandas as pd

def build_targets(df: pd.DataFrame, horizons=(5,20,60)) -> pd.DataFrame:
    c=df.close.astype(float); lr=np.log(c).diff(); out=pd.DataFrame(index=df.index)
    for h in horizons:
        ret=100*np.log(c.shift(-h)/c); out[f"return_h{h}"]=ret; out[f"direction_h{h}"]=(ret>0).astype(float)
        vol=pd.Series([np.nan]*len(c), index=c.index, dtype=float); mdd=vol.copy(); mn=vol.copy()
        for t in range(len(c)-h):
            path=c.iloc[t:t+h+1].to_numpy(); daily=np.diff(np.log(path))
            vol.iloc[t]=100*np.sqrt(252/h*np.square(daily).sum())
            dd=path/np.maximum.accumulate(path)-1; mdd.iloc[t]=100*dd.min(); mn.iloc[t]=100*(path.min()/path[0]-1)
        out[f"volatility_h{h}"]=vol; out[f"mdd_h{h}"]=mdd; out[f"future_min_return_h{h}"]=mn
    return out

