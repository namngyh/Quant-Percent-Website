"""Kiểm định thống kê trên chuỗi giá và trên kết quả chiến lược.

Mục đích: phân biệt **cấu trúc thật** với **ngẫu nhiên trông giống cấu trúc**.
Một chuỗi giá ngẫu nhiên vẫn tạo ra xu hướng, mẫu hình và những chiến lược
trông có lãi, nên trước khi tin một kết quả cần biết dữ liệu có gì để khai
thác hay không.

Mọi kiểm định trong file này trả về **cùng một cấu trúc** (xem ``_result``):
tên, giả thuyết H₀ và H₁ viết bằng lời, thống kê kiểm định, bậc tự do, p-value,
mức ý nghĩa, kết luận, và, phần quan trọng nhất, **giả định** mà kiểm định
đó đứng trên. Một p-value không kèm giả định là một con số không đọc được.

Bốn điểm về tính chặt chẽ, vì đây là chỗ phân tích tài chính hay sai:

1. **Đa kiểm định.** Chạy 12 kiểm định ở α = 0.05 thì xác suất có ít nhất một
   kết quả "có ý nghĩa" do may rủi là 1 − 0.95¹² ≈ 46%. Toàn bộ họ kiểm định ở
   đây được hiệu chỉnh bằng Benjamini–Hochberg (kiểm soát FDR), và cả p thô lẫn
   p hiệu chỉnh đều được báo cáo.
2. **Bậc tự do và phiên bản kiểm định phải nói rõ.** Tỷ số phương sai có hai
   dạng thống kê z (đồng nhất phương sai và bền với phương sai thay đổi) cho ra
   kết luận khác nhau trên dữ liệu tài chính; báo cáo một cái mà gọi tên cái kia
   là sai. Cả hai đều được tính.
3. **Không bác bỏ ≠ chấp nhận H₀.** ADF không bác bỏ nghĩa là *không đủ bằng
   chứng* để nói chuỗi dừng, không phải "chuỗi không dừng". Vì thế ADF luôn đi
   kèm KPSS, vốn đảo ngược giả thuyết; hai kiểm định cùng nhau mới cho một kết
   luận đọc được.
4. **Giả định chuẩn hầu như luôn sai với lợi suất.** Nên mỗi kiểm định tham số
   đều có một kiểm định phi tham số đi kèm (hoán vị, bootstrap, dấu, hạng).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy import stats as sps

from backend.i18n import bi

log = logging.getLogger(__name__)

# Dưới ngưỡng này thì kiểm định tiệm cận không còn đáng tin. Jarque–Bera và ADF
# đều dựa vào phân phối tiệm cận; với 30 quan sát chúng cho p-value sai lệch
# nặng theo hướng bác bỏ quá dễ.
MIN_SAMPLES = 60

ALPHA = 0.05

# Số lần hoán vị/bootstrap. 2000 đủ để p-value ổn định tới ~0.01 mà vẫn chạy
# trong dưới một giây trên 10 000 quan sát.
N_RESAMPLE = 2000
N_PERMUTE = 300

_RNG = np.random.default_rng(20260101)


def _finite(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype="float64")
    return values[np.isfinite(values)]


def _result(
    name: str,
    *,
    null: str,
    alternative: str,
    statistic: float | None,
    p_value: float | None,
    conclusion: str,
    assumptions: str,
    alpha: float = ALPHA,
    df: float | None = None,
    statistic_label: str = "thống kê",
    extra: dict | None = None,
) -> dict:
    """Vỏ chung cho mọi kiểm định.

    ``reject`` là quyết định ở mức α *trước khi* hiệu chỉnh đa kiểm định;
    ``analyse_*`` sẽ thêm ``p_adjusted`` và ``reject_adjusted`` vào sau.
    """
    reject = None
    if p_value is not None and np.isfinite(p_value):
        reject = bool(p_value < alpha)
    return {
        "name": name,
        "null": null,
        "alternative": alternative,
        "statistic": None if statistic is None or not np.isfinite(statistic) else float(statistic),
        "statistic_label": statistic_label,
        "df": df,
        "p_value": None if p_value is None or not np.isfinite(p_value) else float(p_value),
        "alpha": alpha,
        "reject": reject,
        "conclusion": conclusion,
        "assumptions": assumptions,
        **(extra or {}),
    }


def _unavailable(name: str, reason: str) -> dict:
    return {"name": name, "unavailable": reason}


# ------------------------------------------------------ hiệu chỉnh đa kiểm định

def benjamini_hochberg(p_values: list[float], alpha: float = ALPHA) -> list[float]:
    """p-value hiệu chỉnh theo Benjamini–Hochberg (kiểm soát FDR).

    Bonferroni kiểm soát xác suất có *bất kỳ* dương tính giả nào, và với 12
    kiểm định thì nó khắt khe tới mức không kiểm định nào qua nổi. BH kiểm soát
    *tỷ lệ* dương tính giả trong số các kết quả được tuyên bố: đúng thứ cần
    kiểm soát khi ta đang sàng lọc chứ không phải khẳng định một giả thuyết duy
    nhất.

    Trả về p đã hiệu chỉnh, theo đúng thứ tự đầu vào, đã ép đơn điệu.
    """
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    previous = 1.0
    # Duyệt từ p lớn nhất về nhỏ nhất để ép tính đơn điệu.
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        value = min(previous, p_values[i] * m / rank)
        adjusted[i] = value
        previous = value
    return adjusted


def _apply_fdr(tests: dict, alpha: float = ALPHA) -> dict:
    """Gắn p hiệu chỉnh vào một họ kiểm định, và tóm tắt họ đó."""
    keys = [
        k for k, v in tests.items()
        if isinstance(v, dict) and v.get("p_value") is not None
    ]
    if not keys:
        return {"n_tests": 0, "method": "Benjamini–Hochberg (FDR)", "alpha": alpha}

    raw = [tests[k]["p_value"] for k in keys]
    adjusted = benjamini_hochberg(raw, alpha)
    for k, p_adj in zip(keys, adjusted, strict=True):
        tests[k]["p_adjusted"] = float(p_adj)
        tests[k]["reject_adjusted"] = bool(p_adj < alpha)

    return {
        "n_tests": len(keys),
        "method": "Benjamini–Hochberg (FDR)",
        "alpha": alpha,
        "n_significant_raw": sum(1 for p in raw if p < alpha),
        "n_significant_adjusted": sum(1 for p in adjusted if p < alpha),
        "note": bi(
            f"{len(keys)} kiểm định chạy cùng lúc. Nếu tất cả H₀ đều đúng thì "
            f"xác suất có ít nhất một kết quả 'có ý nghĩa' ở α={alpha} là "
            f"{(1 - (1 - alpha) ** len(keys)) * 100:.0f}%. Cột p hiệu chỉnh đã "
            "tính đến điều đó: hãy đọc cột đó, không phải p thô.",
            f"{len(keys)} tests were run together. If every null were true, the "
            f"chance of at least one 'significant' result at α={alpha} is "
            f"{(1 - (1 - alpha) ** len(keys)) * 100:.0f}%. The adjusted column "
            "accounts for that: read that one, not the raw p.",
        ),
    }


# --------------------------------------------------------------- phân phối

def moments(returns: np.ndarray) -> dict:
    """Bốn mô-men đầu, kèm sai số chuẩn dưới giả thuyết chuẩn.

    Độ lệch và độ nhọn không kèm sai số chuẩn là vô nghĩa: với 200 quan sát,
    SE của độ lệch đã là 0.17, nên một độ lệch −0.3 không khác 0 một cách đáng
    kể. Công thức SE là của Cramér, dùng trong kiểm định D'Agostino.
    """
    r = _finite(returns)
    n = r.size
    if n < 8:
        return {"error": f"Cần ít nhất 8 quan sát, hiện có {n}."}

    se_skew = float(np.sqrt(6.0 * n * (n - 1) / ((n - 2) * (n + 1) * (n + 3))))
    se_kurt = float(2.0 * se_skew * np.sqrt((n * n - 1.0) / ((n - 3.0) * (n + 5.0))))

    skew = float(sps.skew(r, bias=False))
    kurt = float(sps.kurtosis(r, bias=False))  # thừa: 0 = chuẩn

    return {
        "n": int(n),
        "mean_pct": float(r.mean() * 100),
        "std_pct": float(r.std(ddof=1) * 100),
        "median_pct": float(np.median(r) * 100),
        "skew": skew,
        "skew_se": se_skew,
        "skew_z": skew / se_skew if se_skew > 0 else None,
        "skew_significant": bool(abs(skew) > 1.96 * se_skew),
        "kurtosis_excess": kurt,
        "kurtosis_se": se_kurt,
        "kurtosis_z": kurt / se_kurt if se_kurt > 0 else None,
        "kurtosis_significant": bool(abs(kurt) > 1.96 * se_kurt),
        "worst_pct": float(r.min() * 100),
        "best_pct": float(r.max() * 100),
    }


def normality(returns: np.ndarray) -> dict:
    """Hai kiểm định chuẩn tính, vì chúng nhạy với những lệch khác nhau."""
    r = _finite(returns)
    out: dict = {}

    if r.size < MIN_SAMPLES:
        reason = f"Cần ít nhất {MIN_SAMPLES} quan sát, hiện có {r.size}."
        return {
            "jarque_bera": _unavailable("Jarque–Bera", reason),
            "dagostino": _unavailable("D'Agostino K²", reason),
        }

    jb_stat, jb_p = sps.jarque_bera(r)
    out["jarque_bera"] = _result(
        "Jarque–Bera",
        null=bi(
            "Lợi suất tuân theo phân phối chuẩn (độ lệch = 0 và độ nhọn thừa = 0).",
            "Returns are normally distributed (skew = 0 and excess kurtosis = 0).",
        ),
        alternative=bi(
            "Phân phối lệch chuẩn ở mô-men bậc ba hoặc bậc bốn.",
            "The distribution departs from normal in its third or fourth moment.",
        ),
        statistic=float(jb_stat),
        statistic_label="JB",
        df=2,
        p_value=float(jb_p),
        conclusion=bi(
            "Bác bỏ chuẩn tính. Mọi công thức giả định phân phối chuẩn, kể cả "
            "Sharpe và VaR tham số, đều đánh giá thấp rủi ro đuôi trên chuỗi này."
            if jb_p < ALPHA else
            "Không đủ bằng chứng bác bỏ chuẩn tính. Lưu ý đây không phải bằng "
            "chứng chuỗi *là* chuẩn; với cỡ mẫu này lực kiểm định có thể còn thấp.",
            "Normality is rejected. Every formula that assumes a normal "
            "distribution, Sharpe and parametric VaR among them, understates "
            "tail risk on this series."
            if jb_p < ALPHA else
            "Not enough evidence to reject normality. Note this is not evidence "
            "that the series *is* normal; at this sample size the test may "
            "simply lack power.",
        ),
        assumptions=bi(
            "Quan sát độc lập cùng phân phối. Phân phối χ²(2) của thống kê chỉ "
            "đúng tiệm cận và hội tụ chậm; với n < 2000, JB bác bỏ dễ hơn mức "
            "danh nghĩa. Tự tương quan phương sai (biến động gom cụm) cũng làm "
            "JB bác bỏ ngay cả khi phân phối biên là chuẩn.",
            "Independent, identically distributed observations. The statistic's "
            "χ²(2) distribution holds only asymptotically and converges slowly; "
            "below n = 2000, JB rejects more readily than its nominal rate. "
            "Autocorrelated variance (volatility clustering) also makes JB "
            "reject even when the marginal distribution is normal.",
        ),
    )

    k2_stat, k2_p = sps.normaltest(r)
    out["dagostino"] = _result(
        "D'Agostino K²",
        null=bi("Lợi suất tuân theo phân phối chuẩn.",
                "Returns are normally distributed."),
        alternative=bi("Độ lệch hoặc độ nhọn khác giá trị chuẩn.",
                       "Skew or kurtosis differs from the normal value."),
        statistic=float(k2_stat),
        statistic_label="K²",
        df=2,
        p_value=float(k2_p),
        conclusion=bi(
            "Bác bỏ chuẩn tính." if k2_p < ALPHA else
            "Không đủ bằng chứng bác bỏ chuẩn tính.",
            "Normality is rejected." if k2_p < ALPHA else
            "Not enough evidence to reject normality.",
        ),
        assumptions=bi(
            "Quan sát độc lập cùng phân phối, n ≥ 20. Dùng biến đổi chuẩn hoá "
            "của độ lệch và độ nhọn nên chính xác hơn Jarque–Bera ở mẫu vừa, "
            "nhưng vẫn giả định độc lập.",
            "Independent, identically distributed observations, n ≥ 20. It uses "
            "normalising transforms of skew and kurtosis, so it is more accurate "
            "than Jarque–Bera at moderate sample sizes, but it still assumes "
            "independence.",
        ),
    )
    return out


def tail_risk(returns: np.ndarray) -> dict:
    """VaR và CVaR theo mô phỏng lịch sử, kèm số quan sát đỡ mỗi ước lượng.

    Đây là chỗ dễ tự lừa nhất trong toàn bộ phân tích: CVaR 99% trên 2 000 nến
    được tính từ đúng 20 quan sát. Con số vẫn hiện ra với hai chữ số thập phân
    và trông chắc chắn như mọi con số khác. Nên số quan sát đuôi được báo cáo
    ngay cạnh, và khoảng tin cậy lấy bằng bootstrap chứ không giả định gì.
    """
    r = _finite(returns)
    n = r.size
    if n < MIN_SAMPLES:
        return {"error": f"Cần ít nhất {MIN_SAMPLES} quan sát, hiện có {n}."}

    out: dict = {"n": int(n)}
    draws = _RNG.integers(0, n, size=(N_RESAMPLE, n))
    resampled = r[draws]

    for level, pct in ((95, 5.0), (99, 1.0)):
        var = float(np.percentile(r, pct))
        tail = r[r <= var]
        cvar = float(tail.mean()) if tail.size else var

        # Bootstrap khoảng tin cậy của VaR: phân vị mẫu có phân phối lệch và
        # công thức sai số chuẩn tiệm cận cần ước lượng mật độ, thứ ta không có.
        boot = np.percentile(resampled, pct, axis=1)
        lo, hi = np.percentile(boot, [2.5, 97.5])

        key = str(level)
        out[f"var_{key}_pct"] = var * 100
        out[f"var_{key}_ci_low_pct"] = float(lo * 100)
        out[f"var_{key}_ci_high_pct"] = float(hi * 100)
        out[f"cvar_{key}_pct"] = cvar * 100
        out[f"tail_n_{key}"] = int(tail.size)
        out[f"tail_reliable_{key}"] = bool(tail.size >= 30)

    out["note"] = bi(
        "VaR/CVaR lịch sử: đọc thẳng từ phân vị mẫu, không giả định phân phối. "
        f"CVaR 99% ở đây dựa trên {out['tail_n_99']} quan sát đuôi"
        + ("" if out["tail_reliable_99"]
           else ": quá ít để ổn định; hãy coi là chỉ dấu, không phải ước lượng")
        + ". Khoảng tin cậy 95% lấy bằng bootstrap "
        f"({N_RESAMPLE} lần lấy mẫu lại có hoàn lại).",
        "Historical VaR/CVaR: read straight off the sample quantile, assuming "
        f"no distribution. The 99% CVaR here rests on {out['tail_n_99']} tail "
        "observations"
        + ("" if out["tail_reliable_99"]
           else ": too few to be stable; treat it as an indication, not an estimate")
        + f". The 95% interval comes from a bootstrap ({N_RESAMPLE} resamples "
        "with replacement).",
    )
    out["horizon_warning"] = bi(
        "Các con số này là cho MỘT nến, không phải một ngày hay một năm. Nhân "
        "với căn bậc hai của thời gian chỉ đúng khi lợi suất độc lập, điều mà "
        "kiểm định biến động gom cụm bên dưới thường bác bỏ.",
        "These figures are for ONE bar, not a day or a year. Scaling by the "
        "square root of time is only valid when returns are independent, which "
        "the volatility-clustering test below usually rejects.",
    )
    return out


def distribution(returns: np.ndarray) -> dict:
    """Gộp mô-men, chuẩn tính và rủi ro đuôi."""
    r = _finite(returns)
    if r.size < MIN_SAMPLES:
        return {"error": f"Cần ít nhất {MIN_SAMPLES} quan sát, hiện có {r.size}."}
    return {
        "moments": moments(r),
        "normality": normality(r),
        "tail": tail_risk(r),
    }


# ------------------------------------------------------- quá trình ngẫu nhiên

def _rs_statistic(series: np.ndarray, window: int) -> float:
    """Trung bình R/S trên các đoạn không chồng lấn độ dài ``window``."""
    n_chunks = series.size // window
    if n_chunks < 1:
        return float("nan")
    chunks = series[: n_chunks * window].reshape(n_chunks, window)
    deviations = chunks - chunks.mean(axis=1, keepdims=True)
    cumulative = np.cumsum(deviations, axis=1)
    ranges = cumulative.max(axis=1) - cumulative.min(axis=1)
    stds = chunks.std(axis=1, ddof=1)
    ok = stds > 0
    if not ok.any():
        return float("nan")
    return float(np.mean(ranges[ok] / stds[ok]))


def _anis_lloyd_expected(window: int) -> float:
    """E[R/S] kỳ vọng của một chuỗi độc lập, theo Anis–Lloyd (1976).

    Không có hiệu chỉnh này thì ước lượng Hurst chệch lên rõ rệt ở cửa sổ nhỏ:
    một chuỗi hoàn toàn ngẫu nhiên vẫn cho H ≈ 0.6 với n vài trăm, và người
    đọc kết luận "có xu hướng" từ nhiễu.
    """
    from math import exp, lgamma, log, pi

    n = window
    indices = np.arange(1, n)
    tail_sum = float(np.sum(np.sqrt((n - indices) / indices)))
    if n > 340:
        front = (n - 0.5) / n * (n * pi / 2.0) ** -0.5
    else:
        # Γ((n−1)/2) / (√π · Γ(n/2)), tính qua lgamma để không tràn số.
        front = (n - 0.5) / n * exp(
            lgamma((n - 1) / 2.0) - 0.5 * log(pi) - lgamma(n / 2.0)
        )
    return float(front * tail_sum)


_EXPECTED_CACHE: dict[int, float] = {}


def _expected_rs(window: int) -> float:
    if window not in _EXPECTED_CACHE:
        _EXPECTED_CACHE[window] = _anis_lloyd_expected(window)
    return _EXPECTED_CACHE[window]


def _hurst_windows(n: int) -> np.ndarray:
    """Cửa sổ cách đều theo thang log, từ 16 tới n/4.

    Dưới 16 thì R/S nhiễu; trên n/4 thì chỉ còn ba đoạn để lấy trung bình và
    ước lượng phụ thuộc vào đúng ba con số.
    """
    max_window = n // 4
    if max_window < 32:
        return np.array([], dtype=int)
    return np.unique(
        np.floor(np.logspace(np.log10(16), np.log10(max_window), 14)).astype(int)
    )


def _hurst_from_returns(
    returns: np.ndarray, windows: np.ndarray
) -> tuple[float, float, float, list]:
    """Hurst hiệu chỉnh Anis–Lloyd. Trả về (H, H thô, SE, các điểm hồi quy)."""
    points = []
    for w in windows:
        observed = _rs_statistic(returns, int(w))
        if not np.isfinite(observed) or observed <= 0:
            continue
        expected = _expected_rs(int(w))
        if expected <= 0:
            continue
        points.append((int(w), observed, expected))

    if len(points) < 5:
        return float("nan"), float("nan"), float("nan"), []

    log_w = np.log(np.array([p[0] for p in points], dtype="float64"))
    log_obs = np.log(np.array([p[1] for p in points], dtype="float64"))
    log_exp = np.log(np.array([p[2] for p in points], dtype="float64"))

    raw = float(np.polyfit(log_w, log_obs, 1)[0])

    # Hiệu chỉnh: hồi quy phần dư so với kỳ vọng độc lập, rồi cộng lại 0.5.
    fit = sps.linregress(log_w, log_obs - log_exp)
    corrected = float(fit.slope + 0.5)
    return corrected, raw, float(fit.stderr), [
        {"window": p[0], "rs_observed": p[1], "rs_expected": p[2]} for p in points
    ]


def hurst(returns: np.ndarray) -> dict:
    """Hurst qua R/S hiệu chỉnh, với p-value bằng kiểm định hoán vị.

    Không dùng công thức tiệm cận cho p-value: phân phối của ước lượng H phụ
    thuộc vào độ dài chuỗi, tập cửa sổ và cả phân phối biên của lợi suất. Hoán
    vị chính chuỗi này giữ nguyên phân phối biên và phá huỷ mọi phụ thuộc theo
    thời gian, nên nó cho đúng phân phối H dưới H₀ cho **chuỗi này**, không
    phải cho một chuỗi lý thuyết nào khác.
    """
    r = _finite(returns)
    if r.size < 256:
        return _unavailable(
            "Hurst (R/S hiệu chỉnh)",
            f"Cần ít nhất 256 quan sát cho R/S, hiện có {r.size}.",
        )

    windows = _hurst_windows(r.size)
    if windows.size == 0:
        return _unavailable(
            bi("Hurst (R/S hiệu chỉnh)", "Hurst (corrected R/S)"),
            bi("Chuỗi quá ngắn cho R/S.", "The series is too short for R/S."))

    h, h_raw, se, points = _hurst_from_returns(r, windows)
    if not np.isfinite(h):
        return _unavailable(
            bi("Hurst (R/S hiệu chỉnh)", "Hurst (corrected R/S)"),
            bi("Không hồi quy được R/S.", "The R/S regression did not fit."))

    # Phân phối H dưới H₀ "không có phụ thuộc thời gian".
    null_values = []
    shuffled = r.copy()
    for _ in range(N_PERMUTE):
        _RNG.shuffle(shuffled)
        value, _, _, _ = _hurst_from_returns(shuffled, windows)
        if np.isfinite(value):
            null_values.append(value)

    if len(null_values) < 50:
        p_value = float("nan")
        null_mean = null_sd = float("nan")
    else:
        null_array = np.array(null_values)
        null_mean = float(null_array.mean())
        null_sd = float(null_array.std(ddof=1))
        # Hai phía, cộng 1 vào tử và mẫu: p-value hoán vị không bao giờ được
        # bằng 0, vì ta chỉ lấy hữu hạn mẫu.
        extreme = int(np.sum(np.abs(null_array - null_mean) >= abs(h - null_mean)))
        p_value = (extreme + 1) / (len(null_values) + 1)

    if not np.isfinite(p_value) or p_value >= ALPHA:
        reading = bi("không phân biệt được với không phụ thuộc thời gian",
                     "indistinguishable from no time dependence")
    elif h > null_mean:
        reading = bi("có quán tính (bộ nhớ dài dương)",
                     "persistent (positive long memory)")
    else:
        reading = bi("hồi quy trung bình", "mean reverting")

    return _result(
        bi("Hurst (R/S hiệu chỉnh Anis–Lloyd)",
           "Hurst (Anis–Lloyd corrected R/S)"),
        null=bi(
            "Lợi suất không có phụ thuộc theo thời gian (H bằng giá trị kỳ vọng "
            "của chuỗi hoán vị).",
            "Returns carry no time dependence (H equals the value expected from "
            "a shuffled series).",
        ),
        alternative=bi("Có bộ nhớ dài: H lệch khỏi giá trị đó.",
                       "Long memory is present: H departs from that value."),
        statistic=h,
        statistic_label="H",
        p_value=p_value,
        conclusion=bi(
            (f"H = {h:.3f}; chuỗi hoán vị cho trung bình {null_mean:.3f} "
             f"(độ lệch chuẩn {null_sd:.3f}). Kết luận: {reading['vi']}."
             if np.isfinite(null_mean) else f"H = {h:.3f}."),
            (f"H = {h:.3f}; shuffled series average {null_mean:.3f} "
             f"(standard deviation {null_sd:.3f}). Reading: {reading['en']}."
             if np.isfinite(null_mean) else f"H = {h:.3f}."),
        ),
        assumptions=bi(
            "R/S trên các đoạn không chồng lấn, cửa sổ 16 tới n/4, đã trừ kỳ "
            "vọng Anis–Lloyd của chuỗi độc lập, nếu bỏ bước này, một chuỗi "
            "ngẫu nhiên cũng cho H ≈ 0.6. p-value lấy từ "
            f"{len(null_values)} lần hoán vị chính chuỗi này, nên nó giữ nguyên "
            "phân phối biên (kể cả đuôi dày) và chỉ phá huỷ trật tự thời gian. "
            "R/S nhạy với biến động thay đổi theo thời gian: một chuỗi có biến "
            "động gom cụm nhưng không có bộ nhớ vẫn có thể cho H > 0.5.",
            "R/S over non-overlapping windows from 16 to n/4, with the "
            "Anis–Lloyd expectation for an independent series subtracted; skip "
            "that step and a purely random series also returns H ≈ 0.6. The "
            f"p-value comes from {len(null_values)} permutations of this series "
            "itself, so it preserves the marginal distribution (fat tails "
            "included) and destroys only the ordering. R/S is sensitive to "
            "time-varying volatility: a series with clustering but no memory can "
            "still return H > 0.5.",
        ),
        extra={
            "hurst_uncorrected": h_raw,
            "regression_se": se,
            "null_mean": null_mean if np.isfinite(null_mean) else None,
            "null_sd": null_sd if np.isfinite(null_sd) else None,
            "n_permutations": len(null_values),
            "reading": reading,
            "rs_points": points,
        },
    )


def variance_ratio(returns: np.ndarray, periods: tuple[int, ...] = (2, 4, 8, 16)) -> dict:
    """Kiểm định tỷ số phương sai Lo–MacKinlay, nhiều kỳ hạn, kèm Chow–Denning.

    Với bước ngẫu nhiên, phương sai của tổng q lợi suất bằng q lần phương sai
    một bước, nên VR(q) = 1.

    Hai điểm mà bản triển khai phổ biến hay làm sai:

    * **z1 và z2 không thay thế nhau.** z1 giả định phương sai đồng nhất; lợi
      suất tài chính thì không, nên z1 bác bỏ bước ngẫu nhiên chỉ vì biến động
      thay đổi theo thời gian. z2 bền với điều đó. Cả hai được báo cáo, và kết
      luận đọc theo z2.
    * **Chạy VR ở bốn kỳ hạn là bốn kiểm định.** Lấy cái nào có p nhỏ nhất là
      thổi phồng sai lầm loại I. Thống kê Chow–Denning lấy max|z| và so với
      phân phối modulus cực đại studentised, nên nó là *một* kiểm định cho toàn
      bộ tập kỳ hạn.
    """
    r = _finite(returns)
    n = r.size
    if n < max(periods) * 20:
        return _unavailable(
            "Tỷ số phương sai (Lo–MacKinlay)",
            f"Cần ít nhất {max(periods) * 20} quan sát cho kỳ hạn tới "
            f"{max(periods)}, hiện có {n}.",
        )

    mu = float(r.mean())
    centred = r - mu
    var_1 = float(np.sum(centred**2) / (n - 1))
    if var_1 <= 0:
        return _unavailable(
            bi("Tỷ số phương sai (Lo–MacKinlay)", "Variance ratio (Lo–MacKinlay)"),
            bi("Phương sai bằng 0.", "The variance is zero."))

    # Mẫu số của δ̂ⱼ trong sai số chuẩn bền với phương sai thay đổi.
    denominator = float(np.sum(centred**2)) ** 2
    per_period = []
    z2_values = []

    for q in periods:
        rolled = np.convolve(r, np.ones(q), mode="valid")
        m = q * (n - q + 1) * (1.0 - q / n)
        var_q = float(np.sum((rolled - q * mu) ** 2) / m)
        vr = var_q / var_1

        # z1: đồng nhất phương sai.
        phi1 = 2.0 * (2.0 * q - 1.0) * (q - 1.0) / (3.0 * q * n)
        z1 = (vr - 1.0) / np.sqrt(phi1) if phi1 > 0 else float("nan")

        # z2: bền với phương sai thay đổi.
        phi2 = 0.0
        for j in range(1, q):
            num = float(np.sum((centred[j:] ** 2) * (centred[:-j] ** 2)))
            delta = num / denominator if denominator > 0 else 0.0
            phi2 += (2.0 * (q - j) / q) ** 2 * delta
        z2 = (vr - 1.0) / np.sqrt(phi2) if phi2 > 0 else float("nan")

        if np.isfinite(z2):
            z2_values.append(abs(z2))

        per_period.append({
            "period": int(q),
            "variance_ratio": float(vr),
            "z_homoskedastic": float(z1) if np.isfinite(z1) else None,
            "p_homoskedastic": float(2 * sps.norm.sf(abs(z1))) if np.isfinite(z1) else None,
            "z_heteroskedastic": float(z2) if np.isfinite(z2) else None,
            "p_heteroskedastic": float(2 * sps.norm.sf(abs(z2))) if np.isfinite(z2) else None,
            "reading": (
                bi("—", "—") if not np.isfinite(z2)
                else bi("quán tính", "trending") if z2 > 1.96
                else bi("hồi quy trung bình", "mean reverting") if z2 < -1.96
                else bi("phù hợp bước ngẫu nhiên", "consistent with a random walk")
            ),
        })

    if not z2_values:
        return _unavailable(
            bi("Tỷ số phương sai (Lo–MacKinlay)", "Variance ratio (Lo–MacKinlay)"),
            bi("Không tính được thống kê z.", "The z statistic could not be computed."))

    # Chow–Denning: max|z2| so với modulus cực đại studentised, bậc tự do ∞.
    m_tests = len(z2_values)
    cd_stat = float(max(z2_values))
    # P(max|Z| ≥ c) với m biến chuẩn độc lập = 1 − (2Φ(c) − 1)^m.
    cd_p = float(1.0 - (2.0 * sps.norm.cdf(cd_stat) - 1.0) ** m_tests)
    cd_critical = float(sps.norm.ppf((1.0 + (1.0 - ALPHA) ** (1.0 / m_tests)) / 2.0))

    return _result(
        bi("Tỷ số phương sai: Chow–Denning (đa kỳ hạn)",
           "Variance ratio: Chow–Denning (multi-horizon)"),
        null=bi(
            f"Chuỗi là bước ngẫu nhiên: VR(q) = 1 đồng thời ở mọi q ∈ {list(periods)}.",
            f"The series is a random walk: VR(q) = 1 simultaneously for every "
            f"q ∈ {list(periods)}.",
        ),
        alternative=bi("VR khác 1 ở ít nhất một kỳ hạn.",
                       "VR differs from 1 at at least one horizon."),
        statistic=cd_stat,
        statistic_label="max|z₂|",
        p_value=cd_p,
        conclusion=bi(
            (f"max|z₂| = {cd_stat:.2f} vượt ngưỡng {cd_critical:.2f}: bác bỏ bước "
             "ngẫu nhiên ở mức toàn cục 5%. Xem bảng kỳ hạn để biết lệch theo hướng nào."
             if cd_p < ALPHA else
             f"max|z₂| = {cd_stat:.2f} dưới ngưỡng {cd_critical:.2f}: không đủ "
             "bằng chứng bác bỏ bước ngẫu nhiên ở bất kỳ kỳ hạn nào trong tập này. "
             "Chỉ báo dựa thuần vào giá quá khứ khó tìm được gì trên chuỗi này."),
            (f"max|z₂| = {cd_stat:.2f} exceeds the {cd_critical:.2f} threshold: "
             "the random walk is rejected at a 5% joint level. The horizon table "
             "shows which way it departs."
             if cd_p < ALPHA else
             f"max|z₂| = {cd_stat:.2f} is below the {cd_critical:.2f} threshold: "
             "not enough evidence to reject a random walk at any horizon in this "
             "set. An indicator built purely on past price will struggle to find "
             "anything here."),
        ),
        assumptions=bi(
            "Ước lượng chồng lấn với hiệu chỉnh mẫu nhỏ của Lo–MacKinlay. z₂ "
            "bền với phương sai thay đổi theo thời gian nhưng vẫn giả định "
            "chênh lệch martingale. Ngưỡng Chow–Denning coi các z là độc lập, "
            "trong khi thực tế các kỳ hạn tương quan dương, nên ngưỡng này hơi "
            "bảo thủ (khó bác bỏ hơn thực tế một chút).",
            "Overlapping estimator with Lo–MacKinlay's small-sample correction. "
            "z₂ is robust to time-varying variance but still assumes a "
            "martingale difference. The Chow–Denning threshold treats the z "
            "statistics as independent, while in practice the horizons are "
            "positively correlated, so it is slightly conservative, rejecting "
            "a little less readily than it should.",
        ),
        extra={
            "critical_value": cd_critical,
            "n_periods": m_tests,
            "per_period": per_period,
        },
    )


def stationarity(prices: np.ndarray, returns: np.ndarray) -> dict:
    """ADF và KPSS, đọc cùng nhau.

    Hai kiểm định đảo ngược giả thuyết của nhau, nên bốn tổ hợp kết quả cho bốn
    kết luận khác nhau, và một trong bốn là "dữ liệu không đủ để nói gì", điều
    mà chạy riêng ADF sẽ giấu mất.
    """
    from statsmodels.tsa.stattools import adfuller, kpss

    out: dict = {}
    r = _finite(returns)
    p = _finite(prices)

    if r.size < MIN_SAMPLES:
        return {"error": f"Cần ít nhất {MIN_SAMPLES} quan sát."}

    def _adf(series: np.ndarray, label: str, subject: str) -> dict:
        label_en = {"giá": "price", "lợi suất": "returns"}[label]
        stat, p_value, used_lag, nobs, crit, _ = adfuller(series, autolag="AIC")
        subject_en = {"Chuỗi giá": "The price series",
                      "Chuỗi lợi suất": "The return series"}[subject]
        return _result(
            bi(f"ADF: {label}", f"ADF: {label_en}"),
            null=bi(f"{subject} có nghiệm đơn vị (không dừng).",
                    f"{subject_en} has a unit root (is non-stationary)."),
            alternative=bi(f"{subject} dừng quanh một hằng số.",
                           f"{subject_en} is stationary around a constant."),
            statistic=float(stat),
            statistic_label="ADF",
            p_value=float(p_value),
            conclusion=bi(
                (f"Bác bỏ nghiệm đơn vị: {subject.lower()} dừng."
                 if p_value < ALPHA else
                 "Không bác bỏ được nghiệm đơn vị. Đây KHÔNG phải bằng chứng "
                 f"{subject.lower()} không dừng: ADF nổi tiếng là lực thấp khi "
                 "hệ số tự hồi quy gần 1."),
                (f"The unit root is rejected: {subject_en.lower()} is stationary."
                 if p_value < ALPHA else
                 "The unit root is not rejected. This is NOT evidence that "
                 f"{subject_en.lower()} is non-stationary: ADF is notoriously "
                 "low-powered when the autoregressive coefficient is near 1."),
            ),
            assumptions=bi(
                f"Hồi quy có hằng số, không có xu hướng. Số trễ {used_lag} chọn "
                f"theo AIC trên {nobs} quan sát. Giá trị tới hạn 5% = "
                f"{crit['5%']:.3f}. p-value nội suy từ bảng MacKinnon.",
                f"Regression with a constant and no trend. {used_lag} lags chosen "
                f"by AIC over {nobs} observations. The 5% critical value is "
                f"{crit['5%']:.3f}. The p-value is interpolated from MacKinnon's "
                "tables.",
            ),
            extra={"used_lag": int(used_lag), "nobs": int(nobs),
                   "critical_5pct": float(crit["5%"])},
        )

    try:
        out["adf_price"] = _adf(p, "giá", "Chuỗi giá")
        out["adf_return"] = _adf(r, "lợi suất", "Chuỗi lợi suất")
    except Exception as exc:
        log.warning("ADF failed: %s", exc)
        out["adf_error"] = str(exc)

    try:
        # KPSS phát cảnh báo khi p rơi ngoài bảng; đó là thông tin, không phải lỗi.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            k_stat, k_p, k_lags, k_crit = kpss(r, regression="c", nlags="auto")
        clipped = k_p in (0.01, 0.1)
        out["kpss_return"] = _result(
            bi("KPSS: lợi suất", "KPSS: returns"),
            null=bi("Chuỗi lợi suất dừng quanh một hằng số.",
                    "The return series is stationary around a constant."),
            alternative=bi("Chuỗi lợi suất có thành phần bước ngẫu nhiên.",
                           "The return series contains a random-walk component."),
            statistic=float(k_stat),
            statistic_label="LM",
            p_value=float(k_p),
            conclusion=bi(
                "Bác bỏ tính dừng." if k_p < ALPHA else "Không bác bỏ tính dừng.",
                "Stationarity is rejected." if k_p < ALPHA else
                "Stationarity is not rejected.",
            ),
            assumptions=bi(
                f"Hồi quy có hằng số, {k_lags} trễ theo quy tắc tự động. "
                "p-value được cắt trong khoảng [0.01, 0.10] vì bảng tới hạn chỉ "
                "có tới đó"
                + (": giá trị này đã bị cắt, con số thật nằm ngoài khoảng."
                   if clipped else "."),
                f"Regression with a constant, {k_lags} lags by the automatic "
                "rule. The p-value is clipped to [0.01, 0.10] because the "
                "critical-value table stops there"
                + (": this value was clipped, and the true figure lies outside "
                   "the range." if clipped else "."),
            ),
            extra={"p_value_clipped": bool(clipped), "lags": int(k_lags),
                   "critical_5pct": float(k_crit["5%"])},
        )
    except Exception as exc:
        log.warning("KPSS failed: %s", exc)
        out["kpss_error"] = str(exc)

    # Đọc chéo ADF × KPSS trên chuỗi lợi suất.
    adf = out.get("adf_return", {})
    kp = out.get("kpss_return", {})
    if adf.get("p_value") is not None and kp.get("p_value") is not None:
        adf_stationary = adf["p_value"] < ALPHA
        kpss_stationary = kp["p_value"] >= ALPHA
        if adf_stationary and kpss_stationary:
            verdict = bi(
                "ADF và KPSS đồng thuận: lợi suất dừng. Đây là điều kiện tiên "
                "quyết để mọi thống kê bên dưới có nghĩa.",
                "ADF and KPSS agree: returns are stationary. That is the "
                "precondition for everything below to mean anything.",
            )
        elif not adf_stationary and not kpss_stationary:
            verdict = bi(
                "ADF và KPSS đồng thuận: lợi suất KHÔNG dừng. Trung bình và "
                "phương sai trôi theo thời gian, nên một backtest trên toàn bộ "
                "giai đoạn đang trộn nhiều chế độ thị trường.",
                "ADF and KPSS agree: returns are NOT stationary. The mean and "
                "variance drift over time, so a backtest across the whole period "
                "is blending several market regimes.",
            )
        elif adf_stationary and not kpss_stationary:
            verdict = bi(
                "Hai kiểm định mâu thuẫn: ADF nói dừng, KPSS nói không. Dạng "
                "điển hình của chuỗi dừng quanh xu hướng hoặc có đứt gãy cấu "
                "trúc giữa kỳ.",
                "The two tests disagree: ADF says stationary, KPSS says not. "
                "That is the signature of a trend-stationary series, or one with "
                "a structural break part-way through.",
            )
        else:
            verdict = bi(
                "Không kiểm định nào kết luận được: dữ liệu không đủ thông tin. "
                "Đừng đọc phần còn lại như một khẳng định.",
                "Neither test concludes: the data does not carry enough "
                "information. Do not read what follows as an assertion.",
            )
        out["verdict"] = verdict

    return out


def autocorrelation(returns: np.ndarray) -> dict:
    """Tự tương quan mức và hiệu ứng ARCH.

    Hai câu hỏi khác hẳn nhau, và trộn chúng là lỗi phổ biến:

    * Lợi suất có tự tương quan không → có cấu trúc *hướng* để khai thác.
    * Bình phương lợi suất có tự tương quan không → biến động gom cụm. Điều
      này gần như luôn đúng và **không** cho phép dự đoán hướng đi, chỉ cho
      phép dự đoán độ lớn. Một chiến lược theo hướng không khai thác được nó.
    """
    from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch

    r = _finite(returns)
    if r.size < MIN_SAMPLES:
        return {"error": f"Cần ít nhất {MIN_SAMPLES} quan sát."}

    out: dict = {}
    lags = int(min(20, max(5, r.size // 20)))

    try:
        lb = acorr_ljungbox(r, lags=[lags], return_df=True)
        stat = float(lb["lb_stat"].iloc[0])
        p_value = float(lb["lb_pvalue"].iloc[0])
        out["ljung_box"] = _result(
            bi("Ljung–Box trên lợi suất", "Ljung–Box on returns"),
            null=bi(f"Lợi suất không tự tương quan ở mọi trễ 1..{lags}.",
                    f"Returns are uncorrelated at every lag 1..{lags}."),
            alternative=bi("Có tự tương quan ở ít nhất một trễ.",
                           "Autocorrelation is present at at least one lag."),
            statistic=stat,
            statistic_label="Q",
            df=lags,
            p_value=p_value,
            conclusion=bi(
                ("Bác bỏ: có tự tương quan tuyến tính. Đây là cấu trúc mà chỉ báo "
                 "dựa trên giá quá khứ có thể khai thác, dù độ lớn mới quyết "
                 "định nó có thắng nổi phí giao dịch hay không."
                 if p_value < ALPHA else
                 "Không có bằng chứng tự tương quan tuyến tính. Giá quá khứ, tự "
                 "nó, không dự đoán được hướng của giá tương lai trên chuỗi này."),
                ("Rejected: linear autocorrelation is present. This is structure "
                 "an indicator built on past price can exploit, though its size "
                 "is what decides whether it can beat trading costs."
                 if p_value < ALPHA else
                 "No evidence of linear autocorrelation. Past price, on its own, "
                 "does not predict the direction of future price on this series."),
            ),
            assumptions=bi(
                f"Q ~ χ²({lags}) dưới H₀. Kiểm định này giả định phương sai đồng "
                "nhất; với lợi suất tài chính có biến động gom cụm, Ljung–Box "
                "bác bỏ dễ hơn mức danh nghĩa. Nó cũng chỉ bắt phụ thuộc TUYẾN "
                "TÍNH: không có tự tương quan không có nghĩa là độc lập.",
                f"Q ~ χ²({lags}) under the null. The test assumes homoskedastic "
                "variance; with the volatility clustering of financial returns, "
                "Ljung–Box rejects more readily than its nominal rate. It also "
                "detects LINEAR dependence only: no autocorrelation does not "
                "mean independence.",
            ),
        )
    except Exception as exc:
        log.warning("Ljung-Box failed: %s", exc)
        out["ljung_box"] = _unavailable(
            bi("Ljung–Box trên lợi suất", "Ljung–Box on returns"), str(exc))

    try:
        arch_lags = int(min(12, max(4, r.size // 50)))
        lm_stat, lm_p, f_stat, f_p = het_arch(r, nlags=arch_lags)
        out["arch_lm"] = _result(
            bi("Engle ARCH-LM (biến động gom cụm)",
               "Engle ARCH-LM (volatility clustering)"),
            null=bi(
                f"Không có hiệu ứng ARCH tới trễ {arch_lags}: phương sai có "
                "điều kiện là hằng số.",
                f"No ARCH effect up to lag {arch_lags}: conditional variance is "
                "constant.",
            ),
            alternative=bi(
                "Phương sai có điều kiện phụ thuộc vào các cú sốc quá khứ.",
                "Conditional variance depends on past shocks.",
            ),
            statistic=float(lm_stat),
            statistic_label="LM",
            df=arch_lags,
            p_value=float(lm_p),
            conclusion=bi(
                ("Bác bỏ: biến động gom cụm. Hệ quả thực tế: rủi ro KHÔNG cố "
                 "định theo thời gian, nên một mức dừng lỗ tính theo phần trăm "
                 "cố định sẽ quá chặt lúc thị trường yên và quá lỏng lúc thị "
                 "trường động. Điều này không giúp dự đoán hướng."
                 if lm_p < ALPHA else
                 "Không có bằng chứng biến động gom cụm: hiếm gặp trên dữ liệu "
                 "thị trường thật; hãy kiểm tra lại độ dài và chất lượng chuỗi."),
                ("Rejected: volatility clusters. The practical consequence is "
                 "that risk is NOT constant over time, so a stop set at a fixed "
                 "percentage is too tight in quiet markets and too loose in "
                 "active ones. It does not help predict direction."
                 if lm_p < ALPHA else
                 "No evidence of volatility clustering: rare on real market "
                 "data; check the length and quality of the series."),
            ),
            assumptions=bi(
                "Hồi quy phụ bình phương phần dư lên chính nó ở các trễ; "
                f"LM ~ χ²({arch_lags}) dưới H₀. Đây là kiểm định ĐÚNG cho biến "
                "động gom cụm; chạy Ljung–Box trên |lợi suất| là một xấp xỉ "
                "không có phân phối tới hạn chuẩn.",
                "An auxiliary regression of squared residuals on their own lags; "
                f"LM ~ χ²({arch_lags}) under the null. This is the CORRECT test "
                "for volatility clustering; running Ljung–Box on |returns| is an "
                "approximation with no standard critical distribution.",
            ),
            extra={"f_statistic": float(f_stat), "f_p_value": float(f_p)},
        )
    except Exception as exc:
        log.warning("ARCH-LM failed: %s", exc)
        out["arch_lm"] = _unavailable("Engle ARCH-LM", str(exc))

    return out


# --------------------------------------------------------------- suy diễn

def _bootstrap_ci(sample: np.ndarray, statistic, alpha: float = 0.05) -> dict:
    """Khoảng tin cậy BCa: hiệu chỉnh chệch và gia tốc.

    Bootstrap phân vị thường bị chệch khi phân phối thống kê lệch, và lợi suất
    từng lệnh thì luôn lệch (nhiều lệnh nhỏ, vài lệnh lớn). BCa hiệu chỉnh cả
    độ chệch lẫn độ lệch, và là mặc định nên dùng.
    """
    n = sample.size
    if n < 8:
        return {"error": "Cần ít nhất 8 quan sát."}

    observed = float(statistic(sample))
    draws = _RNG.integers(0, n, size=(N_RESAMPLE, n))
    boot = np.array([statistic(sample[idx]) for idx in draws])
    boot = boot[np.isfinite(boot)]
    if boot.size < 100:
        return {"error": "Bootstrap không hội tụ."}

    # z₀: hiệu chỉnh chệch.
    proportion = float(np.mean(boot < observed))
    proportion = min(max(proportion, 1.0 / boot.size), 1.0 - 1.0 / boot.size)
    z0 = float(sps.norm.ppf(proportion))

    # a: gia tốc, qua jackknife (lấy mẫu con khi n lớn, để giữ thời gian chạy).
    indices = range(n) if n <= 400 else _RNG.choice(n, 400, replace=False)
    jack = np.array([statistic(np.delete(sample, i)) for i in indices])
    jack = jack[np.isfinite(jack)]
    centred = jack.mean() - jack
    denominator = 6.0 * (float(np.sum(centred**2)) ** 1.5)
    a = float(np.sum(centred**3) / denominator) if denominator > 0 else 0.0

    def _adjust(prob: float) -> float:
        z = sps.norm.ppf(prob)
        adjusted = z0 + (z0 + z) / (1.0 - a * (z0 + z))
        return float(np.clip(sps.norm.cdf(adjusted) * 100.0, 0.1, 99.9))

    lo = float(np.percentile(boot, _adjust(alpha / 2)))
    hi = float(np.percentile(boot, _adjust(1 - alpha / 2)))
    return {
        "observed": observed,
        "ci_low": lo,
        "ci_high": hi,
        "bias_correction_z0": z0,
        "acceleration": a,
        "n_resamples": int(boot.size),
    }


def inference(trade_returns: np.ndarray) -> dict:
    """Lợi thế quan sát được có khác 0 một cách có ý nghĩa không?

    Ba cách hỏi cùng một câu, vì mỗi cách hỏng ở một chỗ khác nhau:

    * **t một mẫu**: mạnh nhất nếu lợi suất xấp xỉ chuẩn, sai nhiều nếu không.
    * **Wilcoxon dấu-hạng**: chỉ cần phân phối đối xứng, không cần chuẩn.
    * **Hoán vị dấu**: không cần giả định gì ngoài việc dấu của các lệnh có
      thể hoán đổi dưới H₀. Đây là kiểm định đáng tin nhất ở đây.

    Nếu ba cái cho kết luận khác nhau thì đó chính là thông tin: nghĩa là kết
    luận phụ thuộc vào giả định chứ không phải vào dữ liệu.
    """
    r = _finite(trade_returns)
    n = r.size
    if n < 8:
        return {"error": f"Cần ít nhất 8 lệnh để kiểm định, hiện có {n}."}

    out: dict = {"n_trades": int(n), "mean_return_pct": float(r.mean() * 100)}

    # --- t một phía
    t_stat, p_two = sps.ttest_1samp(r, 0.0)
    p_one = float(p_two / 2 if t_stat > 0 else 1 - p_two / 2)
    sd = float(r.std(ddof=1))
    se = sd / np.sqrt(n) if sd > 0 else 0.0
    ci = sps.t.interval(0.95, n - 1, loc=r.mean(), scale=se) if se > 0 else (np.nan, np.nan)
    cohen_d = float(r.mean() / sd) if sd > 0 else 0.0

    out["t_test"] = _result(
        bi("Kiểm định t một mẫu, một phía", "One-sample t-test, one-sided"),
        null=bi("Lợi suất kỳ vọng mỗi lệnh bằng 0.",
                "The expected return per trade is zero."),
        alternative=bi("Lợi suất kỳ vọng mỗi lệnh lớn hơn 0.",
                       "The expected return per trade is greater than zero."),
        statistic=float(t_stat),
        statistic_label="t",
        df=n - 1,
        p_value=p_one,
        conclusion=bi(
            ("Bác bỏ H₀: lợi thế trung bình khác 0 theo hướng có lợi."
             if p_one < ALPHA else
             "Không đủ bằng chứng cho rằng lợi thế khác 0. Kết quả quan sát được "
             "nằm trong vùng mà may rủi thuần tuý cũng tạo ra được."),
            ("The null is rejected: the average edge differs from zero in the "
             "favourable direction."
             if p_one < ALPHA else
             "Not enough evidence that the edge differs from zero. The observed "
             "result sits inside the range that pure chance also produces."),
        ),
        assumptions=bi(
            "Lợi suất từng lệnh độc lập cùng phân phối và xấp xỉ chuẩn. Cả hai "
            "giả định đều đáng ngờ: các lệnh liên tiếp trong cùng một chế độ "
            "thị trường thì tương quan, và phân phối lãi/lỗ luôn lệch. Hãy đọc "
            "kiểm định hoán vị bên dưới trước.",
            "Trade returns are independent, identically distributed and roughly "
            "normal. Both assumptions are doubtful: consecutive trades in the "
            "same market regime are correlated, and the distribution of wins and "
            "losses is always skewed. Read the permutation test below first.",
        ),
        extra={
            "ci95_low_pct": float(ci[0] * 100) if np.isfinite(ci[0]) else None,
            "ci95_high_pct": float(ci[1] * 100) if np.isfinite(ci[1]) else None,
            "cohens_d": cohen_d,
        },
    )

    # --- Wilcoxon dấu-hạng
    try:
        non_zero = r[r != 0]
        if non_zero.size >= 6:
            w_stat, w_p = sps.wilcoxon(non_zero, alternative="greater")
            out["wilcoxon"] = _result(
                bi("Wilcoxon dấu-hạng, một phía",
                   "Wilcoxon signed-rank, one-sided"),
                null=bi("Phân phối lợi suất từng lệnh đối xứng quanh 0.",
                        "The distribution of trade returns is symmetric about zero."),
                alternative=bi("Phân phối dịch về phía dương.",
                               "The distribution is shifted to the positive side."),
                statistic=float(w_stat),
                statistic_label="W",
                p_value=float(w_p),
                conclusion=bi(
                    ("Bác bỏ H₀ mà không cần giả định chuẩn."
                     if w_p < ALPHA else
                     "Không đủ bằng chứng, ngay cả khi bỏ giả định chuẩn."),
                    ("The null is rejected without assuming normality."
                     if w_p < ALPHA else
                     "Not enough evidence, even with the normality assumption "
                     "dropped."),
                ),
                assumptions=bi(
                    "Cần đối xứng và độc lập, không cần chuẩn. Các lệnh hoà vốn "
                    f"đúng bằng 0 bị loại ({int(r.size - non_zero.size)} lệnh). "
                    "Kiểm định chạy trên hạng nên một lệnh lãi rất lớn không "
                    "được tính thêm trọng số: tuỳ chiến lược mà điều đó là ưu "
                    "hay nhược.",
                    "Requires symmetry and independence, but not normality. "
                    f"Exactly break-even trades are dropped "
                    f"({int(r.size - non_zero.size)} of them). The test works on "
                    "ranks, so one very large winner carries no extra weight: "
                    "which is an advantage or a drawback depending on the strategy.",
                ),
            )
    except Exception as exc:
        log.warning("Wilcoxon failed: %s", exc)

    # --- Hoán vị dấu: không giả định gì
    signs = _RNG.choice([-1.0, 1.0], size=(N_RESAMPLE, n))
    null_means = (signs * np.abs(r)).mean(axis=1)
    observed_mean = float(r.mean())
    perm_p = float((np.sum(null_means >= observed_mean) + 1) / (N_RESAMPLE + 1))
    out["sign_permutation"] = _result(
        bi("Hoán vị dấu (phi tham số)", "Sign permutation (non-parametric)"),
        null=bi(
            "Dấu lãi/lỗ của mỗi lệnh có thể đảo ngẫu nhiên mà không đổi phân phối.",
            "The sign of each trade's result can be flipped at random without "
            "changing the distribution.",
        ),
        alternative=bi(
            "Lợi suất trung bình lớn hơn mức mà việc đảo dấu ngẫu nhiên tạo ra.",
            "Mean return exceeds what random sign flipping produces.",
        ),
        statistic=observed_mean * 100,
        statistic_label=bi("lợi suất TB (%)", "mean return (%)"),
        p_value=perm_p,
        conclusion=bi(
            ("Bác bỏ H₀. Đây là kết luận đáng tin nhất trong ba kiểm định vì nó "
             "không giả định dạng phân phối nào."
             if perm_p < ALPHA else
             "Không đủ bằng chứng. Vì kiểm định này gần như không có giả định, "
             "kết quả ở đây nên được ưu tiên hơn kiểm định t."),
            ("The null is rejected. This is the most trustworthy of the three, "
             "because it assumes no distributional shape at all."
             if perm_p < ALPHA else
             "Not enough evidence. Since this test assumes almost nothing, its "
             "answer should be preferred over the t-test's."),
        ),
        assumptions=bi(
            f"{N_RESAMPLE} lần đảo dấu ngẫu nhiên, giữ nguyên độ lớn mỗi lệnh. "
            "Chỉ cần giả định các dấu hoán đổi được dưới H₀: tức là độc lập. "
            "Nếu chiến lược có chuỗi thắng/thua kéo dài do tương quan chuỗi, "
            "giả định này bị vi phạm và p-value vẫn lạc quan quá mức.",
            f"{N_RESAMPLE} random sign flips, keeping each trade's magnitude. "
            "The only assumption is that the signs are exchangeable under the "
            "null, that is, independent. If the strategy produces long winning "
            "or losing runs through serial correlation, that assumption breaks "
            "and the p-value is still too optimistic.",
        ),
        extra={"n_permutations": N_RESAMPLE},
    )

    # --- BCa cho lợi suất trung bình
    bca = _bootstrap_ci(r, lambda x: float(np.mean(x)))
    if "error" not in bca:
        out["bootstrap_mean"] = {
            "name": bi("Bootstrap BCa cho lợi suất trung bình",
                       "BCa bootstrap for the mean return"),
            "mean_pct": bca["observed"] * 100,
            "ci95_low_pct": bca["ci_low"] * 100,
            "ci95_high_pct": bca["ci_high"] * 100,
            "excludes_zero": bool(bca["ci_low"] > 0),
            "n_resamples": bca["n_resamples"],
            "note": bi(
                "Khoảng tin cậy hiệu chỉnh chệch và gia tốc, không giả định "
                "phân phối. Nếu khoảng này chứa 0 thì dữ liệu không loại trừ "
                "được khả năng chiến lược không có lợi thế nào.",
                "A bias-corrected and accelerated interval, assuming no "
                "distribution. If it contains zero, the data cannot rule out "
                "the strategy having no edge at all.",
            ),
        }

    # --- Lực kiểm định
    out["power"] = _power_analysis(r, cohen_d)
    return out


def _power_analysis(returns: np.ndarray, effect_size: float) -> dict:
    """Với cỡ mẫu này, kiểm định có đủ lực để phát hiện lợi thế không?

    Đây là câu hỏi bị bỏ qua nhiều nhất. Một p-value 0.30 trên 25 lệnh không
    nói "chiến lược vô dụng"; nó nói "25 lệnh không đủ để biết". Hai câu đó dẫn
    tới hai quyết định hoàn toàn khác nhau.
    """
    n = returns.size
    if n < 5 or not np.isfinite(effect_size) or effect_size == 0:
        return {"error": "Không tính được lực kiểm định."}

    try:
        from statsmodels.stats.power import TTestPower

        analysis = TTestPower()
        power = float(analysis.power(
            effect_size=abs(effect_size), nobs=n, alpha=ALPHA, alternative="larger"
        ))
        required = analysis.solve_power(
            effect_size=abs(effect_size), power=0.80, alpha=ALPHA, alternative="larger"
        )
        required_n = int(np.ceil(float(required))) if np.isfinite(required) else None
    except Exception as exc:
        log.warning("power analysis failed: %s", exc)
        return {"error": str(exc)}

    if power >= 0.80:
        reading = bi(
            "Đủ lực. Nếu lợi thế thật đúng bằng mức quan sát được thì kiểm định "
            "này phát hiện ra nó trong ít nhất 80% trường hợp, nên một kết quả "
            "không có ý nghĩa là bằng chứng thật sự.",
            "Adequately powered. If the true edge equals the observed one, this "
            "test finds it at least 80% of the time, so a non-significant "
            "result here is real evidence.",
        )
    else:
        tail_vi = f" Cần khoảng {required_n} lệnh để đạt lực 80%." if required_n else ""
        tail_en = (f" About {required_n} trades would be needed for 80% power."
                   if required_n else "")
        reading = bi(
            f"Thiếu lực ({power * 100:.0f}%). Với cỡ mẫu này, một kết quả không "
            "có ý nghĩa KHÔNG chứng minh được chiến lược vô dụng; nó chỉ nói "
            "rằng dữ liệu chưa đủ để kết luận." + tail_vi,
            f"Underpowered ({power * 100:.0f}%). At this sample size a "
            "non-significant result does NOT show the strategy is worthless; it "
            "says the data is not yet enough to tell." + tail_en,
        )

    return {
        "name": bi("Phân tích lực kiểm định", "Statistical power analysis"),
        "effect_size_cohens_d": float(effect_size),
        "n": int(n),
        "power": power,
        "adequate": bool(power >= 0.80),
        "n_required_for_80pct": required_n,
        "reading": reading,
        "assumptions": bi(
            "Lực tính hậu nghiệm với cỡ ảnh hưởng bằng đúng giá trị quan sát "
            "được. Đây không phải lực thật (vốn cần cỡ ảnh hưởng thật, không "
            "biết được); hãy đọc nó như câu hỏi 'cần bao nhiêu lệnh', chứ không "
            "phải như bằng chứng bổ sung cho hay chống lại H₀.",
            "Post-hoc power, using the observed effect size. This is not the true "
            "power, which needs the true effect size and is unknowable; read it "
            "as the question 'how many trades would it take', not as extra "
            "evidence for or against the null.",
        ),
    }


# --------------------------------------------- Sharpe có kiểm soát đa thử nghiệm

def sharpe_tests(
    bar_returns: np.ndarray,
    periods_per_year: float,
    n_trials: int = 1,
    trial_dispersion: float | None = None,
) -> dict:
    """PSR, độ dài lịch sử tối thiểu, và Sharpe khử phồng.

    Đây là phần quan trọng nhất của file này đối với một nền tảng có tính năng
    tối ưu tham số. Quét 5 000 tổ hợp rồi báo cáo tổ hợp tốt nhất là chọn ra
    cực đại của 5 000 biến ngẫu nhiên; Sharpe cao nhất trong đó cao hơn hẳn
    Sharpe thật, kể cả khi không tổ hợp nào có lợi thế.

    * **PSR** (Bailey & López de Prado 2012): xác suất Sharpe thật > 0, có
      tính tới độ lệch và độ nhọn của lợi suất.
    * **DSR**: PSR nhưng so với ngưỡng kỳ vọng của giá trị lớn nhất trong
      ``n_trials`` phép thử, thay vì so với 0.
    * **MinTRL**: cần bao nhiêu quan sát để Sharpe quan sát được đạt mức tin
      cậy 95% là thật sự dương.
    """
    r = _finite(bar_returns)
    n = r.size
    if n < 30:
        return {"error": f"Cần ít nhất 30 quan sát, hiện có {n}."}

    std = float(r.std(ddof=1))
    if std <= 0:
        return {"error": "Phương sai bằng 0."}

    sr = float(r.mean() / std)                        # Sharpe mỗi nến
    sr_annual = sr * float(np.sqrt(periods_per_year))
    skew = float(sps.skew(r, bias=False))
    kurt = float(sps.kurtosis(r, bias=False)) + 3.0   # độ nhọn thường

    # Sai số chuẩn của Sharpe theo Mertens: có mô-men bậc ba và bậc bốn, nên
    # không giả định chuẩn.
    sr_se_factor = float(np.sqrt(
        max(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr, 1e-12)
    ))

    def _psr(benchmark: float) -> float:
        return float(sps.norm.cdf((sr - benchmark) * np.sqrt(n - 1) / sr_se_factor))

    psr = _psr(0.0)

    # Ngưỡng khử phồng: kỳ vọng của cực đại n_trials biến chuẩn, nhân với độ
    # phân tán của Sharpe **giữa các phép thử**.
    #
    # Độ phân tán đó là đại lượng quan trọng nhất của công thức và cũng là đại
    # lượng một backtest đơn lẻ không nhìn thấy được: nó cần các phép thử khác.
    # Khi người gọi đo được (optimizer giữ Sharpe của **mọi** ô lưới, nên độ
    # lệch chuẩn của cột đó chính là đại lượng Bailey & López de Prado định
    # nghĩa), truyền vào qua `trial_dispersion`. Khi không có, rơi về sai số
    # chuẩn của chính Sharpe này — một xấp xỉ, và cần nói rõ là xấp xỉ.
    trials = max(int(n_trials), 1)
    dispersion_measured = trial_dispersion is not None and trial_dispersion > 0
    if trials > 1:
        euler = 0.5772156649015329
        expected_max = float(
            (1 - euler) * sps.norm.ppf(1 - 1.0 / trials)
            + euler * sps.norm.ppf(1 - 1.0 / (trials * np.e))
        )
        if dispersion_measured:
            # Người gọi đưa Sharpe theo năm; công thức chạy trên Sharpe mỗi nến.
            sr_dispersion = float(trial_dispersion) / float(np.sqrt(periods_per_year))
        else:
            sr_dispersion = sr_se_factor / float(np.sqrt(max(n - 1, 1)))
        threshold = expected_max * sr_dispersion
        dsr = _psr(threshold)
    else:
        expected_max = 0.0
        threshold = 0.0
        sr_dispersion = 0.0
        dsr = psr

    # MinTRL: cần bao nhiêu quan sát để PSR đạt 95% so với ngưỡng 0.
    z95 = float(sps.norm.ppf(0.95))
    if sr > 0:
        min_trl = 1.0 + (sr_se_factor**2) * (z95 / sr) ** 2
        min_trl_value = int(np.ceil(min_trl))
    else:
        min_trl_value = None

    conclusion_vi = (
        f"PSR = {psr * 100:.1f}%: xác suất Sharpe thật lớn hơn 0, sau khi tính "
        "tới đuôi dày và độ lệch của lợi suất."
    )
    conclusion_en = (
        f"PSR = {psr * 100:.1f}%: the probability that the true Sharpe exceeds "
        "zero, once the fat tails and skew of the returns are accounted for."
    )
    if trials > 1:
        conclusion_vi += (
            f" Sau khi khử phồng cho {trials} lần thử tham số, DSR = "
            f"{dsr * 100:.1f}%"
            + ("; kết quả vẫn đứng vững." if dsr > 0.95 else
               ": không còn vượt ngưỡng 95%. Nói cách khác, một chiến lược "
               "không có lợi thế nào cũng thường tạo ra Sharpe cao thế này khi "
               "được quét từng ấy tổ hợp.")
        )
        conclusion_en += (
            f" After deflating for {trials} parameter trials, DSR = "
            f"{dsr * 100:.1f}%"
            + ("; the result still stands." if dsr > 0.95 else
               ": no longer above the 95% threshold. Put another way, a "
               "strategy with no edge at all routinely produces a Sharpe this "
               "high when that many combinations are swept.")
        )
    conclusion = bi(conclusion_vi, conclusion_en)

    return {
        "name": bi("Sharpe có kiểm soát đa thử nghiệm",
                   "Sharpe with multiple-testing control"),
        "sharpe_per_bar": sr,
        "sharpe_annualised": sr_annual,
        "skew": skew,
        "kurtosis": kurt,
        "n_observations": int(n),
        "n_trials": trials,
        "psr": psr,
        "psr_significant": bool(psr > 0.95),
        "expected_max_sharpe_z": expected_max,
        "deflation_threshold_sharpe": threshold,
        "deflated_sharpe_ratio": dsr,
        "trial_dispersion": sr_dispersion,
        "trial_dispersion_measured": dispersion_measured,
        "trial_dispersion_note": bi(
            "Độ phân tán Sharpe giữa các phép thử được **đo trực tiếp** trên "
            "toàn bộ lưới tối ưu, đúng đại lượng công thức DSR yêu cầu."
            if dispersion_measured else
            "Không đo được độ phân tán Sharpe giữa các phép thử từ một backtest "
            "đơn lẻ, nên dùng sai số chuẩn của chính Sharpe này thay thế. Đây là "
            "một **xấp xỉ**; chạy qua tab Tối ưu sẽ cho con số đo thật.",
            "The cross-trial Sharpe dispersion is **measured directly** over "
            "the whole optimisation grid, which is the quantity the DSR "
            "formula asks for."
            if dispersion_measured else
            "The cross-trial Sharpe dispersion cannot be measured from a single "
            "backtest, so the standard error of this one Sharpe stands in for "
            "it. That is an **approximation**; running through the Optimise tab "
            "measures it properly.",
        ),
        "dsr_significant": bool(dsr > 0.95),
        "min_track_record_length": min_trl_value,
        "sufficient_history": bool(min_trl_value is not None and n >= min_trl_value),
        "conclusion": conclusion,
        "assumptions": bi(
            "PSR giả định lợi suất độc lập cùng phân phối nhưng KHÔNG giả định "
            "chuẩn: độ lệch và độ nhọn được đưa thẳng vào sai số chuẩn "
            "(Mertens). Ngưỡng khử phồng dùng kỳ vọng cực đại của "
            f"{trials} phép thử ĐỘC LẬP; các tổ hợp tham số cạnh nhau thì tương "
            "quan cao nên số phép thử hiệu dụng nhỏ hơn, và DSR ở đây là bảo "
            "thủ. Biến động gom cụm vi phạm giả định độc lập và làm PSR lạc quan.",
            "PSR assumes independent, identically distributed returns but NOT "
            "normality: skew and kurtosis enter the standard error directly "
            "(Mertens). The deflation threshold uses the expected maximum of "
            f"{trials} INDEPENDENT trials; neighbouring parameter combinations "
            "are highly correlated, so the effective number of trials is smaller "
            "and the DSR here is conservative. Volatility clustering violates "
            "the independence assumption and makes PSR optimistic.",
        ),
    }


# ------------------------------------------------------------------ tổng hợp

def analyse_series(df: pd.DataFrame) -> dict:
    """Chạy toàn bộ kiểm định trên một chuỗi giá."""
    close = df["close"].to_numpy(dtype="float64")
    close = close[np.isfinite(close) & (close > 0)]
    if close.size < MIN_SAMPLES + 1:
        return {"error": f"Cần ít nhất {MIN_SAMPLES + 1} nến hợp lệ."}

    # Lợi suất log: cộng dồn được theo thời gian và đối xứng giữa lãi với lỗ.
    # Mọi kiểm định bên dưới đều chạy trên chuỗi này.
    returns = np.diff(np.log(close))

    stationarity_block = stationarity(close, returns)
    autocorrelation_block = autocorrelation(returns)
    normality_block = normality(returns)
    hurst_block = hurst(returns)
    vr_block = variance_ratio(returns)

    tests: dict = {}
    for block, keys in (
        (stationarity_block, ("adf_price", "adf_return", "kpss_return")),
        (autocorrelation_block, ("ljung_box", "arch_lm")),
        (normality_block, ("jarque_bera", "dagostino")),
    ):
        for key in keys:
            candidate = block.get(key)
            if isinstance(candidate, dict) and candidate.get("p_value") is not None:
                tests[key] = candidate
    if hurst_block.get("p_value") is not None:
        tests["hurst"] = hurst_block
    if vr_block.get("p_value") is not None:
        tests["variance_ratio"] = vr_block

    family = _apply_fdr(tests)

    return {
        "bars": int(close.size),
        "return_type": "log",
        "moments": moments(returns),
        "tail": tail_risk(returns),
        "normality": normality_block,
        "stationarity": stationarity_block,
        "autocorrelation": autocorrelation_block,
        "hurst": hurst_block,
        "variance_ratio": vr_block,
        "multiple_testing": family,
        "verdict": _series_verdict(tests, stationarity_block),
    }


def _series_verdict(tests: dict, stationarity_block: dict) -> dict:
    """Một câu kết luận, chỉ dựa trên p đã hiệu chỉnh."""
    def rejected(key: str) -> bool | None:
        test = tests.get(key)
        if not isinstance(test, dict) or test.get("p_adjusted") is None:
            return None
        return bool(test["reject_adjusted"])

    found = [
        (vi, en) for vi, en, key in (
            ("tự tương quan (Ljung–Box)", "autocorrelation (Ljung–Box)", "ljung_box"),
            ("tỷ số phương sai (Chow–Denning)",
             "the variance ratio (Chow–Denning)", "variance_ratio"),
            ("bộ nhớ dài (Hurst)", "long memory (Hurst)", "hurst"),
        )
        if rejected(key)
    ]

    if found:
        code = "structured"
        headline = bi("Có cấu trúc phụ thuộc thời gian",
                      "Time dependence is present")
        detail = bi(
            "Bác bỏ tính ngẫu nhiên qua: " + ", ".join(vi for vi, _ in found) +
            " (p đã hiệu chỉnh đa kiểm định). Có cấu trúc để chỉ báo khai thác. "
            "Lưu ý: cấu trúc tồn tại không có nghĩa nó đủ lớn để thắng phí giao "
            "dịch; đó là câu hỏi của backtest, không phải của kiểm định này.",
            "Randomness is rejected by: " + ", ".join(en for _, en in found) +
            " (on multiple-testing adjusted p-values). There is structure for an "
            "indicator to exploit. Note that structure existing does not mean it "
            "is large enough to beat trading costs; that is a question for the "
            "backtest, not for these tests.",
        )
    else:
        code = "random"
        headline = bi("Không phân biệt được với bước ngẫu nhiên",
                      "Indistinguishable from a random walk")
        detail = bi(
            "Sau hiệu chỉnh đa kiểm định, không kiểm định nào bác bỏ được tính "
            "ngẫu nhiên về hướng. Một chiến lược có lãi trên chuỗi này rất có "
            "thể chỉ đang khớp nhiễu: hãy kiểm chứng bằng walk-forward trước "
            "khi tin vào nó.",
            "After the multiple-testing correction, no test rejects directional "
            "randomness. A strategy that profits on this series is quite likely "
            "fitting noise: verify it with walk-forward before believing it.",
        )

    notes = []
    if rejected("arch_lm"):
        notes.append(bi(
            "Biến động gom cụm được xác nhận: rủi ro thay đổi theo thời gian. "
            "Điều này KHÔNG dự đoán được hướng, nhưng nó nói rằng dừng lỗ và cỡ "
            "vị thế nên co giãn theo biến động thay vì cố định.",
            "Volatility clustering is confirmed: risk varies over time. This does "
            "NOT predict direction, but it does say that stops and position sizes "
            "should scale with volatility rather than stay fixed.",
        ))
    if rejected("jarque_bera") or rejected("dagostino"):
        notes.append(bi(
            "Lợi suất không tuân theo phân phối chuẩn. Sharpe, VaR tham số và "
            "mọi khoảng tin cậy dựa trên giả định chuẩn đều đánh giá thấp rủi "
            "ro đuôi trên chuỗi này.",
            "Returns are not normally distributed. Sharpe, parametric VaR and "
            "every confidence interval built on a normal assumption understate "
            "tail risk on this series.",
        ))
    if stationarity_block.get("verdict"):
        notes.append(stationarity_block["verdict"])

    return {"code": code, "headline": headline, "detail": detail, "notes": notes}


def analyse_strategy(
    trades: list[dict],
    initial_capital: float,
    *,
    bar_returns: np.ndarray | None = None,
    periods_per_year: float = 365.0,
    n_trials: int = 1,
) -> dict:
    """Kiểm định suy diễn trên kết quả một chiến lược.

    ``n_trials`` là số tổ hợp tham số đã thử để chọn ra chiến lược này. Truyền
    số thật vào, nếu tham số đến từ một lần quét 2 000 tổ hợp thì đó là 2 000,
    không phải 1, nếu không thì Sharpe khử phồng sẽ vô nghĩa.
    """
    if not trades:
        return {"error": "Chiến lược chưa tạo lệnh nào."}

    pnls = np.array([t["pnl"] for t in trades], dtype="float64")
    trade_returns = pnls / max(initial_capital, 1e-9)

    result: dict = {"inference": inference(trade_returns)}

    tests = {
        key: value
        for key, value in result["inference"].items()
        if isinstance(value, dict) and value.get("p_value") is not None
    }
    result["multiple_testing"] = _apply_fdr(tests)

    if bar_returns is not None and len(bar_returns) >= 30:
        result["sharpe"] = sharpe_tests(
            np.asarray(bar_returns, dtype="float64"), periods_per_year, n_trials
        )

    if pnls.size >= MIN_SAMPLES:
        result["trade_distribution"] = {
            "moments": moments(trade_returns),
            "tail": tail_risk(trade_returns),
        }
    else:
        result["trade_distribution"] = {
            "note": (
                f"Cần {MIN_SAMPLES} lệnh để phân tích phân phối, hiện có "
                f"{pnls.size}. Với ít lệnh hơn, các ước lượng đuôi chỉ phản ánh "
                "vài quan sát riêng lẻ."
            )
        }

    result["verdict"] = _strategy_verdict(result)
    return result


def _strategy_verdict(result: dict) -> dict:
    inference_block = result.get("inference", {})
    permutation = inference_block.get("sign_permutation", {})
    power = inference_block.get("power", {})
    sharpe = result.get("sharpe", {})

    p_adj = permutation.get("p_adjusted", permutation.get("p_value"))
    significant = p_adj is not None and p_adj < ALPHA
    adequate_power = bool(power.get("adequate"))
    dsr_ok = bool(sharpe.get("dsr_significant")) if sharpe else None

    if significant and dsr_ok is not False:
        code = "robust"
        headline = bi("Lợi thế đứng vững qua kiểm định",
                      "The edge survives testing")
    elif significant and dsr_ok is False:
        code = "deflated_away"
        headline = bi("Có ý nghĩa thống kê, nhưng không sống sót khi khử phồng",
                      "Statistically significant, but not after deflation")
    elif not adequate_power:
        code = "underpowered"
        headline = bi("Chưa đủ dữ liệu để kết luận",
                      "Not enough data to conclude")
    else:
        code = "no_edge"
        headline = bi("Không có bằng chứng về lợi thế",
                      "No evidence of an edge")

    notes = []
    if permutation.get("conclusion"):
        notes.append(permutation["conclusion"])
    if power.get("reading"):
        notes.append(power["reading"])
    if sharpe.get("conclusion"):
        notes.append(sharpe["conclusion"])
    notes.append(bi(
        "Mọi kiểm định ở đây đo lợi suất TỪNG LỆNH và giả định các lệnh độc "
        "lập. Nếu chiến lược vào ra nhiều lần trong cùng một đợt xu hướng thì "
        "giả định đó bị vi phạm và p-value lạc quan hơn thực tế. Walk-forward "
        "là kiểm chứng bổ sung không dựa vào giả định này.",
        "Every test here measures PER-TRADE returns and assumes the trades are "
        "independent. If the strategy enters and exits repeatedly within one "
        "trend, that assumption breaks and the p-values are more optimistic than "
        "the truth. Walk-forward is the additional check that does not rest on "
        "this assumption.",
    ))
    return {
        "code": code,
        "headline": headline,
        "detail": notes[0] if notes else "",
        "notes": notes[1:],
    }
