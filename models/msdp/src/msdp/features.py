from __future__ import annotations
import numpy as np
import pandas as pd

def _slope(x):
    y=np.asarray(x); z=np.arange(len(y)); return np.polyfit(z,y,1)[0] if np.isfinite(y).all() else np.nan

def build_features(df: pd.DataFrame, min_nonmissing=.70, invalid_ohlc_policy="mask_features"):
    from .data_quality import apply_invalid_ohlc_policy
    df,_=apply_invalid_ohlc_policy(df,invalid_ohlc_policy)
    c=df.close.astype(float); lr=np.log(c).diff(); f=pd.DataFrame(index=df.index); meta=[]
    range_vol_groups={"range","volatility","drawdown","market_position"}
    range_vol_names={"macd","macd_histogram","delta_macd","delta_histogram","rsi_14","volume_shock","price_volume_corr_20"}
    def add(name, values, group, formula, lookback, requires="Close"):
        tags=["short","medium","long"]
        if group in range_vol_groups or name in range_vol_names: tags.append("range_volatility")
        f[name]=values; meta.append({"name":name,"group":group,"formula":formula,"lookback":lookback,"requires":requires,"requires_ohlcv":requires.lower()!="close","expert_tags":"|".join(tags)})
    add("log_return_1",lr,"return","log(C_t/C_t-1)",1)
    for w in [2,5,10,20,60]: add(f"return_{w}",c.pct_change(w),"return",f"C_t/C_t-{w}-1",w)
    if "open" in df:
        add("overnight_gap",np.log(df.open/c.shift()),"return","log(O_t/C_t-1)",1,"Open")
        add("intraday_return",np.log(c/df.open),"return","log(C_t/O_t)",1,"Open")
    if {"open","high","low"} <= set(df):
        prev=c.shift(); tr=pd.concat([df.high-df.low,(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1)
        hl=np.log(df.high/df.low)
        add("log_high_low_range",hl,"range","log(H/L)",1,"OHLC")
        add("normalized_true_range",tr/c,"range","TR/C",1,"OHLC")
        add("atr_14",tr.rolling(14).mean()/c,"range","mean(TR,14)/C",14,"OHLC")
        add("parkinson_vol_20",np.sqrt(hl.pow(2).rolling(20).mean()/(4*np.log(2))*252),"range","Parkinson",20,"High Low")
        gk=.5*np.log(df.high/df.low).pow(2)-(2*np.log(2)-1)*np.log(c/df.open).pow(2)
        add("garman_klass_vol_20",np.sqrt(gk.clip(lower=0).rolling(20).mean()*252),"range","Garman-Klass",20,"OHLC")
    for w in [5,10,20,60]: add(f"rolling_vol_{w}",lr.rolling(w).std()*np.sqrt(252),"volatility","std(log return)*sqrt(252)",w)
    for w in [20,60]:
        add(f"downside_vol_{w}",lr.where(lr<0,0).rolling(w).std()*np.sqrt(252),"volatility","downside std",w)
        add(f"skew_{w}",lr.rolling(w).skew(),"volatility","rolling skew",w)
        add(f"kurtosis_{w}",lr.rolling(w).kurt(),"volatility","rolling kurtosis",w)
    for w in [5,20,60,200]:
        ma=c.rolling(w).mean(); add(f"sma_distance_{w}",c/ma-1,"trend","C/SMA-1",w)
    for w in [12,26,50,200]:
        ema=c.ewm(span=w,adjust=False).mean(); add(f"ema_distance_{w}",c/ema-1,"trend","C/EMA-1",w)
    macd=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean(); sig=macd.ewm(span=9,adjust=False).mean()
    add("macd",macd/c,"trend","(EMA12-EMA26)/C",26); add("macd_signal",sig/c,"trend","EMA9(MACD)/C",35)
    add("macd_histogram",(macd-sig)/c,"trend","MACD-signal",35); add("delta_macd",macd.diff()/c,"trend","delta MACD/C",27)
    add("delta_histogram",(macd-sig).diff()/c,"trend","delta histogram/C",36)
    delta=c.diff(); gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean(); loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    add("rsi_14",100-100/(1+gain/loss.replace(0,np.nan)),"trend","Wilder RSI",14)
    for w in [20,60]: add(f"slope_{w}",np.log(c).rolling(w).apply(_slope,raw=True),"trend","OLS slope log(C)",w)
    for w in [10,20]: add(f"up_ratio_{w}",(lr>0).rolling(w).mean(),"trend","fraction positive",w)
    for w in [20,60,252]:
        peak=c.rolling(w).max(); add(f"drawdown_{w}",c/peak-1,"drawdown","C/rolling_max-1",w)
    add("drawdown_change",f["drawdown_60"].diff(),"drawdown","delta drawdown60",61)
    for w in [20,60]:
        lo=c.rolling(w).min(); hi=c.rolling(w).max(); add(f"position_{w}",(c-lo)/(hi-lo),"market_position","rolling min-max",w)
    add("bollinger_z_20",(c-c.rolling(20).mean())/c.rolling(20).std(),"market_position","zscore(C,20)",20)
    add("median_distance_20",c/c.rolling(20).median()-1,"market_position","C/median20-1",20)
    if "volume" in df:
        v=np.log1p(df.volume.clip(lower=0)); add("log_volume",v,"volume","log(1+V)",1,"Volume")
        add("volume_return",v.diff(),"volume","delta log volume",1,"Volume")
        for w in [20,60]: add(f"volume_zscore_{w}",(v-v.rolling(w).mean())/v.rolling(w).std(),"volume","zscore(logV)",w,"Volume")
        add("price_volume_corr_20",lr.rolling(20).corr(v.diff()),"volume","corr(return,delta logV)",20,"Volume")
        add("signed_volume_proxy",np.sign(lr)*v,"volume","sign(return)*logV",1,"Volume")
        add("volume_shock",v-v.rolling(20).median(),"volume","logV-median20",20,"Volume")
    return f.replace([np.inf,-np.inf],np.nan), pd.DataFrame(meta)

def select_features_on_development(features,metadata,development_indices,max_missing=.20):
    """Remove structural warm-up first, then select columns from development only."""
    maximum_lookback=int(metadata.lookback.max()); warmup=maximum_lookback-1; development_indices=np.asarray(development_indices); eligible=development_indices[development_indices>=warmup]
    if not len(eligible): raise ValueError("No development rows remain after feature warm-up")
    missing=features.iloc[eligible].isna().mean(); keep=missing[missing<=max_missing].index.tolist()
    if not keep: raise ValueError("All features were removed using development-only missingness")
    return features[keep],metadata[metadata.name.isin(keep)].copy(),warmup
