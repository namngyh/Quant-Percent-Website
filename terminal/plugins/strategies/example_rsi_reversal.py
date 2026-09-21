"""Ví dụ chiến lược — RSI Mean Reversion (hồi quy về trung bình).

RSI xuống dưới ngưỡng quá bán → LONG. Lên trên ngưỡng quá mua → SHORT.
Giữ vị thế cho tới khi RSI về lại vùng giữa, rồi đứng ngoài.

Khác với EMA Crossover, chiến lược này KHÔNG luôn có vị thế — nó dùng giá
trị 0 để đứng ngoài thị trường. Xem cột "Tỷ lệ nắm giữ" trong kết quả.
"""

import pandas as pd

STRATEGY = {
    "name": "RSI Reversal",
    "side": "both",
    "description": "Mua khi quá bán, bán khi quá mua; đứng ngoài ở vùng giữa.",
    "params": {
        "length":   {"type": "int", "default": 14, "min": 2,  "max": 100, "label": "Chu kỳ RSI"},
        "oversold": {"type": "int", "default": 30, "min": 5,  "max": 45,  "label": "Ngưỡng quá bán"},
        "exit_mid": {"type": "int", "default": 50, "min": 40, "max": 60,  "label": "Ngưỡng thoát"},
    },
}


def _rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1.0 / length, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1.0 / length, adjust=False).mean()
    # A stretch with no losing bars makes loss 0; leave those points empty
    # rather than dividing by zero and drawing RSI as infinity.
    rs = gain / loss.replace(0, float("nan"))
    return 100.0 - 100.0 / (1.0 + rs)


def signals(df, params):
    rsi = _rsi(df["close"], params["length"])
    oversold = params["oversold"]
    overbought = 100 - oversold
    middle = params["exit_mid"]

    out = pd.Series(0, index=df.index, dtype="int8")
    position = 0

    # Stateful: enter at the extreme, hold until RSI crosses back through the
    # middle. Vectorising this would lose the "hold until exit" behaviour.
    values = rsi.to_numpy()
    result = out.to_numpy().copy()

    for i, value in enumerate(values):
        if value != value:          # NaN during the warm-up window
            result[i] = 0
            continue

        if position == 0:
            if value < oversold:
                position = 1
            elif value > overbought:
                position = -1
        elif position == 1 and value >= middle:
            position = 0
        elif position == -1 and value <= middle:
            position = 0

        result[i] = position

    return pd.Series(result, index=df.index)
