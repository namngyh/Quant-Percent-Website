import torch
from msdp.models.blocks import CausalConv1d
def test_causal_convolution_ignores_future_positions():
    torch.manual_seed(1); layer=CausalConv1d(2,3,3); x=torch.randn(1,2,12); a=layer(x); x[:,:,7:]+=1000; b=layer(x); assert torch.allclose(a[:,:,:7],b[:,:,:7])

