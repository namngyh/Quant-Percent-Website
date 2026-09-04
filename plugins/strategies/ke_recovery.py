"""KE Recovery — port từ file AmiBroker `KE_RECOVERY.afl`.

Ý tưởng gốc: dựng một dao động "KF" bằng cách hồi quy tuyến tính RSI và
Stochastic %K, cộng có trọng số, rồi so với đường trung bình WMA của chính nó.
Giao cắt sinh tín hiệu; một bộ lọc EMA dài quyết định chỉ đánh thuận chiều xu
hướng.

    LRSI = LinearReg(RSI(periods), regperiods)
    LSTO = LinearReg(StochK(periods, Ksmooth), regperiods)
    f0   = n1 * LRSI + LSTO
    s0   = WMA(f0, maperiods)

    Buy0   = Cross(f0, s0)        Short0 = Cross(s0, f0)
    Buy    = Flip(Buy0, Short0)   AND C > EMA(C, Length) dịch 1 nến
    Short  = Flip(Short0, Buy0)   AND C < EMA(C, Length) dịch 1 nến

Ba điểm khác biệt so với bản AFL, cần biết khi so sánh kết quả:

1. AmiBroker khớp ở `Close` của chính nến sinh tín hiệu (`BuyPrice = Close`).
   Engine ở đây khớp ở giá **mở nến kế tiếp**. Bản AFL vì thế lạc quan hơn —
   nó giả định bạn khớp được đúng giá đóng cửa mà bạn chỉ biết khi nến đã đóng.
2. Bản AFL không tính phí và trượt giá; ở đây có, chỉnh trong ô "Chi phí & vốn".
3. `SetPositionSize(1, spsShares)` là 1 hợp đồng cố định. Ở đây khối lượng theo
   % vốn, nên đường equity có dạng lãi kép thay vì tuyến tính.

Mặc định tham số giữ nguyên giá trị trong file AFL (296, 27, 20, 64, 6.6, 29).
"""

import numpy as np
import pandas as pd

STRATEGY = {
    "name": "KE Recovery (từ AFL)",
    "side": "both",
    "description": "KF = LinearReg(RSI) * n + LinearReg(StochK), lọc theo EMA dài.",
    "params": {
        # Dải min/max lấy đúng theo các lệnh Optimize() trong file AFL.
        "length":     {"type": "int",   "default": 296, "min": 100, "max": 300, "label": "EMA Len"},
        "periods":    {"type": "int",   "default": 27,  "min": 10,  "max": 100, "label": "Period"},
        "ksmooth":    {"type": "int",   "default": 20,  "min": 6,   "max": 100, "label": "X (Stoch smooth)"},
        "regperiods": {"type": "int",   "default": 64,  "min": 6,   "max": 100, "label": "Y (LinReg)"},
        "n1":         {"type": "float", "default": 6.6, "min": 1.5, "max": 10.0, "step": 0.1, "label": "N (trọng số RSI)"},
        "maperiods":  {"type": "int",   "default": 29,  "min": 6,   "max": 100, "label": "S (WMA)"},
    },
}


# --------------------------------------------------------------------------
# Các hàm AmiBroker dựng lại bằng pandas
# --------------------------------------------------------------------------

