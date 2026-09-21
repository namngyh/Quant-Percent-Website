"""Ví dụ chỉ báo OVERLAY tự viết — EMA Ribbon.

Vẽ 3 đường EMA đè lên nến. Copy file này, đổi tên và sửa logic là bạn có
chỉ báo riêng; nó tự xuất hiện trong danh sách khi bạn tải lại trang.

Contract:
  INDICATOR : dict mô tả tên, loại, tham số, các đường vẽ
  calculate : hàm nhận (df, params), trả về dict {output_key: Series}
"""

INDICATOR = {
    "name": "EMA Ribbon",
    "type": "overlay",                      # "overlay" = đè lên nến
    "category": "custom",
    "description": "Ba đường EMA nhanh/vừa/chậm, dải mở rộng khi xu hướng mạnh.",
    "params": {
        "fast":   {"type": "int", "default": 8,  "min": 2, "max": 100, "label": "EMA nhanh"},
        "medium": {"type": "int", "default": 21, "min": 2, "max": 200, "label": "EMA vừa"},
        "slow":   {"type": "int", "default": 55, "min": 2, "max": 400, "label": "EMA chậm"},
    },
    "outputs": [
        {"key": "fast",   "label": "EMA nhanh", "color": "#26a69a"},
        {"key": "medium", "label": "EMA vừa",   "color": "#ffd600"},
        {"key": "slow",   "label": "EMA chậm",  "color": "#ef5350"},
    ],
}


def calculate(df, params):
    close = df["close"]
    return {
        "fast":   close.ewm(span=params["fast"],   adjust=False).mean(),
        "medium": close.ewm(span=params["medium"], adjust=False).mean(),
        "slow":   close.ewm(span=params["slow"],   adjust=False).mean(),
    }
