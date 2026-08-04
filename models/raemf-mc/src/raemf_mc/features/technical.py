"""Causal technical feature generation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from raemf_mc.features.registry import FeatureRegistry


def _safe_div(a: pd.Series, b: pd.Series, eps: float = 1e-12) -> pd.Series:
    return a / (b.replace(0, np.nan) + eps)


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, FeatureRegistry]:
    """Build causal technical features using only data up to each row."""
    x = pd.DataFrame(index=df.index)
    reg = FeatureRegistry()
    close = df["close"].astype(float)
    ret1 = np.log(close / close.shift(1))
    x["ret_1"] = ret1
    reg.add("ret_1", "return_momentum", 1, "close")
    for w in [2, 5, 10, 20, 40, 60]:
        x[f"log_return_{w}"] = np.log(close / close.shift(w))
        x[f"rolling_return_{w}"] = ret1.rolling(w, min_periods=max(2, w // 3)).sum()
        x[f"up_ratio_{w}"] = (ret1 > 0).rolling(w, min_periods=max(2, w // 3)).mean()
        x[f"drawdown_from_high_{w}"] = np.log(close / close.rolling(w, min_periods=max(2, w // 3)).max())
        x[f"distance_from_low_{w}"] = np.log(close / close.rolling(w, min_periods=max(2, w // 3)).min())
        reg.add(f"log_return_{w}", "return_momentum", w, "close")
        reg.add(f"rolling_return_{w}", "return_momentum", w, "close")
        reg.add(f"up_ratio_{w}", "return_momentum", w, "close")
        reg.add(f"drawdown_from_high_{w}", "return_momentum", w, "close")
        reg.add(f"distance_from_low_{w}", "return_momentum", w, "close")
    signs = np.sign(ret1.fillna(0))
    streak = signs.groupby((signs != signs.shift()).cumsum()).cumcount() + 1
    x["signed_streak"] = streak * signs
    reg.add("signed_streak", "return_momentum", 1, "close")

    for w in [5, 10, 20, 50, 100, 200]:
        sma = close.rolling(w, min_periods=max(3, w // 4)).mean()
        ema = close.ewm(span=w, adjust=False, min_periods=max(3, w // 4)).mean()
        x[f"sma_distance_{w}"] = close / sma - 1
        x[f"ema_distance_{w}"] = close / ema - 1
        x[f"sma_slope_{w}"] = sma / sma.shift(5) - 1
        x[f"ema_slope_{w}"] = ema / ema.shift(5) - 1
        x[f"ma_cross_{w}"] = (ema > sma).astype(float)
        reg.add(f"sma_distance_{w}", "trend", w, "close")
        reg.add(f"ema_distance_{w}", "trend", w, "close")
        reg.add(f"sma_slope_{w}", "trend", w, "close")
        reg.add(f"ema_slope_{w}", "trend", w, "close")
        reg.add(f"ma_cross_{w}", "trend", w, "close")
    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    x["macd"] = macd
    x["macd_signal"] = signal
    x["macd_hist"] = macd - signal
    for name in ["macd", "macd_signal", "macd_hist"]:
        reg.add(name, "trend", 26, "close")

    for w in [5, 10, 20, 40, 60]:
        vol = ret1.rolling(w, min_periods=max(3, w // 3)).std()
        x[f"volatility_{w}"] = vol
        x[f"downside_vol_{w}"] = ret1.where(ret1 < 0, 0).rolling(w, min_periods=max(3, w // 3)).std()
        x[f"upside_vol_{w}"] = ret1.where(ret1 > 0, 0).rolling(w, min_periods=max(3, w // 3)).std()
        x[f"vol_of_vol_{w}"] = vol.rolling(w, min_periods=max(3, w // 3)).std()
        reg.add(f"volatility_{w}", "volatility", w, "close")
        reg.add(f"downside_vol_{w}", "volatility", w, "close")
        reg.add(f"upside_vol_{w}", "volatility", w, "close")
        reg.add(f"vol_of_vol_{w}", "volatility", w, "close")
    x["ewma_volatility"] = ret1.ewm(span=40, adjust=False, min_periods=10).std()
    reg.add("ewma_volatility", "volatility", 40, "close")
    sma20 = close.rolling(20, min_periods=8).mean()
    sd20 = close.rolling(20, min_periods=8).std()
    x["bollinger_bandwidth"] = (4 * sd20) / sma20
    reg.add("bollinger_bandwidth", "volatility", 20, "close")

    if {"high", "low"}.issubset(df.columns) and not df[["high", "low"]].isna().all().any():
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        open_ = df.get("open", close).astype(float)
        x["hl_range"] = _safe_div(high - low, close)
        x["close_position_hl"] = _safe_div(close - low, high - low)
        x["candle_body"] = _safe_div(close - open_, close)
        x["upper_shadow"] = _safe_div(high - np.maximum(open_, close), close)
        x["lower_shadow"] = _safe_div(np.minimum(open_, close) - low, close)
        prev_close = close.shift(1)
        tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        x["atr_14"] = tr.rolling(14, min_periods=5).mean() / close
        park = (np.log(high / low) ** 2).rolling(20, min_periods=8).mean() / (4 * np.log(2))
        x["parkinson_volatility"] = np.sqrt(park)
        for name in ["hl_range", "close_position_hl", "candle_body", "upper_shadow", "lower_shadow", "atr_14", "parkinson_volatility"]:
            reg.add(name, "price_shape", 20, "open,high,low,close", requires_ohlc=True)

    if "volume" in df.columns and not df["volume"].isna().all():
        volu = df["volume"].replace(0, np.nan).astype(float)
        x["log_volume"] = np.log(volu)
        x["volume_change"] = np.log(volu / volu.shift(1))
        vmean = volu.rolling(20, min_periods=8).mean()
        vstd = volu.rolling(20, min_periods=8).std()
        x["volume_zscore"] = (volu - vmean) / (vstd + 1e-12)
        x["volume_ratio_20"] = volu / vmean
        x["return_volume_interaction"] = ret1 * x["volume_zscore"]
        obv = (np.sign(ret1.fillna(0)) * volu.fillna(0)).cumsum()
        x["obv_zscore"] = (obv - obv.rolling(60, min_periods=20).mean()) / (obv.rolling(60, min_periods=20).std() + 1e-12)
        for name in ["log_volume", "volume_change", "volume_zscore", "volume_ratio_20", "return_volume_interaction", "obv_zscore"]:
            reg.add(name, "volume", 60, "volume", requires_volume=True)

    date = pd.to_datetime(df["date"])
    calendar = pd.DataFrame(
        {
            "month": date.dt.month,
            "quarter": date.dt.quarter,
            "day_of_week": date.dt.dayofweek,
            "is_month_start": date.dt.is_month_start.astype(float),
            "is_month_end": date.dt.is_month_end.astype(float),
        },
        index=df.index,
    )
    x = pd.concat([x, calendar], axis=1)
    for name in ["month", "quarter", "day_of_week", "is_month_start", "is_month_end"]:
        reg.add(name, "calendar", 0, "date")
    x = x.replace([np.inf, -np.inf], np.nan)
    return x, reg