def rsi(close: pd.Series, length: int) -> pd.Series:
    """RSI theo Wilder — giống hàm RSI() của AmiBroker."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1.0 / length, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1.0 / length, adjust=False).mean()
    # Chuỗi không có nến giảm nào làm loss = 0; để trống thay vì chia cho 0.
    rs = gain / loss.replace(0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


def stoch_k(df: pd.DataFrame, periods: int, ksmooth: int) -> pd.Series:
    """StochK(periods, ksmooth) — %K thô rồi làm mượt bằng SMA."""
    low = df["low"].rolling(periods).min()
    high = df["high"].rolling(periods).max()
    span = (high - low).replace(0, np.nan)   # nến đi ngang tuyệt đối
    raw = 100.0 * (df["close"] - low) / span
    return raw.rolling(ksmooth).mean()


def linear_reg(series: pd.Series, length: int) -> pd.Series:
    """Giá trị cuối của đường hồi quy tuyến tính trên `length` nến.

    Tương đương LinearReg() của AmiBroker. Dùng công thức đóng cho hệ số góc và
    tung độ gốc, tính vector hoá — vòng lặp Python trên hàng trăm nghìn nến sẽ
    làm phần tối ưu tham số chậm không chấp nhận được.
    """
    n = length
    x_sum = n * (n - 1) / 2.0
    xx_sum = (n - 1) * n * (2 * n - 1) / 6.0
    denom = n * xx_sum - x_sum**2

    y_sum = series.rolling(n).sum()
    # sum(x*y) với x = 0..n-1 tính bằng tích chập với trọng số tăng dần.
    weights = np.arange(n, dtype="float64")
    xy_sum = series.rolling(n).apply(lambda w: float(np.dot(w, weights)), raw=True)

    slope = (n * xy_sum - x_sum * y_sum) / denom
    intercept = (y_sum - slope * x_sum) / n
    return intercept + slope * (n - 1)   # giá trị tại nến cuối cùng


def wma(series: pd.Series, length: int) -> pd.Series:
    """Trung bình có trọng số tuyến tính — WMA() của AmiBroker."""
    weights = np.arange(1, length + 1, dtype="float64")
    return series.rolling(length).apply(
        lambda w: float(np.dot(w, weights) / weights.sum()), raw=True
    )


def cross(a: pd.Series, b: pd.Series) -> pd.Series:
    """Cross(a, b) — a cắt LÊN trên b tại nến này."""
    return (a > b) & (a.shift(1) <= b.shift(1))


def flip(on: pd.Series, off: pd.Series) -> pd.Series:
    """Flip(on, off) — bật tại `on`, giữ nguyên tới khi `off`.

    `on` được ưu tiên khi cả hai cùng bật, giống AmiBroker.
    """
    state = np.zeros(len(on), dtype=bool)
    current = False
    on_values = on.to_numpy()
    off_values = off.to_numpy()

    for i in range(len(state)):
        if on_values[i]:
            current = True
        elif off_values[i]:
            current = False
        state[i] = current

    return pd.Series(state, index=on.index)


# --------------------------------------------------------------------------

def signals(df, params):
    close = df["close"]

    # --- Dao động KF ---
    lrsi = linear_reg(rsi(close, params["periods"]), params["regperiods"])
    lsto = linear_reg(stoch_k(df, params["periods"], params["ksmooth"]), params["regperiods"])

    f0 = params["n1"] * lrsi + lsto
    s0 = wma(f0, params["maperiods"])

    buy0 = cross(f0, s0)
    short0 = cross(s0, f0)

    open_buy = flip(buy0, short0)
    open_short = flip(short0, buy0)

    # Ref(EMA(C, Length), -1): EMA của nến TRƯỚC, nên bộ lọc không dùng
    # thông tin của chính nến đang xét.
    ema_filter = close.ewm(span=params["length"], adjust=False).mean().shift(1)

    enter_long = open_buy & (close > ema_filter)
    enter_short = open_short & (close < ema_filter)

    # AmiBroker: Sell = Short0, Cover = Buy0 — vị thế đóng khi KF cắt ngược,
    # kể cả khi bộ lọc EMA chưa cho vào lệnh mới.
    exit_long = short0
    exit_short = buy0

    # Máy trạng thái tái hiện Buy/Sell/Short/Cover sau ExRem của AmiBroker.
    position = np.zeros(len(df), dtype="int8")
    current = 0
    el = enter_long.to_numpy()
    es = enter_short.to_numpy()
    xl = exit_long.to_numpy()
    xs = exit_short.to_numpy()

    for i in range(len(position)):
        if current == 1 and xl[i]:
            current = 0
        elif current == -1 and xs[i]:
            current = 0

        if current == 0:
            if el[i]:
                current = 1
            elif es[i]:
                current = -1

        position[i] = current

    # Cửa sổ khởi động: trước khi EMA dài nhất có đủ dữ liệu thì đứng ngoài.
    warmup = max(params["length"], params["regperiods"] + params["periods"] + params["maperiods"])
    position[:warmup] = 0

    return pd.Series(position, index=df.index)
