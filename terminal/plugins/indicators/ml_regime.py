"""Phân trạng thái thị trường bằng K-means.

Gom các nến thành vài trạng thái dựa trên xu hướng và biến động, rồi đánh số
lại theo mức biến động để nhãn giữ nguyên ý nghĩa giữa các lần chạy: 0 là yên
ắng nhất, số càng cao càng động.

K-means không dùng nhãn tương lai nên không có rủi ro nhìn trộm như mô hình dự
báo. Nhưng nó vẫn học trên toàn bộ đoạn dữ liệu đang xem, nên hãy đọc nó như
một cách *mô tả* giai đoạn đã qua, đừng dùng làm tín hiệu giao dịch trực tiếp.
"""

import numpy as np
import pandas as pd

INDICATOR = {
    "name": "ML · Trạng thái thị trường",
    "type": "panel",
    "category": "machine learning",
    "description": "K-means gom nến theo xu hướng và biến động; 0 = yên nhất.",
    "params": {
        "clusters": {"type": "int", "default": 3, "min": 2, "max": 6,
                     "label": "Số trạng thái"},
        "window": {"type": "int", "default": 20, "min": 5, "max": 200,
                   "label": "Cửa sổ đặc trưng"},
    },
    "outputs": [
        {"key": "regime", "label": "Trạng thái", "color": "#0e7490"},
    ],
}


def calculate(df, params):
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    window = params["window"]
    k = params["clusters"]

    close = df["close"]
    returns = close.pct_change()

    features = pd.DataFrame(
        {
            "trend": close.pct_change(window),
            "vol": returns.rolling(window).std(),
            "range": ((df["high"] - df["low"]) / close.replace(0, np.nan))
            .rolling(window).mean(),
        },
        index=df.index,
    )

    regime = pd.Series(np.nan, index=df.index, dtype="float64")
    usable = features.notna().all(axis=1)
    if usable.sum() < k * 20:
        return {"regime": regime}

    scaled = StandardScaler().fit_transform(features[usable].to_numpy())
    labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(scaled)

    # K-means numbers its clusters arbitrarily, so a rerun could swap them.
    # Ordering by mean volatility makes the label mean the same thing twice.
    frame = pd.DataFrame({"label": labels, "vol": features[usable]["vol"].to_numpy()})
    order = frame.groupby("label")["vol"].mean().sort_values().index
    remap = {old: new for new, old in enumerate(order)}

    regime[usable] = [remap[v] for v in labels]
    return {"regime": regime}
