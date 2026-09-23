"""Chiến lược ML — hồi quy logistic dự đoán hướng nến kế tiếp.

Mô hình học từ vài đặc trưng đơn giản rồi vào lệnh khi xác suất lệch đủ xa khỏi
0.5. Đây là ví dụ về cách đưa học máy vào giao dịch mà **không tự lừa mình**.

Ba điều quyết định chiến lược này có trung thực hay không:

1. **Huấn luyện lại theo khối, chỉ dự đoán về phía trước.** Mô hình tại nến *i*
   chỉ học từ dữ liệu kết thúc TRƯỚC nến *i*. Nếu fit một lần trên toàn bộ dữ
   liệu rồi dự đoán ngược lại, backtest sẽ đẹp đến phi lý và hoàn toàn vô giá
   trị — đây là sai lầm phổ biến nhất khi ghép ML vào giao dịch.
2. **Đặc trưng chỉ nhìn về quá khứ.** Mọi biến đều tính từ dữ liệu tới lúc nến
   *i* đóng.
3. **Nhãn là nến i+1**, nên hàng cuối không có nhãn và bị loại khỏi tập học.

Ngưỡng vào lệnh mặc định là 0.55 — nghĩa là chỉ giao dịch khi mô hình thực sự
nghiêng về một phía. Để 0.50 thì nó sẽ vào lệnh liên tục và phí ăn hết.

Kỳ vọng thực tế: trên dữ liệu thị trường, độ chệch khỏi 0.5 rất nhỏ. Hãy chạy
walk-forward trước khi tin vào bất kỳ con số nào.
"""

import numpy as np
import pandas as pd

STRATEGY = {
    "name": "ML · Logistic",
    "side": "both",
    "description": "Hồi quy logistic dự đoán hướng nến kế tiếp, học lại định kỳ.",
    "params": {
        "lookback": {"type": "int", "default": 5, "min": 1, "max": 20,
                     "label": "Số lợi suất trễ"},
        "train_bars": {"type": "int", "default": 750, "min": 200, "max": 3000,
                       "label": "Số nến huấn luyện"},
        "refit_every": {"type": "int", "default": 250, "min": 50, "max": 1000,
                        "label": "Học lại mỗi N nến"},
        "threshold": {"type": "float", "default": 0.55, "min": 0.50, "max": 0.70,
                      "step": 0.01, "label": "Ngưỡng vào lệnh"},
    },
}


def _features(df, lookback):
    close = df["close"]
    returns = close.pct_change()

    data = {f"ret_{k}": returns.shift(k - 1) for k in range(1, lookback + 1)}
    data["vol"] = returns.rolling(20).std()
    span = (df["high"] - df["low"]).replace(0, np.nan)
    data["pos"] = (close - df["low"]) / span
    data["dist_ma"] = close / close.rolling(50).mean() - 1.0
    return pd.DataFrame(data, index=df.index)


def signals(df, params):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    lookback = params["lookback"]
    train_bars = params["train_bars"]
    refit_every = params["refit_every"]
    threshold = params["threshold"]

    features = _features(df, lookback)
    target = (df["close"].shift(-1) > df["close"]).astype("float64")
    target.iloc[-1] = np.nan            # nến cuối chưa có nến sau để làm nhãn

    out = pd.Series(0, index=df.index, dtype="int8")
    n = len(df)
    start = train_bars + lookback + 50
    if n <= start + 1:
        return out                       # chưa đủ dữ liệu: đứng ngoài

    model = LogisticRegression(max_iter=400)
    scaler = StandardScaler()

    for block in range(start, n, refit_every):
        train = slice(max(0, block - train_bars), block - 1)
        X, y = features.iloc[train], target.iloc[train]
        ok = X.notna().all(axis=1) & y.notna()
        if ok.sum() < 100 or y[ok].nunique() < 2:
            continue

        try:
            model.fit(scaler.fit_transform(X[ok].to_numpy()), y[ok].to_numpy())
        except Exception:
            continue

        end = min(block + refit_every, n)
        X_pred = features.iloc[block:end]
        valid = X_pred.notna().all(axis=1)
        if not valid.any():
            continue

        prob = model.predict_proba(scaler.transform(X_pred[valid].to_numpy()))[:, 1]
        decided = pd.Series(0, index=X_pred[valid].index, dtype="int8")
        decided[prob > threshold] = 1
        decided[prob < 1.0 - threshold] = -1
        out.loc[decided.index] = decided

    return out
