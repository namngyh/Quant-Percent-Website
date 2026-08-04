from __future__ import annotations
import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import brier_score_loss, log_loss, balanced_accuracy_score, f1_score, matthews_corrcoef, roc_auc_score

def pinball_np(y,p,q):
    e=y[...,None]-p; qs=np.asarray(q); return float(np.mean(np.maximum(qs*e,(qs-1)*e)))

def interval_metrics(y,lo,hi,alpha=.1):
    width=hi-lo; score=width+2/alpha*(lo-y)*(y<lo)+2/alpha*(y-hi)*(y>hi)
    return {"coverage":float(np.mean((y>=lo)&(y<=hi))),"width":float(np.mean(width)),"winkler":float(np.mean(score))}

def evaluate_arrays(yret,ymdd,yvol,ydir,out,qr=(.05,.25,.5,.75,.95),qm=(.1,.5,.9)):
    metrics={}
    for j,h in enumerate([5,20,60][:yret.shape[1]]):
        med=out["return_quantiles"][:,j,len(qr)//2]; p=out["direction_prob"][:,j]; cls=p>=.5
        metrics[f"h{h}"]={
            "return_mae":float(np.mean(abs(yret[:,j]-med))),
            "return_rmse":float(np.sqrt(np.mean((yret[:,j]-med)**2))),
            "return_pinball":pinball_np(yret[:,j],out["return_quantiles"][:,j],qr),
            "spearman":float(spearmanr(yret[:,j],med).statistic),
            "sign_accuracy":float(np.mean((med>0)==ydir[:,j])),
            "brier":float(brier_score_loss(ydir[:,j],p)),
            "log_loss":float(log_loss(ydir[:,j],np.clip(p,1e-6,1-1e-6))),
            "balanced_accuracy":float(balanced_accuracy_score(ydir[:,j],cls)),
            "f1":float(f1_score(ydir[:,j],cls,zero_division=0)),
            "mcc":float(matthews_corrcoef(ydir[:,j],cls)),
            "mdd_mae":float(np.mean(abs(ymdd[:,j]-out["mdd_quantiles"][:,j,1]))),
            "mdd_pinball":pinball_np(ymdd[:,j],out["mdd_quantiles"][:,j],qm),
            "volatility_mae":float(np.mean(abs(yvol[:,j]-out["volatility"][:,j]))),
            "volatility_rmse":float(np.sqrt(np.mean((yvol[:,j]-out["volatility"][:,j])**2))),
        }
        if len(np.unique(ydir[:,j]))==2: metrics[f"h{h}"]["roc_auc"]=float(roc_auc_score(ydir[:,j],p))
        metrics[f"h{h}"].update(interval_metrics(yret[:,j],out["return_quantiles"][:,j,0],out["return_quantiles"][:,j,-1]))
    return metrics
