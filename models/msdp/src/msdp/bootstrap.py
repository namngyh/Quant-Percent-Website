import numpy as np

def moving_block_ci(a,b,metric,n_resamples=500,block=20,seed=42):
    rng=np.random.default_rng(seed); n=len(a); vals=[]
    for _ in range(n_resamples):
        starts=rng.integers(0,max(1,n-block+1),size=int(np.ceil(n/block))); ix=np.concatenate([np.arange(s,min(s+block,n)) for s in starts])[:n]
        vals.append(metric(a[ix])-metric(b[ix]))
    return tuple(np.quantile(vals,[.025,.975]))

