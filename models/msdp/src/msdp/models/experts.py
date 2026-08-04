import torch
from torch import nn
from .blocks import CausalResidualBlock

class ScaleExpert(nn.Module):
    def __init__(self,n_features,hidden,latent,window,pool=1,n_blocks=2,dropout=.1,feature_indices=None):
        super().__init__(); self.window=int(window); self.pool=int(pool); indices=list(range(n_features)) if feature_indices is None else list(feature_indices); self.register_buffer("feature_indices",torch.tensor(indices,dtype=torch.long))
        self.input=nn.Sequential(nn.Linear(len(indices),hidden),nn.LayerNorm(hidden),nn.GELU(),nn.Dropout(dropout)); self.blocks=nn.Sequential(*[CausalResidualBlock(hidden,dropout,2**i) for i in range(n_blocks)]); self.output=nn.Sequential(nn.Linear(2*hidden,latent),nn.LayerNorm(latent))
    def forward(self,x):
        x=x[:,-self.window:,self.feature_indices]
        if self.pool>1:
            keep=(x.shape[1]//self.pool)*self.pool; x=x[:,-keep:]; x=x.reshape(x.shape[0],-1,self.pool,x.shape[-1]).mean(2)
        h=self.blocks(self.input(x).transpose(1,2)).transpose(1,2); return self.output(torch.cat([h.mean(1),h[:,-1]],-1))

class ShortScaleExpert(ScaleExpert): pass
class MediumScaleExpert(ScaleExpert): pass
class LongScaleExpert(ScaleExpert): pass
class RangeVolatilityExpert(ScaleExpert): pass

