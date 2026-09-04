"""Ví dụ chỉ báo PANEL tự viết — Z-Score của giá đóng cửa.

Đo giá hiện tại lệch bao nhiêu độ lệch chuẩn so với trung bình trượt.
Vì thang giá trị (khoảng -3..+3) khác hẳn thang giá BTC, chỉ báo này phải
nằm ở panel riêng bên dưới: "type": "panel".
"""

INDICATOR = {
    "name": "Z-Score",
    "type": "panel",
    "category": "custom",
    "description": "Độ lệch chuẩn hóa của giá so với trung bình trượt.",
    "params": {
        "length": {"type": "int",  "default": 100, "min": 5, "max": 500, "label": "Chu kỳ"},
        "bands":  {"type": "bool", "default": True, "label": "Vẽ ngưỡng ±2σ"},
    },
    "outputs": [
        {"key": "zscore", "label": "Z-Score", "color": "#aa00ff"},
        {"key": "upper",  "label": "+2σ",     "color": "#3d444d"},
        {"key": "lower",  "label": "-2σ",     "color": "#3d444d"},
    ],
}


def calculate(df, params):
    close = df["close"]
    length = params["length"]

    mean = close.rolling(length).mean()
    std = close.rolling(length).std()

    # std can be 0 on a perfectly flat stretch; dividing would give inf, which
    # the chart would draw as a spike. Leave those points empty instead.
    zscore = (close - mean) / std.replace(0, float("nan"))

    if params["bands"]:
        upper = zscore * 0 + 2
        lower = zscore * 0 - 2
    else:
        upper = zscore * float("nan")
        lower = zscore * float("nan")

    return {"zscore": zscore, "upper": upper, "lower": lower}
