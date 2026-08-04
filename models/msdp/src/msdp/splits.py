from __future__ import annotations
import numpy as np

def chronological_split(n, purge=60, dev_ratio=.70, cal_ratio=.15, minimums=None):
    usable=n-2*purge
    if usable <= 3: raise ValueError("Insufficient observations after purge")
    d=int(usable*dev_ratio); c=int(usable*cal_ratio); t=usable-d-c
    if minimums:
        md,mc,mt=minimums
        if usable < md+mc+mt: raise ValueError(f"Need at least {md+mc+mt+2*purge} valid rows")
        d=max(d,md); c=max(c,mc); t=usable-d-c
        if t<mt: d-=mt-t; t=mt
    dev=np.arange(0,d); cal=np.arange(d+purge,d+purge+c); test=np.arange(d+purge+c+purge,n)
    return {"development":dev,"calibration":cal,"test":test}

def expanding_folds(indices, n_folds=3, val_size=252, purge=60):
    idx=np.asarray(indices); need=n_folds*(val_size+purge)
    if len(idx)<=need: val_size=max(20,(len(idx)//(n_folds+1))-purge)
    folds=[]
    for k in range(n_folds,0,-1):
        ve=len(idx)-(k-1)*val_size; vs=ve-val_size; te=vs-purge
        if te>0 and vs<ve: folds.append((idx[:te],idx[vs:ve]))
    if not folds: raise ValueError("Not enough data for walk-forward folds")
    return folds

