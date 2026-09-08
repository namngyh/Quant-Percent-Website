"""Chiến lược mẫu: copy file này, đổi tên rồi sửa logic."""

import pandas as pd

STRATEGY = {
    "name": "Vượt đỉnh N nến",
    "side": "both",             # "long" | "short" | "both"
    "description": "Mua khi vượt đỉnh, bán khi thủng đáy.",
    "params": {
        "lookback": {"type": "int", "default": 20, "min": 5, "max": 200,
                     "label": "Số nến nhìn lại"},
    },
}


def signals(df, params):
    n = params["lookback"]
    # shift(1): đỉnh/đáy của N nến TRƯỚC, không tính nến hiện tại.
    highest = df["high"].rolling(n).max().shift(1)
    lowest = df["low"].rolling(n).min().shift(1)

    out = pd.Series(0, index=df.index, dtype="int8")
    out[df["close"] > highest] = 1
    out[df["close"] < lowest] = -1

    out.iloc[:n] = 0            # cửa sổ khởi động: đứng ngoài
    return out
