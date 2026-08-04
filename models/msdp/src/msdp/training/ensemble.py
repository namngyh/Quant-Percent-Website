import numpy as np

def average_predictions(predictions):
    out={k:np.mean([p[k] for p in predictions],axis=0) for k in predictions[0]}
    for key in ("return_quantiles","mdd_quantiles"): out[key]=np.maximum.accumulate(out[key],axis=-1)
    out["mdd_quantiles"]=np.minimum(out["mdd_quantiles"],0)
    if "aux_return_median" in out: out["expert_disagreement"]=out["aux_return_median"].std(axis=-1)
    return out
