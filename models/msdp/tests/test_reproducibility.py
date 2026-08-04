import torch
from msdp.models import MSDP
from msdp.reproducibility import set_global_seed
def test_seed_reproducibility():
    set_global_seed(42); a=MSDP(3,hidden_dim=8,latent_dim=8); x=torch.randn(1,252,3); a.eval(); ya=a(x)["return_quantiles"]; set_global_seed(42); b=MSDP(3,hidden_dim=8,latent_dim=8); x2=torch.randn(1,252,3); b.eval(); assert torch.allclose(ya,b(x2)["return_quantiles"])

