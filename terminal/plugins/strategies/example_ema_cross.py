"""Ví dụ chiến lược — EMA Crossover (thuận xu hướng).

EMA nhanh cắt lên EMA chậm → LONG. Cắt xuống → SHORT.

Copy file này, đổi tên và sửa logic là bạn có chiến lược riêng; nó tự xuất
hiện trong danh sách khi bạn tải lại trang.

Contract:
  STRATEGY : dict mô tả tên, chiều lệnh, tham số
  signals  : hàm nhận (df, params), trả về Series 1 / -1 / 0
             (1 = long, -1 = short, 0 = đứng ngoài)

QUAN TRỌNG: giá trị tại nến i chỉ được dùng thông tin tới lúc nến i ĐÓNG.
Engine sẽ khớp lệnh ở giá mở nến i+1, nên bạn không thể vô tình giao dịch
bằng thông tin chưa xảy ra.
"""

import pandas as pd

STRATEGY = {
    "name": "EMA Crossover",
    "side": "both",                         # "long" | "short" | "both"
    "description": "EMA nhanh cắt EMA chậm; thuận xu hướng, luôn có vị thế.",
    "params": {
        "fast": {"type": "int", "default": 20, "min": 2, "max": 200, "label": "EMA nhanh"},
        "slow": {"type": "int", "default": 50, "min": 3, "max": 400, "label": "EMA chậm"},
    },
}


def signals(df, params):
    fast = df["close"].ewm(span=params["fast"], adjust=False).mean()
    slow = df["close"].ewm(span=params["slow"], adjust=False).mean()

    out = pd.Series(0, index=df.index, dtype="int8")
    out[fast > slow] = 1
    out[fast < slow] = -1

    # Cửa sổ khởi động: trước khi EMA chậm đủ dữ liệu thì đứng ngoài.
    out.iloc[: params["slow"]] = 0
    return out
