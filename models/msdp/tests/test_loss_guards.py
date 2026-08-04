import pytest,torch
from msdp.losses import pinball
def test_nan_loss_is_detectable():
    loss=pinball(torch.tensor([[[float("nan")]]]),torch.tensor([[0.]]),[.5]); assert not torch.isfinite(loss)
