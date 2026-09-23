"""Xác suất nến kế tiếp tăng — hồi quy logistic.

Mô hình học từ vài đặc trưng đơn giản (lợi suất các phiên gần nhất, RSI, biến
động) để ước lượng xác suất nến TIẾP THEO đóng cao hơn nến này.

Điểm quan trọng nhất — tính nhân quả:

* Đặc trưng tại nến *i* chỉ dùng dữ liệu tới lúc nến *i* đóng.
* Nhãn là hướng của nến *i+1*, nên hàng cuối cùng không có nhãn và bị loại.
* Mô hình được **huấn luyện lại định kỳ** và chỉ dự đoán cho các nến SAU đoạn
  dữ liệu đã học. Nếu fit một lần trên toàn bộ rồi dự đoán ngược lại, chỉ báo
  sẽ trông chính xác một cách phi lý — đó là nhìn trộm tương lai.

Giá trị 0.5 nghĩa là mô hình không biết. Chệch khỏi 0.5 mới có thông tin, và
với dữ liệu thị trường thì độ chệch thường rất nhỏ — đó là điều bình thường,
không phải lỗi.
"""

import numpy as np
import pandas as pd

INDICATOR = {
    "name": "ML · Xác suất tăng",
    "type": "panel",
    "category": "machine learning",
    "description": "Hồi quy logistic ước lượng P(nến kế tiếp tăng).",
    "params": {
        "lookback": {"type": "int", "default": 5, "min": 1, "max": 30,
                     "label": "Số lợi suất trễ"},
        "train_bars": {"type": "int", "default": 500, "min": 100, "max": 3000,
                       "label": "Số nến huấn luyện"},
        "refit_every": {"type": "int", "default": 100, "min": 20, "max": 1000,
                        "label": "Học lại mỗi N nến"},
    },
    "outputs": [
        {"key": "prob", "label": "P(tăng)", "color": "#7c3aed"},
        {"key": "neutral", "label": "0.5", "color": "#c3c9d1"},
    ],
}


def _features(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    close = df["close"]
    returns = close.pct_change()

    data = {f"ret_{k}": returns.shift(k - 1) for k in range(1, lookback + 1)}

    # Biến động và vị trí trong biên độ ngày — đều chỉ nhìn về quá khứ.
    data["vol"] = returns.rolling(20).std()
    span = (df["high"] - df["low"]).replace(0, np.nan)
    data["pos_in_range"] = (close - df["low"]) / span
    data["dist_ma"] = close / close.rolling(50).mean() - 1.0

    return pd.DataFrame(data, index=df.index)


def calculate(df, params):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    lookback = params["lookback"]
    train_bars = params["train_bars"]
    refit_every = params["refit_every"]

    features = _features(df, lookback)
    # Nhãn: nến kế tiếp có đóng cao hơn không. shift(-1) nên hàng cuối là NaN.
    target = (df["close"].shift(-1) > df["close"]).astype("float64")
    target.iloc[-1] = np.nan

    prob = pd.Series(np.nan, index=df.index, dtype="float64")
    n = len(df)

    start = train_bars + lookback + 50          # đủ cho mọi cửa sổ trượt
    if n <= start + 1:
        # Không đủ dữ liệu để vừa học vừa dự đoán; trả về rỗng còn hơn trả về
        # một con số bịa.
        return {"prob": prob, "neutral": pd.Series(0.5, index=df.index)}

    model = LogisticRegression(max_iter=400, C=1.0)
    scaler = StandardScaler()
    fitted = False

    for block_start in range(start, n, refit_every):
        # Chỉ học trên dữ liệu KẾT THÚC TRƯỚC block hiện tại.
        train_slice = slice(max(0, block_start - train_bars), block_start - 1)
        X_train = features.iloc[train_slice]
        y_train = target.iloc[train_slice]

        usable = X_train.notna().all(axis=1) & y_train.notna()
        if usable.sum() < 60 or y_train[usable].nunique() < 2:
            continue

        try:
            X_scaled = scaler.fit_transform(X_train[usable].to_numpy())
            model.fit(X_scaled, y_train[usable].to_numpy())
            fitted = True
        except Exception:
            continue

        if not fitted:
            continue

        block_end = min(block_start + refit_every, n)
        X_pred = features.iloc[block_start:block_end]
        valid = X_pred.notna().all(axis=1)
        if not valid.any():
            continue

        scaled = scaler.transform(X_pred[valid].to_numpy())
        prob.iloc[block_start:block_end] = pd.Series(
            model.predict_proba(scaled)[:, 1], index=X_pred[valid].index
        ).reindex(X_pred.index)

    return {"prob": prob, "neutral": pd.Series(0.5, index=df.index)}
