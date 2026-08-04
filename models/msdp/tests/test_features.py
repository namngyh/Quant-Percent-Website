import numpy as np, pandas as pd
from msdp.features import build_features,select_features_on_development
def test_features_are_causal():
    n=400; z=np.exp(np.arange(n)/1000); d=pd.DataFrame({"close":100*z,"open":100*z,"high":101*z,"low":99*z,"volume":np.arange(n)+100}); a,_=build_features(d); d.loc[301:,"close"]*=2; b,_=build_features(d); pd.testing.assert_series_equal(a.loc[300],b.loc[300])
def test_close_only_and_missing_volume_are_supported():
    d=pd.DataFrame({"close":100*np.exp(np.arange(400)/1000)}); f,m=build_features(d); assert len(f.columns)>10 and not m.requires.astype(str).str.contains("Volume").any()
def test_feature_selection_uses_development_only_and_warmup_is_known():
    d=pd.DataFrame({"close":100*np.exp(np.arange(500)/1000)}); f,m=build_features(d); selected,_,warmup=select_features_on_development(f,m,np.arange(300),.2); changed=f.copy(); changed.loc[350:,selected.columns[0]]=np.nan; selected2,_,_=select_features_on_development(changed,m,np.arange(300),.2); assert list(selected)==list(selected2); assert warmup==int(m.lookback.max())-1

