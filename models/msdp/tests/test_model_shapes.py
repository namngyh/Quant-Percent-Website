import torch
from msdp.models import MSDP
def test_shapes_and_ranges():
    o=MSDP(8,hidden_dim=8,latent_dim=8)(torch.randn(2,252,8)); assert o["return_quantiles"].shape==(2,3,5); assert o["gate_weights"].shape==(2,3,4); assert o["aux_return_median"].shape==(2,3,4); assert torch.allclose(o["gate_weights"].sum(-1),torch.ones(2,3),atol=1e-6); assert ((o["direction_prob"]>=0)&(o["direction_prob"]<=1)).all(); assert torch.isfinite(o["volatility"]).all()

