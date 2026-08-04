from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

def invalid_ohlc_mask(df: pd.DataFrame) -> pd.Series:
    if not {"open","high","low","close"}<=set(df): return pd.Series(False,index=df.index)
    return (df[["open","high","low","close"]]<=0).any(axis=1)|(df.high<df[["open","close"]].max(axis=1))|(df.low>df[["open","close"]].min(axis=1))|(df.high<df.low)

def apply_invalid_ohlc_policy(df: pd.DataFrame,policy="mask_features") -> tuple[pd.DataFrame,pd.DataFrame]:
    mask=invalid_ohlc_mask(df); invalid=df.loc[mask,[c for c in ["date","open","high","low","close","volume"] if c in df]].copy(); out=df.copy()
    if not mask.any(): return out,invalid
    if policy=="error": raise ValueError(f"Found {int(mask.sum())} invalid OHLC rows")
    if policy=="drop_rows": out=out.loc[~mask].reset_index(drop=True)
    elif policy=="mask_features": out.loc[mask,[c for c in ["open","high","low"] if c in out]]=float("nan")
    elif policy=="close_only_fallback": out=out.drop(columns=[c for c in ["open","high","low"] if c in out])
    else: raise ValueError(f"Unknown invalid_ohlc_policy: {policy}")
    return out,invalid

def assess_quality(df: pd.DataFrame) -> dict:
    cols=set(df.columns); issues=[]
    if {"open","high","low","close"} <= cols:
        bad_high=int((df.high < df[["open","close"]].max(axis=1)).sum())
        bad_low=int((df.low > df[["open","close"]].min(axis=1)).sum())
        if bad_high or bad_low: issues.append(f"OHLC constraint violations: high={bad_high}, low={bad_low}")
    else: issues.append("OHLC incomplete; range features disabled")
    if "volume" not in cols: issues.append("Volume missing; volume features disabled")
    return {"rows":len(df), "start":str(df.date.min().date()), "end":str(df.date.max().date()),
            "duplicate_dates":int(df.date.duplicated().sum()), "missing":df.isna().sum().to_dict(), "issues":issues}

def save_quality(report: dict, path: str | Path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, indent=2), encoding="utf-8")
