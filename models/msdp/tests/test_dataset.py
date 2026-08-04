import numpy as np,pandas as pd
from msdp.dataset import SequenceDataset
def test_shape():
    d=SequenceDataset(np.ones((20,3)),pd.DataFrame({"y":np.ones(20)}),range(20),5,["y"]); x,y,_=d[0]; assert x.shape==(5,3) and y.shape==(1,)

