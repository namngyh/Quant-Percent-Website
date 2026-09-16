"""Mean Reversion với Student-t Bollinger Bands trên VN30F1M."""

import numpy as np
import pandas as pd
from scipy.stats import t


STRATEGY = {
    "name": "VN30F1M Student-t Bollinger Mean Reversion",
    "side": "both",               # long | short | both
    "params": {
        # Số nến dùng để tính mean và volatility
        "length": {
            "type": "int",
            "default": 20,
            "min": 5,
            "max": 400,
        },

        # Bậc tự do của Student-t.
        # df càng nhỏ -> tail càng dày -> band càng rộng.
        "df": {
            "type": "float",
            "default": 5.0,
            "min": 2.1,
            "max": 100.0,
        },

        # Xác suất nằm ngoài hai band.
        # alpha=0.05 tương ứng khoảng 95% central interval.
        "alpha": {
            "type": "float",
            "default": 0.05,
            "min": 0.001,
            "max": 0.30,
        },

        # Nếu True: chỉ cần high/low chạm band là kích hoạt entry.
        # Nếu False: close phải ra ngoài band.
        "use_wick": {
            "type": "bool",
            "default": True,
        },
    },
}


def signals(df, params):
    """
    Trả về Series:
        1  = giữ Long
       -1  = giữ Short
        0  = đứng ngoài

    Logic
    -----
    Flat:
        low <= lower band  -> Long
        high >= upper band -> Short

    Long:
        giữ Long cho tới khi close >= MA

    Short:
        giữ Short cho tới khi close <= MA

    Tất cả điều kiện tại nến i chỉ dùng dữ liệu có sẵn khi nến i đóng.
    Engine sẽ thực hiện thay đổi vị thế tại open của nến i+1.
    """

    length = int(params["length"])
    nu = float(params["df"])
    alpha = float(params["alpha"])
    use_wick = bool(params["use_wick"])

    close = df["close"]

    # ============================================================
    # 1. Đường trung bình
    # ============================================================
    ma = close.rolling(
        window=length,
        min_periods=length
    ).mean()

    # ============================================================
    # 2. Ước lượng scale
    # ============================================================
    # Sample standard deviation.
    sigma = close.rolling(
        window=length,
        min_periods=length
    ).std(ddof=1)

    # ============================================================
    # 3. Student-t multiplier
    # ============================================================
    #
    # Ví dụ:
    # Normal 95%:      q ≈ 1.96
    # Student-t df=5:  q ≈ 2.571
    #
    # Vì Student-t có tail dày hơn nên band thường rộng hơn
    # Normal Bollinger tại cùng coverage probability.
    #
    q = t.ppf(1.0 - alpha / 2.0, df=nu)

    upper = ma + q * sigma
    lower = ma - q * sigma

    # ============================================================
    # 4. Điều kiện chạm band
    # ============================================================

    if use_wick:
        touch_lower = df["low"] <= lower
        touch_upper = df["high"] >= upper
    else:
        touch_lower = close <= lower
        touch_upper = close >= upper

    # ============================================================
    # 5. State machine
    # ============================================================

    signal = pd.Series(
        0,
        index=df.index,
        dtype=int,
    )

    position = 0

    for i in range(len(df)):

        # Chưa đủ dữ liệu để tính band.
        if (
            pd.isna(ma.iloc[i])
            or pd.isna(upper.iloc[i])
            or pd.isna(lower.iloc[i])
        ):
            signal.iloc[i] = 0
            continue

        # --------------------------------------------------------
        # FLAT
        # --------------------------------------------------------
        if position == 0:

            lower_hit = bool(touch_lower.iloc[i])
            upper_hit = bool(touch_upper.iloc[i])

            # Có trường hợp một cây nến cực lớn chạm cả hai band.
            # Không giao dịch để tránh quyết định tùy ý.
            if lower_hit and upper_hit:
                position = 0

            elif lower_hit:
                # Oversold -> mean reversion Long
                position = 1

            elif upper_hit:
                # Overbought -> mean reversion Short
                position = -1

        # --------------------------------------------------------
        # LONG
        # --------------------------------------------------------
        elif position == 1:

            # Giá đã hồi về / vượt mean.
            if close.iloc[i] >= ma.iloc[i]:
                position = 0

        # --------------------------------------------------------
        # SHORT
        # --------------------------------------------------------
        elif position == -1:

            # Giá đã giảm về / dưới mean.
            if close.iloc[i] <= ma.iloc[i]:
                position = 0

        signal.iloc[i] = position

    return signal