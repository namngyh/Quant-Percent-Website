import numpy as np
from scipy.stats import t

INDICATOR = {
    "name": "Student's t-Bollinger Bands",
    "type": "overlay",          # "overlay" đè lên nến | "panel" khung riêng
    "category": "custom",
    "description": "Dải Bollinger sử dụng phân phối t-Student để xử lý đuôi béo (Fat tails).",
    "params": {
        "length": {
            "type": "int", "default": 20, "min": 2, "max": 200,
            "label": "Cửa sổ (N)"
        },
        "alpha": {
            "type": "float", "default": 0.05, "min": 0.001, "max": 0.5,
            "label": "Mức ý nghĩa (Alpha)"
        },
        "show_mid": {
            "type": "bool", "default": True, 
            "label": "Vẽ đường SMA giữa"
        },
    },
    "outputs": [
        {"key": "upper", "label": "Dải trên",  "color": "#12805c"},
        {"key": "mid",   "label": "Đường giữa", "color": "#949ca6"},
        {"key": "lower", "label": "Dải dưới",  "color": "#c8372d"},
    ],
}

def calculate(df, params):
    n = params["length"]
    alpha = params["alpha"]
    
    # 1. Dải giữa (Middle Band) - SMA của giá đóng cửa
    mid = df["close"].rolling(n).mean()
    
    # 2. Độ lệch chuẩn mẫu (Sample Standard Deviation) 
    # ddof=1 kích hoạt hiệu chỉnh Bessel (chia cho n-1)
    s = df["close"].rolling(n).std(ddof=1)
    
    # 3. Tính giá trị tới hạn của phân phối t-Student
    # Số bậc tự do (Degrees of freedom)
    df_t = n - 1
    # Giá trị t tới hạn (two-tailed)
    t_crit = t.ppf(1 - alpha / 2, df_t)
    
    # 4. Tính dải trên và dải dưới
    upper = mid + t_crit * s
    lower = mid - t_crit * s
    
    # 5. Tùy chọn ẩn đường giữa
    if not params["show_mid"]:
        mid = mid * np.nan
        
    return {"upper": upper, "mid": mid, "lower": lower}