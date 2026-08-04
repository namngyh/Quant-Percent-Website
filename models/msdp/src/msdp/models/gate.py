import torch
from torch import nn

class ContextNetwork(nn.Module):
    def __init__(self,n_features,latent,n_experts,dropout=.1): super().__init__(); self.net=nn.Sequential(nn.Linear(n_features+n_experts*latent,latent),nn.GELU(),nn.Dropout(dropout),nn.LayerNorm(latent))
    def forward(self,x_last,latents): return self.net(torch.cat([x_last,latents.flatten(1)],-1))

class HorizonGate(nn.Module):
    def __init__(self,latent,n_horizons,n_experts=4,temperature=1.,dropout=.1,horizon_dependent=True):
        super().__init__(); self.temperature=float(temperature); self.horizon_dependent=horizon_dependent; self.embedding=nn.Embedding(n_horizons,latent); self.score=nn.Sequential(nn.Linear(3*latent,latent),nn.GELU(),nn.Dropout(dropout),nn.Linear(latent,1))
    def forward(self,latents,context):
        b,k,d=latents.shape; scores=[]
        for h in range(self.embedding.num_embeddings):
            e=self.embedding.weight[h if self.horizon_dependent else 0].expand(b,k,-1); c=context[:,None,:].expand(-1,k,-1); scores.append(self.score(torch.cat([latents,c,e],-1)).squeeze(-1))
        return torch.softmax(torch.stack(scores,1)/self.temperature,dim=-1)

