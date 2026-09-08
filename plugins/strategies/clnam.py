import pandas as pd
from scipy.stats import t

STRATEGY = {
    "name": "Đảo chiều t-Bollinger Bands",
    "side": "both",             # "long" | "short" | "both"
    "description": "Mua khi chạm dải dưới (oversold), Bán khi chạm dải trên (overbought).",
    "params": {
        "length": {
            "type": "int", "default": 20, "min": 5, "max": 200,
            "label": "Cửa sổ (N)"
        },
        "alpha": {
            "type": "float", "default": 0.05, "min": 0.001, "max": 0.5,
            "label": "Mức ý nghĩa (Alpha)"
        },
    },
}

def signals(df, params):
    n = params["length"]
    alpha = params["alpha"]
    
    # 1. Tính toán các thành phần của t-Bollinger Bands
    mid = df["close"].rolling(n).mean()
    s = df["close"].rolling(n).std(ddof=1)
    
    df_t = n - 1
    t_crit = t.ppf(1 - alpha / 2, df_t)
    
    upper = mid + t_crit * s
    lower = mid - t_crit * s
    
    # Dịch dải băng về trước 1 nến (shift) để tránh Look-ahead Bias 
    # (So sánh giá High/Low của nến hiện tại với dải băng của nến TRƯỚC ĐÓ)
    upper_prev = upper.shift(1)
    lower_prev = lower.shift(1)

    out = pd.Series(0, index=df.index, dtype="int8")
    
    # 2. Logic đảo chiều:
    # Mua (1) khi bóng nến dưới (low) đâm thủng hoặc chạm dải dưới
    out[df["low"] <= lower_prev] = 1
    
    # Bán (-1) khi bóng nến trên (high) đâm thủng hoặc chạm dải trên
    out[df["high"] >= upper_prev] = -1

    # 3. Loại bỏ tín hiệu trong khoảng thời gian khởi động (warm-up period)
    out.iloc[:n] = 0            
    return out