import torch
from torch import nn
from torch.nn import functional as F

class CausalConv1d(nn.Module):
    def __init__(self,in_channels,out_channels,kernel_size=3,dilation=1,bias=True):
        super().__init__(); self.left_padding=dilation*(kernel_size-1); self.conv=nn.Conv1d(in_channels,out_channels,kernel_size,dilation=dilation,padding=0,bias=bias)
    def forward(self,x): return self.conv(F.pad(x,(self.left_padding,0)))

class CausalResidualBlock(nn.Module):
    def __init__(self,channels,dropout=.1,dilation=1):
        super().__init__(); self.conv1=CausalConv1d(channels,channels,3,dilation); self.conv2=CausalConv1d(channels,channels,3,dilation); self.norm1=nn.LayerNorm(channels); self.norm2=nn.LayerNorm(channels); self.drop=nn.Dropout(dropout)
    def forward(self,x):
        y=self.conv1(x).transpose(1,2); y=self.drop(F.gelu(self.norm1(y))).transpose(1,2); y=self.conv2(y); return self.norm2((x+y).transpose(1,2)).transpose(1,2)

ResidualBlock=CausalResidualBlock
