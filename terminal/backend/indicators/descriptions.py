"""Giải thích chỉ báo bằng tiếng Việt.

Docstring của pandas-ta viết bằng tiếng Anh và phần lớn chỉ nêu công thức, nên
người dùng nhìn vào một cái tên như `cksp` hay `qqe` vẫn không biết nó đo gì.
Bảng dưới đây mô tả các chỉ báo hay dùng theo hướng *dùng để làm gì*, và những
cái không có trong bảng thì rơi về docstring gốc: vẫn hơn là không có gì.

Mỗi mục gồm:
    what  : nó đo cái gì, một câu
    how   : đọc nó thế nào
    watch : điều dễ hiểu sai hoặc cần cẩn thận (có thể bỏ trống)
"""

from __future__ import annotations

DESCRIPTIONS: dict[str, dict[str, str]] = {
    # ---------- Trung bình trượt & kênh giá ----------
    "sma": {
        "what": "Trung bình cộng giá đóng cửa của N nến gần nhất.",
        "how": "Giá trên đường là xu hướng tăng, dưới là giảm. Đường càng dài càng chậm.",
        "watch": "Luôn trễ so với giá: đó là bản chất, không phải lỗi.",
    },
    "ema": {
        "what": "Trung bình trượt có trọng số giảm dần, nến gần đây quan trọng hơn.",
        "how": "Phản ứng nhanh hơn SMA cùng chu kỳ, nên bám giá sát hơn.",
        "watch": "Nhanh hơn cũng nghĩa là nhiễu hơn trong thị trường đi ngang.",
    },
    "wma": {
        "what": "Trung bình có trọng số tuyến tính theo thứ tự thời gian.",
        "how": "Nằm giữa SMA và EMA về độ nhạy.",
    },
    "vwap": {
        "what": "Giá trung bình có trọng số khối lượng, tính lại theo phiên.",
        "how": "Giá trên VWAP thường được coi là bên mua đang kiểm soát phiên.",
        "watch": "Chỉ có nghĩa với dữ liệu trong ngày; trên khung ngày nó vô nghĩa.",
    },
    "bbands": {
        "what": "Bollinger Bands: đường giữa là SMA, hai dải cách nó N độ lệch chuẩn.",
        "how": "Dải bóp hẹp = biến động thấp, thường trước một cú bung. Giá chạm dải trên/dưới không phải tín hiệu mua bán, chỉ là 'đang xa trung bình'.",
        "watch": "Hai đường BBB (độ rộng dải) và BBP (vị trí trong dải) khác thang giá nên nền tảng tự tách xuống khung riêng.",
    },
    "kc": {
        "what": "Keltner Channel: kênh quanh EMA, độ rộng theo ATR thay vì độ lệch chuẩn.",
        "how": "Mượt hơn Bollinger vì ATR ít giật hơn độ lệch chuẩn.",
    },
    "donchian": {
        "what": "Kênh nối đỉnh cao nhất và đáy thấp nhất trong N nến.",
        "how": "Nền tảng của các hệ thống phá vỡ kênh (breakout) kiểu Turtle.",
    },
    "supertrend": {
        "what": "Đường bám xu hướng, lật phía trên/dưới giá dựa trên ATR.",
        "how": "Đường dưới giá = xu hướng tăng, trên giá = giảm.",
        "watch": "Trả về hai đường long/short **luân phiên**: mỗi lúc chỉ một đường có giá trị, đó là thiết kế chứ không phải thiếu dữ liệu.",
    },
    "psar": {
        "what": "Parabolic SAR: các chấm dừng lỗ trượt dần theo xu hướng.",
        "how": "Chấm nhảy sang phía kia của giá là tín hiệu đảo chiều.",
        "watch": "Rất nhiễu khi thị trường đi ngang.",
    },
    "ichimoku": {
        "what": "Hệ thống Nhật gồm nhiều đường: Tenkan, Kijun, hai đường Senkou tạo 'mây', và Chikou.",
        "how": "Giá trên mây là tăng, dưới mây là giảm, trong mây là chưa rõ.",
        "watch": "Chikou (ICS) **định nghĩa là dịch lùi 26 nến**, nên không bao giờ chạm nến mới nhất. Đây không phải lỗi.",
    },

    # ---------- Dao động ----------
    "rsi": {
        "what": "Đo sức mạnh tương đối giữa các phiên tăng và giảm, thang 0–100.",
        "how": "Trên 70 thường gọi là quá mua, dưới 30 là quá bán.",
        "watch": "Trong xu hướng mạnh, RSI có thể ở trên 70 hàng tuần. 'Quá mua' không có nghĩa là sắp giảm.",
    },
    "macd": {
        "what": "Hiệu của hai EMA nhanh/chậm, kèm đường tín hiệu và histogram.",
        "how": "MACD cắt lên đường tín hiệu là động lượng tăng; histogram là khoảng cách giữa hai đường.",
    },
    "stoch": {
        "what": "Vị trí giá đóng cửa trong biên độ cao–thấp của N nến, thang 0–100.",
        "how": "%K nhanh, %D là bản làm mượt của %K.",
    },
    "adx": {
        "what": "Đo **độ mạnh** của xu hướng, không đo chiều.",
        "how": "Trên 25 thường coi là có xu hướng rõ; dưới 20 là đi ngang.",
        "watch": "ADX cao không nói lên tăng hay giảm: phải nhìn thêm DMP/DMN.",
    },
    "cci": {
        "what": "Độ lệch của giá so với trung bình, chuẩn hoá theo độ lệch trung bình.",
        "how": "Ngoài khoảng ±100 được coi là lệch mạnh.",
    },
    "willr": {
        "what": "Williams %R: giống Stochastic nhưng thang từ -100 đến 0.",
        "how": "Trên -20 là quá mua, dưới -80 là quá bán.",
    },
    "mfi": {
        "what": "Như RSI nhưng có tính khối lượng.",
        "how": "Phân kỳ giữa MFI và giá đôi khi báo trước đảo chiều.",
    },
    "roc": {
        "what": "Tốc độ thay đổi giá theo phần trăm sau N nến.",
        "how": "Dương là đang tăng nhanh hơn N nến trước.",
    },

    # ---------- Biến động ----------
    "atr": {
        "what": "Biên độ dao động trung bình thật của N nến, tính theo đơn vị giá.",
        "how": "Dùng để đặt dừng lỗ theo biến động thay vì theo % cố định.",
        "watch": "Là số tuyệt đối nên không so được giữa các mã có mức giá khác nhau: dùng NATR nếu cần so sánh.",
    },
    "natr": {
        "what": "ATR chuẩn hoá theo phần trăm giá.",
        "how": "So sánh được giữa các mã và các thời kỳ khác nhau.",
    },
    "true_range": {
        "what": "Biên độ thật của một nến, có tính khoảng nhảy so với nến trước.",
        "how": "Thành phần cơ sở của ATR.",
    },

    # ---------- Khối lượng ----------
    "obv": {
        "what": "Cộng dồn khối lượng theo chiều nến, tăng thì cộng, giảm thì trừ.",
        "how": "OBV tăng trong khi giá đi ngang có thể là tích luỹ.",
    },
    "ad": {
        "what": "Đường tích luỹ/phân phối, có tính vị trí đóng cửa trong biên độ.",
        "how": "Phân kỳ với giá là điểm đáng chú ý.",
    },
    "cmf": {
        "what": "Chaikin Money Flow: dòng tiền vào ra trong N nến.",
        "how": "Dương là dòng tiền vào, âm là ra.",
    },

    # ---------- Thống kê ----------
    "stdev": {
        "what": "Độ lệch chuẩn của giá trong N nến: thước đo biến động thô.",
        "how": "Là thành phần tạo nên dải Bollinger.",
    },
    "zscore": {
        "what": "Giá lệch bao nhiêu độ lệch chuẩn so với trung bình trượt.",
        "how": "Vượt ±2 là hiếm nếu phân phối chuẩn, nhưng giá tài chính đuôi dày hơn chuẩn nhiều.",
    },
    "linreg": {
        "what": "Giá trị cuối của đường hồi quy tuyến tính trên N nến.",
        "how": "Là một dạng trung bình trượt mượt, ít trễ hơn SMA.",
    },
    "dpo": {
        "what": "Detrended Price Oscillator: bỏ xu hướng để lộ chu kỳ.",
        "watch": "Là chỉ báo **căn giữa**, dịch lại nửa chu kỳ, nên thiếu vài nến cuối theo đúng định nghĩa.",
    },
    "hwc": {
        "what": "Kênh Holt-Winters: làm mượt ba tầng (mức, xu hướng, gia tốc).",
        "watch": "Ba tham số na/nb/nc là **hệ số làm mượt, phải nhỏ hơn 1**. Đặt lớn hơn sẽ khiến mô hình phân kỳ.",
    },
}

# Diễn giải cho các chỉ báo do người dùng tự viết được lấy từ docstring của file.
FALLBACK = {
    "what": "",
    "how": "",
    "watch": "",
}


def describe(indicator_id: str, docstring: str = "") -> dict:
    """Trả về phần giải thích cho một chỉ báo."""
    entry = DESCRIPTIONS.get(indicator_id)
    if entry:
        return {"source": "curated", **{**FALLBACK, **entry}}

    # Không có bản tiếng Việt: đưa docstring gốc, gọn lại cho vừa hộp thoại.
    text = " ".join((docstring or "").split())
    return {
        "source": "docstring" if text else "none",
        "what": text[:600],
        "how": "",
        "watch": "",
    }
