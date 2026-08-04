import torch
from torch import nn
from torch.nn import functional as F

class MedianCenteredReturnQuantileHead(nn.Module):
    def __init__(self,d): super().__init__(); self.raw=nn.Linear(d,5)
    def forward(self,x):
        median,l1,l2,u1,u2=self.raw(x).unbind(-1); gap25=F.softplus(l1); gap05=gap25+F.softplus(l2); gap75=F.softplus(u1); gap95=gap75+F.softplus(u2)
        return torch.stack([median-gap05,median-gap25,median,median+gap75,median+gap95],-1)

class NegativeMonotonicMDDHead(nn.Module):
    def __init__(self,d): super().__init__(); self.raw=nn.Linear(d,3)
    def forward(self,x):
        a,b,c=self.raw(x).unbind(-1); severity90=F.softplus(a); severity50=severity90+F.softplus(b); severity10=severity50+F.softplus(c)
        return torch.stack([-severity10,-severity50,-severity90],-1)

class AuxReturnHead(nn.Module):
    def __init__(self,d,dropout=.1): super().__init__(); self.net=nn.Sequential(nn.Linear(d,d),nn.GELU(),nn.Dropout(dropout),nn.Linear(d,1))
    def forward(self,x): return self.net(x).squeeze(-1)

# Backward-compatible alias for external imports; return grids are fixed at five quantiles.
MonotonicQuantileHead=MedianCenteredReturnQuantileHead

