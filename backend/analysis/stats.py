"""Kiểm định thống kê trên chuỗi giá và trên kết quả chiến lược.

Mục đích chung của mọi thứ trong file này: phân biệt **cấu trúc thật** với
**ngẫu nhiên trông giống cấu trúc**. Một chuỗi giá ngẫu nhiên vẫn tạo ra xu
hướng, mẫu hình và những chiến lược trông có lãi — nên trước khi tin vào một
kết quả, cần biết dữ liệu có gì để khai thác hay không.

Bốn nhóm:

* **Phân phối** — lợi suất tài chính đuôi dày hơn phân phối chuẩn rất nhiều,
  nên mọi công thức giả định chuẩn (kể cả Sharpe) đều đánh giá thấp rủi ro
  đuôi. Jarque–Bera cho biết mức lệch, VaR/CVaR đo đuôi trực tiếp.
* **Quá trình ngẫu nhiên** — ADF hỏi chuỗi có dừng không, Ljung–Box hỏi có tự
  tương quan không, Hurst và tỷ số phương sai hỏi nó là bước ngẫu nhiên, xu
  hướng hay hồi quy trung bình. Nếu tất cả đều nói "bước ngẫu nhiên" thì không
  chỉ báo nào tìm được gì.
* **Suy diễn** — kiểm định t một phía trên lợi suất từng lệnh: lợi thế quan sát
  được có khác 0 một cách có ý nghĩa không, hay chỉ là may.
* **Bayes** — hậu nghiệm Beta–Nhị thức trên tỷ lệ thắng. Trả lời đúng câu hỏi
  người giao dịch thực sự muốn hỏi: *"với 12 thắng trên 20 lệnh, tỷ lệ thắng
  thật của tôi nằm trong khoảng nào?"* — và với 20 lệnh thì khoảng đó rộng đến
  mức gần như vô dụng, điều mà một con số 60% đơn lẻ che mất.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy import stats as sps

log = logging.getLogger(__name__)

MIN_SAMPLES = 60


def _finite(values: np.ndarray) -> np.ndarray:
    return values[np.isfinite(values)]


# --------------------------------------------------------------- phân phối

def distribution(returns: np.ndarray) -> dict:
    """Hình dạng phân phối lợi suất, và độ lệch khỏi chuẩn."""
    r = _finite(returns)
    if r.size < MIN_SAMPLES:
        return {"error": f"Cần ít nhất {MIN_SAMPLES} quan sát, hiện có {r.size}."}

    jb_stat, jb_p = sps.jarque_bera(r)
    var95, var99 = np.percentile(r, [5, 1])
    tail95 = r[r <= var95]
    tail99 = r[r <= var99]

    return {
        "n": int(r.size),
        "mean_pct": float(r.mean() * 100),
        "std_pct": float(r.std(ddof=1) * 100),
        "skew": float(sps.skew(r)),
        "kurtosis_excess": float(sps.kurtosis(r)),   # 0 = chuẩn
        "jarque_bera_stat": float(jb_stat),
        "jarque_bera_p": float(jb_p),
        # p < 0.05: bác bỏ giả thuyết phân phối chuẩn.
        "is_normal": bool(jb_p > 0.05),
        "var_95_pct": float(var95 * 100),
        "var_99_pct": float(var99 * 100),
        "cvar_95_pct": float(tail95.mean() * 100) if tail95.size else float(var95 * 100),
        "cvar_99_pct": float(tail99.mean() * 100) if tail99.size else float(var99 * 100),
        "worst_pct": float(r.min() * 100),
        "best_pct": float(r.max() * 100),
    }


# ------------------------------------------------------- quá trình ngẫu nhiên

def hurst_exponent(series: np.ndarray, max_lag: int = 60) -> float:
    """Ước lượng Hurst bằng độ lệch chuẩn của hiệu theo độ trễ.

    0.5 = bước ngẫu nhiên; > 0.5 = có quán tính (xu hướng); < 0.5 = hồi quy
    trung bình. Ước lượng này nhạy với độ dài chuỗi, nên đọc như một dấu hiệu
    chứ đừng đọc như một hằng số.
    """
    s = _finite(series)
    if s.size < max_lag * 4:
        max_lag = max(10, s.size // 4)
    if s.size < 40:
        return float("nan")

    lags = range(2, max_lag)
    tau = []
    for lag in lags:
        diff = s[lag:] - s[:-lag]
        tau.append(np.sqrt(np.std(diff)) if diff.size else np.nan)

    tau = np.array(tau, dtype="float64")
    ok = np.isfinite(tau) & (tau > 0)
    if ok.sum() < 5:
        return float("nan")

    slope = np.polyfit(np.log(np.array(list(lags))[ok]), np.log(tau[ok]), 1)[0]
    return float(slope * 2.0)


def variance_ratio(returns: np.ndarray, period: int = 5) -> dict:
    """Kiểm định tỷ số phương sai Lo–MacKinlay.

    Với bước ngẫu nhiên, phương sai của tổng q lợi suất bằng q lần phương sai
    một bước, nên tỷ số bằng 1. Lệch đáng kể khỏi 1 là bằng chứng chống lại
    bước ngẫu nhiên.
    """
    r = _finite(returns)
    n = r.size
    if n < period * 20:
        return {"error": "Không đủ dữ liệu cho kiểm định này."}

    mu = r.mean()
    var1 = np.sum((r - mu) ** 2) / (n - 1)

    rolled = np.convolve(r, np.ones(period), mode="valid")
    var_q = np.sum((rolled - period * mu) ** 2) / (
        (n - period + 1) * period * (1 - period / n)
    )
    if var1 <= 0:
        return {"error": "Phương sai bằng 0."}

    vr = var_q / var1
    # Sai số chuẩn theo giả định phương sai thay đổi (heteroskedastic).
    phi = 2.0 * (2.0 * period - 1.0) * (period - 1.0) / (3.0 * period * n)
    z = (vr - 1.0) / np.sqrt(phi) if phi > 0 else 0.0

    return {
        "period": period,
        "variance_ratio": float(vr),
        "z_score": float(z),
        "p_value": float(2 * (1 - sps.norm.cdf(abs(z)))),
        "random_walk": bool(abs(z) < 1.96),
    }


def stochastic(prices: np.ndarray, returns: np.ndarray) -> dict:
    """Chuỗi này là bước ngẫu nhiên, xu hướng, hay hồi quy trung bình?"""
    from statsmodels.stats.diagnostic import acorr_ljungbox
    from statsmodels.tsa.stattools import adfuller

    r = _finite(returns)
    p = _finite(prices)
    if r.size < MIN_SAMPLES:
        return {"error": f"Cần ít nhất {MIN_SAMPLES} quan sát."}

    result: dict = {}

    # ADF: giá gần như luôn không dừng, lợi suất thì thường dừng. Nếu ngược lại
    # thì có gì đó bất thường trong dữ liệu.
    try:
        adf_price = adfuller(p, autolag="AIC")
        adf_ret = adfuller(r, autolag="AIC")
        result["adf_price_p"] = float(adf_price[1])
        result["adf_price_stationary"] = bool(adf_price[1] < 0.05)
        result["adf_return_p"] = float(adf_ret[1])
        result["adf_return_stationary"] = bool(adf_ret[1] < 0.05)
    except Exception as exc:
        log.warning("ADF failed: %s", exc)
        result["adf_error"] = str(exc)

    # Ljung-Box: lợi suất có tự tương quan không? Có nghĩa là có cấu trúc để
    # khai thác; không có nghĩa là chỉ báo dựa trên giá quá khứ khó ăn thua.
    try:
        lags = min(20, max(5, r.size // 20))
        lb = acorr_ljungbox(r, lags=[lags], return_df=True)
        result["ljungbox_lags"] = int(lags)
        result["ljungbox_p"] = float(lb["lb_pvalue"].iloc[0])
        result["has_autocorrelation"] = bool(lb["lb_pvalue"].iloc[0] < 0.05)
    except Exception as exc:
        log.warning("Ljung-Box failed: %s", exc)
        result["ljungbox_error"] = str(exc)

    h = hurst_exponent(p)
    result["hurst"] = h
    result["hurst_reading"] = (
        "không tính được" if not np.isfinite(h)
        else "hồi quy trung bình" if h < 0.45
        else "xu hướng" if h > 0.55
        else "gần bước ngẫu nhiên"
    )
    result["variance_ratio"] = variance_ratio(r)

    # Tự tương quan của |lợi suất|: biến động gom cụm là đặc trưng gần như phổ
    # quát của thị trường, và là thứ các mô hình GARCH khai thác.
    try:
        abs_r = np.abs(r)
        lb_abs = acorr_ljungbox(abs_r, lags=[min(20, max(5, r.size // 20))], return_df=True)
        result["volatility_clustering_p"] = float(lb_abs["lb_pvalue"].iloc[0])
        result["has_volatility_clustering"] = bool(lb_abs["lb_pvalue"].iloc[0] < 0.05)
    except Exception:
        pass

    return result


# --------------------------------------------------------------- suy diễn

def inference(trade_returns: np.ndarray) -> dict:
    """Lợi thế quan sát được có khác 0 một cách có ý nghĩa không?"""
    r = _finite(trade_returns)
    if r.size < 5:
        return {"error": f"Cần ít nhất 5 lệnh, hiện có {r.size}."}

    t_stat, p_two = sps.ttest_1samp(r, 0.0)
    # Một phía: ta chỉ quan tâm lợi suất trung bình có LỚN HƠN 0 không.
    p_one = p_two / 2 if t_stat > 0 else 1 - p_two / 2

    se = r.std(ddof=1) / np.sqrt(r.size) if r.size > 1 else float("nan")
    ci = sps.t.interval(0.95, r.size - 1, loc=r.mean(), scale=se) if se > 0 else (np.nan, np.nan)

    return {
        "n_trades": int(r.size),
        "mean_return_pct": float(r.mean() * 100),
        "t_statistic": float(t_stat),
        "p_value_one_sided": float(p_one),
        "significant": bool(p_one < 0.05),
        "ci95_low_pct": float(ci[0] * 100),
        "ci95_high_pct": float(ci[1] * 100),
        # Với ít lệnh, khoảng tin cậy rộng đến mức con số trung bình vô nghĩa.
        "underpowered": bool(r.size < 30),
    }


# ------------------------------------------------------------------ Bayes

def bayesian_win_rate(wins: int, losses: int, prior_alpha: float = 1.0,
                      prior_beta: float = 1.0) -> dict:
    """Hậu nghiệm Beta–Nhị thức trên tỷ lệ thắng.

    Tiên nghiệm mặc định Beta(1,1) là phân phối đều: chưa biết gì. Hậu nghiệm
    là Beta(1+thắng, 1+thua), và bề rộng của nó nói lên điều mà tỷ lệ thắng đơn
    lẻ giấu đi — với 20 lệnh, khoảng tin cậy rộng tới hàng chục điểm phần trăm.
    """
    n = wins + losses
    if n < 1:
        return {"error": "Chưa có lệnh nào."}

    a = prior_alpha + wins
    b = prior_beta + losses
    posterior = sps.beta(a, b)
    lo, hi = posterior.interval(0.95)

    return {
        "wins": int(wins),
        "losses": int(losses),
        "observed_win_rate_pct": float(wins / n * 100),
        "posterior_mean_pct": float(a / (a + b) * 100),
        "credible_95_low_pct": float(lo * 100),
        "credible_95_high_pct": float(hi * 100),
        "credible_width_pct": float((hi - lo) * 100),
        # Xác suất tỷ lệ thắng thật vượt 50% — câu hỏi thực sự đáng quan tâm.
        "prob_better_than_coin_pct": float((1 - posterior.cdf(0.5)) * 100),
        "prior": f"Beta({prior_alpha:g}, {prior_beta:g})",
    }


# ------------------------------------------------------------------ tổng hợp

def analyse_series(df: pd.DataFrame) -> dict:
    """Chạy toàn bộ kiểm định trên một chuỗi giá."""
    close = df["close"].to_numpy(dtype="float64")
    returns = np.diff(close) / close[:-1]

    return {
        "bars": int(len(df)),
        "distribution": distribution(returns),
        "stochastic": stochastic(close, returns),
    }


def analyse_strategy(trades: list[dict], initial_capital: float) -> dict:
    """Chạy kiểm định suy diễn và Bayes trên kết quả một chiến lược."""
    if not trades:
        return {"error": "Chiến lược chưa tạo lệnh nào."}

    pnls = np.array([t["pnl"] for t in trades], dtype="float64")
    trade_returns = pnls / max(initial_capital, 1e-9)
    wins = int((pnls > 0).sum())
    losses = int((pnls < 0).sum())

    return {
        "inference": inference(trade_returns),
        "bayesian": bayesian_win_rate(wins, losses),
        "trade_distribution": distribution(trade_returns) if len(pnls) >= MIN_SAMPLES else {
            "note": f"Cần {MIN_SAMPLES} lệnh để phân tích phân phối, hiện có {len(pnls)}."
        },
    }
