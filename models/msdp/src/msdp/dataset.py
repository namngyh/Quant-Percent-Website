from __future__ import annotations
import numpy as np
import torch
from torch.utils.data import Dataset

class SequenceDataset(Dataset):
    def __init__(self, features, targets, indices, lookback, target_columns):
        self.x=np.asarray(features,dtype=np.float32); self.y=np.asarray(targets[target_columns],dtype=np.float32)
        self.indices=np.asarray([i for i in indices if i>=lookback-1 and np.isfinite(self.x[i-lookback+1:i+1]).all() and np.isfinite(self.y[i]).all()])
        self.lookback=lookback
    def __len__(self): return len(self.indices)
    def __getitem__(self,j):
        i=self.indices[j]; return torch.from_numpy(self.x[i-self.lookback+1:i+1]), torch.from_numpy(self.y[i]), int(i)
