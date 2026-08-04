import torch
from msdp.models import MSDP
def test_horizon_gate_and_disagreement():
    torch.manual_seed(4); o=MSDP(6,hidden_dim=8,latent_dim=8)(torch.randn(4,252,6)); assert o["expert_disagreement"].shape==(4,3); assert torch.allclose(o["expert_disagreement"],o["aux_return_median"].std(-1,unbiased=False)); assert not torch.allclose(o["gate_weights"][:,0],o["gate_weights"][:,1])

