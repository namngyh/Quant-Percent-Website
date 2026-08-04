import torch

def pinball(pred,target,quantiles):
    error=target.unsqueeze(-1)-pred; q=torch.as_tensor(quantiles,device=pred.device,dtype=pred.dtype); return torch.maximum(q*error,(q-1)*error).mean()

def gate_statistics(weights):
    usage=weights.mean(dim=(0,1)); k=weights.shape[-1]; balance=((usage-1/k)**2).sum(); entropy=-(weights*torch.log(weights.clamp_min(1e-8))).sum(-1).mean()
    return balance,{"gate_balance":balance,"gate_entropy":entropy,"normalized_gate_entropy":entropy/torch.log(torch.tensor(float(k),device=weights.device)),"gate_min":weights.min(),"gate_max":weights.max()}

def multitask_loss(out,y,horizons,qr,qm,weights):
    h=len(horizons); ret=y[:,:h]; direction=y[:,h:2*h]; mdd=y[:,2*h:3*h]; vol=y[:,3*h:4*h]
    balance,gate=gate_statistics(out["gate_weights"])
    losses={"return":pinball(out["return_quantiles"],ret,qr),"direction":torch.nn.functional.binary_cross_entropy_with_logits(out["direction_logits"],direction),"mdd":pinball(out["mdd_quantiles"],mdd,qm),"volatility":torch.nn.functional.huber_loss(out["volatility"],vol),"balance":balance,"aux":torch.nn.functional.l1_loss(out["aux_return_median"],ret.unsqueeze(-1).expand_as(out["aux_return_median"]))}
    total=sum(float(weights.get(k,0))*v for k,v in losses.items()); return total,{**losses,**gate}
