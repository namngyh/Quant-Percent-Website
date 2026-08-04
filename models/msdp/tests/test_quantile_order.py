import torch
from msdp.models import MSDP
def test_quantile_order_sign_and_gradient():
    m=MSDP(4,hidden_dim=8,latent_dim=8); o=m(torch.randn(3,252,4)); assert (o["return_quantiles"].diff(dim=-1)>=0).all(); assert (o["mdd_quantiles"].diff(dim=-1)>=0).all(); assert (o["mdd_quantiles"]<=0).all(); o["mdd_quantiles"].sum().backward(); assert all(p.grad is not None for p in m.mdd.parameters())

