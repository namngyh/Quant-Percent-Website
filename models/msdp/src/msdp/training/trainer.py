from __future__ import annotations
import copy
import numpy as np
import torch
from torch.utils.data import DataLoader
from ..losses import multitask_loss

def train_model(model,train_ds,val_ds,cfg,device="cpu",trial=None):
    model.to(device); tc=cfg["training"]; opt=torch.optim.AdamW(model.parameters(),lr=tc["learning_rate"],weight_decay=tc["weight_decay"]); scheduler=torch.optim.lr_scheduler.ReduceLROnPlateau(opt,patience=max(1,tc["patience"]//3),factor=.5)
    train=DataLoader(train_ds,batch_size=tc["batch_size"],shuffle=True,num_workers=tc.get("num_workers",0)); val=DataLoader(val_ds,batch_size=tc["batch_size"],shuffle=False,num_workers=tc.get("num_workers",0))
    if not len(train) or not len(val): raise ValueError("Empty train or validation dataset after warm-up/purge")
    best=float("inf"); state=None; patience=0; history=[]
    for epoch in range(tc["epochs"]):
        record={"epoch":epoch+1,"learning_rate":opt.param_groups[0]["lr"]}; model.train(); train_parts={}
        for x,y,_ in train:
            x=x.to(device); y=y.to(device); opt.zero_grad(); total,parts=multitask_loss(model(x),y,cfg["horizons"],cfg["quantiles"],cfg["mdd_quantiles"],cfg["loss_weights"])
            if not torch.isfinite(total): raise FloatingPointError(f"Non-finite training loss at epoch {epoch+1}")
            total.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),float(tc.get("gradient_clip",1.))); opt.step()
            for k,v in {"total":total,**parts}.items(): train_parts.setdefault(k,[]).append(float(v.detach()))
        model.eval(); vals=[]
        with torch.no_grad():
            for x,y,_ in val:
                total,_=multitask_loss(model(x.to(device)),y.to(device),cfg["horizons"],cfg["quantiles"],cfg["mdd_quantiles"],cfg["loss_weights"])
                if not torch.isfinite(total): raise FloatingPointError(f"Non-finite validation loss at epoch {epoch+1}")
                vals.append(float(total))
        score=float(np.mean(vals)); scheduler.step(score); record.update({f"train_{k}":float(np.mean(v)) for k,v in train_parts.items()}); record["validation_total"]=score; history.append(record)
        if trial is not None: trial.report(score,epoch); 
        if trial is not None and trial.should_prune():
            import optuna; raise optuna.TrialPruned()
        if score<best: best=score; state=copy.deepcopy(model.state_dict()); patience=0
        else: patience+=1
        if patience>=tc["patience"]: break
    if state is None: raise RuntimeError("Training produced no finite checkpoint")
    model.load_state_dict(state); return model,history

def predict(model,ds,batch_size=256,device="cpu"):
    model.eval(); bags={}; indices=[]
    with torch.no_grad():
        for x,_,ix in DataLoader(ds,batch_size=batch_size,shuffle=False):
            out=model(x.to(device)); indices.extend(ix.numpy().tolist())
            for k,v in out.items():
                if k not in {"expert_latents","context","direction_logits"}: bags.setdefault(k,[]).append(v.cpu().numpy())
    if not indices: raise ValueError("Prediction dataset is empty")
    return {k:np.concatenate(v) for k,v in bags.items()},np.asarray(indices)

def train_fixed_epochs(model,dataset,cfg,epochs,device="cpu"):
    """Production retraining after evaluation with an epoch policy frozen beforehand."""
    model.to(device); tc=cfg["training"]; loader=DataLoader(dataset,batch_size=tc["batch_size"],shuffle=True,num_workers=tc.get("num_workers",0)); opt=torch.optim.AdamW(model.parameters(),lr=tc["learning_rate"],weight_decay=tc["weight_decay"])
    for epoch in range(int(epochs)):
        model.train()
        for x,y,_ in loader:
            opt.zero_grad(); total,_=multitask_loss(model(x.to(device)),y.to(device),cfg["horizons"],cfg["quantiles"],cfg["mdd_quantiles"],cfg["loss_weights"])
            if not torch.isfinite(total): raise FloatingPointError(f"Non-finite production loss at epoch {epoch+1}")
            total.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),float(tc.get("gradient_clip",1.))); opt.step()
    return model
