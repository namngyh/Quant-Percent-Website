"""Chiến lược: Trend Breakout + EMA + ATR Filter."""

import pandas as pd

STRATEGY = {
    "name": "Trend Breakout ATR",
    "side": "both",
    "description": (
        "Giao dịch breakout theo xu hướng, kết hợp EMA regime "
        "và ATR để loại bỏ các breakout trong vùng biến động thấp."
    ),
    "params": {
        "lookback": {
            "type": "int",
            "default": 20,
            "min": 5,
            "max": 100,
            "label": "Số nến breakout",
        },
        "ema_fast": {
            "type": "int",
            "default": 20,
            "min": 5,
            "max": 100,
            "label": "EMA nhanh",
        },
        "ema_slow": {
            "type": "int",
            "default": 50,
            "min": 20,
            "max": 200,
            "label": "EMA chậm",
        },
        "atr_period": {
            "type": "int",
            "default": 14,
            "min": 5,
            "max": 50,
            "label": "ATR Period",
        },
        "atr_threshold": {
            "type": "float",
            "default": 0.002,
            "min": 0.0001,
            "max": 0.02,
            "step": 0.0001,
            "label": "ATR/Close tối thiểu",
        },
    },
}


def signals(df, params):
    lookback = params["lookback"]
    ema_fast_period = params["ema_fast"]
    ema_slow_period = params["ema_slow"]
    atr_period = params["atr_period"]
    atr_threshold = params["atr_threshold"]

    # =========================================================
    # 1. EMA TREND REGIME
    # =========================================================

    ema_fast = df["close"].ewm(
        span=ema_fast_period,
        adjust=False
    ).mean()

    ema_slow = df["close"].ewm(
        span=ema_slow_period,
        adjust=False
    ).mean()

    bullish_regime = ema_fast > ema_slow
    bearish_regime = ema_fast < ema_slow

    # =========================================================
    # 2. ATR
    # =========================================================

    prev_close = df["close"].shift(1)

    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    atr = true_range.rolling(
        atr_period
    ).mean()

    # Chuẩn hóa ATR theo giá
    volatility = atr / df["close"]

    volatility_ok = volatility > atr_threshold

    # =========================================================
    # 3. BREAKOUT CỦA N NẾN TRƯỚC
    # =========================================================

    highest = (
        df["high"]
        .rolling(lookback)
        .max()
        .shift(1)
    )

    lowest = (
        df["low"]
        .rolling(lookback)
        .min()
        .shift(1)
    )

    breakout_long = df["close"] > highest
    breakout_short = df["close"] < lowest

    # =========================================================
    # 4. SIGNAL
    # =========================================================

    out = pd.Series(
        0,
        index=df.index,
        dtype="int8"
    )

    # LONG:
    # Breakout đỉnh + xu hướng tăng + volatility đủ lớn
    long_condition = (
        breakout_long
        & bullish_regime
        & volatility_ok
    )

    # SHORT:
    # Breakout đáy + xu hướng giảm + volatility đủ lớn
    short_condition = (
        breakout_short
        & bearish_regime
        & volatility_ok
    )

    out[long_condition] = 1
    out[short_condition] = -1

    # =========================================================
    # 5. STARTUP WINDOW
    # =========================================================

    warmup = max(
        lookback,
        ema_slow_period,
        atr_period
    )

    out.iloc[:warmup] = 0

    return out